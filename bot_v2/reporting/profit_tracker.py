from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import pandas as pd


@dataclass
class ProfitTracker:
    initial_balance: float
    closed_trades: List[Dict[str, Any]] = field(default_factory=list)
    # mỗi trade dict nên có: close_time, pnl_usd

    def add_closed_trade(self, close_time: datetime, pnl_usd: float):
        self.closed_trades.append({"close_time": close_time, "pnl_usd": float(pnl_usd)})

    def _df(self) -> pd.DataFrame:
        if not self.closed_trades:
            return pd.DataFrame(columns=["close_time", "pnl_usd"])
        df = pd.DataFrame(self.closed_trades)
        df["close_time"] = pd.to_datetime(df["close_time"])
        df["date"] = df["close_time"].dt.date
        return df

    def snapshot(self, current_balance: float, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or datetime.now()
        df = self._df()

        def sum_between(d0: date, d1: date) -> float:
            """Sum PnL between d0 (inclusive) and d1 (exclusive)"""
            if df.empty:
                return 0.0
            mask = (df["date"] >= d0) & (df["date"] < d1)
            return float(df.loc[mask, "pnl_usd"].sum())

        today = now.date()
        year, week, weekday = today.isocalendar()
        
        # Current period starts
        week_start = today.fromisocalendar(year, week, 1)  # Monday of current week
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)
        
        # Previous period ranges
        from datetime import timedelta
        if week == 1:
            # First week of year - previous week is last week of previous year
            prev_week_start = date(year - 1, 12, 31) - timedelta(days=6)
            prev_week_end = week_start
        else:
            prev_week_start = today.fromisocalendar(year, week - 1, 1)
            prev_week_end = week_start
        
        if today.month == 1:
            prev_month_start = date(year - 1, 12, 1)
        else:
            prev_month_start = date(year, today.month - 1, 1)
        prev_month_end = month_start
        
        prev_year_start = date(year - 1, 1, 1)
        prev_year_end = year_start

        # Current period (this week/month/year) - include today
        from datetime import timedelta
        tomorrow = today + timedelta(days=1)
        wtd = sum_between(week_start, tomorrow)
        mtd = sum_between(month_start, tomorrow)
        ytd = sum_between(year_start, tomorrow)
        
        # Previous period (last week/month/year)
        last_week = sum_between(prev_week_start, prev_week_end)
        last_month = sum_between(prev_month_start, prev_month_end)
        last_year = sum_between(prev_year_start, prev_year_end)

        total = current_balance - self.initial_balance

        def pct(x: float) -> float:
            return (x / self.initial_balance) * 100.0 if self.initial_balance > 0 else 0.0

        return {
            "initial": self.initial_balance,
            "balance": current_balance,
            "total_usd": total,
            "total_pct": pct(total),
            # Current period
            "wtd_usd": wtd,
            "wtd_pct": pct(wtd),
            "mtd_usd": mtd,
            "mtd_pct": pct(mtd),
            "ytd_usd": ytd,
            "ytd_pct": pct(ytd),
            # Previous period
            "last_week_usd": last_week,
            "last_week_pct": pct(last_week),
            "last_month_usd": last_month,
            "last_month_pct": pct(last_month),
            "last_year_usd": last_year,
            "last_year_pct": pct(last_year),
            "closed_trades": 0 if df.empty else int(len(df)),
        }

