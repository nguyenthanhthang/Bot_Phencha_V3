"""
MT5 Execution Module
Handles order execution on MetaTrader 5
"""

import MetaTrader5 as mt5
from typing import Optional, Dict
from datetime import datetime
from enum import Enum


class OrderType(Enum):
    """Order types"""
    BUY = "BUY"
    SELL = "SELL"


class MT5Executor:
    """Executes trades on MT5"""
    
    def __init__(self, login: Optional[int] = None, password: Optional[str] = None,
                 server: Optional[str] = None):
        """
        Initialize MT5 executor
        
        Args:
            login: MT5 account login
            password: MT5 account password
            server: MT5 server name
        """
        self.login = login
        self.password = password
        self.server = server
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to MT5"""
        if not mt5.initialize():
            return False
        
        if self.login and self.password and self.server:
            authorized = mt5.login(self.login, password=self.password, server=self.server)
            if not authorized:
                return False
        
        self.connected = True
        return True
    
    def disconnect(self) -> None:
        """Disconnect from MT5"""
        mt5.shutdown()
        self.connected = False
    
    def place_market_order(self, symbol: str, order_type: OrderType, volume: float,
                          stop_loss: Optional[float] = None,
                          take_profit: Optional[float] = None,
                          comment: str = "") -> Optional[int]:
        """
        Place a market order
        
        Args:
            symbol: Trading symbol
            order_type: BUY or SELL
            volume: Order volume in lots
            stop_loss: Stop loss price
            take_profit: Take profit price
            comment: Order comment
            
        Returns:
            Order ticket if successful, None otherwise
        """
        if not self.connected:
            if not self.connect():
                return None
        
        # Get current price
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return None
        
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return None
        
        # Prepare order request
        if order_type == OrderType.BUY:
            price = mt5.symbol_info_tick(symbol).ask
            order_type_mt5 = mt5.ORDER_TYPE_BUY
        else:
            price = mt5.symbol_info_tick(symbol).bid
            order_type_mt5 = mt5.ORDER_TYPE_SELL
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type_mt5,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        if stop_loss:
            request["sl"] = stop_loss
        if take_profit:
            request["tp"] = take_profit
        
        # Send order
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return None
        
        return result.order
    
    def close_position(self, ticket: int, volume: Optional[float] = None) -> bool:
        """
        Close a position
        
        Args:
            ticket: Position ticket
            volume: Volume to close (None = close all)
            
        Returns:
            True if successful
        """
        if not self.connected:
            if not self.connect():
                return False
        
        # Get position info
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return False
        
        position = position[0]
        symbol = position.symbol
        position_type = position.type
        
        # Determine close price and order type
        if position_type == mt5.POSITION_TYPE_BUY:
            price = mt5.symbol_info_tick(symbol).bid
            order_type = mt5.ORDER_TYPE_SELL
        else:
            price = mt5.symbol_info_tick(symbol).ask
            order_type = mt5.ORDER_TYPE_BUY
        
        close_volume = volume if volume else position.volume
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": close_volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        return result.retcode == mt5.TRADE_RETCODE_DONE
    
    def close_partial(self, ticket: int, lot: float) -> bool:
        """
        Close partial position (for scale-out TP1)
        
        Args:
            ticket: Position ticket
            lot: Volume to close in lots
            
        Returns:
            True if successful
        """
        return self.close_position(ticket, volume=lot)
    
    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """
        Modify stop loss only (for BE+ after TP1)
        
        Args:
            ticket: Position ticket
            new_sl: New stop loss price
            
        Returns:
            True if successful
        """
        return self.modify_position(ticket, stop_loss=new_sl)
    
    def modify_position(self, ticket: int, stop_loss: Optional[float] = None,
                       take_profit: Optional[float] = None) -> bool:
        """
        Modify position SL/TP
        
        Args:
            ticket: Position ticket
            stop_loss: New stop loss
            take_profit: New take profit
            
        Returns:
            True if successful
        """
        if not self.connected:
            if not self.connect():
                return False
        
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return False
        
        position = position[0]
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": ticket,
            "sl": stop_loss if stop_loss else position.sl,
            "tp": take_profit if take_profit else position.tp,
        }
        
        result = mt5.order_send(request)
        return result.retcode == mt5.TRADE_RETCODE_DONE
    
    def get_positions(self, symbol: Optional[str] = None) -> list:
        """
        Get open positions
        
        Args:
            symbol: Filter by symbol (None = all symbols)
            
        Returns:
            List of position dictionaries
        """
        if not self.connected:
            if not self.connect():
                return []
        
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        if positions is None:
            return []
        
        result = []
        for pos in positions:
            result.append({
                'ticket': pos.ticket,
                'symbol': pos.symbol,
                'type': 'BUY' if pos.type == mt5.POSITION_TYPE_BUY else 'SELL',
                'volume': pos.volume,
                'price_open': pos.price_open,
                'price_current': pos.price_current,
                'sl': pos.sl,
                'tp': pos.tp,
                'profit': pos.profit,
                'time': datetime.fromtimestamp(pos.time)
            })
        
        return result


