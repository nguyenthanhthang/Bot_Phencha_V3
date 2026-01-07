from typing import List, Dict
from execution.backtest_executor import Trade


def compute_metrics(initial_balance: float, trades: List[Trade]) -> Dict[str, float]:
    balance = initial_balance
    peak = initial_balance
    max_dd = 0.0

    wins = 0
    losses = 0
    total_pnl = 0.0

    for t in trades:
        pnl = float(t.pnl_usd or 0.0)
        balance += pnl
        total_pnl += pnl

        if pnl >= 0:
            wins += 1
        else:
            losses += 1

        if balance > peak:
            peak = balance
        dd = (peak - balance)
        if dd > max_dd:
            max_dd = dd

    n = len(trades)
    winrate = (wins / n * 100.0) if n else 0.0
    ret_pct = ((balance - initial_balance) / initial_balance * 100.0) if initial_balance else 0.0

    return {
        "trades": float(n),
        "final_balance": float(balance),
        "total_pnl_usd": float(total_pnl),
        "return_pct": float(ret_pct),
        "max_drawdown_usd": float(max_dd),
        "winrate_pct": float(winrate),
        "wins": float(wins),
        "losses": float(losses),
    }
