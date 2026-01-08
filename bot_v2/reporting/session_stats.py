"""
Session Statistics Module
Tracks statistics per trading session
"""

from typing import Dict, List, Optional
from datetime import datetime, date
from collections import defaultdict


class SessionStats:
    """Tracks session statistics"""
    
    def __init__(self):
        """Initialize session stats tracker"""
        self.session_stats: Dict[str, Dict] = defaultdict(lambda: {
            'trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'max_profit': 0.0,
            'max_loss': 0.0,
            'start_time': None,
            'end_time': None
        })
    
    def record_trade(self, session: str, pnl: float, 
                    trade_time: Optional[datetime] = None) -> None:
        """
        Record a trade for a session
        
        Args:
            session: Session name (e.g., 'asia', 'london', 'new_york')
            pnl: Profit/Loss of the trade
            trade_time: Trade time (default: now)
        """
        if trade_time is None:
            trade_time = datetime.now()
        
        stats = self.session_stats[session]
        stats['trades'] += 1
        
        if pnl > 0:
            stats['winning_trades'] += 1
            stats['max_profit'] = max(stats['max_profit'], pnl)
        else:
            stats['losing_trades'] += 1
            stats['max_loss'] = min(stats['max_loss'], pnl)
        
        stats['total_pnl'] += pnl
        
        if stats['start_time'] is None:
            stats['start_time'] = trade_time
        stats['end_time'] = trade_time
    
    def get_session_stats(self, session: str) -> Dict:
        """
        Get statistics for a session
        
        Args:
            session: Session name
            
        Returns:
            Statistics dictionary
        """
        stats = self.session_stats[session].copy()
        
        if stats['trades'] > 0:
            stats['win_rate'] = (stats['winning_trades'] / stats['trades']) * 100
            stats['avg_pnl'] = stats['total_pnl'] / stats['trades']
        else:
            stats['win_rate'] = 0.0
            stats['avg_pnl'] = 0.0
        
        return stats
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get all session statistics"""
        result = {}
        for session, stats in self.session_stats.items():
            result[session] = self.get_session_stats(session)
        
        return result
    
    def get_best_session(self) -> Optional[str]:
        """Get best performing session"""
        if not self.session_stats:
            return None
        
        return max(self.session_stats.keys(), 
                  key=lambda s: self.session_stats[s]['total_pnl'])
    
    def get_worst_session(self) -> Optional[str]:
        """Get worst performing session"""
        if not self.session_stats:
            return None
        
        return min(self.session_stats.keys(), 
                  key=lambda s: self.session_stats[s]['total_pnl'])
    
    def reset_session(self, session: str) -> None:
        """Reset statistics for a session"""
        if session in self.session_stats:
            del self.session_stats[session]
    
    def reset_all(self) -> None:
        """Reset all statistics"""
        self.session_stats.clear()
    
    def get_summary(self) -> str:
        """Get summary string"""
        summary = []
        summary.append("Session Statistics:")
        summary.append("-" * 60)
        
        for session, stats in self.get_all_stats().items():
            summary.append(f"\n{session.upper()}:")
            summary.append(f"  Trades: {stats['trades']}")
            summary.append(f"  Win Rate: {stats['win_rate']:.1f}%")
            summary.append(f"  Total P&L: ${stats['total_pnl']:.2f}")
            summary.append(f"  Avg P&L: ${stats['avg_pnl']:.2f}")
        
        return "\n".join(summary)


