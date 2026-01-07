from dataclasses import dataclass
from typing import Optional

import pandas as pd

from utils.time_utils import in_time_range
from risk.position_sizing import calc_lot_by_risk


@dataclass
class Signal:
    direction: str  # "BUY" / "SELL"
    entry_price: float
    sl: float
    tp: float
    lot: float
    reason: str


class SessionStrategyV1:
    """
    V1:
    - Asia (06:00-11:00): Mean Reversion (BB + RSI)
    - London (14:00-17:30): ORB breakout (range 13:00-14:00)
    """

    def __init__(self, cfg: dict, symbol_specs: dict):
        self.cfg = cfg
        self.symbol_specs = symbol_specs

        self.risk_pct = float(cfg["risk"]["risk_per_trade_pct"])
        self.contract_size = float(symbol_specs.get("contract_size", 100.0))
        self.min_lot = float(symbol_specs.get("min_lot", 0.01))
        self.lot_step = float(symbol_specs.get("lot_step", 0.01))

        self.asia = cfg["sessions"]["asia"]
        self.london = cfg["sessions"]["london"]

        # ORB state (reset mỗi ngày)
        self.cur_day = None
        self.range_high = None
        self.range_low = None
        self.range_ready = False
        self.orb_traded = False

    def on_new_day(self, day):
        self.cur_day = day
        self.range_high = None
        self.range_low = None
        self.range_ready = False
        self.orb_traded = False

    def update_orb_range(self, t_vn, high, low):
        # build range 13:00-14:00
        if in_time_range(t_vn, "13:00", "14:00"):
            self.range_high = high if self.range_high is None else max(self.range_high, high)
            self.range_low = low if self.range_low is None else min(self.range_low, low)
        # after 14:00, mark ready if we collected something
        if t_vn.strftime("%H:%M") >= "14:00" and self.range_high is not None and self.range_low is not None:
            self.range_ready = True

    def get_signal(
        self,
        i: int,
        df: pd.DataFrame,
        balance: float,
    ) -> Optional[Signal]:
        row = df.iloc[i]
        t_vn = row["time_vn"]
        day = t_vn.date()

        if self.cur_day != day:
            self.on_new_day(day)

        # update ORB range always
        self.update_orb_range(t_vn, float(row["high"]), float(row["low"]))

        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        atr = float(row["atr"])
        rsi = float(row["rsi"])
        bb_mid = float(row["bb_mid"])
        bb_up = float(row["bb_up"])
        bb_low = float(row["bb_low"])

        # ===== Asia Mean Reversion =====
        if in_time_range(t_vn, self.asia["start"], self.asia["end"]):
            # buy
            if close <= bb_low and rsi < 30:
                sl_dist = 1.2 * atr
                sl = close - sl_dist
                tp = close + 1.0 * atr  # tp nhanh
                lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
                return Signal("BUY", close, sl, tp, lot, "ASIA_MR_BUY")

            # sell
            if close >= bb_up and rsi > 70:
                sl_dist = 1.2 * atr
                sl = close + sl_dist
                tp = close - 1.0 * atr
                lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
                return Signal("SELL", close, sl, tp, lot, "ASIA_MR_SELL")

        # ===== London ORB Breakout =====
        if in_time_range(t_vn, self.london["start"], self.london["end"]):
            if self.range_ready and not self.orb_traded:
                buffer = 0.1 * atr
                buy_trigger = self.range_high + buffer
                sell_trigger = self.range_low - buffer

                # breakout up -> enter at trigger
                if high >= buy_trigger:
                    entry = buy_trigger
                    sl_dist = 1.0 * atr
                    sl = entry - sl_dist
                    tp = entry + 1.8 * atr
                    lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
                    self.orb_traded = True
                    return Signal("BUY", entry, sl, tp, lot, "LONDON_ORB_BUY")

                # breakout down -> enter at trigger
                if low <= sell_trigger:
                    entry = sell_trigger
                    sl_dist = 1.0 * atr
                    sl = entry + sl_dist
                    tp = entry - 1.8 * atr
                    lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
                    self.orb_traded = True
                    return Signal("SELL", entry, sl, tp, lot, "LONDON_ORB_SELL")

        return None

