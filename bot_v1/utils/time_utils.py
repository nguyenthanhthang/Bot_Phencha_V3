"""
Time Utilities Module
Time-related helper functions
"""

from datetime import datetime, time, timedelta, date
from typing import Optional
import pytz
import pandas as pd


def get_session_time(session: str) -> tuple[time, time]:
    """
    Get session start and end times
    
    Args:
        session: Session name ('asia', 'london', 'new_york')
        
    Returns:
        Tuple of (start_time, end_time)
    """
    sessions = {
        'asia': (time(0, 0), time(9, 0)),
        'london': (time(8, 0), time(17, 0)),
        'new_york': (time(13, 0), time(22, 0)),
        'overlap_london_ny': (time(13, 0), time(17, 0))
    }
    
    return sessions.get(session.lower(), (time(0, 0), time(23, 59)))


def is_session_active(current_time: datetime, session: str) -> bool:
    """
    Check if session is currently active
    
    Args:
        current_time: Current datetime
        session: Session name
        
    Returns:
        True if session is active
    """
    start_time, end_time = get_session_time(session)
    current_time_only = current_time.time()
    
    return start_time <= current_time_only <= end_time


def convert_timezone(dt: datetime, from_tz: str, to_tz: str) -> datetime:
    """
    Convert datetime between timezones
    
    Args:
        dt: Datetime to convert
        from_tz: Source timezone
        to_tz: Target timezone
        
    Returns:
        Converted datetime
    """
    from_tz_obj = pytz.timezone(from_tz)
    to_tz_obj = pytz.timezone(to_tz)
    
    if dt.tzinfo is None:
        dt = from_tz_obj.localize(dt)
    
    return dt.astimezone(to_tz_obj)


def get_market_open_time(date: date, session: str, timezone: str = "UTC") -> datetime:
    """
    Get market open time for a date and session
    
    Args:
        date: Date
        session: Session name
        timezone: Timezone
        
    Returns:
        Market open datetime
    """
    start_time, _ = get_session_time(session)
    tz = pytz.timezone(timezone)
    
    dt = datetime.combine(date, start_time)
    return tz.localize(dt)


def get_market_close_time(date: date, session: str, timezone: str = "UTC") -> datetime:
    """
    Get market close time for a date and session
    
    Args:
        date: Date
        session: Session name
        timezone: Timezone
        
    Returns:
        Market close datetime
    """
    _, end_time = get_session_time(session)
    tz = pytz.timezone(timezone)
    
    dt = datetime.combine(date, end_time)
    return tz.localize(dt)


def is_weekend(dt: datetime) -> bool:
    """
    Check if datetime is on weekend
    
    Args:
        dt: Datetime to check
        
    Returns:
        True if weekend
    """
    return dt.weekday() >= 5


def is_market_open(dt: datetime, session: str) -> bool:
    """
    Check if market is open
    
    Args:
        dt: Datetime to check
        session: Session name
        
    Returns:
        True if market is open
    """
    if is_weekend(dt):
        return False
    
    return is_session_active(dt, session)


def get_next_trading_day(dt: datetime) -> datetime:
    """
    Get next trading day (skip weekends)
    
    Args:
        dt: Current datetime
        
    Returns:
        Next trading day
    """
    next_day = dt + timedelta(days=1)
    
    while is_weekend(next_day):
        next_day += timedelta(days=1)
    
    return next_day


def to_vn_time(ts_utc: pd.Series) -> pd.Series:
    # input: datetime64 (UTC) -> output: Asia/Ho_Chi_Minh
    return pd.to_datetime(ts_utc, utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")


def in_time_range(t_vn, start_hhmm: str, end_hhmm: str) -> bool:
    # t_vn is timezone-aware datetime
    hhmm = t_vn.strftime("%H:%M")
    return start_hhmm <= hhmm <= end_hhmm

