import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

import pandas as pd
from indicators import atr, rsi, bollinger, sma, ema
from utils.logger import setup_logger


def main():
    logger = setup_logger("BOT_XAUUSD_INDICATORS_TEST", level="INFO")

    path_m15 = "data_cache/XAUUSDm_M15_2025-01-01_2026-01-01.csv"
    df = pd.read_csv(path_m15, parse_dates=["time"])
    logger.info(f"Loaded: {path_m15} | rows={len(df)}")

    df["atr14"] = atr(df, 14)
    df["rsi14"] = rsi(df["close"], 14)
    mid, up, low = bollinger(df["close"], 20, 2.0)
    df["bb_mid"] = mid
    df["bb_up"] = up
    df["bb_low"] = low
    df["sma20"] = sma(df["close"], 20)
    df["ema20"] = ema(df["close"], 20)

    # Check NaN lengths
    nan_counts = df[["atr14", "rsi14", "bb_mid", "bb_up", "bb_low", "sma20", "ema20"]].isna().sum()
    logger.info(f"NaN counts:\n{nan_counts}")

    # Alignment sanity
    assert len(df["atr14"]) == len(df)
    assert df["atr14"].index.equals(df.index)

    # Drop warmup and show last rows
    df2 = df.dropna().reset_index(drop=True)
    logger.info(f"After dropna: rows={len(df2)}")
    logger.info("Last 3 rows sample:")
    logger.info(df2.tail(3).to_string(index=False))

    logger.info("Indicators test OK ✅")


if __name__ == "__main__":
    main()

