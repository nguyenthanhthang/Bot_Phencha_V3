import pandas as pd
from typing import List

from execution.backtest_executor import BacktestExecutor, Trade
from strategies.session_v1 import SessionStrategyV1
from utils.config_loader import get_nested


def run_backtest_m15(df: pd.DataFrame, cfg: dict, symbol_specs: dict) -> list[Trade]:
    initial_balance = float(get_nested(cfg, "account.initial_balance", 1000))
    balance = initial_balance

    executor = BacktestExecutor(contract_size=float(symbol_specs.get("contract_size", 100.0)))
    strat = SessionStrategyV1(cfg, symbol_specs)

    trades: list[Trade] = []
    open_trade: Trade | None = None

    for i in range(len(df)):
        row = df.iloc[i]
        t_vn = row["time_vn"]

        # 1) manage open trade
        if open_trade is not None:
            exit_info = executor.check_exit(open_trade, row)
            if exit_info:
                exit_price, reason = exit_info
                open_trade.exit_time = pd.to_datetime(row["time"]).isoformat()
                open_trade.exit_price = float(exit_price)
                open_trade.exit_reason = reason
                open_trade.pnl_usd = executor.calc_pnl_usd(open_trade, float(exit_price))
                balance += float(open_trade.pnl_usd)
                trades.append(open_trade)
                open_trade = None

        # 2) entry if no trade
        if open_trade is None:
            sig = strat.get_signal(i, df, balance)
            if sig:
                # Extract setup from reason
                reason_str = getattr(sig, "reason", "")
                setup_str = ""
                if reason_str:
                    if "REACTION" in reason_str or "HVN_VAL" in reason_str:
                        setup_str = "A"
                    elif "SECOND_ENTRY" in reason_str or "SECOND" in reason_str:
                        setup_str = "B"
                    elif "VA_REENTRY" in reason_str or "REENTRY_TRAP" in reason_str or "VA_TRAP" in reason_str:
                        setup_str = "D"
                    elif "GAP" in reason_str or "LVN_GAP" in reason_str:
                        setup_str = "E"
                
                open_trade = Trade(
                    direction=sig.direction,
                    entry_time=pd.to_datetime(row["time"]).isoformat(),
                    entry_price=float(sig.entry_price),
                    sl=float(sig.sl),
                    tp=float(sig.tp),
                    lot=float(sig.lot),
                    setup=setup_str,
                    reason=reason_str,
                )

    # close end
    if open_trade is not None:
        last = df.iloc[-1]
        exit_price = float(last["close"])
        open_trade.exit_time = pd.to_datetime(last["time"]).isoformat()
        open_trade.exit_price = exit_price
        open_trade.exit_reason = "EOD"
        open_trade.pnl_usd = executor.calc_pnl_usd(open_trade, exit_price)
        trades.append(open_trade)

    return trades


def run_backtest_dummy(df_m15: pd.DataFrame, initial_balance: float = 1000.0) -> List[Trade]:
    """
    Dummy strategy for pipeline test:
    - Open BUY at first candle of each day at close price
    - SL = entry - 10
    - TP = entry + 15
    - lot = 0.01
    """
    executor = BacktestExecutor(contract_size=100.0)
    trades: List[Trade] = []

    open_trade: Trade | None = None
    last_day = None

    for _, row in df_m15.iterrows():
        t = pd.to_datetime(row["time"])
        day = t.date()

        # Manage open trade
        if open_trade is not None:
            exit_info = executor.check_exit(open_trade, row)
            if exit_info:
                exit_price, reason = exit_info
                open_trade.exit_time = t.isoformat()
                open_trade.exit_price = float(exit_price)
                open_trade.exit_reason = reason
                open_trade.pnl_usd = executor.calc_pnl_usd(open_trade, float(exit_price))
                trades.append(open_trade)
                open_trade = None

        # Open new trade once per day (if no open trade)
        if open_trade is None and day != last_day:
            entry = float(row["close"])
            open_trade = Trade(
                direction="BUY",
                entry_time=t.isoformat(),
                entry_price=entry,
                sl=entry - 10.0,
                tp=entry + 15.0,
                lot=0.01,
            )
            last_day = day

    # If still open at end, close at last close
    if open_trade is not None:
        last = df_m15.iloc[-1]
        t = pd.to_datetime(last["time"])
        exit_price = float(last["close"])
        open_trade.exit_time = t.isoformat()
        open_trade.exit_price = exit_price
        open_trade.exit_reason = "EOD"
        open_trade.pnl_usd = executor.calc_pnl_usd(open_trade, exit_price)
        trades.append(open_trade)

    return trades
