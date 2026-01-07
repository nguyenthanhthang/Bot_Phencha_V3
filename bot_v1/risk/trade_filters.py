"""
Trade Filters Module
Filters trades based on various conditions
"""

import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime, time


class TradeFilter:
    """Base class for trade filters"""
    
    def should_allow(self, **kwargs) -> tuple[bool, str]:
        """
        Check if trade should be allowed
        
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        raise NotImplementedError


class TimeFilter(TradeFilter):
    """Filter trades based on time"""
    
    def __init__(self, allowed_hours: List[tuple[int, int]]):
        """
        Initialize time filter
        
        Args:
            allowed_hours: List of (start_hour, end_hour) tuples
        """
        self.allowed_hours = allowed_hours
    
    def should_allow(self, current_time: datetime, **kwargs) -> tuple[bool, str]:
        """Check if current time is allowed"""
        current_hour = current_time.hour
        
        for start_hour, end_hour in self.allowed_hours:
            if start_hour <= current_hour < end_hour:
                return True, "OK"
        
        return False, f"Trading not allowed at {current_time.time()}"


class SpreadFilter(TradeFilter):
    """Filter trades based on spread"""
    
    def __init__(self, max_spread_pips: float):
        """
        Initialize spread filter
        
        Args:
            max_spread_pips: Maximum allowed spread in pips
        """
        self.max_spread_pips = max_spread_pips
    
    def should_allow(self, spread_pips: float, **kwargs) -> tuple[bool, str]:
        """Check if spread is acceptable"""
        if spread_pips > self.max_spread_pips:
            return False, f"Spread too wide: {spread_pips:.1f} pips (max: {self.max_spread_pips})"
        
        return True, "OK"


class VolatilityFilter(TradeFilter):
    """Filter trades based on volatility"""
    
    def __init__(self, min_atr_pips: float = 5.0, max_atr_pips: float = 50.0):
        """
        Initialize volatility filter
        
        Args:
            min_atr_pips: Minimum ATR in pips
            max_atr_pips: Maximum ATR in pips
        """
        self.min_atr_pips = min_atr_pips
        self.max_atr_pips = max_atr_pips
    
    def should_allow(self, atr_pips: float, **kwargs) -> tuple[bool, str]:
        """Check if volatility is acceptable"""
        if atr_pips < self.min_atr_pips:
            return False, f"Volatility too low: {atr_pips:.1f} pips (min: {self.min_atr_pips})"
        
        if atr_pips > self.max_atr_pips:
            return False, f"Volatility too high: {atr_pips:.1f} pips (max: {self.max_atr_pips})"
        
        return True, "OK"


class NewsFilter(TradeFilter):
    """Filter trades around news events"""
    
    def __init__(self, news_blackout_minutes: int = 30):
        """
        Initialize news filter
        
        Args:
            news_blackout_minutes: Minutes before/after news to avoid trading
        """
        self.news_blackout_minutes = news_blackout_minutes
        self.news_events: List[datetime] = []
    
    def add_news_event(self, event_time: datetime) -> None:
        """Add a news event"""
        self.news_events.append(event_time)
    
    def should_allow(self, current_time: datetime, **kwargs) -> tuple[bool, str]:
        """Check if too close to news event"""
        from datetime import timedelta
        
        for event_time in self.news_events:
            time_diff = abs((current_time - event_time).total_seconds() / 60)
            if time_diff < self.news_blackout_minutes:
                return False, f"Too close to news event at {event_time}"
        
        return True, "OK"


class CompositeFilter:
    """Combines multiple filters"""
    
    def __init__(self, filters: List[TradeFilter]):
        """
        Initialize composite filter
        
        Args:
            filters: List of trade filters
        """
        self.filters = filters
    
    def should_allow(self, **kwargs) -> tuple[bool, str]:
        """Check all filters"""
        for filter_obj in self.filters:
            allowed, reason = filter_obj.should_allow(**kwargs)
            if not allowed:
                return False, reason
        
        return True, "OK"


