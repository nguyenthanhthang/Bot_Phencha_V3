"""
Math Utilities Module
Mathematical helper functions
"""

import numpy as np
from typing import List, Optional


def calculate_pips(price1: float, price2: float, pip_value: float = 0.0001) -> float:
    """
    Calculate pips between two prices
    
    Args:
        price1: First price
        price2: Second price
        pip_value: Pip value for the symbol
        
    Returns:
        Pips difference
    """
    return abs(price1 - price2) / pip_value


def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """
    Calculate percentage change
    
    Args:
        old_value: Old value
        new_value: New value
        
    Returns:
        Percentage change
    """
    if old_value == 0:
        return 0.0
    
    return ((new_value - old_value) / old_value) * 100


def round_to_lot_size(volume: float, lot_size: float) -> float:
    """
    Round volume to nearest lot size
    
    Args:
        volume: Volume to round
        lot_size: Lot size step
        
    Returns:
        Rounded volume
    """
    return round(volume / lot_size) * lot_size


def calculate_position_value(volume: float, price: float) -> float:
    """
    Calculate position value
    
    Args:
        volume: Position volume in lots
        price: Current price
        
    Returns:
        Position value
    """
    return volume * 100000 * price  # 1 lot = 100,000 units


def calculate_pnl(entry_price: float, exit_price: float, volume: float,
                  order_type: str) -> float:
    """
    Calculate profit/loss
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        volume: Position volume in lots
        order_type: 'BUY' or 'SELL'
        
    Returns:
        Profit/Loss
    """
    if order_type.upper() == 'BUY':
        pnl = (exit_price - entry_price) * volume * 100000
    else:  # SELL
        pnl = (entry_price - exit_price) * volume * 100000
    
    return pnl


def calculate_risk_reward_ratio(entry_price: float, stop_loss: float,
                               take_profit: float, order_type: str) -> float:
    """
    Calculate risk/reward ratio
    
    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        take_profit: Take profit price
        order_type: 'BUY' or 'SELL'
        
    Returns:
        Risk/reward ratio
    """
    if order_type.upper() == 'BUY':
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
    else:  # SELL
        risk = abs(stop_loss - entry_price)
        reward = abs(entry_price - take_profit)
    
    if risk == 0:
        return 0.0
    
    return reward / risk


def calculate_win_rate(wins: int, losses: int) -> float:
    """
    Calculate win rate percentage
    
    Args:
        wins: Number of wins
        losses: Number of losses
        
    Returns:
        Win rate percentage
    """
    total = wins + losses
    if total == 0:
        return 0.0
    
    return (wins / total) * 100


def calculate_profit_factor(gross_profit: float, gross_loss: float) -> float:
    """
    Calculate profit factor
    
    Args:
        gross_profit: Total gross profit
        gross_loss: Total gross loss (positive value)
        
    Returns:
        Profit factor
    """
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    
    return gross_profit / gross_loss


def normalize_value(value: float, min_val: float, max_val: float) -> float:
    """
    Normalize value to 0-1 range
    
    Args:
        value: Value to normalize
        min_val: Minimum value
        max_val: Maximum value
        
    Returns:
        Normalized value (0-1)
    """
    if max_val == min_val:
        return 0.0
    
    return (value - min_val) / (max_val - min_val)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp value between min and max
    
    Args:
        value: Value to clamp
        min_val: Minimum value
        max_val: Maximum value
        
    Returns:
        Clamped value
    """
    return max(min_val, min(value, max_val))


