import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

import pandas as pd
import logging

from utils.logger import setup_logger
from utils.config_loader import load_yaml
from indicators import atr
from utils.time_utils import to_vn_time
from volume_profile.cache import SessionProfileCache
from strategies.vp_v1 import VPStrategyV1
from execution.backtest_executor import BacktestExecutor, Trade
from execution.trade_manager import TradeManager
from backtest.metrics import compute_metrics
from reporting.trade_logger import save_trades_csv


def main():
    # Use separate log file for backtest to avoid conflicts with live bot
    logger = setup_logger("BOT_VP_BACKTEST", log_dir="logs", level="INFO")
    
    # Replace file handler with backtest-specific log file
    # Remove existing file handlers
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()
    
    # Add backtest-specific log file (non-rotating to avoid permission issues)
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    backtest_log_path = log_dir / "backtest.log"
    
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    # Use regular FileHandler instead of RotatingFileHandler to avoid permission issues
    fh = logging.FileHandler(backtest_log_path, encoding='utf-8', mode='a')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    
    # Also setup logger for strategies module to ensure logging works (same as live)
    # Fix: Reuse main logger handlers to avoid opening the same file twice (same as live fix)
    strategies_logger = logging.getLogger("strategies.vp_v1")
    strategies_logger.setLevel(logging.INFO)
    strategies_logger.propagate = False
    
    # Remove any existing handlers (like NullHandler)
    strategies_logger.handlers.clear()
    
    # Reuse main logger handlers (console + file) to avoid duplicate file handles
    # This matches the fix in runner_live.py
    for h in logger.handlers:
        strategies_logger.addHandler(h)

    cfg_backtest = load_yaml("config/backtest.yaml")
    cfg_settings = load_yaml("config/settings.yaml")
    cfg_vp = load_yaml("config/vp.yaml")
    symbols = load_yaml("config/symbols.yaml")

    # merge configs (settings + vp + backtest risk)
    cfg_all = {}
    cfg_all.update(cfg_settings)
    cfg_all["vp"] = cfg_vp["vp"]
    cfg_all["rules"] = cfg_vp["rules"]
    cfg_all["sessions"] = cfg_vp["sessions"]
    cfg_all["risk"] = cfg_settings["risk"]
    cfg_all["account"] = cfg_backtest["account"]
    cfg_all["london_mode"] = cfg_vp.get("london_mode", {})  # London mode config
    cfg_all["us_mode"] = cfg_vp.get("us_mode", {})  # US mode config

    # Load data for multiple years (2020-2025)
    import os
    from datetime import datetime
    
    data_dir = "data_cache"
    start_year = 2020
    end_year = 2025
    
    logger.info(f"Loading data from {start_year} to {end_year}...")
    
    # Find and load M15 data files (prefer yearly files, fallback to monthly)
    df_m15_list = []
    for year in range(start_year, end_year + 1):
        # Try yearly file first
        yearly_file = f"{data_dir}/XAUUSDm_M15_{year}-01-01_{year+1}-01-01.csv"
        if os.path.exists(yearly_file):
            logger.info(f"Loading M15: {yearly_file}")
            df_year = pd.read_csv(yearly_file, parse_dates=["time"])
            df_m15_list.append(df_year)
        else:
            # Fallback: try to find monthly files for this year
            monthly_files = []
            for month in range(1, 13):
                if month == 12:
                    next_file = f"{data_dir}/XAUUSDm_M15_{year}-12-01_{year+1}-01-01.csv"
                else:
                    next_month = month + 1
                    next_file = f"{data_dir}/XAUUSDm_M15_{year}-{month:02d}-01_{year}-{next_month:02d}-01.csv"
                
                if os.path.exists(next_file):
                    monthly_files.append(next_file)
            
            if monthly_files:
                logger.info(f"Loading M15: {len(monthly_files)} monthly files for {year}")
                for mfile in monthly_files:
                    df_month = pd.read_csv(mfile, parse_dates=["time"])
                    df_m15_list.append(df_month)
            else:
                logger.warning(f"No M15 data found for year {year}")
    
    if not df_m15_list:
        logger.error("No M15 data files found!")
        return
    
    # Concatenate and sort M15 data
    df_m15 = pd.concat(df_m15_list, ignore_index=True)
    df_m15 = df_m15.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
    logger.info(f"Loaded M15: {len(df_m15)} total rows from {df_m15['time'].min()} to {df_m15['time'].max()}")
    
    # Find and load M1 data files (prefer yearly files, fallback to monthly)
    df_m1_list = []
    for year in range(start_year, end_year + 1):
        # Try yearly file first
        yearly_file = f"{data_dir}/XAUUSDm_M1_{year}-01-01_{year+1}-01-01.csv"
        if os.path.exists(yearly_file):
            logger.info(f"Loading M1: {yearly_file}")
            df_year = pd.read_csv(yearly_file, parse_dates=["time"])
            df_m1_list.append(df_year)
        else:
            # Fallback: try to find monthly files for this year
            monthly_files = []
            for month in range(1, 13):
                if month == 12:
                    next_file = f"{data_dir}/XAUUSDm_M1_{year}-12-01_{year+1}-01-01.csv"
                else:
                    next_month = month + 1
                    next_file = f"{data_dir}/XAUUSDm_M1_{year}-{month:02d}-01_{year}-{next_month:02d}-01.csv"
                
                if os.path.exists(next_file):
                    monthly_files.append(next_file)
            
            if monthly_files:
                logger.info(f"Loading M1: {len(monthly_files)} monthly files for {year}")
                for mfile in monthly_files:
                    df_month = pd.read_csv(mfile, parse_dates=["time"])
                    df_m1_list.append(df_month)
            else:
                logger.warning(f"No M1 data found for year {year}")
    
    if not df_m1_list:
        logger.error("No M1 data files found!")
        return
    
    # Concatenate and sort M1 data
    df_m1 = pd.concat(df_m1_list, ignore_index=True)
    df_m1 = df_m1.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
    logger.info(f"Loaded M1: {len(df_m1)} total rows from {df_m1['time'].min()} to {df_m1['time'].max()}")

    logger.info(f"M1 rows={len(df_m1)} | M15 rows={len(df_m15)}")

    df_m15["time_vn"] = to_vn_time(df_m15["time"])
    df_m15["atr"] = atr(df_m15, int(cfg_vp["rules"]["atr_period"]))
    df_m15 = df_m15.dropna().reset_index(drop=True)
    
    # Check if enough data for signal detection (need at least 20 candles for breakout detection)
    if len(df_m15) < 20:
        logger.error(f"Not enough M15 data: {len(df_m15)} candles (need at least 20 for breakout detection)")
        return

    # symbol specs (bạn có thể thêm XAUUSDm vào symbols.yaml để chuẩn)
    symbol_specs = symbols.get("XAUUSDm", symbols.get("XAUUSD", {"contract_size": 100, "min_lot": 0.01, "lot_step": 0.01}))

    vp_cache = SessionProfileCache(df_m1, cfg_all)
    strat = VPStrategyV1(cfg_all, symbol_specs, vp_cache)
    
    # Fill model config (spread/slippage)
    fill_cfg = cfg_backtest.get("fill_model", {})
    spread_points = float(fill_cfg.get("fixed_spread_points", 30.0))
    slippage_mode = fill_cfg.get("slippage_mode", "OFF")
    slippage_points = float(fill_cfg.get("slippage_points", 0.0)) if slippage_mode != "OFF" else 0.0
    point_value = 0.01  # XAUUSD: 0.01 per point (2 decimals)
    
    executor = BacktestExecutor(
        contract_size=float(symbol_specs.get("contract_size", 100.0)),
        spread_points=spread_points,
        slippage_points=slippage_points,
        point_value=point_value,
    )
    
    # TradeManager for scale-out TP
    tm_cfg = cfg_vp.get("trade_management", {})
    tm = TradeManager(
        contract_size=float(symbol_specs.get("contract_size", 100.0)),
        spread_points=spread_points,
        slippage_points=slippage_points,
        point_value=point_value,
    )

    initial_balance = float(cfg_all["account"]["initial_balance"])
    balance = initial_balance
    trades = []
    open_trades = []  # Changed to list to support multiple open trades

    # Risk management config
    risk_cfg = cfg_all["risk"]
    max_consec_loss = int(risk_cfg.get("max_consecutive_loss", 3))
    
    # Risk state variables
    consec_loss = 0
    day_blocked = False  # Only for consecutive loss blocking
    current_day = None

    for i in range(len(df_m15)):
        row = df_m15.iloc[i]  # Current candle (may be forming)
        t_vn = row["time_vn"]
        cur_day = t_vn.date()

        # Reset daily state when new day starts
        if current_day is None or cur_day != current_day:
            current_day = cur_day
            day_blocked = False
            consec_loss = 0  # Reset consecutive loss count each day
            logger.info(f"New day: {cur_day} | Balance: {balance:.2f}")

        # B) Only use closed candle for signal detection (similar to live)
        # When i=0, no closed candle yet, skip signal check
        # When i>=1, candle i-1 is closed, use it for signal
        
        # Manage open trades using current candle (for TP1/TP2/SL check)
        still_open = []
        for tr in open_trades:
            # Use current candle (row) for position management
            realized, closed_all, r = tm.update_trade_on_bar(tr, row, tm_cfg)
            if realized != 0.0:
                balance += realized
                if tr.pnl_usd is None:
                    tr.pnl_usd = 0.0
                tr.pnl_usd += realized

            if closed_all:
                tr.exit_time = pd.to_datetime(row["time"]).isoformat()
                # Use appropriate exit price based on reason (apply exit fill for consistency)
                if r == "SL":
                    tr.exit_price = tm.apply_exit_fill(tr.direction, tr.sl)
                elif r == "TP1_FULL":
                    tr.exit_price = tm.apply_exit_fill(tr.direction, tr.tp1)
                elif r == "TP2":
                    tr.exit_price = tm.apply_exit_fill(tr.direction, tr.tp2)
                else:
                    tr.exit_price = tm.apply_exit_fill(tr.direction, float(row["close"]))
                tr.exit_reason = r or "CLOSED"
                trades.append(tr)
                
                # Update consecutive loss counter
                # tr.pnl_usd đã là pnl của cả trade (cộng dồn partial), dùng nó để tính chuỗi thua
                if tr.pnl_usd is not None and tr.pnl_usd < 0:
                    consec_loss += 1
                else:
                    consec_loss = 0
            else:
                still_open.append(tr)

        open_trades = still_open

        # Entry checks: block if day_blocked (consecutive loss) or consecutive loss
        if day_blocked:
            continue
        if consec_loss >= max_consec_loss:
            day_blocked = True  # stop luôn tới ngày mới cho "đúng chất"
            logger.info(f"Consecutive loss stop: {consec_loss} >= {max_consec_loss} (blocked until next day)")
            continue

        # A) Signal detection - ONLY on closed candle (similar to live)
        # Only check signal when we have at least 1 closed candle (i >= 1)
        if len(open_trades) == 0 and i >= 1:
            # Get session times from config (define once, use multiple times)
            asia_start = cfg_all["sessions"]["asia"]["start"]
            asia_end = cfg_all["sessions"]["asia"]["end"]
            lon_start = cfg_all["sessions"]["london"]["start"]
            lon_end = cfg_all["sessions"]["london"]["end"]
            us_start = cfg_all["sessions"]["us"]["start"]
            us_end = cfg_all["sessions"]["us"]["end"]
            
            # Use closed candle (i-1) for signal detection
            row_closed = df_m15.iloc[i-1]  # Last closed candle
            t_vn_closed = row_closed["time_vn"]
            
            # Convert time strings to minutes for proper comparison (same as live)
            def time_to_minutes(time_str: str) -> int:
                h, m = map(int, time_str.split(":"))
                return h * 60 + m
            
            # Log closed candle (similar to live, but only once per candle)
            if i == 1 or (i > 1 and df_m15.iloc[i-1]["time"] != df_m15.iloc[i-2]["time"]):
                # Determine session first for logging (same as live)
                hour_min_check = t_vn_closed.strftime("%H:%M")
                session_name_check = "OUTSIDE"
                
                current_minutes_check = time_to_minutes(hour_min_check)
                asia_start_min_check = time_to_minutes(asia_start)
                asia_end_min_check = time_to_minutes(asia_end)
                lon_start_min_check = time_to_minutes(lon_start)
                lon_end_min_check = time_to_minutes(lon_end)
                us_start_min_check = time_to_minutes(us_start)
                us_end_min_check = time_to_minutes(us_end)
                
                if asia_start_min_check <= current_minutes_check <= asia_end_min_check:
                    session_name_check = "ASIA"
                elif lon_start_min_check <= current_minutes_check <= lon_end_min_check:
                    session_name_check = "LONDON"
                elif us_start_min_check <= current_minutes_check <= us_end_min_check:
                    session_name_check = "US"
                
                atr_val = float(row_closed["atr"]) if "atr" in row_closed else 0.0
                logger.info(
                    f"✅ NEW CLOSED CANDLE: {t_vn_closed.strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"O:{row_closed['open']:.2f} H:{row_closed['high']:.2f} "
                    f"L:{row_closed['low']:.2f} C:{row_closed['close']:.2f}"
                )
            
            # Determine session for logging (same logic as live)
            hour_min = t_vn_closed.strftime("%H:%M")
            session_name = "OUTSIDE"
            
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
            
            # Log candle info (same format as live)
            atr_val = float(row_closed["atr"]) if "atr" in row_closed else 0.0
            candle_time_str = t_vn_closed.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[{session_name}] Closed Candle: {candle_time_str} | O:{row_closed['open']:.2f} H:{row_closed['high']:.2f} L:{row_closed['low']:.2f} C:{row_closed['close']:.2f} | ATR:{atr_val:.2f}")
            
            logger.info(f"Checking for signals (on closed candle)... Session={session_name}, Time={hour_min}, Risk: consec_loss={consec_loss}/{max_consec_loss}, day_blocked={day_blocked}, paused=False, Data: {len(df_m15)} candles")
            
            try:
                # Use closed candle index (i-1) for signal detection
                sig = strat.get_signal(i-1, df_m15, balance)
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
                
                # Extract setup from reason (same as live)
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
                
                # Get TP1/TP2 from signal or calculate from config
                entry_lot = float(tm_cfg.get("entry_lot", 0.04))
                tp1_lot = float(tm_cfg.get("tp1_close_lot", 0.02))
                
                # TP1 price: từ signal hoặc tính từ config
                tp1_mode = tm_cfg.get("tp1_mode", "POC")
                if sig.tp1 is not None:
                    tp1_price = float(sig.tp1)
                elif tp1_mode == "POC":
                    tp1_price = float(sig.tp)  # fallback
                elif tp1_mode == "MID_VA":
                    tp1_price = float(sig.tp)  # fallback
                else:
                    # FIXED_ATR - use ATR from closed candle
                    atr_val = float(row_closed["atr"]) if "atr" in row_closed else 1.0
                    k = float(tm_cfg.get("tp1_atr", 1.0))
                    tp1_price = float(sig.entry_price) + (k * atr_val if sig.direction == "BUY" else -k * atr_val)
                
                # TP2 price: từ signal hoặc fallback
                tp2_price = float(sig.tp2) if sig.tp2 is not None else float(sig.tp)
                
                # D) Apply entry fill (spread + slippage)
                # In backtest, we use fixed spread from config (no real tick data)
                # But we simulate the logic: use close price of closed candle as reference
                entry_price_filled = executor.apply_entry_fill(sig.direction, float(sig.entry_price))
                
                # Log entry details (same format as live)
                logger.info("=" * 80)
                logger.info(f"SIGNAL DETECTED: {sig.reason}")
                logger.info(f"Direction: {sig.direction} | Entry: {sig.entry_price:.2f} | SL: {sig.sl:.2f}")
                tp1_str = f"{tp1_price:.2f}" if tp1_price is not None else "N/A"
                tp2_str = f"{tp2_price:.2f}" if tp2_price is not None else "N/A"
                logger.info(f"TP1: {tp1_str} | TP2: {tp2_str}")
                logger.info("=" * 80)
                
                logger.info("=" * 80)
                logger.info(f"POSITION OPENED: {sig.direction} {entry_lot} lot @ {entry_price_filled:.2f}")
                logger.info(f"TP1: {tp1_price:.2f} ({tp1_lot} lot) | TP2: {tp2_price:.2f} ({entry_lot - tp1_lot} lot)")
                logger.info(f"SL: {sig.sl:.2f}")
                logger.info("=" * 80)
                
                open_trades.append(
                    Trade(
                        direction=sig.direction,
                        entry_time=pd.to_datetime(row["time"]).isoformat(),
                        entry_price=entry_price_filled,  # Use filled price
                        sl=float(sig.sl),
                        tp=float(tp2_price if tp2_price is not None else sig.tp),  # giữ compat
                        lot=entry_lot,
                        
                        lot_open=entry_lot,
                        lot_tp1=tp1_lot,
                        tp1=tp1_price,
                        tp2=tp2_price,
                        
                        setup=setup_str,
                        reason=reason_str,
                    )
                )
            else:
                logger.info("No signal")

    # close end - close all remaining trades
    for tr in open_trades:
        last = df_m15.iloc[-1]
        exit_price_raw = float(last["close"])
        # Apply exit fill for consistency
        exit_price_filled = tm.apply_exit_fill(tr.direction, exit_price_raw)
        tr.exit_time = pd.to_datetime(last["time"]).isoformat()
        tr.exit_price = exit_price_filled
        tr.exit_reason = "EOD"
        if tr.pnl_usd is None:
            tr.pnl_usd = 0.0
        # Calculate final PnL for remaining lot (use filled price)
        final_pnl = tm.pnl_usd(tr.direction, tr.entry_price, exit_price_filled, tr.lot_open)
        tr.pnl_usd += final_pnl
        balance += final_pnl
        trades.append(tr)

    m = compute_metrics(initial_balance, trades)
    
    # Save trades with date range in filename
    start_date_str = df_m15["time"].min().strftime("%Y-%m-%d")
    end_date_str = df_m15["time"].max().strftime("%Y-%m-%d")
    output_file = f"reports/trades_vp_v1_{start_year}_{end_year}_{start_date_str}_{end_date_str}.csv"
    save_trades_csv(trades, output_file)
    
    logger.info("=" * 80)
    logger.info(f"📊 BACKTEST RESULTS ({start_year}-{end_year})")
    logger.info("=" * 80)
    logger.info(f"Data period: {start_date_str} to {end_date_str}")
    logger.info(f"Trades: {len(trades)} | Final: {m['final_balance']:.2f} | Return: {m['return_pct']:.2f}%")
    logger.info(f"MaxDD: {m['max_drawdown_usd']:.2f} | Winrate: {m['winrate_pct']:.2f}%")
    logger.info(f"Saved: {output_file}")
    
    # Thống kê theo năm
    logger.info("")
    logger.info("=" * 80)
    logger.info("📅 THỐNG KÊ THEO TỪNG NĂM")
    logger.info("=" * 80)
    
    # Phân loại trades theo năm (dựa vào entry_time)
    from datetime import datetime
    trades_by_year = {}
    for trade in trades:
        if trade.entry_time:
            try:
                entry_date = pd.to_datetime(trade.entry_time)
                year = entry_date.year
                if year not in trades_by_year:
                    trades_by_year[year] = []
                trades_by_year[year].append(trade)
            except:
                pass
    
    # Tính metrics cho mỗi năm
    year_metrics = []
    cumulative_balance = initial_balance
    
    for year in sorted(trades_by_year.keys()):
        year_trades = trades_by_year[year]
        year_start_balance = cumulative_balance
        year_metrics_dict = compute_metrics(year_start_balance, year_trades)
        cumulative_balance = year_metrics_dict['final_balance']
        
        year_metrics.append({
            'year': year,
            'trades': len(year_trades),
            'start_balance': year_start_balance,
            'final_balance': year_metrics_dict['final_balance'],
            'total_pnl': year_metrics_dict['total_pnl_usd'],
            'return_pct': year_metrics_dict['return_pct'],
            'max_dd': year_metrics_dict['max_drawdown_usd'],
            'winrate': year_metrics_dict['winrate_pct'],
            'wins': int(year_metrics_dict['wins']),
            'losses': int(year_metrics_dict['losses']),
        })
    
    # Hiển thị bảng
    logger.info(f"{'Năm':<6} {'Trades':<8} {'Start $':<10} {'Final $':<10} {'PnL $':<12} {'Return %':<10} {'MaxDD $':<10} {'Winrate %':<10} {'W/L':<8}")
    logger.info("-" * 100)
    
    for ym in year_metrics:
        wl_str = f"{ym['wins']}/{ym['losses']}"
        logger.info(
            f"{ym['year']:<6} "
            f"{ym['trades']:<8} "
            f"${ym['start_balance']:>8.2f} "
            f"${ym['final_balance']:>8.2f} "
            f"${ym['total_pnl']:>10.2f} "
            f"{ym['return_pct']:>8.2f}% "
            f"${ym['max_dd']:>8.2f} "
            f"{ym['winrate']:>8.2f}% "
            f"{wl_str:<8}"
        )
    
    logger.info("-" * 100)
    
    # Tổng kết
    total_trades_all = sum(ym['trades'] for ym in year_metrics)
    total_pnl_all = sum(ym['total_pnl'] for ym in year_metrics)
    avg_return = sum(ym['return_pct'] for ym in year_metrics) / len(year_metrics) if year_metrics else 0.0
    avg_winrate = sum(ym['winrate'] for ym in year_metrics) / len(year_metrics) if year_metrics else 0.0
    max_dd_all = max(ym['max_dd'] for ym in year_metrics) if year_metrics else 0.0
    
    logger.info(f"{'TỔNG':<6} {total_trades_all:<8} ${initial_balance:>8.2f} ${cumulative_balance:>8.2f} ${total_pnl_all:>10.2f} {avg_return:>8.2f}% ${max_dd_all:>8.2f} {avg_winrate:>8.2f}%")
    logger.info("=" * 100)
    
    # Năm tốt nhất và tệ nhất
    if year_metrics:
        best_year = max(year_metrics, key=lambda x: x['return_pct'])
        worst_year = min(year_metrics, key=lambda x: x['return_pct'])
        
        logger.info(f"🏆 Năm tốt nhất: {best_year['year']} - Return: {best_year['return_pct']:.2f}% | PnL: ${best_year['total_pnl']:.2f} | Trades: {best_year['trades']}")
        logger.info(f"📉 Năm tệ nhất: {worst_year['year']} - Return: {worst_year['return_pct']:.2f}% | PnL: ${worst_year['total_pnl']:.2f} | Trades: {worst_year['trades']}")
        logger.info("=" * 100)
    
    # Thống kê BUY vs SELL
    buy_trades = [t for t in trades if t.direction == "BUY"]
    sell_trades = [t for t in trades if t.direction == "SELL"]
    
    def calc_stats(trade_list, name):
        if len(trade_list) == 0:
            return {
                "count": 0,
                "total_pnl": 0.0,
                "win_count": 0,
                "loss_count": 0,
                "winrate": 0.0,
                "avg_pnl": 0.0,
                "max_win": 0.0,
                "max_loss": 0.0,
            }
        
        pnls = [t.pnl_usd if t.pnl_usd is not None else 0.0 for t in trade_list]
        total_pnl = sum(pnls)
        win_count = sum(1 for pnl in pnls if pnl > 0)
        loss_count = sum(1 for pnl in pnls if pnl < 0)
        winrate = (win_count / len(trade_list)) * 100.0 if len(trade_list) > 0 else 0.0
        avg_pnl = total_pnl / len(trade_list) if len(trade_list) > 0 else 0.0
        max_win = max(pnls) if pnls else 0.0
        max_loss = min(pnls) if pnls else 0.0
        
        return {
            "count": len(trade_list),
            "total_pnl": total_pnl,
            "win_count": win_count,
            "loss_count": loss_count,
            "winrate": winrate,
            "avg_pnl": avg_pnl,
            "max_win": max_win,
            "max_loss": max_loss,
        }
    
    buy_stats = calc_stats(buy_trades, "BUY")
    sell_stats = calc_stats(sell_trades, "SELL")
    
    logger.info("=" * 80)
    logger.info("📊 THỐNG KÊ BUY vs SELL")
    logger.info("=" * 80)
    logger.info(f"BUY:  {buy_stats['count']:4d} lệnh | PnL: ${buy_stats['total_pnl']:10.2f} | Winrate: {buy_stats['winrate']:5.2f}% | Win: {buy_stats['win_count']:3d} | Loss: {buy_stats['loss_count']:3d}")
    logger.info(f"      Avg PnL: ${buy_stats['avg_pnl']:8.2f} | Max Win: ${buy_stats['max_win']:8.2f} | Max Loss: ${buy_stats['max_loss']:8.2f}")
    logger.info(f"SELL: {sell_stats['count']:4d} lệnh | PnL: ${sell_stats['total_pnl']:10.2f} | Winrate: {sell_stats['winrate']:5.2f}% | Win: {sell_stats['win_count']:3d} | Loss: {sell_stats['loss_count']:3d}")
    logger.info(f"      Avg PnL: ${sell_stats['avg_pnl']:8.2f} | Max Win: ${sell_stats['max_win']:8.2f} | Max Loss: ${sell_stats['max_loss']:8.2f}")
    logger.info("-" * 80)
    
    if buy_stats['total_pnl'] > sell_stats['total_pnl']:
        diff = buy_stats['total_pnl'] - sell_stats['total_pnl']
        logger.info(f"✅ BUY lãi nhiều hơn SELL: ${diff:.2f} (BUY: ${buy_stats['total_pnl']:.2f} vs SELL: ${sell_stats['total_pnl']:.2f})")
    elif sell_stats['total_pnl'] > buy_stats['total_pnl']:
        diff = sell_stats['total_pnl'] - buy_stats['total_pnl']
        logger.info(f"✅ SELL lãi nhiều hơn BUY: ${diff:.2f} (SELL: ${sell_stats['total_pnl']:.2f} vs BUY: ${buy_stats['total_pnl']:.2f})")
    else:
        logger.info(f"⚖️  BUY và SELL lãi bằng nhau: ${buy_stats['total_pnl']:.2f}")
    
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

