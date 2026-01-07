"""
Shared bot state for communication between trading runner and Telegram bot
Thread-safe state management
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import threading
import time

from reporting.profit_tracker import ProfitTracker


@dataclass
class BotState:
    """Thread-safe bot state shared between runner and Telegram bot"""
    
    # Control flags
    paused: bool = False
    day_blocked: bool = False
    consec_loss: int = 0
    
    # Runtime info
    symbol: str = "XAUUSDm"
    timeframe: str = "M15"
    session: str = "OFF"  # Asia/London/OFF
    balance: float = 1000.0
    equity: Optional[float] = None
    last_error: Optional[str] = None
    
    # Last trade summary
    last_trade: Dict[str, Any] = field(default_factory=dict)
    
    # Open positions snapshot (backward compatibility)
    positions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Open trades snapshot (new format)
    open_trades: List[Dict[str, Any]] = field(default_factory=list)
    
    # Last event
    last_event: Optional[str] = None
    
    # Profit tracker
    profit: ProfitTracker = field(default_factory=lambda: ProfitTracker(initial_balance=1000.0))
    
    # MT5 snapshot (account + positions)
    account: Dict[str, Any] = field(default_factory=dict)
    mt5_positions: List[Dict[str, Any]] = field(default_factory=list)
    
    # MT5 profit from history deals
    mt5_profit: Dict[str, Any] = field(default_factory=dict)
    
    # Daily metrics
    pnl_today: float = 0.0
    trades_today: int = 0
    win_today: int = 0
    loss_today: int = 0
    
    # Internal lock for thread safety
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def set(self, **kwargs):
        """Thread-safe setter"""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)
    
    def set_open_trades(self, trades: List[Dict[str, Any]]):
        """Thread-safe setter for open trades"""
        with self._lock:
            self.open_trades = trades
            # Also update positions for backward compatibility
            self.positions = trades
    
    def set_mt5_snapshot(self, account: Dict[str, Any], positions: List[Dict[str, Any]]):
        """Thread-safe setter for MT5 snapshot"""
        with self._lock:
            self.account = account
            self.mt5_positions = positions
    
    def set_mt5_profit(self, profit: Dict[str, Any]):
        """Thread-safe setter for MT5 profit from history deals"""
        with self._lock:
            self.mt5_profit = profit
    
    def get_snapshot(self) -> Dict[str, Any]:
        """Thread-safe getter - returns a copy of current state"""
        with self._lock:
            return {
                "paused": self.paused,
                "day_blocked": self.day_blocked,
                "consec_loss": self.consec_loss,
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "session": self.session,
                "balance": self.balance,
                "equity": self.equity,
                "last_error": self.last_error,
                "last_trade": dict(self.last_trade),
                "positions": list(self.positions),
                "open_trades": list(self.open_trades),
                "last_event": self.last_event,
                "account": dict(self.account),
                "mt5_positions": list(self.mt5_positions),
                "mt5_profit": dict(self.mt5_profit),
                "pnl_today": self.pnl_today,
                "trades_today": self.trades_today,
                "win_today": self.win_today,
                "loss_today": self.loss_today,
                "ts": time.time(),
            }
    
    def snapshot(self) -> Dict[str, Any]:
        """Alias for get_snapshot() for compatibility"""
        return self.get_snapshot()

