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
    
    def apply_entry_fill(self, direction: str, price: float, spread_points: Optional[float] = None) -> float:
        """Apply spread and slippage to entry price
        
        Args:
            direction: BUY or SELL
            price: Entry price
            spread_points: If provided, use this spread instead of self.spread_points
        """
        spread_pts = spread_points if spread_points is not None else self.spread_points
        spread_cost = (spread_pts / 2.0) * self.point_value
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

    def update_trade_on_tick(self, trade, tick_bid: float, tick_ask: float, atr: float, cfg_tm: dict):
        """
        Check TP1/TP2/SL based on tick bid/ask (for live trading).
        
        Rules:
        - BUY: TP hit based on bid (exit SELL side), SL hit based on bid
        - SELL: TP hit based on ask, SL hit based on ask
        
        Args:
            trade: Trade object
            tick_bid: Current bid price
            tick_ask: Current ask price
            atr: Current ATR value
            cfg_tm: Trade management config
            
        Returns:
            (realized_pnl, closed_all, reason)
        """
        realized = 0.0
        
        # Determine price to check based on direction
        # BUY: check bid (exit price), SELL: check ask (exit price)
        check_price = tick_bid if trade.direction == "BUY" else tick_ask
        
        # 1) Check SL first (conservative)
        if trade.direction == "BUY":
            if check_price <= trade.sl:
                # SL hit for BUY (bid <= SL)
                exit_price_filled = check_price  # Use bid directly (no fill model for live)
                realized += self.pnl_usd(trade.direction, trade.entry_price, exit_price_filled, trade.lot_open)
                trade.lot_open = 0.0
                return realized, True, "SL"
        else:  # SELL
            if check_price >= trade.sl:
                # SL hit for SELL (ask >= SL)
                exit_price_filled = check_price  # Use ask directly
                realized += self.pnl_usd(trade.direction, trade.entry_price, exit_price_filled, trade.lot_open)
                trade.lot_open = 0.0
                return realized, True, "SL"
        
        # 2) TP1 partial close
        if (not trade.tp1_hit) and (trade.tp1 is not None):
            tp1_hit = False
            if trade.direction == "BUY":
                if check_price >= trade.tp1:  # bid >= TP1
                    tp1_hit = True
            else:  # SELL
                if check_price <= trade.tp1:  # ask <= TP1
                    tp1_hit = True
            
            if tp1_hit:
                # Close TP1 partial
                tp1_filled = check_price  # Use current bid/ask
                realized += self.pnl_usd(trade.direction, trade.entry_price, tp1_filled, trade.lot_tp1)
                
                trade.tp1_hit = True
                trade.lot_open = max(0.0, trade.lot_open - trade.lot_tp1)
                
                # Move SL to BE+
                be_mode = cfg_tm.get("be_plus_mode", "ATR")
                if be_mode == "ATR":
                    buf = float(cfg_tm.get("be_plus_atr", 0.1)) * atr
                else:
                    buf = float(cfg_tm.get("be_plus_points", 0.0))
                
                if trade.direction == "BUY":
                    trade.sl = trade.entry_price + buf
                else:
                    trade.sl = trade.entry_price - buf
                
                trade.sl_after_tp1 = trade.sl
                
                # If all closed
                if trade.lot_open <= 0:
                    return realized, True, "TP1_FULL"
                
                # Partial close, continue runner
                return realized, False, "TP1_PARTIAL"
        
        # 3) TP2 close remaining
        if trade.tp2 is not None:
            tp2_hit = False
            if trade.direction == "BUY":
                if check_price >= trade.tp2:  # bid >= TP2
                    tp2_hit = True
            else:  # SELL
                if check_price <= trade.tp2:  # ask <= TP2
                    tp2_hit = True
            
            if tp2_hit:
                tp2_filled = check_price
                realized += self.pnl_usd(trade.direction, trade.entry_price, tp2_filled, trade.lot_open)
                trade.lot_open = 0.0
                return realized, True, "TP2"
        
        return realized, False, None