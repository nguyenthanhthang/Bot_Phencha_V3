from __future__ import annotations

from pathlib import Path
import pandas as pd


def make_cache_path(
    cache_dir: str,
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
) -> Path:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{symbol}_{timeframe}_{start}_{end}.csv"
    return Path(cache_dir) / filename


def save_df_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)


def load_df_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["time"])
