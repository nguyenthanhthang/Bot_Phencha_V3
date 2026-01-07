from __future__ import annotations
from datetime import datetime, date
from typing import Optional

from dotenv import load_dotenv

from utils.config_loader import load_yaml, get_nested
from utils.logger import setup_logger
from utils.time_utils import to_vn_time
from execution.mt5_executor import MT5Executor
from risk.live_risk_manager import LiveRiskManager
from volume_profile.cache import SessionProfileCache
from strategies.vp_v1 import VPStrategyV1
from execution.trade_manager import TradeManager
from data.mt5_fetcher import MT5Fetcher
from data.resample import resample_ohlc
import pandas as pd


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
    symbols = load_yaml("config/symbols.yaml")
    tg_cfg = load_yaml("config/telegram.yaml")
    cfg_vp = load_yaml("config/vp.yaml")

    logger = setup_logger(
        name=get_nested(cfg, "app.name", "BOT_XAUUSD"),
        level="INFO",
    )

    app_name = get_nested(cfg, "app.name", "BOT_XAUUSD")
    tz = get_nested(cfg, "app.timezone", "Asia/Ho_Chi_Minh")
    symbol = get_nested(cfg, "symbol.name", "XAUUSD")
    tf = get_nested(cfg, "symbol.timeframe", "M15")

    # Risk management config
    risk_cfg = cfg["risk"]
    risk_trade = float(risk_cfg.get("risk_per_trade_pct", 0.5))
    max_consec_loss = int(risk_cfg.get("max_consecutive_loss", 3))

    asia_start = get_nested(cfg, "sessions.asia.start", "06:00")
    asia_end = get_nested(cfg, "sessions.asia.end", "11:00")
    lon_start = get_nested(cfg, "sessions.london.start", "14:00")
    lon_end = get_nested(cfg, "sessions.london.end", "17:30")

    sym_specs = symbols.get(symbol, {})
    min_lot = sym_specs.get("min_lot", None)
    lot_step = sym_specs.get("lot_step", None)

    logger.info("Boot LIVE runner OK")
    logger.info(f"App: {app_name} | TZ: {tz}")
    logger.info(f"Symbol: {symbol} | TF: {tf}")
    logger.info(f"Sessions: Asia {asia_start}-{asia_end} | London {lon_start}-{lon_end}")
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

    # Initialize Volume Profile cache and strategy
    # Note: For live, you may need to load recent M1 data or fetch on-demand
    # This is a placeholder - you'll need to implement M1 data fetching for live
    logger.info("Loading M1 data for Volume Profile...")
    # TODO: Fetch recent M1 data (e.g., last 30 days) for VP calculation
    # df_m1 = fetch_recent_m1_data(mt5_fetcher, symbol, days=30)
    # For now, using empty DataFrame as placeholder
    df_m1 = pd.DataFrame(columns=["time", "close", "volume"])
    df_m1["time"] = pd.to_datetime(df_m1["time"], utc=True)
    
    vp_cache = SessionProfileCache(df_m1, cfg_all)
    strat = VPStrategyV1(cfg_all, sym_specs, vp_cache)

    # Fill model config (spread/slippage) - same as backtest
    fill_cfg = cfg.get("fill_model", {})
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

    logger.info("Live runner started. Waiting for candles...")
    
    # Track open positions (similar to backtest's open_trades list)
    # In live, we track MT5 position tickets and their metadata
    # You'll need to maintain a mapping: ticket -> Trade object (for TP1/TP2 tracking)
    open_positions = {}  # {ticket: Trade object}
    
    # TODO: Implement your candle loop here
    # Structure similar to backtest:
    #
    # import time
    # from indicators import atr
    #
    # while True:
    #     # Get current M15 candle
    #     current_time = datetime.now()
    #     t_vn = to_vn_time(pd.Series([current_time]))[0]
    #     cur_day = t_vn.date()
    #
    #     # Fetch current M15 candle data
    #     df_m15 = fetch_current_candle(mt5_fetcher, symbol, "M15")
    #     if df_m15.empty:
    #         time.sleep(60)
    #         continue
    #
    #     row = df_m15.iloc[-1]  # Latest candle
    #     df_m15["time_vn"] = to_vn_time(df_m15["time"])
    #     df_m15["atr"] = atr(df_m15, 14)
    #
    #     # Get current balance
    #     balance = get_account_balance(mt5_executor)
    #
    #     # Check new day and reset risk state
    #     if risk_mgr.check_new_day(cur_day):
    #         logger.info(f"New day: {cur_day} | Balance: {balance:.2f}")
    #         open_positions = {}  # Reset position tracking
    #
    #     # Manage open positions (scale-out TP logic - same as backtest)
    #     positions = mt5_executor.get_positions(symbol=symbol)
    #     still_open = {}
    #
    #     for ticket, trade_obj in open_positions.items():
    #         # Check if position still exists in MT5
    #         pos = next((p for p in positions if p['ticket'] == ticket), None)
    #         if pos is None:
    #             # Position closed externally - update consecutive loss
    #             # Note: You'll need to track PnL when position closes
    #             continue
    #
    #         # Use TradeManager to check TP1/TP2/SL (same logic as backtest)
    #         realized, closed_all, r = tm.update_trade_on_bar(trade_obj, row, tm_cfg)
    #
    #         if realized != 0.0:
    #             # Partial close (TP1) or full close
    #             if r == "TP1_PARTIAL":
    #                 # Partial close TP1
    #                 mt5_executor.close_partial(ticket, trade_obj.lot_tp1)
    #                 # Modify SL to BE+
    #                 mt5_executor.modify_sl(ticket, trade_obj.sl_after_tp1)
    #                 logger.info(f"TP1 hit: Partial close {trade_obj.lot_tp1} lot, SL moved to BE+")
    #
    #             elif closed_all:
    #                 # Full close (SL, TP1_FULL, TP2)
    #                 mt5_executor.close_position(ticket)
    #                 pnl = realized  # Use realized PnL
    #                 risk_mgr.update_consecutive_loss(pnl)
    #                 logger.info(f"Position closed: {r} | PnL: {pnl:.2f}")
    #                 del open_positions[ticket]
    #                 continue
    #
    #         still_open[ticket] = trade_obj
    #
    #     open_positions = still_open
    #
    #     # Entry checks: block if day_blocked, max trades, or consecutive loss
    #     can_open, reason = risk_mgr.can_open_new_trade()
    #     if not can_open:
    #         if reason == "max_consecutive_loss":
    #             logger.info(f"Consecutive loss stop: {risk_mgr.consec_loss} >= {max_consec_loss} (blocked until next day)")
    #         continue  # Skip entry
    #
    #     # Check for signal (same as backtest)
    #     if len(open_positions) == 0:  # Only one position at a time
    #         # Get signal from strategy
    #         sig = strat.get_signal(len(df_m15) - 1, df_m15, balance)
    #         if sig:
    #             # Apply entry fill (spread + slippage) - same as backtest
    #             entry_price_filled = tm.apply_entry_fill(sig.direction, float(sig.entry_price))
    #
    #             # Get TP1/TP2 from signal
    #             entry_lot = float(tm_cfg.get("entry_lot", 0.04))
    #             tp1_lot = float(tm_cfg.get("tp1_close_lot", 0.02))
    #
    #             tp1_mode = tm_cfg.get("tp1_mode", "POC")
    #             if sig.tp1 is not None:
    #                 tp1_price = float(sig.tp1)
    #             else:
    #                 tp1_price = float(sig.tp)  # fallback
    #
    #             tp2_price = float(sig.tp2) if sig.tp2 is not None else float(sig.tp)
    #
    #             # Open position via MT5
    #             order_type = MT5Executor.OrderType.BUY if sig.direction == "BUY" else MT5Executor.OrderType.SELL
    #             ticket = mt5_executor.place_market_order(
    #                 symbol=symbol,
    #                 order_type=order_type,
    #                 volume=entry_lot,
    #                 stop_loss=sig.sl,
    #                 take_profit=tp2_price,  # Set TP2 as initial TP (will modify after TP1)
    #                 comment=f"VP_{sig.reason}",
    #             )
    #
    #             if ticket:
    #                 # Create Trade object for tracking (same structure as backtest)
    #                 from execution.backtest_executor import Trade
    #                 trade_obj = Trade(
    #                     direction=sig.direction,
    #                     entry_time=current_time.isoformat(),
    #                     entry_price=entry_price_filled,
    #                     sl=float(sig.sl),
    #                     tp=float(tp2_price),
    #                     lot=entry_lot,
    #                     lot_open=entry_lot,
    #                     lot_tp1=tp1_lot,
    #                     tp1=tp1_price,
    #                     tp2=tp2_price,
    #                     setup="D",  # Extract from reason
    #                     reason=sig.reason,
    #                 )
    #                 open_positions[ticket] = trade_obj
    #                 risk_mgr.record_new_trade()
    #                 logger.info(f"Opened {sig.direction} position: ticket={ticket}, lot={entry_lot}, entry={entry_price_filled:.2f}")
    #
    #     time.sleep(60)  # Wait for next candle

    logger.info("Live runner stopped")


if __name__ == "__main__":
    main()
