import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI using EMA smoothing.
    Input: close series
    Output: RSI 0..100 aligned with close.index
    """
    close = close.astype(float)
    delta = close.diff()

    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-12)
    return 100 - (100 / (1 + rs))
