"""
London Session Opening Range Breakout (ORB) Strategy
"""

import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime, time


class LondonORB:
    """Opening Range Breakout strategy for London session"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize strategy
        
        Args:
            config: Strategy configuration dict
        """
        self.config = config or {}
        self.name = "London ORB"
        
        # Default parameters
        self.session_start = time(8, 0)   # 08:00 London time
        self.orb_start = time(8, 0)        # ORB start
        self.orb_end = time(10, 0)         # ORB end (2-hour range)
        self.breakout_threshold = self.config.get('breakout_threshold', 0.0002)
    
    def is_orb_period(self, current_time: datetime) -> bool:
        """
        Check if current time is within ORB period
        
        Args:
            current_time: Current datetime
            
        Returns:
            True if in ORB period
        """
        current_time_only = current_time.time()
        return self.orb_start <= current_time_only <= self.orb_end
    
    def is_trading_period(self, current_time: datetime) -> bool:
        """
        Check if current time is within trading period
        
        Args:
            current_time: Current datetime
            
        Returns:
            True if in trading period
        """
        current_time_only = current_time.time()
        return current_time_only >= self.orb_end
    
    def calculate_orb(self, df: pd.DataFrame, 
                     orb_start: datetime, orb_end: datetime) -> Dict:
        """
        Calculate Opening Range (high and low)
        
        Args:
            df: OHLCV DataFrame
            orb_start: ORB start datetime
            orb_end: ORB end datetime
            
        Returns:
            Dict with 'high' and 'low' of ORB
        """
        orb_data = df[(df.index >= orb_start) & (df.index <= orb_end)]
        
        if orb_data.empty:
            return {'high': None, 'low': None}
        
        return {
            'high': orb_data['high'].max(),
            'low': orb_data['low'].min()
        }
    
    def calculate_signals(self, df: pd.DataFrame, 
                         indicators: Dict) -> pd.DataFrame:
        """
        Calculate trading signals
        
        Args:
            df: OHLCV DataFrame
            indicators: Dict of calculated indicators
            
        Returns:
            DataFrame with signals
        """
        signals = pd.DataFrame(index=df.index)
        signals['signal'] = 0
        signals['entry_price'] = None
        signals['stop_loss'] = None
        signals['take_profit'] = None
        
        # Strategy logic here
        # This is a placeholder - implement actual strategy logic
        
        return signals
    
    def should_enter_long(self, df: pd.DataFrame, orb_high: float, 
                         current_price: float) -> bool:
        """
        Check if should enter long (breakout above ORB high)
        
        Args:
            df: OHLCV DataFrame
            orb_high: ORB high price
            current_price: Current price
            
        Returns:
            True if should enter long
        """
        if orb_high is None:
            return False
        
        return current_price > orb_high + self.breakout_threshold
    
    def should_enter_short(self, df: pd.DataFrame, orb_low: float, 
                          current_price: float) -> bool:
        """
        Check if should enter short (breakdown below ORB low)
        
        Args:
            df: OHLCV DataFrame
            orb_low: ORB low price
            current_price: Current price
            
        Returns:
            True if should enter short
        """
        if orb_low is None:
            return False
        
        return current_price < orb_low - self.breakout_threshold
    
    def calculate_stop_loss(self, entry_price: float, direction: int, 
                           orb_high: float, orb_low: float) -> float:
        """
        Calculate stop loss (inside ORB)
        
        Args:
            entry_price: Entry price
            direction: 1 for long, -1 for short
            orb_high: ORB high
            orb_low: ORB low
            
        Returns:
            Stop loss price
        """
        if direction == 1:  # Long
            return orb_low - (orb_high - orb_low) * 0.1
        else:  # Short
            return orb_high + (orb_high - orb_low) * 0.1
    
    def calculate_take_profit(self, entry_price: float, direction: int, 
                             orb_range: float) -> float:
        """
        Calculate take profit (based on ORB range)
        
        Args:
            entry_price: Entry price
            direction: 1 for long, -1 for short
            orb_range: ORB range (high - low)
            
        Returns:
            Take profit price
        """
        tp_multiplier = self.config.get('tp_range_multiplier', 1.5)
        tp_distance = orb_range * tp_multiplier
        
        if direction == 1:  # Long
            return entry_price + tp_distance
        else:  # Short
            return entry_price - tp_distance


