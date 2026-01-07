import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

import pandas as pd

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
    logger = setup_logger("BOT_VP_BACKTEST", level="INFO")

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

    path_m1 = "data_cache/XAUUSDm_M1_2025-01-01_2026-01-01.csv"
    path_m15 = "data_cache/XAUUSDm_M15_2025-01-01_2026-01-01.csv"

    df_m1 = pd.read_csv(path_m1, parse_dates=["time"])
    df_m15 = pd.read_csv(path_m15, parse_dates=["time"])

    logger.info(f"M1 rows={len(df_m1)} | M15 rows={len(df_m15)}")

    df_m15["time_vn"] = to_vn_time(df_m15["time"])
    df_m15["atr"] = atr(df_m15, int(cfg_vp["rules"]["atr_period"]))
    df_m15 = df_m15.dropna().reset_index(drop=True)

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
        row = df_m15.iloc[i]
        t_vn = row["time_vn"]
        cur_day = t_vn.date()

        # Reset daily state when new day starts
        if current_day is None or cur_day != current_day:
            current_day = cur_day
            day_blocked = False
            consec_loss = 0  # Reset consecutive loss count each day
            logger.info(f"New day: {cur_day} | Balance: {balance:.2f}")

        # manage open trades (scale-out TP)
        still_open = []
        for tr in open_trades:
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

        # entry (only if no open trades)
        if len(open_trades) == 0:
            sig = strat.get_signal(i, df_m15, balance)
            if sig:
                # Extract setup from reason
                reason_str = sig.reason
                setup_str = ""
                if "REACTION" in reason_str or "HVN_VAL" in reason_str:
                    setup_str = "A"
                elif "SECOND_ENTRY" in reason_str or "SECOND" in reason_str:
                    setup_str = "B"
                elif "VA_REENTRY" in reason_str or "REENTRY_TRAP" in reason_str or "VA_TRAP" in reason_str or "ABSORB" in reason_str:
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
                    # FIXED_ATR
                    atr_val = float(row["atr"])
                    k = float(tm_cfg.get("tp1_atr", 1.0))
                    tp1_price = float(sig.entry_price) + (k * atr_val if sig.direction == "BUY" else -k * atr_val)
                
                # TP2 price: từ signal hoặc fallback
                tp2_price = float(sig.tp2) if sig.tp2 is not None else float(sig.tp)
                
                # Apply entry fill (spread + slippage)
                entry_price_filled = executor.apply_entry_fill(sig.direction, float(sig.entry_price))
                
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
    save_trades_csv(trades, "reports/trades_vp_v1_2025.csv")

    logger.info(f"Trades: {len(trades)} | Final: {m['final_balance']:.2f} | Return: {m['return_pct']:.2f}%")
    logger.info(f"MaxDD: {m['max_drawdown_usd']:.2f} | Winrate: {m['winrate_pct']:.2f}%")
    logger.info("Saved: reports/trades_vp_v1_2025.csv")


if __name__ == "__main__":
    main()

