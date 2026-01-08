import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

from datetime import datetime, timedelta
import argparse
import pandas as pd

from utils.logger import setup_logger
from data.mt5_fetcher import MT5Fetcher
from data.data_cache import make_cache_path, save_df_csv
from data.resample import resample_ohlc


def month_ranges(start_date: str, end_date: str):
    """
    Yield (start_dt, end_dt) month by month in [start, end)
    """
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    cur = datetime(start.year, start.month, 1)
    # align cur to start
    if cur < start:
        cur = start

    while cur < end:
        if cur.month == 12:
            nxt = datetime(cur.year + 1, 1, 1)
        else:
            nxt = datetime(cur.year, cur.month + 1, 1)

        chunk_start = cur
        chunk_end = min(nxt, end)
        yield chunk_start, chunk_end
        cur = nxt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSDm")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD (exclusive recommended)")
    parser.add_argument("--cache_dir", default="data_cache")
    parser.add_argument("--merge", action="store_true", help="Merge monthly M1 into one file")
    parser.add_argument("--save_m15", action="store_true", help="Also save merged M15 resampled from merged M1")
    args = parser.parse_args()

    logger = setup_logger("BOT_XAUUSD_MONTHLY", level="INFO")
    fetcher = MT5Fetcher()

    tf_m1 = None
    all_parts = []

    try:
        fetcher.connect()
        logger.info("Connected to MT5")
        tf_m1 = fetcher.tf_name_to_mt5("M1")

        for s_dt, e_dt in month_ranges(args.start, args.end):
            s = s_dt.strftime("%Y-%m-%d")
            e = e_dt.strftime("%Y-%m-%d")
            logger.info(f"Downloading {args.symbol} M1: {s} -> {e}")

            df = fetcher.fetch_rates_range(args.symbol, tf_m1, s_dt, e_dt)
            logger.info(f"  rows: {len(df)}")

            out = make_cache_path(args.cache_dir, args.symbol, "M1", s, e)
            save_df_csv(df, out)
            logger.info(f"  saved: {out}")

            if args.merge:
                all_parts.append(df)

    finally:
        fetcher.shutdown()
        logger.info("MT5 shutdown")

    if args.merge and all_parts:
        logger.info("Merging monthly files...")
        df_all = pd.concat(all_parts, ignore_index=True)
        df_all["time"] = pd.to_datetime(df_all["time"], utc=True)
        df_all = df_all.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)

        out_merged_m1 = make_cache_path(args.cache_dir, args.symbol, "M1", args.start, args.end)
        save_df_csv(df_all, out_merged_m1)
        logger.info(f"Merged M1 saved: {out_merged_m1} | rows={len(df_all)}")

        if args.save_m15:
            df_m15 = resample_ohlc(df_all, "15min")
            out_merged_m15 = make_cache_path(args.cache_dir, args.symbol, "M15", args.start, args.end)
            save_df_csv(df_m15, out_merged_m15)
            logger.info(f"Merged M15 saved: {out_merged_m15} | rows={len(df_m15)}")


if __name__ == "__main__":
    main()

