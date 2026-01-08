import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))



from datetime import datetime
import argparse

from utils.logger import setup_logger
from data.mt5_fetcher import MT5Fetcher
from data.data_cache import make_cache_path, save_df_csv
from data.resample import resample_ohlc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--cache_dir", default="data_cache")
    parser.add_argument("--save_m15", action="store_true", help="Also save M15 resampled from M1")
    args = parser.parse_args()

    logger = setup_logger("BOT_XAUUSD_DATA", level="INFO")
    fetcher = MT5Fetcher()

    start_dt = datetime.fromisoformat(args.start)
    end_dt = datetime.fromisoformat(args.end)

    try:
        fetcher.connect()
        logger.info("Connected to MT5")

        tf_m1 = fetcher.tf_name_to_mt5("M1")
        df_m1 = fetcher.fetch_rates_range(args.symbol, tf_m1, start_dt, end_dt)

        logger.info(f"Fetched rows M1: {len(df_m1)}")

        out_m1 = make_cache_path(args.cache_dir, args.symbol, "M1", args.start, args.end)
        save_df_csv(df_m1, out_m1)
        logger.info(f"Saved: {out_m1}")

        if args.save_m15:
            df_m15 = resample_ohlc(df_m1, "15min")
            out_m15 = make_cache_path(args.cache_dir, args.symbol, "M15", args.start, args.end)
            save_df_csv(df_m15, out_m15)
            logger.info(f"Saved: {out_m15} (resampled)")

    finally:
        fetcher.shutdown()
        logger.info("MT5 shutdown")


if __name__ == "__main__":
    main()

