"""
Fill Model Module
Simulates order fills with different models
"""

from typing import Optional
from enum import Enum
import random


class FillModel(Enum):
    """Fill model types"""
    INSTANT = "instant"
    PARTIAL = "partial"
    REALISTIC = "realistic"


class FillModelSimulator:
    """Simulates order fills"""
    
    def __init__(self, model_type: FillModel = FillModel.INSTANT,
                 partial_fill_probability: float = 0.8,
                 max_slippage_pips: float = 3.0):
        """
        Initialize fill model
        
        Args:
            model_type: Type of fill model
            partial_fill_probability: Probability of partial fill (for partial model)
            max_slippage_pips: Maximum slippage in pips
        """
        self.model_type = model_type
        self.partial_fill_probability = partial_fill_probability
        self.max_slippage_pips = max_slippage_pips
    
    def fill_order(self, requested_volume: float, price: float,
                   pip_value: float = 0.0001) -> tuple[float, float]:
        """
        Simulate order fill
        
        Args:
            requested_volume: Requested order volume
            price: Requested price
            pip_value: Pip value
            
        Returns:
            Tuple of (filled_volume, fill_price)
        """
        if self.model_type == FillModel.INSTANT:
            return self._instant_fill(requested_volume, price, pip_value)
        elif self.model_type == FillModel.PARTIAL:
            return self._partial_fill(requested_volume, price, pip_value)
        elif self.model_type == FillModel.REALISTIC:
            return self._realistic_fill(requested_volume, price, pip_value)
        else:
            return requested_volume, price
    
    def _instant_fill(self, requested_volume: float, price: float,
                     pip_value: float) -> tuple[float, float]:
        """Instant fill - always fills at requested price"""
        return requested_volume, price
    
    def _partial_fill(self, requested_volume: float, price: float,
                     pip_value: float) -> tuple[float, float]:
        """Partial fill - may fill partially"""
        if random.random() < self.partial_fill_probability:
            # Partial fill
            fill_ratio = random.uniform(0.5, 1.0)
            filled_volume = requested_volume * fill_ratio
        else:
            filled_volume = requested_volume
        
        # Add small slippage
        slippage_pips = random.uniform(0, self.max_slippage_pips)
        fill_price = price + (slippage_pips * pip_value * random.choice([-1, 1]))
        
        return filled_volume, fill_price
    
    def _realistic_fill(self, requested_volume: float, price: float,
                       pip_value: float) -> tuple[float, float]:
        """Realistic fill - simulates market conditions"""
        # Larger orders may fill partially
        if requested_volume > 1.0:
            fill_ratio = random.uniform(0.7, 1.0)
            filled_volume = requested_volume * fill_ratio
        else:
            filled_volume = requested_volume
        
        # Slippage increases with volume
        slippage_multiplier = min(requested_volume / 1.0, 2.0)
        slippage_pips = random.uniform(0, self.max_slippage_pips * slippage_multiplier)
        fill_price = price + (slippage_pips * pip_value * random.choice([-1, 1]))
        
        return filled_volume, fill_price


