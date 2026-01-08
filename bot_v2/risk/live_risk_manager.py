"""
Live Risk Manager
Manages daily risk limits and consecutive loss tracking for live trading
"""

from datetime import date
from typing import Optional


class LiveRiskManager:
    """Manages risk limits for live trading"""
    
    def __init__(
        self,
        max_daily_loss_pct: float = 0.0,  # Disabled
        max_trades_per_day: int = 999999,  # Disabled (set very high)
        max_consecutive_loss: int = 3,
    ):
        self.max_daily_loss_pct = max_daily_loss_pct  # Not used anymore
        self.max_trades_per_day = max_trades_per_day  # Not used anymore
        self.max_consecutive_loss = max_consecutive_loss
        
        # State variables
        self.consec_loss = 0
        self.day_blocked = False  # Only for consecutive loss blocking
        self.current_day: Optional[date] = None
    
    def reset_daily_state(self, current_day: date, day_start_balance: float = 0.0) -> None:
        """Reset all daily counters when new day starts"""
        self.current_day = current_day
        self.day_blocked = False
        self.consec_loss = 0
    
    def check_new_day(self, current_day: date, current_balance: float = 0.0) -> bool:
        """
        Check if it's a new day and reset if needed
        
        Returns:
            True if it's a new day (state was reset)
        """
        if self.current_day is None or current_day != self.current_day:
            self.reset_daily_state(current_day)
            return True
        return False
    
    def update_consecutive_loss(self, trade_pnl: float) -> None:
        """
        Update consecutive loss counter based on trade PnL
        
        Args:
            trade_pnl: Trade PnL (negative = loss, positive = win)
        """
        if trade_pnl < 0:
            self.consec_loss += 1
        else:
            self.consec_loss = 0
    
    def can_open_new_trade(self) -> tuple[bool, str]:
        """
        Check if new trade can be opened
        
        Returns:
            (can_open: bool, reason: str)
        """
        if self.day_blocked:  # Blocked by consecutive loss
            return False, "day_blocked"
        if self.consec_loss >= self.max_consecutive_loss:
            self.day_blocked = True
            return False, "max_consecutive_loss"
        return True, ""
    
    def record_new_trade(self) -> None:
        """Record that a new trade was opened (no-op, kept for compatibility)"""
        pass
    
    def get_status(self) -> dict:
        """Get current risk status"""
        return {
            "day_blocked": self.day_blocked,
            "consec_loss": self.consec_loss,
            "current_day": self.current_day,
        }

