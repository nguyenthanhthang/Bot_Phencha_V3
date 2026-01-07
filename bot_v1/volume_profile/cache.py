import pandas as pd
from dataclasses import dataclass

from volume_profile.builder import build_profile, compute_poc, compute_value_area
from volume_profile.zones import extract_zones, Zone


@dataclass
class ProfilePack:
    poc: float
    val: float
    vah: float
    hvn: list[Zone]
    lvn: list[Zone]


class SessionProfileCache:
    def __init__(self, df_m1: pd.DataFrame, cfg_vp: dict):
        self.df_m1 = df_m1.copy()
        self.cfg = cfg_vp
        self._cache = {}

        # chuẩn hoá time
        self.df_m1["time"] = pd.to_datetime(self.df_m1["time"], utc=True)
        self.df_m1["time_vn"] = self.df_m1["time"].dt.tz_convert("Asia/Ho_Chi_Minh")

    def _slice_session(self, day, start_hhmm: str, end_hhmm: str) -> pd.DataFrame:
        x = self.df_m1[self.df_m1["time_vn"].dt.date == day]
        if len(x) == 0:
            return x
        hhmm = x["time_vn"].dt.strftime("%H:%M")
        return x[(hhmm >= start_hhmm) & (hhmm <= end_hhmm)]

    def get(self, day, session_name: str, start_hhmm: str, end_hhmm: str) -> ProfilePack:
        key = (day, session_name)
        if key in self._cache:
            return self._cache[key]

        df_sess = self._slice_session(day, start_hhmm, end_hhmm)

        bin_size = float(self.cfg["vp"]["bin_size"])
        va_pct = float(self.cfg["vp"]["value_area_pct"])
        hvn_top = int(self.cfg["vp"]["hvn_top_bins"])
        lvn_bottom = int(self.cfg["vp"]["lvn_bottom_bins"])
        merge_gap = int(self.cfg["vp"]["merge_gap_bins"])

        prof = build_profile(df_sess, bin_size)
        poc = compute_poc(prof)
        val, vah = compute_value_area(prof, va_pct)
        hvn, lvn = extract_zones(prof, bin_size, hvn_top, lvn_bottom, merge_gap)

        pack = ProfilePack(poc=poc, val=val, vah=vah, hvn=hvn, lvn=lvn)
        self._cache[key] = pack
        return pack

