"""
Equity Curve Module
Tracks and visualizes equity curve
"""

import pandas as pd
import matplotlib.pyplot as plt
from typing import List, Dict, Optional
from datetime import datetime
import numpy as np


class EquityCurve:
    """Tracks equity curve"""
    
    def __init__(self, initial_balance: float = 10000.0):
        """
        Initialize equity curve tracker
        
        Args:
            initial_balance: Starting balance
        """
        self.initial_balance = initial_balance
        self.equity_points: List[Dict] = []
        self.current_balance = initial_balance
        self.current_equity = initial_balance
    
    def update(self, balance: float, equity: float, timestamp: Optional[datetime] = None) -> None:
        """
        Update equity curve
        
        Args:
            balance: Current balance
            equity: Current equity
            timestamp: Timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self.current_balance = balance
        self.current_equity = equity
        
        self.equity_points.append({
            'timestamp': timestamp,
            'balance': balance,
            'equity': equity
        })
    
    def get_dataframe(self) -> pd.DataFrame:
        """Get equity curve as DataFrame"""
        if not self.equity_points:
            return pd.DataFrame()
        
        df = pd.DataFrame(self.equity_points)
        df.set_index('timestamp', inplace=True)
        return df
    
    def plot(self, filepath: Optional[str] = None, show: bool = False) -> None:
        """
        Plot equity curve
        
        Args:
            filepath: Path to save plot (optional)
            show: Whether to display plot
        """
        df = self.get_dataframe()
        if df.empty:
            return
        
        plt.figure(figsize=(12, 6))
        plt.plot(df.index, df['equity'], label='Equity', linewidth=2)
        plt.plot(df.index, df['balance'], label='Balance', linewidth=1, linestyle='--')
        plt.axhline(y=self.initial_balance, color='gray', linestyle=':', label='Initial Balance')
        
        plt.title('Equity Curve', fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Equity ($)', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        if filepath:
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
    
    def calculate_drawdown(self) -> pd.Series:
        """Calculate drawdown series"""
        df = self.get_dataframe()
        if df.empty:
            return pd.Series()
        
        running_max = df['equity'].expanding().max()
        drawdown = df['equity'] - running_max
        
        return drawdown
    
    def plot_drawdown(self, filepath: Optional[str] = None, show: bool = False) -> None:
        """
        Plot drawdown
        
        Args:
            filepath: Path to save plot (optional)
            show: Whether to display plot
        """
        drawdown = self.calculate_drawdown()
        if drawdown.empty:
            return
        
        plt.figure(figsize=(12, 6))
        plt.fill_between(drawdown.index, drawdown, 0, alpha=0.3, color='red')
        plt.plot(drawdown.index, drawdown, color='red', linewidth=2)
        
        plt.title('Drawdown', fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Drawdown ($)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        if filepath:
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
        
        if show:
            plt.show()
        else:
            plt.close()
    
    def get_max_drawdown(self) -> float:
        """Get maximum drawdown"""
        drawdown = self.calculate_drawdown()
        if drawdown.empty:
            return 0.0
        
        return abs(drawdown.min())
    
    def get_max_drawdown_pct(self) -> float:
        """Get maximum drawdown percentage"""
        max_dd = self.get_max_drawdown()
        if self.initial_balance == 0:
            return 0.0
        
        return (max_dd / self.initial_balance) * 100
    
    def reset(self) -> None:
        """Reset equity curve"""
        self.equity_points.clear()
        self.current_balance = self.initial_balance
        self.current_equity = self.initial_balance


