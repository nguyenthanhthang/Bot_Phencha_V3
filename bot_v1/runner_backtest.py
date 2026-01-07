import pandas as pd

from utils.config_loader import load_yaml
from utils.logger import setup_logger
from indicators import atr, rsi, bollinger
from utils.time_utils import to_vn_time
from backtest.engine import run_backtest_m15
from backtest.metrics import compute_metrics
from reporting.trade_logger import save_trades_csv


def main():
    cfg = load_yaml("config/backtest.yaml")
    symbols = load_yaml("config/symbols.yaml")
    logger = setup_logger("BOT_XAUUSD_BACKTEST", level="INFO")

    path_m15 = "data_cache/XAUUSDm_M15_2025-01-01_2026-01-01.csv"
    df = pd.read_csv(path_m15, parse_dates=["time"])
    logger.info(f"Loaded M15: {path_m15} | rows={len(df)}")

    # add VN time
    df["time_vn"] = to_vn_time(df["time"])

    # indicators
    df["atr"] = atr(df, 14)
    df["rsi"] = rsi(df["close"], 14)
    bb_mid, bb_up, bb_low = bollinger(df["close"], 20, 2.0)
    df["bb_mid"] = bb_mid
    df["bb_up"] = bb_up
    df["bb_low"] = bb_low

    # drop warmup NaN
    df = df.dropna().reset_index(drop=True)

    symbol_specs = symbols["XAUUSD"] if "XAUUSD" in symbols else {"contract_size": 100, "min_lot": 0.01, "lot_step": 0.01}

    trades = run_backtest_m15(df, cfg, symbol_specs)
    logger.info(f"Trades: {len(trades)}")

    initial_balance = float(cfg["account"]["initial_balance"])
    m = compute_metrics(initial_balance, trades)

    save_trades_csv(trades, "reports/trades_v1_2025_m15.csv")

    logger.info(f"Final balance: {m['final_balance']:.2f} | Return: {m['return_pct']:.2f}%")
    logger.info(f"Max DD: {m['max_drawdown_usd']:.2f} | Winrate: {m['winrate_pct']:.2f}%")
    logger.info("Saved trades: reports/trades_v1_2025_m15.csv")


if __name__ == "__main__":
    main()
