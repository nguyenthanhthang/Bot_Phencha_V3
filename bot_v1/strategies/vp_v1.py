from dataclasses import dataclass
from typing import Optional
import logging

import pandas as pd

from risk.position_sizing import calc_lot_by_risk
from volume_profile.cache import SessionProfileCache, ProfilePack
from utils.time_utils import in_time_range

# Use root logger or ensure it's configured
logger = logging.getLogger("strategies.vp_v1")
# If no handlers, add a null handler to prevent errors
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)


@dataclass
class Signal:
    direction: str
    entry_price: float
    sl: float
    tp: float
    lot: float
    reason: str
    tp1: Optional[float] = None  # TP1 (POC/midVA)
    tp2: Optional[float] = None  # TP2 (VA edge/HVN)


def price_in_zone(price: float, low: float, high: float) -> bool:
    return low <= price <= high


class VPStrategyV1:
    def __init__(self, cfg_all: dict, symbol_specs: dict, vp_cache: SessionProfileCache):
        self.cfg = cfg_all
        self.symbol_specs = symbol_specs
        self.vp_cache = vp_cache

        self.contract_size = float(symbol_specs.get("contract_size", 100.0))
        self.min_lot = float(symbol_specs.get("min_lot", 0.01))
        self.lot_step = float(symbol_specs.get("lot_step", 0.01))
        self.risk_pct = float(cfg_all["risk"]["risk_per_trade_pct"])

        self.rules = cfg_all["rules"]
        self.sessions = cfg_all["sessions"]

        self.cur_day = None
        self.asia_traded = False   # không còn dùng để giới hạn 1 lệnh/ngày, giữ lại cho compat
        self.london_traded = False
        self.us_traded = False
        
        # London mode config
        london_cfg = cfg_all.get("london_mode", {})
        self.london_enabled = london_cfg.get("enabled", True)
        
        # US mode config (giống London)
        us_cfg = cfg_all.get("us_mode", {})
        self.us_enabled = us_cfg.get("enabled", True)
        
        # Track setups for second entry
        self.asia_first_entry_price = None
        self.asia_first_entry_idx = None
        self.asia_setup_a_triggered = False

    def on_new_day(self, day):
        self.cur_day = day
        self.asia_traded = False   # reset nhưng không còn dùng để chặn entry Asia
        self.london_traded = False
        self.us_traded = False
        self.asia_first_entry_price = None
        self.asia_first_entry_idx = None
        self.asia_setup_a_triggered = False

    def _asia_reaction_buy(self, i: int, df: pd.DataFrame, balance: float, pack: ProfilePack) -> Optional[Signal]:
        if self.asia_traded:
            return None

        row = df.iloc[i]
        t_vn = row["time_vn"]
        close = float(row["close"])
        low = float(row["low"])
        atr = float(row["atr"])

        # ưu tiên vùng dày dưới: VAL hoặc HVN thấp nhất
        target_low = pack.val
        target_high = pack.val + float(self.cfg["vp"]["bin_size"]) * 2  # vùng quanh VAL

        # nếu không có VAL (nan) thì dùng HVN cuối
        if target_low != target_low:  # nan check
            if pack.hvn:
                z = sorted(pack.hvn, key=lambda x: x.low)[0]
                target_low, target_high = z.low, z.high
            else:
                return None

        if not price_in_zone(low, target_low, target_high) and not price_in_zone(close, target_low, target_high):
            return None

        # retest logic: trong lookback có >= min_retests lần low chạm zone
        lookback = int(self.rules["asia_retest_lookback_m15"])
        min_retests = int(self.rules["asia_min_retests"])
        start = max(0, i - lookback)
        lows = df.iloc[start:i+1]["low"].astype(float)

        touches = ((lows >= target_low) & (lows <= target_high)).sum()
        if touches < min_retests:
            return None

        # volume spike filter (M15 tick volume) so với quantile của session
        q = float(self.rules["vol_spike_quantile"])
        sess_mask = df["time_vn"].dt.date == t_vn.date()
        sess_vol = df.loc[sess_mask, "volume"].astype(float)
        thresh = float(sess_vol.quantile(q))
        if float(row["volume"]) < thresh:
            return None

        # Rejection candle đơn giản: close > open và wick dưới tương đối (optional)
        # V1 tối giản: close >= open
        if float(row["close"]) < float(row["open"]):
            return None

        sl_dist = float(self.rules["sl_atr_mult_reaction"]) * atr
        tp_dist = float(self.rules["tp_atr_mult_reaction"]) * atr

        entry = close
        sl = entry - sl_dist
        tp = entry + tp_dist

        lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)

        self.asia_traded = True
        self.asia_setup_a_triggered = True
        self.asia_first_entry_price = entry
        self.asia_first_entry_idx = i
        return Signal("BUY", entry, sl, tp, lot, "VP_ASIA_HVN_VAL_REACTION_BUY")

    def _london_gap_sell(self, i: int, df: pd.DataFrame, balance: float, pack: ProfilePack) -> Optional[Signal]:
        if self.london_traded:
            return None

        row = df.iloc[i]
        atr = float(row["atr"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        # định nghĩa "edge breakdown" = VAL (hoặc HVN thấp) như biên hút thanh khoản
        edge = pack.val
        if edge != edge:
            return None

        buffer = float(self.rules["gap_buffer_atr"]) * atr

        # Break & Retest: candle trước đóng dưới edge, candle này hồi test edge+buffer rồi quay xuống
        if i < 2:
            return None

        prev = df.iloc[i-1]
        prev_close = float(prev["close"])

        broke = prev_close < (edge - buffer)
        retest = high >= (edge + buffer)
        accept_down = close < edge  # đóng dưới

        if broke and retest and accept_down:
            entry = min(edge, close)  # conservative
            sl_dist = float(self.rules["sl_atr_mult_gap"]) * atr
            tp_dist = float(self.rules["tp_atr_mult_gap"]) * atr

            sl = entry + sl_dist
            tp = entry - tp_dist

            lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
            self.london_traded = True
            return Signal("SELL", entry, sl, tp, lot, "VP_LONDON_LVN_GAP_SELL")

        return None

    def _asia_second_entry_buy(self, i: int, df: pd.DataFrame, balance: float, pack: ProfilePack) -> Optional[Signal]:
        """
        Setup B: Second Entry - mẹo buy tiếp sau khi đã có reaction đầu tiên
        Logic: Sau Setup A, nếu price pullback về zone lại thì vào tiếp
        """
        if not self.asia_setup_a_triggered or self.asia_first_entry_price is None:
            return None
        
        # Chỉ check asia_traded ở cuối, sau khi đã confirm signal

        row = df.iloc[i]
        t_vn = row["time_vn"]
        close = float(row["close"])
        low = float(row["low"])
        atr = float(row["atr"])

        # Xác định zone (giống Setup A)
        target_low = pack.val
        target_high = pack.val + float(self.cfg["vp"]["bin_size"]) * 2

        if target_low != target_low:
            if pack.hvn:
                z = sorted(pack.hvn, key=lambda x: x.low)[0]
                target_low, target_high = z.low, z.high
            else:
                return None

        # Price phải pullback về zone
        if not price_in_zone(low, target_low, target_high) and not price_in_zone(close, target_low, target_high):
            return None

        # Kiểm tra move từ entry đầu: phải có move lên đủ lớn rồi mới pullback
        move_from_first = close - self.asia_first_entry_price
        min_move = float(self.rules["second_entry_min_move_atr"]) * atr
        
        if move_from_first < min_move:
            return None

        # Pullback về ít nhất X% của move
        pullback_pct = float(self.rules["second_entry_pullback_pct"])
        max_pullback = move_from_first * pullback_pct
        current_pullback = close - self.asia_first_entry_price
        
        if current_pullback > -max_pullback:  # Chưa pullback đủ
            return None

        # Volume confirmation
        q = float(self.rules["vol_spike_quantile"])
        sess_mask = df["time_vn"].dt.date == t_vn.date()
        sess_vol = df.loc[sess_mask, "volume"].astype(float)
        thresh = float(sess_vol.quantile(q))
        if float(row["volume"]) < thresh * 0.7:  # Cho phép volume nhẹ hơn một chút
            return None

        # Bullish candle
        if float(row["close"]) < float(row["open"]):
            return None

        sl_dist = float(self.rules["sl_atr_mult_second_entry"]) * atr
        tp_dist = float(self.rules["tp_atr_mult_second_entry"]) * atr

        entry = close
        sl = entry - sl_dist
        tp = entry + tp_dist

        lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)

        # Không dùng asia_traded để giới hạn 1 lệnh/ngày nữa; backtest vẫn chỉ cho 1 lệnh mở tại 1 thời điểm
        return Signal("BUY", entry, sl, tp, lot, "VP_ASIA_SECOND_ENTRY_BUY")

    def _asia_is_balanced(self, df: pd.DataFrame, i: int) -> bool:
        """
        Check if Asia session is balanced (not trending strongly).
        London trap chỉ chạy khi Asia balanced để tránh trend day.
        """
        london_cfg = self.cfg.get("london_mode", {})
        if not london_cfg.get("asia_balanced_filter", True):
            return True
        
        max_range_atr = float(london_cfg.get("asia_balanced_max_range_atr", 4.0))
        
        # Lấy ATR hiện tại
        atr = float(df.iloc[i]["atr"])
        if atr <= 0:
            return False
        
        # Lấy high/low của Asia session trong ngày hiện tại
        t_vn = df.iloc[i]["time_vn"]
        day = t_vn.date()
        
        # Lọc candles Asia cùng ngày
        asia_start = self.sessions.get("asia", {}).get("start", "06:00")
        asia_end = self.sessions.get("asia", {}).get("end", "13:50")
        
        sub = df[df["time_vn"].dt.date == day].copy()
        sub_asia = sub[sub["time_vn"].apply(lambda x: in_time_range(x, asia_start, asia_end))]
        
        if len(sub_asia) < 10:
            logger.info(f"Asia balanced check: Not enough candles ({len(sub_asia)} < 10)")
            return False
        
        rng = float(sub_asia["high"].max() - sub_asia["low"].min())
        max_range = max_range_atr * atr
        is_balanced = rng <= max_range
        
        logger.info(f"Asia balanced check: Range={rng:.2f}, MaxRange={max_range:.2f} ({max_range_atr}*ATR), Balanced={is_balanced}")
        
        return is_balanced

    def _asia_va_reentry_trap(self, i: int, df: pd.DataFrame, balance: float, pack: ProfilePack) -> Optional[Signal]:
        """
        Setup D: VA Re-entry trap (gộp với Setup A - absorption confirmation)
        Logic: 
        - Early entry (absorption): Chạm VAL/VAH + volume spike + close giữ trong VA
        - Standard trap: Price breakout VA rồi quay lại test VA
        """
        row = df.iloc[i]
        t_vn = row["time_vn"]
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        atr = float(row["atr"])
        open_price = float(row["open"])

        val = pack.val
        vah = pack.vah
        poc = pack.poc

        if val != val or vah != vah:  # nan check
            return None

        # ===== ABSORPTION CONFIRM (gộp logic A) =====
        # Nếu chạm VAL/VAH + volume spike + close giữ trong VA => coi như re-entry sớm
        sess = df.loc[df["time_vn"].dt.date == t_vn.date(), "volume"].astype(float)
        q = float(self.rules.get("vol_spike_quantile", 0.75))
        vol_spike = float(row["volume"]) >= float(sess.quantile(q))

        if vol_spike and (val <= close <= vah):
            # BUY near VAL (absorption)
            if low <= val and close >= open_price:
                entry = close
                sl_dist = float(self.rules["sl_atr_mult_va_trap"]) * atr
                
                # TP1 = POC, TP2 = VAH (VA edge đối diện)
                tp1_price = poc if poc == poc else entry + (1.0 * atr)
                tp2_price = vah if vah == vah else entry + (1.8 * atr)
                
                sl = entry - sl_dist
                tp = tp2_price  # giữ compat

                lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
                self.asia_setup_a_triggered = True
                self.asia_first_entry_price = entry
                self.asia_first_entry_idx = i
                return Signal("BUY", entry, sl, tp, lot, "VP_ASIA_VA_REENTRY_ABSORB_BUY", tp1=tp1_price, tp2=tp2_price)

            # SELL near VAH (absorption)
            if high >= vah and close <= open_price:
                entry = close
                sl_dist = float(self.rules["sl_atr_mult_va_trap"]) * atr
                
                # TP1 = POC, TP2 = VAL (VA edge đối diện)
                tp1_price = poc if poc == poc else entry - (1.0 * atr)
                tp2_price = val if val == val else entry - (1.8 * atr)
                
                sl = entry + sl_dist
                tp = tp2_price  # giữ compat

                lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
                self.asia_setup_a_triggered = True
                self.asia_first_entry_price = entry
                self.asia_first_entry_idx = i
                return Signal("SELL", entry, sl, tp, lot, "VP_ASIA_VA_REENTRY_ABSORB_SELL", tp1=tp1_price, tp2=tp2_price)

        # ===== STANDARD TRAP (breakout-fail) =====
        if i < 5:  # Cần đủ history cho breakout detection
            return None

        buffer = float(self.rules["va_reentry_buffer_atr"]) * atr

        # Lookback để tìm breakout
        lookback = 10
        start = max(0, i - lookback)
        recent = df.iloc[start:i+1]

        # Tìm breakout lên trên VA
        breakout_up = False
        breakout_down = False
        
        for j in range(len(recent) - 1):
            prev_high = float(recent.iloc[j]["high"])
            if prev_high > (vah + buffer):
                breakout_up = True
                break
        
        for j in range(len(recent) - 1):
            prev_low = float(recent.iloc[j]["low"])
            if prev_low < (val - buffer):
                breakout_down = True
                break

        # SELL trap: breakout up rồi quay lại test VA từ trên
        if breakout_up and high >= (vah - buffer) and close < vah:
            entry = min(close, vah)
            sl_dist = float(self.rules["sl_atr_mult_va_trap"]) * atr
            
            # TP1 = POC, TP2 = VAL (VA edge đối diện)
            tp1_price = poc if poc == poc else entry - (1.0 * atr)
            tp2_price = val if val == val else entry - (1.8 * atr)

            sl = entry + sl_dist
            tp = tp2_price  # giữ compat

            lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
            self.asia_setup_a_triggered = True
            self.asia_first_entry_price = entry
            self.asia_first_entry_idx = i
            return Signal("SELL", entry, sl, tp, lot, "VP_ASIA_VA_REENTRY_TRAP_SELL", tp1=tp1_price, tp2=tp2_price)

        # BUY trap: breakout down rồi quay lại test VA từ dưới
        if breakout_down and low <= (val + buffer) and close > val:
            entry = max(close, val)
            sl_dist = float(self.rules["sl_atr_mult_va_trap"]) * atr
            
            # TP1 = POC, TP2 = VAH (VA edge đối diện)
            tp1_price = poc if poc == poc else entry + (1.0 * atr)
            tp2_price = vah if vah == vah else entry + (1.8 * atr)

            sl = entry - sl_dist
            tp = tp2_price  # giữ compat

            lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
            self.asia_setup_a_triggered = True
            self.asia_first_entry_price = entry
            self.asia_first_entry_idx = i
            return Signal("BUY", entry, sl, tp, lot, "VP_ASIA_VA_REENTRY_TRAP_BUY", tp1=tp1_price, tp2=tp2_price)

        return None

    def _london_va_reentry_trap(self, i: int, df: pd.DataFrame, balance: float, pack: ProfilePack) -> Optional[Signal]:
        """
        London Setup D - Trap only (không có absorption).
        Chỉ trade breakout-fail re-entry vào VA.
        Không giới hạn số lệnh/ngày (giống Asia).
        """
        
        london_cfg = self.cfg.get("london_mode", {})
        buffer_atr = float(london_cfg.get("london_reentry_buffer_atr", 0.15))
        sl_mult = float(london_cfg.get("london_sl_atr_mult", 1.0))
        
        row = df.iloc[i]
        atr = float(row["atr"])
        if atr <= 0:
            return None
        
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])

        val = pack.val
        vah = pack.vah
        poc = pack.poc

        if val != val or vah != vah:  # nan check
            return None
        
        # Cần đủ history cho breakout detection
        if i < 5:
            return None
        
        buffer = buffer_atr * atr
        
        # Lookback để tìm breakout
        lookback = 10
        start = max(0, i - lookback)
        recent = df.iloc[start:i+1]
        
        # Tìm breakout lên trên VA
        breakout_up = False
        breakout_down = False
        
        for j in range(len(recent) - 1):
            prev_high = float(recent.iloc[j]["high"])
            if prev_high > (vah + buffer):
                breakout_up = True
                break
        
        for j in range(len(recent) - 1):
            prev_low = float(recent.iloc[j]["low"])
            if prev_low < (val - buffer):
                breakout_down = True
                break

        lookback = 10
        start = max(0, i - lookback)
        recent = df.iloc[start:i+1]

        breakout_up = False
        breakout_down = False

        for j in range(len(recent) - 1):
            prev_high = float(recent.iloc[j]["high"])
            if prev_high > (vah + buffer):
                breakout_up = True
                break

        for j in range(len(recent) - 1):
            prev_low = float(recent.iloc[j]["low"])
            if prev_low < (val - buffer):
                breakout_down = True
                break

        # SELL trap: breakout up rồi quay lại test VA từ trên
        if breakout_up and high >= (vah - buffer) and close < vah:
            entry = min(close, vah)
            sl_dist = sl_mult * atr
            
            # TP1 = POC, TP2 = VAL (VA edge đối diện)
            tp1_price = poc if poc == poc else entry - (1.0 * atr)
            tp2_price = val if val == val else entry - (1.8 * atr)
            
            sl = entry + sl_dist
            tp = tp2_price
            
            lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
            return Signal("SELL", entry, sl, tp, lot, "VP_LONDON_VA_TRAP_SELL", tp1=tp1_price, tp2=tp2_price)
        
        # BUY trap: breakout down rồi quay lại test VA từ dưới
        if breakout_down and low <= (val + buffer) and close > val:
            entry = max(close, val)
            sl_dist = sl_mult * atr
            
            # TP1 = POC, TP2 = VAH (VA edge đối diện)
            tp1_price = poc if poc == poc else entry + (1.0 * atr)
            tp2_price = vah if vah == vah else entry + (1.8 * atr)
            
            sl = entry - sl_dist
            tp = tp2_price
            
            lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
            return Signal("BUY", entry, sl, tp, lot, "VP_LONDON_VA_TRAP_BUY", tp1=tp1_price, tp2=tp2_price)

        return None

    def _us_va_reentry_trap(self, i: int, df: pd.DataFrame, balance: float, pack: ProfilePack) -> Optional[Signal]:
        """
        US Setup D - Trap only (giống London logic).
        Chỉ trade breakout-fail re-entry vào VA.
        """
        
        us_cfg = self.cfg.get("us_mode", {})
        buffer_atr = float(us_cfg.get("us_reentry_buffer_atr", 0.15))
        sl_mult = float(us_cfg.get("us_sl_atr_mult", 1.0))
        
        row = df.iloc[i]
        atr = float(row["atr"])
        if atr <= 0:
            logger.debug("US trap: ATR <= 0")
            return None
        
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])

        val = pack.val
        vah = pack.vah
        poc = pack.poc

        if val != val or vah != vah:  # nan check
            logger.info(f"US trap: VP data invalid (VAL={val}, VAH={vah})")
            return None
        
        # Cần đủ history cho breakout detection
        if i < 5:
            logger.info(f"US trap: Not enough history (i={i} < 5, need at least 5 candles)")
            return None
        
        buffer = buffer_atr * atr
        
        # Lookback để tìm breakout
        lookback = 10
        start = max(0, i - lookback)
        recent = df.iloc[start:i+1]
        
        # Tìm breakout lên trên VA
        breakout_up = False
        breakout_down = False
        
        for j in range(len(recent) - 1):
            prev_high = float(recent.iloc[j]["high"])
            if prev_high > (vah + buffer):
                breakout_up = True
                break
        
        for j in range(len(recent) - 1):
            prev_low = float(recent.iloc[j]["low"])
            if prev_low < (val - buffer):
                breakout_down = True
                break

        logger.info(f"US trap: Price={close:.2f}, VAL={val:.2f}, VAH={vah:.2f}, POC={poc:.2f}, Breakout_up={breakout_up}, Breakout_down={breakout_down}, High={high:.2f}, Low={low:.2f}")

        # SELL trap: breakout up rồi quay lại test VA từ trên
        if breakout_up and high >= (vah - buffer) and close < vah:
            entry = min(close, vah)
            sl_dist = sl_mult * atr
            
            # TP1 = POC, TP2 = VAL (VA edge đối diện)
            tp1_price = poc if poc == poc else entry - (1.0 * atr)
            tp2_price = val if val == val else entry - (1.8 * atr)
            
            sl = entry + sl_dist
            tp = tp2_price
            
            lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
            return Signal("SELL", entry, sl, tp, lot, "VP_US_VA_TRAP_SELL", tp1=tp1_price, tp2=tp2_price)
        
        # BUY trap: breakout down rồi quay lại test VA từ dưới
        if breakout_down and low <= (val + buffer) and close > val:
            entry = max(close, val)
            sl_dist = sl_mult * atr
            
            # TP1 = POC, TP2 = VAH (VA edge đối diện)
            tp1_price = poc if poc == poc else entry + (1.0 * atr)
            tp2_price = vah if vah == vah else entry + (1.8 * atr)
            
            sl = entry - sl_dist
            tp = tp2_price
            
            lot = calc_lot_by_risk(balance, self.risk_pct, sl_dist, self.contract_size, self.min_lot, self.lot_step)
            return Signal("BUY", entry, sl, tp, lot, "VP_US_VA_TRAP_BUY", tp1=tp1_price, tp2=tp2_price)

        return None

    def get_signal(self, i: int, df: pd.DataFrame, balance: float) -> Optional[Signal]:
        row = df.iloc[i]
        t_vn = row["time_vn"]
        day = t_vn.date()
        hour_min = t_vn.strftime("%H:%M")

        if self.cur_day != day:
            self.on_new_day(day)

        logger.info(f"get_signal: i={i}, day={day}, time={hour_min}, asia_range={self.sessions['asia']['start']}-{self.sessions['asia']['end']}, london_range={self.sessions['london']['start']}-{self.sessions['london']['end']}, us_range={self.sessions['us']['start']}-{self.sessions['us']['end']}")

        # ASIA - Multiple setups
        if in_time_range(t_vn, self.sessions["asia"]["start"], self.sessions["asia"]["end"]):
            logger.info(f"Asia session check: time={hour_min} is in range")
            pack = self.vp_cache.get(day, "asia", self.sessions["asia"]["start"], self.sessions["asia"]["end"])
            
            # Setup D: VA Re-entry trap (gộp với Setup A - absorption confirmation)
            sig_d = self._asia_va_reentry_trap(i, df, balance, pack)
            if sig_d:
                return sig_d
            
            # Setup B: Second Entry (sau khi Setup A đã trigger - giữ lại để test)
            sig_b = self._asia_second_entry_buy(i, df, balance, pack)
            if sig_b:
                return sig_b

        # LONDON session: chỉ dùng Setup D - Trap only (không absorption)
        if in_time_range(t_vn, self.sessions["london"]["start"], self.sessions["london"]["end"]):
            logger.info(f"London session check: time={hour_min} is in range")
            if not self.london_enabled:
                logger.info("London session: disabled")
                return None
            
            # Filter: Asia phải balanced (không trend mạnh) mới trade London
            if not self._asia_is_balanced(df, i):
                logger.info("London session: Asia not balanced (filtered out)")
                return None
            
            pack_lon = self.vp_cache.get(day, "london", self.sessions["london"]["start"], self.sessions["london"]["end"])
            sig_lon = self._london_va_reentry_trap(i, df, balance, pack_lon)
            if sig_lon:
                return sig_lon

        # US session: chỉ dùng Setup D - Trap only (giống London logic)
        if in_time_range(t_vn, self.sessions["us"]["start"], self.sessions["us"]["end"]):
            logger.info(f"US session check: time={hour_min} is in range")
            if not self.us_enabled:
                logger.info("US session: disabled")
                return None
            
            # Filter: Asia phải balanced (không trend mạnh) mới trade US (giống London)
            asia_balanced = self._asia_is_balanced(df, i)
            if not asia_balanced:
                logger.info(f"US session: Asia not balanced (filtered out) - skipping US trade")
                return None
            
            pack_us = self.vp_cache.get(day, "us", self.sessions["us"]["start"], self.sessions["us"]["end"])
            sig_us = self._us_va_reentry_trap(i, df, balance, pack_us)
            if sig_us:
                return sig_us
            else:
                logger.info(f"US session: No trap signal (no breakout+reentry setup)")

        # Ngoài Asia/London/US: không trade
        return None

