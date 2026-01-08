"""
Message Templates Module
Formats messages for notifications
"""

from typing import Dict, Optional
from datetime import datetime


class MessageTemplates:
    """Message formatting templates"""
    
    @staticmethod
    def trade_open(symbol: str, order_type: str, volume: float, 
                  entry_price: float, stop_loss: Optional[float] = None,
                  take_profit: Optional[float] = None) -> str:
        """
        Format trade open message
        
        Args:
            symbol: Trading symbol
            order_type: BUY or SELL
            volume: Position volume
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            
        Returns:
            Formatted message
        """
        emoji = "🟢" if order_type == "BUY" else "🔴"
        
        message = f"{emoji} <b>Trade Opened</b>\n\n"
        message += f"Symbol: {symbol}\n"
        message += f"Type: {order_type}\n"
        message += f"Volume: {volume} lots\n"
        message += f"Entry: {entry_price:.5f}\n"
        
        if stop_loss:
            message += f"SL: {stop_loss:.5f}\n"
        if take_profit:
            message += f"TP: {take_profit:.5f}\n"
        
        message += f"\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message
    
    @staticmethod
    def trade_close(symbol: str, order_type: str, volume: float,
                   entry_price: float, exit_price: float, pnl: float,
                   exit_reason: str = "Manual") -> str:
        """
        Format trade close message
        
        Args:
            symbol: Trading symbol
            order_type: BUY or SELL
            volume: Position volume
            entry_price: Entry price
            exit_price: Exit price
            pnl: Profit/Loss
            exit_reason: Reason for closing
            
        Returns:
            Formatted message
        """
        emoji = "✅" if pnl > 0 else "❌"
        pnl_emoji = "💰" if pnl > 0 else "📉"
        
        message = f"{emoji} <b>Trade Closed</b>\n\n"
        message += f"Symbol: {symbol}\n"
        message += f"Type: {order_type}\n"
        message += f"Volume: {volume} lots\n"
        message += f"Entry: {entry_price:.5f}\n"
        message += f"Exit: {exit_price:.5f}\n"
        message += f"{pnl_emoji} P&L: ${pnl:.2f}\n"
        message += f"Reason: {exit_reason}\n"
        message += f"\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message
    
    @staticmethod
    def daily_summary(total_trades: int, winning_trades: int,
                     total_pnl: float, win_rate: float) -> str:
        """
        Format daily summary message
        
        Args:
            total_trades: Total number of trades
            winning_trades: Number of winning trades
            total_pnl: Total profit/loss
            win_rate: Win rate percentage
            
        Returns:
            Formatted message
        """
        emoji = "📊"
        pnl_emoji = "💰" if total_pnl > 0 else "📉"
        
        message = f"{emoji} <b>Daily Summary</b>\n\n"
        message += f"Total Trades: {total_trades}\n"
        message += f"Winning: {winning_trades}\n"
        message += f"Win Rate: {win_rate:.1f}%\n"
        message += f"{pnl_emoji} Total P&L: ${total_pnl:.2f}\n"
        message += f"\nDate: {datetime.now().strftime('%Y-%m-%d')}"
        
        return message
    
    @staticmethod
    def error(error_message: str, context: Optional[str] = None) -> str:
        """
        Format error message
        
        Args:
            error_message: Error message
            context: Additional context
            
        Returns:
            Formatted message
        """
        message = f"⚠️ <b>Error</b>\n\n"
        message += f"{error_message}\n"
        
        if context:
            message += f"\nContext: {context}\n"
        
        message += f"\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message
    
    @staticmethod
    def warning(warning_message: str, context: Optional[str] = None) -> str:
        """
        Format warning message
        
        Args:
            warning_message: Warning message
            context: Additional context
            
        Returns:
            Formatted message
        """
        message = f"⚠️ <b>Warning</b>\n\n"
        message += f"{warning_message}\n"
        
        if context:
            message += f"\nContext: {context}\n"
        
        message += f"\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message
    
    @staticmethod
    def backtest_summary(metrics: Dict) -> str:
        """
        Format backtest summary message
        
        Args:
            metrics: Backtest metrics dictionary
            
        Returns:
            Formatted message
        """
        message = f"📈 <b>Backtest Results</b>\n\n"
        message += f"Total Trades: {metrics.get('total_trades', 0)}\n"
        message += f"Win Rate: {metrics.get('win_rate', 0):.2f}%\n"
        message += f"Profit Factor: {metrics.get('profit_factor', 0):.2f}\n"
        message += f"Total P&L: ${metrics.get('total_pnl', 0):.2f}\n"
        message += f"Return: {metrics.get('return_pct', 0):.2f}%\n"
        message += f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}\n"
        message += f"Max Drawdown: {metrics.get('max_drawdown_pct', 0):.2f}%"
        
        return message


