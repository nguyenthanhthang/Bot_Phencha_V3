import pandas as pd


def sma(close: pd.Series, period: int = 20) -> pd.Series:
    close = close.astype(float)
    return close.rolling(period).mean()


def ema(close: pd.Series, period: int = 20) -> pd.Series:
    close = close.astype(float)
    return close.ewm(span=period, adjust=False).mean()

