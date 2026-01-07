"""
Notifier Module
Unified notification interface
"""

from typing import Optional, Dict
from abc import ABC, abstractmethod

from .telegram_client import TelegramClient
from .templates import MessageTemplates


class Notifier(ABC):
    """Base notifier interface"""
    
    @abstractmethod
    def send(self, message: str) -> bool:
        """Send notification"""
        pass


class TelegramNotifier(Notifier):
    """Telegram notifier implementation"""
    
    def __init__(self, token: str, chat_id: str, enabled: bool = True):
        """
        Initialize Telegram notifier
        
        Args:
            token: Telegram bot token
            chat_id: Chat ID
            enabled: Whether notifications are enabled
        """
        self.client = TelegramClient(token, chat_id)
        self.enabled = enabled
        self.templates = MessageTemplates()
    
    def send(self, message: str) -> bool:
        """Send message"""
        if not self.enabled:
            return False
        
        return self.client.send_message(message)
    
    def notify_trade_open(self, symbol: str, order_type: str, volume: float,
                         entry_price: float, stop_loss: Optional[float] = None,
                         take_profit: Optional[float] = None) -> bool:
        """Notify trade opening"""
        message = self.templates.trade_open(
            symbol, order_type, volume, entry_price, stop_loss, take_profit
        )
        return self.send(message)
    
    def notify_trade_close(self, symbol: str, order_type: str, volume: float,
                          entry_price: float, exit_price: float, pnl: float,
                          exit_reason: str = "Manual") -> bool:
        """Notify trade closing"""
        message = self.templates.trade_close(
            symbol, order_type, volume, entry_price, exit_price, pnl, exit_reason
        )
        return self.send(message)
    
    def notify_daily_summary(self, total_trades: int, winning_trades: int,
                            total_pnl: float, win_rate: float) -> bool:
        """Notify daily summary"""
        message = self.templates.daily_summary(
            total_trades, winning_trades, total_pnl, win_rate
        )
        return self.send(message)
    
    def notify_error(self, error_message: str, context: Optional[str] = None) -> bool:
        """Notify error"""
        message = self.templates.error(error_message, context)
        return self.send(message)
    
    def notify_warning(self, warning_message: str, context: Optional[str] = None) -> bool:
        """Notify warning"""
        message = self.templates.warning(warning_message, context)
        return self.send(message)
    
    def notify_backtest_summary(self, metrics: Dict) -> bool:
        """Notify backtest summary"""
        message = self.templates.backtest_summary(metrics)
        return self.send(message)


class ConsoleNotifier(Notifier):
    """Console notifier (for testing)"""
    
    def __init__(self, enabled: bool = True):
        """Initialize console notifier"""
        self.enabled = enabled
    
    def send(self, message: str) -> bool:
        """Print message to console"""
        if not self.enabled:
            return False
        
        print("=" * 60)
        print(message)
        print("=" * 60)
        return True


