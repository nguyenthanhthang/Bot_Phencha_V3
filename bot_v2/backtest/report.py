"""
Backtest Report Module
Generates backtest reports
"""

import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import json


class BacktestReport:
    """Generate backtest reports"""
    
    def __init__(self, metrics: Dict, trades: List[Dict], 
                 equity_curve: pd.Series):
        """
        Initialize report generator
        
        Args:
            metrics: Performance metrics dictionary
            trades: List of trade dictionaries
            equity_curve: Equity curve time series
        """
        self.metrics = metrics
        self.trades = trades
        self.equity_curve = equity_curve
        self.df_trades = pd.DataFrame(trades) if trades else pd.DataFrame()
    
    def generate_text_report(self) -> str:
        """Generate text report"""
        report = []
        report.append("=" * 60)
        report.append("BACKTEST REPORT")
        report.append("=" * 60)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Summary
        report.append("SUMMARY")
        report.append("-" * 60)
        report.append(f"Total Trades: {self.metrics.get('total_trades', 0)}")
        report.append(f"Win Rate: {self.metrics.get('win_rate', 0):.2f}%")
        report.append(f"Profit Factor: {self.metrics.get('profit_factor', 0):.2f}")
        report.append(f"Total P&L: ${self.metrics.get('total_pnl', 0):.2f}")
        report.append(f"Return: {self.metrics.get('return_pct', 0):.2f}%")
        report.append("")
        
        # Performance Metrics
        report.append("PERFORMANCE METRICS")
        report.append("-" * 60)
        report.append(f"Sharpe Ratio: {self.metrics.get('sharpe_ratio', 0):.2f}")
        report.append(f"Sortino Ratio: {self.metrics.get('sortino_ratio', 0):.2f}")
        report.append(f"Max Drawdown: ${self.metrics.get('max_drawdown', 0):.2f}")
        report.append(f"Max Drawdown %: {self.metrics.get('max_drawdown_pct', 0):.2f}%")
        report.append("")
        
        # Trade Statistics
        report.append("TRADE STATISTICS")
        report.append("-" * 60)
        report.append(f"Average Win: ${self.metrics.get('avg_win', 0):.2f}")
        report.append(f"Average Loss: ${self.metrics.get('avg_loss', 0):.2f}")
        report.append(f"Largest Win: ${self.metrics.get('largest_win', 0):.2f}")
        report.append(f"Largest Loss: ${self.metrics.get('largest_loss', 0):.2f}")
        report.append(f"Expectancy: ${self.metrics.get('expectancy', 0):.2f}")
        report.append("")
        
        # Monthly Breakdown
        if not self.df_trades.empty and 'time_close' in self.df_trades.columns:
            report.append("MONTHLY BREAKDOWN")
            report.append("-" * 60)
            monthly = self._calculate_monthly_stats()
            for month, stats in monthly.items():
                report.append(f"{month}: {stats['trades']} trades, "
                            f"P&L: ${stats['pnl']:.2f}")
            report.append("")
        
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def generate_html_report(self) -> str:
        """Generate HTML report"""
        html = []
        html.append("<!DOCTYPE html>")
        html.append("<html><head><title>Backtest Report</title>")
        html.append("<style>")
        html.append("body { font-family: Arial, sans-serif; margin: 20px; }")
        html.append("table { border-collapse: collapse; width: 100%; margin: 20px 0; }")
        html.append("th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }")
        html.append("th { background-color: #4CAF50; color: white; }")
        html.append("</style></head><body>")
        html.append("<h1>Backtest Report</h1>")
        html.append(f"<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>")
        
        # Summary table
        html.append("<h2>Summary</h2>")
        html.append("<table>")
        html.append("<tr><th>Metric</th><th>Value</th></tr>")
        html.append(f"<tr><td>Total Trades</td><td>{self.metrics.get('total_trades', 0)}</td></tr>")
        html.append(f"<tr><td>Win Rate</td><td>{self.metrics.get('win_rate', 0):.2f}%</td></tr>")
        html.append(f"<tr><td>Profit Factor</td><td>{self.metrics.get('profit_factor', 0):.2f}</td></tr>")
        html.append(f"<tr><td>Total P&L</td><td>${self.metrics.get('total_pnl', 0):.2f}</td></tr>")
        html.append(f"<tr><td>Return</td><td>{self.metrics.get('return_pct', 0):.2f}%</td></tr>")
        html.append("</table>")
        
        html.append("</body></html>")
        return "\n".join(html)
    
    def generate_json_report(self) -> str:
        """Generate JSON report"""
        report = {
            'generated': datetime.now().isoformat(),
            'metrics': self.metrics,
            'trade_count': len(self.trades)
        }
        return json.dumps(report, indent=2, default=str)
    
    def save_report(self, filepath: str, format: str = 'text') -> None:
        """
        Save report to file
        
        Args:
            filepath: Output file path
            format: Report format ('text', 'html', 'json')
        """
        if format == 'text':
            content = self.generate_text_report()
        elif format == 'html':
            content = self.generate_html_report()
        elif format == 'json':
            content = self.generate_json_report()
        else:
            raise ValueError(f"Unknown format: {format}")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def _calculate_monthly_stats(self) -> Dict:
        """Calculate monthly statistics"""
        if self.df_trades.empty or 'time_close' not in self.df_trades.columns:
            return {}
        
        self.df_trades['time_close'] = pd.to_datetime(self.df_trades['time_close'])
        self.df_trades['month'] = self.df_trades['time_close'].dt.to_period('M')
        
        monthly = self.df_trades.groupby('month').agg({
            'pnl': 'sum',
            'ticket': 'count'
        }).rename(columns={'ticket': 'trades'})
        
        return monthly.to_dict('index')


