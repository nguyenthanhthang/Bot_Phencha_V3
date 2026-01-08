"""
MT5 Execution Module
Handles order execution on MetaTrader 5
"""

from __future__ import annotations
import MetaTrader5 as mt5
from typing import Optional, Dict, List
from datetime import datetime, timezone, timedelta, date
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
            comment: Order comment (will be truncated to 32 chars and sanitized)
            
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
        
        # Sanitize and truncate comment (MT5 limit is usually 32-64 chars, use 32 for safety)
        # Remove any non-ASCII or special characters that might cause issues
        safe_comment = comment.encode('ascii', 'ignore').decode('ascii')
        # Remove any control characters
        safe_comment = ''.join(c for c in safe_comment if c.isprintable())
        # Truncate to 32 characters (MT5 safe limit)
        safe_comment = safe_comment[:32] if len(safe_comment) > 32 else safe_comment
        # Ensure it's not empty
        if not safe_comment:
            safe_comment = "VP"
        
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
            "comment": safe_comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        if stop_loss:
            request["sl"] = stop_loss
        if take_profit:
            request["tp"] = take_profit
        
        # Send order
        result = mt5.order_send(request)
        
        # Check if order_send returned None (connection/terminal issue)
        if result is None:
            err = mt5.last_error()
            raise RuntimeError(f"MT5 order_send returned None. Last error: {err}")
        
        # Check retcode
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            # Log error details
            err_msg = f"Order failed: retcode={result.retcode}, comment={result.comment if hasattr(result, 'comment') else 'N/A'}"
            raise RuntimeError(err_msg)
        
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
        if result is None:
            err = mt5.last_error()
            raise RuntimeError(f"MT5 order_send returned None. Last error: {err}")
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
        if result is None:
            err = mt5.last_error()
            raise RuntimeError(f"MT5 order_send returned None. Last error: {err}")
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
    
    def fetch_account_snapshot(self) -> Dict:
        """
        Fetch account information snapshot
        
        Returns:
            Dictionary with account info
        """
        if not self.connected:
            if not self.connect():
                return {"ok": False, "error": "MT5 not connected"}
        
        info = mt5.account_info()
        if info is None:
            return {"ok": False, "error": "mt5.account_info() returned None"}
        
        return {
            "ok": True,
            "login": info.login,
            "server": info.server,
            "currency": info.currency,
            "balance": float(info.balance),
            "equity": float(info.equity),
            "margin": float(info.margin),
            "margin_free": float(info.margin_free),
            "margin_level": float(info.margin_level) if info.margin_level is not None else None,
        }
    
    def fetch_open_positions(self, symbol: Optional[str] = None, magic: Optional[int] = None) -> List[Dict]:
        """
        Fetch open positions from MT5
        
        Args:
            symbol: Filter by symbol (None = all symbols) - case-insensitive
            magic: Filter by magic number (None = all)
            
        Returns:
            List of position dictionaries, or list with error dict if MT5 connection issue
        """
        if not self.connected:
            if not self.connect():
                err = mt5.last_error()
                return [{"_error": f"MT5Executor not connected | last_error={err}"}]
        
        # IMPORTANT: detect MT5 connection status
        term = mt5.terminal_info()
        if term is None:
            err = mt5.last_error()
            return [{"_error": f"terminal_info None | last_error={err}"}]
        
        # Always fetch all positions first, then filter case-insensitive
        # This ensures we get all positions regardless of symbol case
        positions = mt5.positions_get()
        if positions is None:
            err = mt5.last_error()
            return [{"_error": f"positions_get None | last_error={err}"}]
        
        out = []
        for p in positions:
            # Filter by magic if specified
            if magic is not None and p.magic != magic:
                continue
            
            # p.type: 0=BUY, 1=SELL
            direction = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
            
            # Convert time to readable string
            try:
                time_open = datetime.fromtimestamp(int(p.time)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                time_open = str(p.time)
            
            out.append({
                "ticket": int(p.ticket),
                "symbol": str(p.symbol),
                "direction": direction,
                "lots": float(p.volume),
                "price_open": float(p.price_open),
                "sl": float(p.sl) if p.sl else 0.0,
                "tp": float(p.tp) if p.tp else 0.0,
                "profit": float(p.profit),
                "swap": float(p.swap) if hasattr(p, 'swap') else 0.0,
                "commission": float(p.commission) if hasattr(p, 'commission') else 0.0,
                "time_open": time_open,
                "magic": int(p.magic),
                "comment": str(p.comment) if hasattr(p, 'comment') else "",
            })
        
        # Filter by symbol case-insensitive if provided (after building list)
        if symbol:
            sym = symbol.lower()
            out = [x for x in out if x["symbol"].lower() == sym]
        
        return out


# Standalone functions for easy access (can be used without MT5Executor instance)
def fetch_account_snapshot() -> Dict:
    """
    Standalone function to fetch account snapshot
    Note: MT5 must be initialized before calling this function
    """
    # Check if MT5 is already initialized
    if not mt5.initialize():
        return {"ok": False, "error": "MT5 initialize failed"}
    
    info = mt5.account_info()
    if info is None:
        return {"ok": False, "error": "mt5.account_info() returned None"}
    
    return {
        "ok": True,
        "login": info.login,
        "server": info.server,
        "currency": info.currency,
        "balance": float(info.balance),
        "equity": float(info.equity),
        "margin": float(info.margin),
        "margin_free": float(info.margin_free),
        "margin_level": float(info.margin_level) if info.margin_level is not None else None,
    }


def fetch_open_positions(symbol: Optional[str] = None, magic: Optional[int] = None) -> List[Dict]:
    """
    Standalone function to fetch open positions
    
    Note: MT5 must be initialized before calling this function.
    Symbol filtering is case-insensitive.
    Returns list with error dict if MT5 connection issue.
    """
    # Check if MT5 is already initialized
    init_result = mt5.initialize()
    if not init_result:
        err = mt5.last_error()
        return [{"_error": f"MT5 initialize failed | last_error={err}"}]
    
    # IMPORTANT: detect MT5 connection status
    term = mt5.terminal_info()
    if term is None:
        err = mt5.last_error()
        return [{"_error": f"terminal_info None | last_error={err}"}]
    
    # Always fetch all positions first, then filter case-insensitive
    # This ensures we get all positions regardless of symbol case
    positions = mt5.positions_get()
    if positions is None:
        err = mt5.last_error()
        return [{"_error": f"positions_get None | last_error={err}"}]
    
    out = []
    for p in positions:
        # Filter by magic if specified
        if magic is not None and p.magic != magic:
            continue
        
        # p.type: 0=BUY, 1=SELL
        direction = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
        
        # Convert time to readable string
        try:
            time_open = datetime.fromtimestamp(int(p.time)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            time_open = str(p.time)
        
        out.append({
            "ticket": int(p.ticket),
            "symbol": str(p.symbol),
            "direction": direction,
            "lots": float(p.volume),
            "price_open": float(p.price_open),
            "sl": float(p.sl) if p.sl else 0.0,
            "tp": float(p.tp) if p.tp else 0.0,
            "profit": float(p.profit),
            "swap": float(p.swap) if hasattr(p, 'swap') else 0.0,
            "commission": float(p.commission) if hasattr(p, 'commission') else 0.0,
            "time_open": time_open,
            "magic": int(p.magic),
            "comment": str(p.comment) if hasattr(p, 'comment') else "",
        })
    
    # Filter by symbol case-insensitive if provided (after building list)
    if symbol:
        sym = symbol.lower()
        out = [x for x in out if x["symbol"].lower() == sym]
    
    return out


# ========== Profit from MT5 History Deals ==========

def _sum_deals_profit(dt_from: datetime, dt_to: datetime) -> Dict:
    """
    Sum profit, swap, commission from MT5 history deals in date range
    
    Args:
        dt_from: Start datetime (inclusive)
        dt_to: End datetime (exclusive)
        
    Returns:
        Dict with ok, deals count, profit, swap, commission, net
    """
    if not mt5.initialize():
        return {"ok": False, "error": "MT5 not initialized"}
    
    deals = mt5.history_deals_get(dt_from, dt_to)
    if deals is None:
        err = mt5.last_error()
        return {"ok": False, "error": f"history_deals_get None | last_error={err}"}
    
    profit = 0.0
    swap = 0.0
    commission = 0.0
    count = 0
    
    for d in deals:
        # Only count trading deals (exclude balance operations like deposit/withdrawal)
        # DEAL_TYPE_BALANCE = 6, DEAL_TYPE_CREDIT = 7, DEAL_TYPE_CHARGE = 8, DEAL_TYPE_CORRECTION = 9
        # DEAL_TYPE_BONUS = 10, DEAL_TYPE_COMMISSION = 11, DEAL_TYPE_COMMISSION_DAILY = 12
        # DEAL_TYPE_COMMISSION_MONTHLY = 13, DEAL_TYPE_COMMISSION_AGENT_DAILY = 14
        # DEAL_TYPE_COMMISSION_AGENT_MONTHLY = 15, DEAL_TYPE_INTEREST = 16
        # We only want: DEAL_TYPE_BUY = 0, DEAL_TYPE_SELL = 1 (and their close operations)
        
        # Filter: Only trading deals (have symbol and type < 6)
        deal_symbol = getattr(d, "symbol", None)
        deal_type = getattr(d, "type", None)
        
        # Skip if no symbol (not a trading deal) or if type >= 6 (balance operations)
        if not deal_symbol or (deal_type is not None and deal_type >= 6):
            continue
        
        # deal.profit includes profit for that deal; commission/swap are separate
        # Only sum profit/swap/commission from trading deals
        profit += float(getattr(d, "profit", 0.0) or 0.0)
        swap += float(getattr(d, "swap", 0.0) or 0.0)
        commission += float(getattr(d, "commission", 0.0) or 0.0)
        count += 1
    
    net = profit + swap + commission
    return {
        "ok": True,
        "deals": count,
        "profit": profit,
        "swap": swap,
        "commission": commission,
        "net": net,
        "from": dt_from.strftime("%Y-%m-%d"),
        "to": dt_to.strftime("%Y-%m-%d"),
    }


def fetch_profit_buckets(now: Optional[datetime] = None) -> Dict:
    """
    Fetch profit buckets from MT5 history deals:
    today, yesterday, this_week, last_week, this_month, last_month, this_year, last_year
    
    Returns:
        Dict with ok, asof timestamp, and buckets dict
    """
    now = now or datetime.now()
    
    # NOTE: MT5 expects naive datetime in local machine time; keep naive consistently
    today = now.date()
    
    # Today and yesterday
    today_start = datetime(today.year, today.month, today.day, 0, 0, 0)
    today_end = today_start + timedelta(days=1)
    yesterday_start = today_start - timedelta(days=1)
    yesterday_end = today_start
    
    # Week: ISO, start Monday
    iso = today.isocalendar()
    this_week_start = today.fromisocalendar(iso.year, iso.week, 1)
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = this_week_start
    
    # Month
    this_month_start = today.replace(day=1)
    last_month_end = this_month_start
    # Last month start: go back 1 day then set day=1
    prev_month_day = this_month_start - timedelta(days=1)
    last_month_start = prev_month_day.replace(day=1)
    
    # Year
    this_year_start = today.replace(month=1, day=1)
    last_year_end = this_year_start
    last_year_start = today.replace(year=today.year - 1, month=1, day=1)
    
    def dt(d: date) -> datetime:
        """date -> datetime start-of-day"""
        return datetime(d.year, d.month, d.day, 0, 0, 0)
    
    buckets = {
        "today": _sum_deals_profit(today_start, today_end),
        "yesterday": _sum_deals_profit(yesterday_start, yesterday_end),
        "this_week": _sum_deals_profit(dt(this_week_start), today_end),
        "last_week": _sum_deals_profit(dt(last_week_start), dt(last_week_end)),
        "this_month": _sum_deals_profit(dt(this_month_start), today_end),
        "last_month": _sum_deals_profit(dt(last_month_start), dt(last_month_end)),
        "this_year": _sum_deals_profit(dt(this_year_start), today_end),
        "last_year": _sum_deals_profit(dt(last_year_start), dt(last_year_end)),
    }
    
    return {
        "ok": True,
        "asof": now.strftime("%Y-%m-%d %H:%M:%S"),
        "buckets": buckets,
    }
