"""
Position Sizing Module
Calculates appropriate position size based on risk management rules
"""

from typing import Optional
from decimal import Decimal


class PositionSizer:
    """Calculate position sizes based on risk"""
    
    def __init__(self, account_balance: float, risk_per_trade: float = 0.02,
                 max_risk_per_trade: float = 0.05):
        """
        Initialize position sizer
        
        Args:
            account_balance: Current account balance
            risk_per_trade: Risk percentage per trade (default 2%)
            max_risk_per_trade: Maximum risk percentage per trade (default 5%)
        """
        self.account_balance = account_balance
        self.risk_per_trade = risk_per_trade
        self.max_risk_per_trade = max_risk_per_trade
    
    def calculate_by_risk_amount(self, risk_amount: float, 
                                stop_loss_pips: float, 
                                pip_value: float = 0.0001,
                                lot_size: float = 0.01) -> float:
        """
        Calculate position size based on risk amount
        
        Args:
            risk_amount: Amount to risk in account currency
            stop_loss_pips: Stop loss in pips
            pip_value: Pip value for the symbol
            lot_size: Minimum lot size
            
        Returns:
            Position size in lots
        """
        if stop_loss_pips <= 0:
            return 0.0
        
        # Calculate position size
        # Risk = Position Size * Stop Loss Pips * Pip Value
        # Position Size = Risk / (Stop Loss Pips * Pip Value)
        position_size = risk_amount / (stop_loss_pips * pip_value * 100)
        
        # Round to nearest lot size
        position_size = round(position_size / lot_size) * lot_size
        
        return max(0.0, position_size)
    
    def calculate_by_percentage(self, stop_loss_pips: float,
                               pip_value: float = 0.0001,
                               lot_size: float = 0.01,
                               risk_percentage: Optional[float] = None) -> float:
        """
        Calculate position size based on risk percentage
        
        Args:
            stop_loss_pips: Stop loss in pips
            pip_value: Pip value for the symbol
            lot_size: Minimum lot size
            risk_percentage: Risk percentage (uses self.risk_per_trade if None)
            
        Returns:
            Position size in lots
        """
        if risk_percentage is None:
            risk_percentage = self.risk_per_trade
        
        # Clamp risk percentage
        risk_percentage = min(risk_percentage, self.max_risk_per_trade)
        
        # Calculate risk amount
        risk_amount = self.account_balance * risk_percentage
        
        return self.calculate_by_risk_amount(
            risk_amount, stop_loss_pips, pip_value, lot_size
        )
    
    def calculate_by_atr(self, atr_pips: float, atr_multiplier: float = 2.0,
                        pip_value: float = 0.0001,
                        lot_size: float = 0.01,
                        risk_percentage: Optional[float] = None) -> float:
        """
        Calculate position size using ATR-based stop loss
        
        Args:
            atr_pips: ATR value in pips
            atr_multiplier: ATR multiplier for stop loss
            pip_value: Pip value for the symbol
            lot_size: Minimum lot size
            risk_percentage: Risk percentage
            
        Returns:
            Position size in lots
        """
        stop_loss_pips = atr_pips * atr_multiplier
        return self.calculate_by_percentage(
            stop_loss_pips, pip_value, lot_size, risk_percentage
        )
    
    def validate_position_size(self, position_size: float,
                               min_lot: float, max_lot: float) -> float:
        """
        Validate and clamp position size
        
        Args:
            position_size: Calculated position size
            min_lot: Minimum allowed lot size
            max_lot: Maximum allowed lot size
            
        Returns:
            Validated position size
        """
        return max(min_lot, min(position_size, max_lot))
    
    def update_balance(self, new_balance: float) -> None:
        """Update account balance"""
        self.account_balance = new_balance


import math


def round_to_step(x: float, step: float) -> float:
    return math.floor(x / step) * step


def calc_lot_by_risk(
    balance: float,
    risk_pct: float,
    sl_usd: float,
    contract_size: float = 100.0,
    min_lot: float = 0.01,
    lot_step: float = 0.01,
) -> float:
    """
    XAUUSD pnl per $ move:
    pnl = move_usd * lot * contract_size
    risk_usd = balance * risk_pct/100
    lot = risk_usd / (sl_usd * contract_size)
    """
    risk_usd = balance * (risk_pct / 100.0)
    raw = risk_usd / (max(sl_usd, 1e-9) * contract_size)
    lot = max(min_lot, round_to_step(raw, lot_step))
    return lot


