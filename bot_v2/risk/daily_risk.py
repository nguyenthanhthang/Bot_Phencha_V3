"""
Daily Risk Management Module
Tracks and enforces daily risk limits
"""

from datetime import datetime, date
from typing import Dict, Optional
from collections import defaultdict


class DailyRiskManager:
    """Manages daily risk limits"""
    
    def __init__(self, max_daily_loss: float = 0.05, 
                 max_daily_trades: int = 20,
                 max_concurrent_positions: int = 5):
        """
        Initialize daily risk manager
        
        Args:
            max_daily_loss: Maximum daily loss as percentage of balance
            max_daily_trades: Maximum number of trades per day
            max_concurrent_positions: Maximum concurrent positions
        """
        self.max_daily_loss = max_daily_loss
        self.max_daily_trades = max_daily_trades
        self.max_concurrent_positions = max_concurrent_positions
        
        # Daily tracking
        self.daily_stats: Dict[date, Dict] = defaultdict(lambda: {
            'trades': 0,
            'loss': 0.0,
            'starting_balance': 0.0,
            'current_balance': 0.0,
            'positions': 0
        })
    
    def get_today_stats(self) -> Dict:
        """Get today's statistics"""
        today = date.today()
        return self.daily_stats[today]
    
    def can_trade(self, current_balance: float) -> tuple[bool, str]:
        """
        Check if trading is allowed
        
        Args:
            current_balance: Current account balance
            
        Returns:
            Tuple of (can_trade: bool, reason: str)
        """
        today = date.today()
        stats = self.daily_stats[today]
        
        # Check if first trade of the day
        if stats['trades'] == 0:
            stats['starting_balance'] = current_balance
        
        stats['current_balance'] = current_balance
        
        # Check daily loss limit
        if stats['starting_balance'] > 0:
            daily_loss_pct = (stats['starting_balance'] - current_balance) / stats['starting_balance']
            if daily_loss_pct >= self.max_daily_loss:
                return False, f"Daily loss limit reached: {daily_loss_pct:.2%}"
        
        # Check trade count limit
        if stats['trades'] >= self.max_daily_trades:
            return False, f"Daily trade limit reached: {self.max_daily_trades}"
        
        # Check concurrent positions
        if stats['positions'] >= self.max_concurrent_positions:
            return False, f"Max concurrent positions reached: {self.max_concurrent_positions}"
        
        return True, "OK"
    
    def record_trade_open(self, current_balance: float) -> None:
        """Record a trade opening"""
        today = date.today()
        stats = self.daily_stats[today]
        stats['positions'] += 1
        stats['trades'] += 1
    
    def record_trade_close(self, pnl: float, current_balance: float) -> None:
        """
        Record a trade closing
        
        Args:
            pnl: Profit/Loss of the trade
            current_balance: Current account balance
        """
        today = date.today()
        stats = self.daily_stats[today]
        stats['positions'] = max(0, stats['positions'] - 1)
        stats['loss'] += pnl if pnl < 0 else 0
        stats['current_balance'] = current_balance
    
    def reset_daily_stats(self, target_date: Optional[date] = None) -> None:
        """
        Reset daily statistics
        
        Args:
            target_date: Date to reset (default: today)
        """
        if target_date is None:
            target_date = date.today()
        
        if target_date in self.daily_stats:
            del self.daily_stats[target_date]
    
    def get_daily_pnl(self) -> float:
        """Get today's P&L"""
        today = date.today()
        stats = self.daily_stats[today]
        
        if stats['starting_balance'] > 0:
            return stats['current_balance'] - stats['starting_balance']
        
        return 0.0
    
    def get_daily_loss_pct(self) -> float:
        """Get today's loss percentage"""
        today = date.today()
        stats = self.daily_stats[today]
        
        if stats['starting_balance'] > 0:
            return (stats['starting_balance'] - stats['current_balance']) / stats['starting_balance']
        
        return 0.0


