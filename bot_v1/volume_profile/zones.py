import pandas as pd
from dataclasses import dataclass


@dataclass
class Zone:
    zone_type: str   # "HVN" or "LVN"
    low: float
    high: float
    score: float     # tổng volume vùng


def _merge_bins_to_zones(bin_prices: list[float], vols: dict[float, float], bin_size: float, merge_gap_bins: int, zone_type: str):
    if not bin_prices:
        return []
    bin_prices = sorted(bin_prices)
    zones = []

    cur_low = bin_prices[0]
    cur_high = bin_prices[0]
    cur_score = vols.get(bin_prices[0], 0.0)

    for p in bin_prices[1:]:
        # nếu cách nhau <= merge_gap_bins * bin_size thì merge
        if p <= cur_high + (merge_gap_bins * bin_size):
            cur_high = p
            cur_score += vols.get(p, 0.0)
        else:
            zones.append(Zone(zone_type, cur_low, cur_high + bin_size, cur_score))
            cur_low = p
            cur_high = p
            cur_score = vols.get(p, 0.0)

    zones.append(Zone(zone_type, cur_low, cur_high + bin_size, cur_score))
    return zones


def extract_zones(
    prof: pd.DataFrame,
    bin_size: float,
    hvn_top_bins: int,
    lvn_bottom_bins: int,
    merge_gap_bins: int,
) -> tuple[list[Zone], list[Zone]]:
    """
    Returns (hvn_zones, lvn_zones)
    """
    if len(prof) == 0:
        return [], []

    prof = prof.copy()
    prof = prof.sort_values("vol", ascending=False).reset_index(drop=True)

    hvn_bins = prof.head(hvn_top_bins)["bin_price"].tolist()

    prof_low = prof.sort_values("vol", ascending=True).reset_index(drop=True)
    lvn_bins = prof_low.head(lvn_bottom_bins)["bin_price"].tolist()

    vols = {float(r["bin_price"]): float(r["vol"]) for _, r in prof.iterrows()}

    hvn_zones = _merge_bins_to_zones(hvn_bins, vols, bin_size, merge_gap_bins, "HVN")
    lvn_zones = _merge_bins_to_zones(lvn_bins, vols, bin_size, merge_gap_bins, "LVN")

    # ưu tiên zone score cao trước
    hvn_zones.sort(key=lambda z: z.score, reverse=True)
    lvn_zones.sort(key=lambda z: z.score, reverse=True)

    return hvn_zones, lvn_zones

