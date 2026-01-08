import math
from typing import Optional


def price_hit_tp(direction: str, high: float, low: float, tp: float) -> bool:
    return (high >= tp) if direction == "BUY" else (low <= tp)


def price_hit_sl(direction: str, high: float, low: float, sl: float) -> bool:
    return (low <= sl) if direction == "BUY" else (high >= sl)


def round_step(x: float, step: float) -> float:
    return math.floor(x / step) * step


class TradeManager:
    def __init__(
        self,
        contract_size: float,
        spread_points: float = 30.0,
        slippage_points: float = 0.0,
        point_value: float = 0.01,
    ):
        self.contract_size = float(contract_size)
        self.spread_points = float(spread_points)
        self.slippage_points = float(slippage_points)
        self.point_value = float(point_value)
    
    def apply_entry_fill(self, direction: str, price: float) -> float:
        """Apply spread and slippage to entry price"""
        spread_cost = (self.spread_points / 2.0) * self.point_value
        slippage_cost = self.slippage_points * self.point_value
        
        if direction == "BUY":
            return price + spread_cost + slippage_cost
        else:
            return price - spread_cost - slippage_cost
    
    def apply_exit_fill(self, direction: str, price: float) -> float:
        """Apply spread and slippage to exit price (conservative)"""
        spread_cost = (self.spread_points / 2.0) * self.point_value
        slippage_cost = self.slippage_points * self.point_value
        
        if direction == "BUY":
            return price - spread_cost - slippage_cost
        else:
            return price + spread_cost + slippage_cost

    def pnl_usd(self, direction: str, entry: float, exitp: float, lot: float) -> float:
        # XAUUSD: pnl ~ (exit - entry) * contract_size * lot (tùy broker)
        diff = (exitp - entry) if direction == "BUY" else (entry - exitp)
        return diff * self.contract_size * lot

    def update_trade_on_bar(self, trade, bar, cfg_tm: dict):
        """
        bar: row with open/high/low/close/atr
        return: realized_pnl (float), closed_all (bool), reason (str|None)
        """
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        atr = float(bar.get("atr", 0.0))

        realized = 0.0

        # 1) Check SL first (conservative)
        if price_hit_sl(trade.direction, high, low, trade.sl):
            exit_price_filled = self.apply_exit_fill(trade.direction, trade.sl)
            realized += self.pnl_usd(trade.direction, trade.entry_price, exit_price_filled, trade.lot_open)
            trade.lot_open = 0.0
            return realized, True, "SL"

        # 2) TP1 partial close
        if (not trade.tp1_hit) and (trade.tp1 is not None) and price_hit_tp(trade.direction, high, low, trade.tp1):
            # chốt lot_tp1 tại tp1 (apply fill)
            tp1_filled = self.apply_exit_fill(trade.direction, trade.tp1)
            realized += self.pnl_usd(trade.direction, trade.entry_price, tp1_filled, trade.lot_tp1)

            trade.tp1_hit = True
            trade.lot_open = max(0.0, trade.lot_open - trade.lot_tp1)

            # kéo SL runner về BE+
            be_mode = cfg_tm.get("be_plus_mode", "ATR")
            if be_mode == "ATR":
                buf = float(cfg_tm.get("be_plus_atr", 0.1)) * atr
            else:
                buf = float(cfg_tm.get("be_plus_points", 0.0))  # points -> tùy bạn map sau, tạm dùng raw

            if trade.direction == "BUY":
                trade.sl = trade.entry_price + buf
            else:
                trade.sl = trade.entry_price - buf

            trade.sl_after_tp1 = trade.sl

            # nếu lot_open == 0 thì xong luôn
            if trade.lot_open <= 0:
                return realized, True, "TP1_FULL"
            # không đóng toàn bộ, tiếp tục runner
            return realized, False, "TP1_PARTIAL"

        # 3) TP2 close remaining
        if (trade.tp2 is not None) and price_hit_tp(trade.direction, high, low, trade.tp2):
            tp2_filled = self.apply_exit_fill(trade.direction, trade.tp2)
            realized += self.pnl_usd(trade.direction, trade.entry_price, tp2_filled, trade.lot_open)
            trade.lot_open = 0.0
            return realized, True, "TP2"

        return realized, False, None

