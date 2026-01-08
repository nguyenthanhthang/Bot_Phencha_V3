import csv
from pathlib import Path
from typing import Iterable

from execution.backtest_executor import Trade


def save_trades_csv(trades: Iterable[Trade], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "setup", "reason",
        "direction", "lot",
        "entry_time", "entry_price", "sl", "tp",
        "exit_time", "exit_price", "exit_reason",
        "pnl_usd",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in trades:
            w.writerow({
                "setup": t.setup,
                "reason": t.reason,
                "direction": t.direction,
                "lot": t.lot,
                "entry_time": t.entry_time,
                "entry_price": t.entry_price,
                "sl": t.sl,
                "tp": t.tp,
                "exit_time": t.exit_time,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "pnl_usd": t.pnl_usd,
            })
