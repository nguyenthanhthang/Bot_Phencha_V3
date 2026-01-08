import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ATR using EMA smoothing (common for trading bots).
    Requires columns: high, low, close
    Returns: pd.Series aligned with df.index
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_close = close.shift(1)

    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.ewm(alpha=1 / period, adjust=False).mean()
