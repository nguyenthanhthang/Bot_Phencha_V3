from __future__ import annotations
from datetime import datetime, date, timedelta
from typing import Optional
import time
import threading
import logging

from dotenv import load_dotenv
import pandas as pd

from utils.config_loader import load_yaml, get_nested
from utils.logger import setup_logger
from utils.time_utils import to_vn_time
from execution.mt5_executor import MT5Executor, OrderType, fetch_account_snapshot, fetch_open_positions, fetch_profit_buckets
from risk.live_risk_manager import LiveRiskManager
from volume_profile.cache import SessionProfileCache
from strategies.vp_v1 import VPStrategyV1
from execution.trade_manager import TradeManager
from execution.backtest_executor import Trade
from data.mt5_fetcher import MT5Fetcher
from data.resample import resample_ohlc
from indicators import atr

# Telegram integration
from notification.bot_state import BotState
from notification.telegram_client import TelegramClient, load_telegram_config
from notification.telegram_notifier import TelegramNotifier
from notification.telegram_bot import run_telegram_command_bot


def get_account_balance(mt5_executor: MT5Executor) -> float:
    """Get current account balance from MT5"""
    import MetaTrader5 as mt5
    account_info = mt5.account_info()
    if account_info is None:
        return 0.0
    return float(account_info.balance)


def main() -> None:
    load_dotenv()  # reads .env if exists

    cfg = load_yaml("config/settings.yaml")
    cfg_backtest = load_yaml("config/backtest.yaml")
    symbols = load_yaml("config/symbols.yaml")
    tg_cfg = load_yaml("config/telegram.yaml")
    cfg_vp = load_yaml("config/vp.yaml")

    logger = setup_logger(
        name=get_nested(cfg, "app.name", "BOT_XAUUSD"),
        level="INFO",
    )
    
    # Also setup logger for strategies module to ensure logging works
    # Fix: Reuse main logger handlers to avoid opening the same file twice
    # This prevents WinError 32 when RotatingFileHandler tries to rollover
    strategies_logger = logging.getLogger("strategies.vp_v1")
    strategies_logger.setLevel(logging.INFO)
    strategies_logger.propagate = False
    
    # Remove any existing handlers (like NullHandler)
    strategies_logger.handlers.clear()
    
    # Reuse main logger handlers (console + file) to avoid duplicate file handles
    # This prevents "file is being used by another process" error on Windows
    for h in logger.handlers:
        strategies_logger.addHandler(h)

    app_name = get_nested(cfg, "app.name", "BOT_XAUUSD")
    tz = get_nested(cfg, "app.timezone", "Asia/Ho_Chi_Minh")
    symbol = get_nested(cfg, "symbol.name", "XAUUSD")
    tf = get_nested(cfg, "symbol.timeframe", "M15")

    # Risk management config
    risk_cfg = cfg["risk"]
    risk_trade = float(risk_cfg.get("risk_per_trade_pct", 0.5))
    max_consec_loss = int(risk_cfg.get("max_consecutive_loss", 3))

    asia_start = get_nested(cfg, "sessions.asia.start", "06:00")
    asia_end = get_nested(cfg, "sessions.asia.end", "13:50")
    lon_start = get_nested(cfg, "sessions.london.start", "14:00")
    lon_end = get_nested(cfg, "sessions.london.end", "17:30")
    us_start = get_nested(cfg, "sessions.us.start", "18:00")
    us_end = get_nested(cfg, "sessions.us.end", "23:00")

    sym_specs = symbols.get(symbol, {})
    min_lot = sym_specs.get("min_lot", None)
    lot_step = sym_specs.get("lot_step", None)

    logger.info("Boot LIVE runner OK")
    logger.info(f"App: {app_name} | TZ: {tz}")
    logger.info(f"Symbol: {symbol} | TF: {tf}")
    logger.info(f"Sessions: Asia {asia_start}-{asia_end} | London {lon_start}-{lon_end} | US {us_start}-{us_end}")
    logger.info(
        f"Risk: {risk_trade}%/trade | MaxConsecLoss: {max_consec_loss}"
    )
    logger.info(f"Symbol specs: min_lot={min_lot}, lot_step={lot_step}")

    tg_enabled = bool(tg_cfg.get("enabled", False))
    logger.info(f"Telegram enabled: {tg_enabled}")

    # Initialize MT5 executor
    mt5_executor = MT5Executor()
    if not mt5_executor.connect():
        logger.error("Failed to connect to MT5")
        return

    # Initialize MT5 fetcher for M1 data (for Volume Profile)
    mt5_fetcher = MT5Fetcher()
    mt5_fetcher.connect()

    # Merge configs (same as backtest)
    cfg_all = {}
    cfg_all.update(cfg)
    cfg_all["vp"] = cfg_vp["vp"]
    cfg_all["rules"] = cfg_vp["rules"]
    cfg_all["sessions"] = cfg_vp["sessions"]
    cfg_all["risk"] = cfg["risk"]
    cfg_all["london_mode"] = cfg_vp.get("london_mode", {})
    cfg_all["us_mode"] = cfg_vp.get("us_mode", {})

    # Initialize Volume Profile cache and strategy
    logger.info("Loading M1 data for Volume Profile...")
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        tf_m1 = mt5_fetcher.tf_name_to_mt5("M1")
        df_m1 = mt5_fetcher.fetch_rates_range(symbol, tf_m1, start_date, end_date)
        logger.info(f"Loaded M1 data: {len(df_m1)} rows from {start_date.date()} to {end_date.date()}")
    except Exception as e:
        logger.error(f"Failed to fetch M1 data: {e}. Using empty DataFrame.")
        df_m1 = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        df_m1["time"] = pd.to_datetime(df_m1["time"], utc=True)
    
    vp_cache = SessionProfileCache(df_m1, cfg_all)
    strat = VPStrategyV1(cfg_all, sym_specs, vp_cache)

    # Fill model config (spread/slippage) - same as backtest
    fill_cfg = cfg_backtest.get("fill_model", {})
    spread_points = float(fill_cfg.get("fixed_spread_points", 30.0))
    slippage_mode = fill_cfg.get("slippage_mode", "OFF")
    slippage_points = float(fill_cfg.get("slippage_points", 0.0)) if slippage_mode != "OFF" else 0.0
    point_value = 0.01  # XAUUSD: 0.01 per point (2 decimals)

    # TradeManager for scale-out TP (same as backtest)
    tm_cfg = cfg_vp.get("trade_management", {})
    tm = TradeManager(
        contract_size=float(sym_specs.get("contract_size", 100.0)),
        spread_points=spread_points,
        slippage_points=slippage_points,
        point_value=point_value,
    )

    # Initialize Risk Manager (handles MaxConsecLoss only)
    risk_mgr = LiveRiskManager(
        max_daily_loss_pct=0.0,  # Disabled
        max_trades_per_day=999999,  # Disabled (set very high)
        max_consecutive_loss=max_consec_loss,
    )

    # Initialize Telegram
    tg_cfg_telegram = load_telegram_config()
    tg_client = TelegramClient(tg_cfg_telegram)  # Keep for backward compatibility
    notifier = TelegramNotifier()  # New notifier with templates
    bot_state = BotState()
    bot_state.set(symbol=symbol, timeframe=tf)
    
    # Initialize ProfitTracker with initial balance
    initial_balance = get_account_balance(mt5_executor)
    if initial_balance <= 0:
        initial_balance = 1000.0  # Fallback
    bot_state.balance = initial_balance
    bot_state.profit.initial_balance = initial_balance
    logger.info(f"Initial balance: ${initial_balance:.2f}")
    
    # Close all callback for Telegram
    def close_all_callback():
        """Callback for /closeall command"""
        try:
            positions = mt5_executor.get_positions(symbol=symbol)
            if not positions:
                return True, "No positions to close"
            
            closed_count = 0
            for pos in positions:
                ticket = pos['ticket']
                if mt5_executor.close_position(ticket):
                    closed_count += 1
            
            # Clear tracked positions
            open_positions.clear()
            return True, f"Closed {closed_count} position(s)"
        except Exception as e:
            return False, str(e)
    
    # Start Telegram command bot in background thread
    def start_telegram_thread():
        """Start Telegram command bot in separate thread"""
        try:
            th = threading.Thread(
                target=run_telegram_command_bot,
                kwargs={"state": bot_state, "on_close_all": close_all_callback},
                daemon=True,
                name="TelegramBot"
            )
            th.start()
            logger.info("Telegram command bot started in background thread")
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
    
    if tg_cfg_telegram.enabled:
        start_telegram_thread()
        # Send start notification with detailed info
        sessions_str = f"Asia {asia_start}-{asia_end} | London {lon_start}-{lon_end} | US {us_start}-{us_end}"
        cfg_summary = f"Lot={tm_cfg.get('entry_lot', 0.04)} | TP1 close={tm_cfg.get('tp1_close_lot', 0.02)} | MaxConsecLoss={max_consec_loss}"
        notifier.notify_start(
            app=app_name,
            symbol=symbol,
            tf=tf,
            tz=tz,
            sessions=sessions_str,
            cfg_summary=cfg_summary,
        )

    logger.info("Live runner started. Waiting for candles...")
    
    # Track open positions: {ticket: Trade object}
    open_positions = {}
    
    # Daily state tracking
    day_start_balance = None
    day_start_pnl = 0.0
    
    # Get M15 timeframe for fetching
    tf_m15 = mt5_fetcher.tf_name_to_mt5("M15")
    
    # Main trading loop - Structured with 3 independent timers:
    # 1) Tick-based position management (1s)
    # 2) MT5 snapshot pull for external positions (3s)
    # 3) M15 fetch & signal detection on closed candle (5s)
    
    last_closed_candle_time = None  # Track last CLOSED M15 candle (iloc[-2])
    
    # Fix 1: Tách 2 biến riêng để tránh conflict
    last_tick_manage = 0.0
    last_snapshot_pull = 0.0
    last_m15_pull = 0.0
    TICK_MANAGE_INTERVAL = 1.0  # Position management every 1 second (tick-based)
    SNAPSHOT_PULL_INTERVAL = 3.0  # MT5 snapshot pull every 3 seconds
    M15_PULL_INTERVAL = 5.0  # M15 fetch every 5 seconds (not every loop)
    
    last_profit_pull = 0.0
    PROFIT_PULL_INTERVAL = 60.0  # Pull MT5 profit history every 60 seconds
    last_notified_tickets = set()  # Track already notified tickets to avoid duplicates
    last_session_name = None  # Track previous session for session change detection
    
    # VP cache update
    last_vp_update = 0.0
    VP_UPDATE_INTERVAL = 600.0  # Update VP cache every 10 minutes (or on M15 close)
    last_m1_time = None  # Track last M1 time for incremental update
    
    # Health check / Heartbeat
    last_heartbeat = 0.0
    HEARTBEAT_INTERVAL = 1800.0  # Send heartbeat every 30 minutes (1800 seconds)
    last_data_check_log = 0.0
    DATA_CHECK_LOG_INTERVAL = 300.0  # Log data status every 5 minutes
    
    # Fix 1: Initialize balance before while loop
    balance = get_account_balance(mt5_executor)
    if balance <= 0:
        balance = 1000.0  # Fallback
    logger.info(f"Initial balance: ${balance:.2f}")
    
    running = True
    try:
        while running:
            current_time = datetime.now()
            now_ts = time.time()
            t_vn = to_vn_time(pd.Series([current_time]))[0]
            cur_day = t_vn.date()
            
            # 1) Tick-based position management (ONLY HERE - Fix 4: single manage point)
            if now_ts - last_tick_manage >= TICK_MANAGE_INTERVAL and len(open_positions) > 0:
                try:
                    import MetaTrader5 as mt5
                    tick = mt5.symbol_info_tick(symbol)
                    if tick:
                        tick_bid = float(tick.bid)
                        tick_ask = float(tick.ask)
                        
                        # Get current ATR from last closed candle (if available)
                        # We'll update this when we process M15 data
                        current_atr = getattr(tm, '_last_atr', 1.0)  # Use cached ATR
                        
                        # Quick check all positions with tick
                        positions = mt5_executor.get_positions(symbol=symbol)
                        still_open_quick = {}
                        
                        # Fix 2: Iterate on list snapshot to avoid "dictionary changed size during iteration"
                        for ticket, trade_obj in list(open_positions.items()):
                            pos = next((p for p in positions if p['ticket'] == ticket), None)
                            if pos is None:
                                # Position closed externally - will be handled in snapshot pull
                                continue
                            
                            # Use tick-based management
                            realized, closed_all, r = tm.update_trade_on_tick(trade_obj, tick_bid, tick_ask, current_atr, tm_cfg)
                            
                            # Fix 4: Track if position was successfully closed in MT5
                            closed_success = False
                            
                            if realized != 0.0:
                                if r == "TP1_PARTIAL":
                                    ok1 = mt5_executor.close_partial(ticket, trade_obj.lot_tp1)
                                    ok2 = ok1 and mt5_executor.modify_sl(ticket, trade_obj.sl_after_tp1)
                                    if ok2:
                                        notifier.notify_tp1({
                                            "direction": trade_obj.direction,
                                            "setup": trade_obj.setup,
                                            "tp1": trade_obj.tp1,
                                            "closed_lot": trade_obj.lot_tp1,
                                            "runner_lot": trade_obj.lot_open - trade_obj.lot_tp1,
                                            "new_sl": trade_obj.sl_after_tp1,
                                            "pnl_part": realized,
                                        })
                                        # TP1 partial doesn't remove from tracking, keep it
                                        still_open_quick[ticket] = trade_obj
                                        continue
                                
                                elif closed_all:
                                    actual_pnl = pos.get("profit", 0.0)
                                    if mt5_executor.close_position(ticket):
                                        closed_success = True
                                        risk_mgr.update_consecutive_loss(actual_pnl)
                                        day_start_pnl += actual_pnl
                                        
                                        bot_state.set(
                                            pnl_today=day_start_pnl,
                                            trades_today=bot_state.trades_today + 1,
                                            win_today=bot_state.win_today + (1 if actual_pnl > 0 else 0),
                                            loss_today=bot_state.loss_today + (1 if actual_pnl <= 0 else 0),
                                        )
                                        
                                        notifier.notify_close({
                                            "direction": trade_obj.direction,
                                            "setup": trade_obj.setup,
                                            "reason": r,
                                            "exit_price": pos.get('price_current', trade_obj.entry_price),
                                            "pnl": actual_pnl,
                                            "balance": get_account_balance(mt5_executor),
                                            "consec_loss": risk_mgr.get_status()['consec_loss'],
                                        })
                                    # Only remove from tracking if successfully closed
                                    if closed_success:
                                        continue
                            
                            # Fix 4: Only keep in tracking if not successfully closed
                            if not closed_success:
                                still_open_quick[ticket] = trade_obj
                        
                        # Update open_positions with quick check results
                        open_positions = still_open_quick
                        
                except Exception as e:
                    logger.debug(f"Tick-based position management error: {e}")
                
                last_tick_manage = now_ts
            
            # 2) MT5 snapshot pull (for external/manual positions detection)
            if now_ts - last_snapshot_pull >= SNAPSHOT_PULL_INTERVAL:
                try:
                    # Use MT5Executor instance methods to ensure proper connection
                    acc = mt5_executor.fetch_account_snapshot()
                    
                    # Fetch positions with case-insensitive symbol filter
                    pos = mt5_executor.fetch_open_positions(symbol=symbol)
                    
                    # Check for errors in positions list
                    pos_errors = [p for p in pos if "_error" in p]
                    pos_valid = [p for p in pos if "_error" not in p]
                    
                    if pos_errors:
                        for err_dict in pos_errors:
                            logger.error(f"MT5 positions error: {err_dict.get('_error')}")
                    
                    # Fix 3: Use separate variables for different purposes
                    tracked_tickets = set(open_positions.keys())
                    mt5_tickets_fetch = {p['ticket'] for p in pos_valid}  # For external NEW detection
                    new_tickets = mt5_tickets_fetch - tracked_tickets - last_notified_tickets
                    
                    # Notify about new external positions (only once per ticket)
                    if new_tickets:
                        for ticket in new_tickets:
                            p = next((p for p in pos_valid if p['ticket'] == ticket), None)
                            if p:
                                logger.info(f"🔔 NEW EXTERNAL POSITION DETECTED: #{p['ticket']} {p['symbol']} {p['direction']} {p['lots']:.2f} lot @ {p['price_open']:.2f}")
                                notifier.send(
                                    f"🔔 <b>NEW EXTERNAL POSITION</b>\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🎫 Ticket: <b>#{p['ticket']}</b>\n"
                                    f"📊 Symbol: {p['symbol']} | {p['direction']}\n"
                                    f"📦 Lot: <b>{p['lots']:.2f}</b>\n"
                                    f"💰 Entry: <b>{p['price_open']:.2f}</b>\n"
                                    f"🛡️ SL: {p['sl']:.2f} | TP: {p['tp']:.2f}\n"
                                    f"🕐 Time: {p['time_open']}\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"<i>Manual trade detected</i>"
                                )
                                last_notified_tickets.add(ticket)
                    
                    # Clean up old notified tickets (keep only current MT5 tickets from fetch)
                    last_notified_tickets = last_notified_tickets & mt5_tickets_fetch
                    
                    # Store both valid positions and errors (for /status to display)
                    bot_state.set_mt5_snapshot(acc, pos)  # Store full list including errors
                    
                    # Fix 3: Update bot state with positions snapshot (use get_positions for consistent schema)
                    # Lấy positions theo schema thống nhất
                    positions = mt5_executor.get_positions(symbol=symbol)
                    
                    positions_snapshot = []
                    for posi in positions:
                        trade_obj = open_positions.get(posi['ticket'])
                        positions_snapshot.append({
                            'ticket': posi['ticket'],
                            'symbol': posi.get('symbol', symbol),
                            'side': posi.get('type', ''),
                            'lot': posi.get('volume', 0.0),
                            'entry': posi.get('price_open', 0.0),
                            'sl': posi.get('sl', 0.0),
                            'tp': posi.get('tp', 0.0),
                            'tp1': trade_obj.tp1 if trade_obj and trade_obj.tp1 else 0.0,
                            'tp2': trade_obj.tp2 if trade_obj and trade_obj.tp2 else 0.0,
                            'pnl': posi.get('profit', 0.0),
                        })
                    bot_state.set(positions=positions_snapshot)
                    
                    # Update balance from MT5 account if available
                    if acc.get("ok"):
                        balance = acc.get("balance", balance)
                    
                    # Fix 3: Use separate variable for external CLOSE detection
                    mt5_tickets_live = {p['ticket'] for p in positions}  # For external CLOSE detection
                    
                    # Detect positions closed externally (not in MT5 but still in open_positions)
                    for ticket, trade_obj in list(open_positions.items()):
                        if ticket not in mt5_tickets_live:
                            # Position closed externally - fetch PnL from MT5 history
                            logger.warning(f"Position {ticket} closed externally - fetching PnL from MT5 history...")
                            try:
                                import MetaTrader5 as mt5
                                deals = mt5.history_deals_get(ticket=ticket)
                                if deals and len(deals) > 0:
                                    actual_pnl = 0.0
                                    for deal in deals:
                                        actual_pnl += float(getattr(deal, "profit", 0.0) or 0.0)
                                        actual_pnl += float(getattr(deal, "swap", 0.0) or 0.0)
                                        actual_pnl += float(getattr(deal, "commission", 0.0) or 0.0)
                                    
                                    risk_mgr.update_consecutive_loss(actual_pnl)
                                    status = risk_mgr.get_status()
                                    day_start_pnl += actual_pnl
                                    bot_state.set(
                                        pnl_today=day_start_pnl,
                                        trades_today=bot_state.trades_today + 1,
                                    )
                                    if actual_pnl > 0:
                                        bot_state.set(win_today=bot_state.win_today + 1)
                                    else:
                                        bot_state.set(loss_today=bot_state.loss_today + 1)
                                    
                                    exit_price = trade_obj.entry_price
                                    if deals:
                                        last_deal = deals[-1]
                                        exit_price = float(getattr(last_deal, "price", trade_obj.entry_price))
                                    
                                    bot_state.set(last_trade={
                                        'direction': trade_obj.direction,
                                        'setup': trade_obj.setup,
                                        'entry': trade_obj.entry_price,
                                        'exit': exit_price,
                                        'pnl': actual_pnl,
                                        'reason': 'MANUAL',
                                        'time': current_time.strftime("%Y-%m-%d %H:%M:%S"),
                                    })
                                    
                                    close_time = datetime.now()
                                    bot_state.profit.add_closed_trade(close_time=close_time, pnl_usd=actual_pnl)
                                    
                                    notifier.notify_close({
                                        "direction": trade_obj.direction,
                                        "setup": trade_obj.setup,
                                        "reason": "MANUAL",
                                        "exit_price": exit_price,
                                        "pnl": actual_pnl,
                                        "balance": get_account_balance(mt5_executor),
                                        "consec_loss": status['consec_loss'],
                                    })
                                    
                                    logger.info(f"  Position {ticket} closed manually | PnL: ${actual_pnl:.2f}")
                                    del open_positions[ticket]
                            except Exception as e:
                                logger.error(f"  Failed to fetch PnL for closed position {ticket}: {e}")
                                del open_positions[ticket]
                
                except Exception as e:
                    logger.error(f"Failed to fetch MT5 snapshot: {e}", exc_info=True)
                
                last_snapshot_pull = now_ts
            
            # 3) M15 fetch & signal detection on closed candle
            if now_ts - last_m15_pull >= M15_PULL_INTERVAL:
                try:
                    # Fix 4: Use datetime.now() naive for fetch (MT5 uses terminal timezone)
                    # Only convert to UTC for staleness calculation
                    end_date = current_time
                    # Tăng từ 7 lên 30 ngày để đảm bảo đủ history cho breakout detection
                    start_date = end_date - timedelta(days=30)
                    fetch_start_ts = time.time()
                    df_m15 = mt5_fetcher.fetch_rates_range(symbol, tf_m15, start_date, end_date)
                    fetch_duration = time.time() - fetch_start_ts
                    
                    # Convert to UTC for staleness calculation only
                    import pytz
                    if current_time.tzinfo is None:
                        tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
                        current_time_local = tz_vn.localize(current_time)
                        current_time_utc = current_time_local.astimezone(pytz.UTC)
                    else:
                        current_time_utc = current_time.astimezone(pytz.UTC)
                
                    if df_m15.empty:
                        logger.warning("⚠️ No M15 data available from MT5. Waiting...")
                        if now_ts - last_data_check_log >= DATA_CHECK_LOG_INTERVAL:
                            notifier.send(
                                f"⚠️ <b>DATA WARNING</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"❌ No M15 data from MT5\n"
                                f"🕐 {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"🔍 Check MT5 connection"
                            )
                            last_data_check_log = now_ts
                        last_m15_pull = now_ts
                        time.sleep(1)
                        continue
                
                    # Check if new candle
                    df_m15["time"] = pd.to_datetime(df_m15["time"], utc=True)
                    df_m15 = df_m15.sort_values("time").reset_index(drop=True)
                    latest_candle_time = df_m15.iloc[-1]["time"]
                    latest_candle_time_vn = to_vn_time(pd.Series([latest_candle_time]))[0]
                    
                    # Calculate data staleness
                    current_time_utc_ts = pd.Timestamp(current_time_utc)
                    data_age_minutes = (current_time_utc_ts - latest_candle_time).total_seconds() / 60.0
                    
                    # Log data status periodically (every 5 minutes)
                    if now_ts - last_data_check_log >= DATA_CHECK_LOG_INTERVAL:
                        logger.info(
                            f"📊 DATA STATUS: Fetched {len(df_m15)} candles | "
                            f"Latest: {latest_candle_time_vn.strftime('%Y-%m-%d %H:%M:%S')} | "
                            f"Age: {data_age_minutes:.1f} min | "
                            f"Fetch time: {fetch_duration:.2f}s"
                        )
                        last_data_check_log = now_ts
                        
                        # Warning if data is stale (>20 minutes old)
                        if data_age_minutes > 20:
                            logger.warning(f"⚠️ STALE DATA: Latest candle is {data_age_minutes:.1f} minutes old!")
                            notifier.send(
                                f"⚠️ <b>STALE DATA WARNING</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"📊 Latest candle: {latest_candle_time_vn.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"⏰ Age: <b>{data_age_minutes:.1f} minutes</b>\n"
                                f"🕐 Current: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"⚠️ MT5 may not be updating data"
                            )
                    
                    # Process timezone and indicators
                    df_m15["time_vn"] = to_vn_time(df_m15["time"])
                    df_m15["atr"] = atr(df_m15, int(cfg_vp["rules"]["atr_period"]))
                    df_m15 = df_m15.dropna().reset_index(drop=True)
                    
                    if len(df_m15) < 2:
                        last_m15_pull = now_ts
                        time.sleep(1)
                        continue
                    
                    # Cache ATR from closed candle for tick-based position management
                    last_closed_atr = float(df_m15.iloc[-2]["atr"]) if "atr" in df_m15.iloc[-2] else 1.0
                    tm._last_atr = last_closed_atr
                    
                    # B) Check for CLOSED candle (use iloc[-2] - last closed candle)
                    last_closed = df_m15.iloc[-2]  # Last closed candle
                    last_closed_time = last_closed["time"]
                
                    # Check if we have a new closed candle
                    new_closed_candle = False
                    if last_closed_candle_time is None or last_closed_time != last_closed_candle_time:
                        new_closed_candle = True
                        last_closed_candle_time = last_closed_time
                        last_closed_time_vn = to_vn_time(pd.Series([last_closed_time]))[0]
                        logger.info(
                            f"✅ NEW CLOSED CANDLE: {last_closed_time_vn.strftime('%Y-%m-%d %H:%M:%S')} | "
                            f"O:{last_closed['open']:.2f} H:{last_closed['high']:.2f} "
                            f"L:{last_closed['low']:.2f} C:{last_closed['close']:.2f}"
                        )
                        
                        # C) Update VP cache when M15 closes (Fix 1+2: timezone + datetime conversion)
                        try:
                            # Fetch new M1 data since last update
                            # Fix 2: Use naive datetime (same as M15 fetch) for consistency
                            if last_m1_time is None:
                                # First time: fetch last 30 days
                                start_m1 = current_time - timedelta(days=30)
                            else:
                                # Fix 1: Convert pd.Timestamp to datetime if needed
                                if hasattr(last_m1_time, "to_pydatetime"):
                                    start_m1 = last_m1_time.to_pydatetime()
                                elif isinstance(last_m1_time, pd.Timestamp):
                                    start_m1 = last_m1_time.to_pydatetime()
                                else:
                                    start_m1 = last_m1_time
                            
                            end_m1 = current_time  # Use naive datetime (same as M15)
                            tf_m1 = mt5_fetcher.tf_name_to_mt5("M1")
                            df_m1_new = mt5_fetcher.fetch_rates_range(symbol, tf_m1, start_m1, end_m1)
                            
                            if not df_m1_new.empty:
                                # Append to existing M1 data in cache
                                df_m1_new["time"] = pd.to_datetime(df_m1_new["time"], utc=True)
                                # Update cache's df_m1 (append new data, remove duplicates)
                                vp_cache.df_m1 = pd.concat([vp_cache.df_m1, df_m1_new]).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
                                # Fix 1: Convert to datetime immediately to avoid type mismatch
                                last_m1_time_max = df_m1_new["time"].max()
                                if hasattr(last_m1_time_max, "to_pydatetime"):
                                    last_m1_time = last_m1_time_max.to_pydatetime()
                                elif isinstance(last_m1_time_max, pd.Timestamp):
                                    last_m1_time = last_m1_time_max.to_pydatetime()
                                else:
                                    last_m1_time = last_m1_time_max
                                # Clear cache to force rebuild with new data
                                vp_cache._cache.clear()
                                logger.info(f"📊 VP cache updated: Added {len(df_m1_new)} M1 candles, Total: {len(vp_cache.df_m1)}")
                        except Exception as e:
                            logger.warning(f"Failed to update VP cache: {e}")
                    
                    # Use closed candle for signal detection
                    row_closed = last_closed
                    t_vn = row_closed["time_vn"]
                    cur_day = t_vn.date()
                    
                    # Get current balance
                    balance = get_account_balance(mt5_executor)
                    
                    # Check new day and reset risk state
                    if risk_mgr.check_new_day(cur_day):
                        logger.info(f"New day: {cur_day} | Balance: {balance:.2f}")
                        open_positions = {}
                        day_start_balance = balance
                        day_start_pnl = 0.0
                        bot_state.set(
                            pnl_today=0.0,
                            trades_today=0,
                            win_today=0,
                            loss_today=0,
                            day_blocked=False,
                        )
                    
                    # Determine session (use proper time comparison, not string)
                    hour_min = t_vn.strftime("%H:%M")
                    session_name = "OUTSIDE"
                    
                    # Convert time strings to minutes for proper comparison
                    def time_to_minutes(time_str: str) -> int:
                        h, m = map(int, time_str.split(":"))
                        return h * 60 + m
                    
                    current_minutes = time_to_minutes(hour_min)
                    asia_start_min = time_to_minutes(asia_start)
                    asia_end_min = time_to_minutes(asia_end)
                    lon_start_min = time_to_minutes(lon_start)
                    lon_end_min = time_to_minutes(lon_end)
                    us_start_min = time_to_minutes(us_start)
                    us_end_min = time_to_minutes(us_end)
                    
                    if asia_start_min <= current_minutes <= asia_end_min:
                        session_name = "ASIA"
                    elif lon_start_min <= current_minutes <= lon_end_min:
                        session_name = "LONDON"
                    elif us_start_min <= current_minutes <= us_end_min:
                        session_name = "US"
                    
                    # Check if session changed and notify on session start
                    if session_name != last_session_name and session_name != "OUTSIDE":
                        # Check if we're at the start of the session (within first 5 minutes)
                        session_start_times = {
                            "ASIA": asia_start,
                            "LONDON": lon_start,
                            "US": us_start,
                        }
                        session_start = session_start_times.get(session_name)
                        if session_start:
                            # Check if current time is within 5 minutes of session start
                            start_h, start_m = map(int, session_start.split(":"))
                            current_h, current_m = map(int, hour_min.split(":"))
                            start_minutes = start_h * 60 + start_m
                            current_minutes = current_h * 60 + current_m
                            time_diff = current_minutes - start_minutes
                            
                            # Notify if within first 5 minutes of session start
                            if 0 <= time_diff <= 5:
                                time_str = t_vn.strftime("%Y-%m-%d %H:%M:%S")
                                notifier.notify_session_start(session_name, time_str)
                                logger.info(f"📢 Session notification sent: {session_name} started at {time_str}")
                    
                    last_session_name = session_name
                    
                    # Pull MT5 profit history periodically (every 60 seconds)
                    if now_ts - last_profit_pull >= PROFIT_PULL_INTERVAL:
                        try:
                            profit_data = fetch_profit_buckets(now=current_time)
                            bot_state.set_mt5_profit(profit_data)
                            last_profit_pull = now_ts
                            logger.debug(f"MT5 profit history updated: {profit_data.get('asof')}")
                        except Exception as e:
                            logger.warning(f"Failed to fetch MT5 profit history: {e}", exc_info=True)
                    
                    # Update bot state
                    status = risk_mgr.get_status()
                    bot_state.set(
                        paused=bot_state.paused,  # Keep current paused state
                        day_blocked=status['day_blocked'],
                        consec_loss=status['consec_loss'],
                        session=session_name,
                        balance=balance,
                        equity=balance,  # Simple: equity = balance (can enhance later)
                    )
                    
                    # Update open_trades snapshot
                    open_trades_snapshot = []
                    for t, tr in open_positions.items():
                        open_trades_snapshot.append({
                            "direction": tr.direction,
                            "setup": tr.setup,
                            "lot_open": tr.lot_open,
                            "entry": tr.entry_price,
                            "sl": tr.sl,
                            "tp1": tr.tp1,
                            "tp2": tr.tp2,
                        })
                    bot_state.set_open_trades(open_trades_snapshot)
                    
                    # Heartbeat notification (every 30 minutes)
                    if now_ts - last_heartbeat >= HEARTBEAT_INTERVAL:
                        latest_candle_time_vn_check = to_vn_time(pd.Series([latest_candle_time]))[0]
                        # Use same timezone conversion as above
                        import pytz
                        if current_time.tzinfo is None:
                            tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
                            current_time_local = tz_vn.localize(current_time)
                            current_time_utc = current_time_local.astimezone(pytz.UTC)
                        else:
                            current_time_utc = current_time.astimezone(pytz.UTC)
                        current_time_utc_ts = pd.Timestamp(current_time_utc)
                        data_age_minutes = (current_time_utc_ts - latest_candle_time).total_seconds() / 60.0
                        
                        status_emoji = "✅" if data_age_minutes <= 20 else "⚠️"
                        notifier.send(
                            f"{status_emoji} <b>BOT HEARTBEAT</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📊 Session: <b>{session_name}</b>\n"
                            f"📈 Latest candle: {latest_candle_time_vn_check.strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"⏰ Data age: <b>{data_age_minutes:.1f} min</b>\n"
                            f"💰 Balance: <b>{balance:.2f}$</b>\n"
                            f"📦 Positions: <b>{len(open_positions)}</b>\n"
                            f"🕐 {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"✅ Bot is running"
                        )
                        last_heartbeat = now_ts
                        logger.info(f"💓 Heartbeat sent: Session={session_name}, Data age={data_age_minutes:.1f} min, Positions={len(open_positions)}")
                
                    # Log candle info (Fix 3: Use row_closed instead of row)
                    candle_time_str = t_vn.strftime("%Y-%m-%d %H:%M:%S")
                    logger.info(f"[{session_name}] Closed Candle: {candle_time_str} | O:{row_closed['open']:.2f} H:{row_closed['high']:.2f} L:{row_closed['low']:.2f} C:{row_closed['close']:.2f} | ATR:{row_closed['atr']:.2f}")
                
                    # Entry checks
                    can_open, reason = risk_mgr.can_open_new_trade()
                    if not can_open:
                        if reason == "max_consecutive_loss":
                            logger.info(f"Consecutive loss stop: {risk_mgr.consec_loss} >= {max_consec_loss}")
                            # Telegram notification: STOP DAY
                            status = risk_mgr.get_status()
                            if status['day_blocked'] and not bot_state.day_blocked:
                                notifier.notify_stop_day(consec_loss=status['consec_loss'])
                        elif bot_state.paused:
                            # Bot is paused via Telegram
                            pass
                        last_m15_pull = now_ts
                        time.sleep(1)
                        continue
                    
                    # Check if bot is paused
                    if bot_state.paused:
                        last_m15_pull = now_ts
                        time.sleep(1)
                        continue
                    
                    # A) Signal detection - ONLY when new closed candle detected
                    if new_closed_candle:
                        if len(open_positions) > 0:
                            logger.info(f"Skipping entry check: {len(open_positions)} position(s) already open")
                        else:
                            hour_min = row_closed["time_vn"].strftime("%H:%M")
                            session_name = "OUTSIDE"
                            
                            # Convert time strings to minutes for proper comparison
                            def time_to_minutes(time_str: str) -> int:
                                h, m = map(int, time_str.split(":"))
                                return h * 60 + m
                            
                            current_minutes = time_to_minutes(hour_min)
                            asia_start_min = time_to_minutes(asia_start)
                            asia_end_min = time_to_minutes(asia_end)
                            lon_start_min = time_to_minutes(lon_start)
                            lon_end_min = time_to_minutes(lon_end)
                            us_start_min = time_to_minutes(us_start)
                            us_end_min = time_to_minutes(us_end)
                            
                            if asia_start_min <= current_minutes <= asia_end_min:
                                session_name = "ASIA"
                            elif lon_start_min <= current_minutes <= lon_end_min:
                                session_name = "LONDON"
                            elif us_start_min <= current_minutes <= us_end_min:
                                session_name = "US"
                            
                            logger.info(f"Checking for signals (on closed candle)... Session={session_name}, Time={hour_min}, Risk: consec_loss={risk_mgr.consec_loss}/{max_consec_loss}, day_blocked={risk_mgr.day_blocked}, paused={bot_state.paused}, Data: {len(df_m15)} candles")
                        
                            # Log tick data (10-20 dòng) để kiểm tra giá bid/ask
                            try:
                                import MetaTrader5 as mt5
                                tick = mt5.symbol_info_tick(symbol)
                                if tick:
                                    tick_time = datetime.fromtimestamp(tick.time)
                                    logger.info(f"📊 TICK DATA: Time={tick_time.strftime('%Y-%m-%d %H:%M:%S')} | Bid={tick.bid:.2f} | Ask={tick.ask:.2f} | Spread={(tick.ask - tick.bid):.2f} | Volume={tick.volume}")
                                    logger.info(f"   Price source: mt5.symbol_info_tick() | OHLC source: mt5.copy_rates_range(M15)")
                                    logger.info(f"   Trade management timeframe: Tick-based (1s interval)")
                            except Exception as e:
                                logger.warning(f"Failed to get tick data: {e}")
                            
                            # Fix 2: get_signal() chạy ngoài try/except (không phụ thuộc vào tick)
                            # Use closed candle index (iloc[-2] = len - 2)
                            signal_idx = len(df_m15) - 2  # Use closed candle for signal
                            logger.debug(f"Signal check: index={signal_idx} (closed candle), total_candles={len(df_m15)}")
                            try:
                                sig = strat.get_signal(signal_idx, df_m15, balance)
                            except Exception as e:
                                logger.error(f"Error in get_signal(): {e}", exc_info=True)
                                sig = None
                            
                            if sig:
                                logger.info("=" * 80)
                                logger.info(f"SIGNAL DETECTED: {sig.reason}")
                                logger.info(f"Direction: {sig.direction} | Entry: {sig.entry_price:.2f} | SL: {sig.sl:.2f}")
                                tp1_str = f"{sig.tp1:.2f}" if sig.tp1 is not None else "N/A"
                                tp2_str = f"{sig.tp2:.2f}" if sig.tp2 is not None else "N/A"
                                logger.info(f"TP1: {tp1_str} | TP2: {tp2_str}")
                                logger.info("=" * 80)
                                # Extract setup from reason
                                reason_str = sig.reason
                                setup_str = ""
                                if "REACTION" in reason_str or "HVN_VAL" in reason_str:
                                    setup_str = "A"
                                elif "SECOND_ENTRY" in reason_str or "SECOND" in reason_str:
                                    setup_str = "B"
                                elif "VA_REENTRY" in reason_str or "REENTRY_TRAP" in reason_str or "VA_TRAP" in reason_str or "ABSORB" in reason_str or "TRAP" in reason_str:
                                    setup_str = "D"
                                elif "GAP" in reason_str or "LVN_GAP" in reason_str:
                                    setup_str = "E"
                                
                                # Get TP1/TP2
                                entry_lot = float(tm_cfg.get("entry_lot", 0.04))
                                tp1_lot = float(tm_cfg.get("tp1_close_lot", 0.02))
                                
                                tp1_mode = tm_cfg.get("tp1_mode", "POC")
                                if sig.tp1 is not None:
                                    tp1_price = float(sig.tp1)
                                elif tp1_mode == "POC":
                                    tp1_price = float(sig.tp)
                                else:
                                    # Fix 3: Use row_closed instead of row
                                    atr_val = float(row_closed["atr"]) if "atr" in row_closed else 1.0
                                    k = float(tm_cfg.get("tp1_atr", 1.0))
                                    tp1_price = float(sig.entry_price) + (k * atr_val if sig.direction == "BUY" else -k * atr_val)
                                
                                tp2_price = float(sig.tp2) if sig.tp2 is not None else float(sig.tp)
                                
                                # D) Use real spread from tick for entry fill
                                try:
                                    import MetaTrader5 as mt5
                                    tick = mt5.symbol_info_tick(symbol)
                                    if tick:
                                        tick_bid = float(tick.bid)
                                        tick_ask = float(tick.ask)
                                        tick_spread = tick_ask - tick_bid
                                        # Convert spread to points (XAUUSD: 1 point = 0.01)
                                        spread_points = tick_spread / point_value
                                        
                                        # Apply entry fill with real spread
                                        entry_price_filled = tm.apply_entry_fill(sig.direction, float(sig.entry_price), spread_points=spread_points)
                                        
                                        tick_time = datetime.fromtimestamp(tick.time)
                                        logger.info(f"📊 TICK DATA (Before Order): Time={tick_time.strftime('%Y-%m-%d %H:%M:%S')} | Bid={tick_bid:.2f} | Ask={tick_ask:.2f} | Spread={tick_spread:.2f} ({spread_points:.1f} pts)")
                                        logger.info(f"   Entry price (signal): {sig.entry_price:.2f} | Entry price (filled with real spread): {entry_price_filled:.2f}")
                                    else:
                                        # Fallback to fixed spread
                                        entry_price_filled = tm.apply_entry_fill(sig.direction, float(sig.entry_price))
                                        logger.warning("Failed to get tick, using fixed spread")
                                except Exception as e:
                                    logger.warning(f"Failed to get tick data before order: {e}, using fixed spread")
                                    entry_price_filled = tm.apply_entry_fill(sig.direction, float(sig.entry_price))
                                
                                # Open position via MT5
                                order_type = OrderType.BUY if sig.direction == "BUY" else OrderType.SELL
                                # Create short comment for MT5 (max 32 chars, remove VP_ prefix if already present)
                                reason_short = sig.reason.replace("VP_", "") if sig.reason.startswith("VP_") else sig.reason
                                comment = f"VP_{reason_short}"[:32]  # Truncate to 32 chars max
                                
                                ticket = mt5_executor.place_market_order(
                                    symbol=symbol,
                                    order_type=order_type,
                                    volume=entry_lot,
                                    stop_loss=float(sig.sl),
                                    take_profit=tp2_price,
                                    comment=comment,
                                )
                                
                                if ticket:
                                    trade_obj = Trade(
                                        direction=sig.direction,
                                        entry_time=current_time.isoformat(),
                                        entry_price=entry_price_filled,
                                        sl=float(sig.sl),
                                        tp=float(tp2_price if tp2_price is not None else sig.tp),
                                        lot=entry_lot,
                                        lot_open=entry_lot,
                                        lot_tp1=tp1_lot,
                                        tp1=tp1_price,
                                        tp2=tp2_price,
                                        setup=setup_str,
                                        reason=reason_str,
                                    )
                                    open_positions[ticket] = trade_obj
                                    risk_mgr.record_new_trade()
                                    logger.info("=" * 80)
                                    logger.info(f"POSITION OPENED: Ticket={ticket}")
                                    logger.info(f"{sig.direction} {entry_lot} lot @ {entry_price_filled:.2f}")
                                    logger.info(f"TP1: {tp1_price:.2f} ({tp1_lot} lot) | TP2: {tp2_price:.2f} ({entry_lot - tp1_lot} lot)")
                                    logger.info(f"SL: {sig.sl:.2f}")
                                    logger.info("=" * 80)
                                    
                                    # Telegram notification: ENTRY
                                    notifier.notify_open({
                                        "direction": sig.direction,
                                        "setup": setup_str,
                                        "session": session_name,
                                        "entry": entry_price_filled,
                                        "sl": float(sig.sl),
                                        "tp1": tp1_price,
                                        "tp2": tp2_price,
                                        "lot": entry_lot,
                                        "reason": reason_str,
                                    })
                                    
                                    # Update open_trades in bot_state
                                    open_trades_snapshot = []
                                    for t, tr in open_positions.items():
                                        open_trades_snapshot.append({
                                            "direction": tr.direction,
                                            "setup": tr.setup,
                                            "lot_open": tr.lot_open,
                                            "entry": tr.entry_price,
                                            "sl": tr.sl,
                                            "tp1": tr.tp1,
                                            "tp2": tr.tp2,
                                        })
                                    bot_state.set_open_trades(open_trades_snapshot)
                            else:
                                logger.info("No signal")
                
                except Exception as e:
                    logger.error(f"Error in M15 fetch/signal detection: {e}", exc_info=True)
                
                last_m15_pull = now_ts
            
            # Fix 0: Add small sleep to prevent 100% CPU usage
            time.sleep(0.05)  # 50ms sleep to prevent CPU spinning
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down...")
        # Use silent_fail=True to prevent network errors from crashing during shutdown
        try:
            notifier.send(
                "🛑 <b>BOT STOPPED</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⏹️ Keyboard interrupt\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                silent_fail=True
            )
        except Exception as e:
            logger.warning(f"Failed to send shutdown notification: {e}")
        running = False  # Exit while loop
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in trading loop: {e}", exc_info=True)
        bot_state.set(last_error=error_msg)
        
        # Telegram notification: ERROR
        try:
            notifier.notify_error(err=error_msg)
        except Exception as notify_err:
            logger.warning(f"Failed to send error notification: {notify_err}")
        
        # Sleep and retry - restart the while loop
        logger.warning("Error occurred, will retry after 60s...")
        time.sleep(60)
        # Note: Exception will exit the while loop, but we want to restart
        # For now, just log and let it exit gracefully
        # TODO: Add retry mechanism if needed
    
    finally:
        mt5_executor.disconnect()
        mt5_fetcher.shutdown()
        logger.info("Live runner stopped")


if __name__ == "__main__":
    main()
