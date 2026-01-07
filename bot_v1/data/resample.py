from __future__ import annotations

import pandas as pd


def resample_ohlc(df_m1: pd.DataFrame, rule: str = "15min") -> pd.DataFrame:
    """
    Input: df with columns: time, open, high, low, close, volume
    time must be datetime.
    Output: resampled OHLCV.
    """
    df = df_m1.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time").sort_index()

    ohlc = df["close"].resample(rule).ohlc()
    ohlc["open"] = df["open"].resample(rule).first()
    ohlc["high"] = df["high"].resample(rule).max()
    ohlc["low"] = df["low"].resample(rule).min()
    ohlc["close"] = df["close"].resample(rule).last()
    ohlc["volume"] = df["volume"].resample(rule).sum()

    ohlc = ohlc.dropna().reset_index()
    return ohlc[["time", "open", "high", "low", "close", "volume"]]
