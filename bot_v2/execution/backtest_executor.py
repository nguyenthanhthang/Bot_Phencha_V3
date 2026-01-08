from dataclasses import dataclass
from typing import Optional


@dataclass
class Trade:
    direction: str          # "BUY" or "SELL"
    entry_time: str
    entry_price: float
    sl: float
    tp: float              # giữ lại cho compatibility (tp2 hoặc tp legacy)
    lot: float

    # ---- add for scale-out ----
    lot_open: float = 0.0
    lot_tp1: float = 0.0
    tp1: Optional[float] = None
    tp1_hit: bool = False
    sl_after_tp1: Optional[float] = None
    tp2: Optional[float] = None

    # reporting
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_usd: Optional[float] = None

    setup: str = ""
    reason: str = ""


class BacktestExecutor:
    """
    Candle-based simulation:
    - If candle touches SL/TP (via high/low) => close trade.
    - For simplicity: assume SL hits first if both hit in same candle (conservative).
    - Supports spread and slippage for stress testing.
    """
    def __init__(
        self,
        contract_size: float = 100.0,
        spread_points: float = 30.0,
        slippage_points: float = 0.0,
        point_value: float = 0.01,  # XAUUSD: 0.01 per point
    ):
        self.contract_size = contract_size
        self.spread_points = float(spread_points)
        self.slippage_points = float(slippage_points)
        self.point_value = float(point_value)
    
    def apply_entry_fill(self, direction: str, price: float) -> float:
        """
        Apply spread and slippage to entry price
        
        Args:
            direction: "BUY" or "SELL"
            price: Base price (close price)
            
        Returns:
            Filled entry price
        """
        spread_cost = (self.spread_points / 2.0) * self.point_value
        slippage_cost = self.slippage_points * self.point_value
        
        if direction == "BUY":
            # BUY: pay ask = close + spread/2 + slippage
            return price + spread_cost + slippage_cost
        else:
            # SELL: get bid = close - spread/2 - slippage
            return price - spread_cost - slippage_cost
    
    def apply_exit_fill(self, direction: str, price: float) -> float:
        """
        Apply spread and slippage to exit price (conservative: worse for trader)
        
        Args:
            direction: "BUY" or "SELL"
            price: Base price (SL/TP)
            
        Returns:
            Filled exit price
        """
        spread_cost = (self.spread_points / 2.0) * self.point_value
        slippage_cost = self.slippage_points * self.point_value
        
        if direction == "BUY":
            # BUY close: sell at bid = price - spread/2 - slippage
            return price - spread_cost - slippage_cost
        else:
            # SELL close: buy at ask = price + spread/2 + slippage
            return price + spread_cost + slippage_cost

    def check_exit(self, trade: Trade, candle) -> Optional[tuple[float, str]]:
        """
        candle: dict-like with keys: high, low
        return (exit_price, reason) or None
        """
        high = float(candle["high"])
        low = float(candle["low"])

        if trade.direction == "BUY":
            sl_hit = low <= trade.sl
            tp_hit = high >= trade.tp
            if sl_hit and tp_hit:
                return trade.sl, "SL"  # conservative
            if sl_hit:
                return trade.sl, "SL"
            if tp_hit:
                return trade.tp, "TP"

        if trade.direction == "SELL":
            sl_hit = high >= trade.sl
            tp_hit = low <= trade.tp
            if sl_hit and tp_hit:
                return trade.sl, "SL"
            if sl_hit:
                return trade.sl, "SL"
            if tp_hit:
                return trade.tp, "TP"

        return None

    def calc_pnl_usd(self, trade: Trade, exit_price: float) -> float:
        # XAUUSD: pnl = (exit - entry) * lot * contract_size (BUY), reversed for SELL
        if trade.direction == "BUY":
            return (exit_price - trade.entry_price) * trade.lot * self.contract_size
        else:
            return (trade.entry_price - exit_price) * trade.lot * self.contract_size
