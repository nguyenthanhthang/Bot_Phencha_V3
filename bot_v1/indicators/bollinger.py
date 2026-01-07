import pandas as pd
from typing import Tuple


def bollinger(
    close: pd.Series,
    period: int = 20,
    std_mult: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands:
    mid = SMA(period)
    upper/lower = mid +/- std_mult * std
    """
    close = close.astype(float)
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    return mid, upper, lower
