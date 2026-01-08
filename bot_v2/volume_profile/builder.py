import pandas as pd
import numpy as np


def price_to_bin(price: float, bin_size: float) -> float:
    # bin center (or bin floor); V1 dùng floor cho ổn định
    return np.floor(price / bin_size) * bin_size


def build_profile(df_m1: pd.DataFrame, bin_size: float) -> pd.DataFrame:
    """
    Input df_m1: columns time, close, volume (tick volume)
    Output: DataFrame bins with columns: bin_price, vol
    """
    x = df_m1.copy()
    x["close"] = x["close"].astype(float)
    x["volume"] = x["volume"].astype(float)

    x["bin"] = x["close"].apply(lambda p: price_to_bin(p, bin_size))
    prof = x.groupby("bin", as_index=False)["volume"].sum().rename(columns={"bin": "bin_price", "volume": "vol"})
    prof = prof.sort_values("bin_price").reset_index(drop=True)
    return prof


def compute_poc(prof: pd.DataFrame) -> float:
    if len(prof) == 0:
        return float("nan")
    i = prof["vol"].idxmax()
    return float(prof.loc[i, "bin_price"])


def compute_value_area(prof: pd.DataFrame, value_area_pct: float) -> tuple[float, float]:
    """
    Value Area around POC by expanding to neighboring bins by volume until reaching pct of total.
    Returns (VAL, VAH)
    """
    if len(prof) == 0:
        return float("nan"), float("nan")

    prof = prof.copy().reset_index(drop=True)
    total = prof["vol"].sum()
    target = total * value_area_pct

    poc_idx = int(prof["vol"].idxmax())
    included = set([poc_idx])
    acc = prof.loc[poc_idx, "vol"]

    left = poc_idx - 1
    right = poc_idx + 1

    while acc < target and (left >= 0 or right < len(prof)):
        left_vol = prof.loc[left, "vol"] if left >= 0 else -1
        right_vol = prof.loc[right, "vol"] if right < len(prof) else -1

        if right_vol >= left_vol:
            if right < len(prof):
                included.add(right)
                acc += right_vol
                right += 1
            else:
                included.add(left)
                acc += left_vol
                left -= 1
        else:
            if left >= 0:
                included.add(left)
                acc += left_vol
                left -= 1
            else:
                included.add(right)
                acc += right_vol
                right += 1

    bins = prof.loc[sorted(included), "bin_price"]
    return float(bins.min()), float(bins.max())

