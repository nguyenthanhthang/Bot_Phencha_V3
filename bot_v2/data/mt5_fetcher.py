from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
except Exception as e:
    mt5 = None  # type: ignore


@dataclass
class MT5Credentials:
    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None


class MT5Fetcher:
    def __init__(self, creds: MT5Credentials | None = None):
        self.creds = creds or MT5Credentials()

    def connect(self) -> None:
        if mt5 is None:
            raise RuntimeError(
                "MetaTrader5 package not available. Install it and run on Windows with MT5 installed."
            )

        # If login info is not provided, try to initialize with the currently logged-in MT5 terminal
        if self.creds.login and self.creds.password and self.creds.server:
            ok = mt5.initialize(
                login=self.creds.login,
                password=self.creds.password,
                server=self.creds.server,
            )
        else:
            ok = mt5.initialize()

        if not ok:
            err = mt5.last_error()
            raise RuntimeError(f"MT5 initialize failed: {err}")

        term = mt5.terminal_info()
        if term is None:
            raise RuntimeError("MT5 terminal_info is None (terminal not ready).")

    def shutdown(self) -> None:
        if mt5 is not None:
            mt5.shutdown()

    def ensure_symbol(self, symbol: str) -> None:
        if mt5 is None:
            raise RuntimeError("MT5 not initialized.")
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Symbol not found in MT5: {symbol}")
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                raise RuntimeError(f"Failed to select symbol: {symbol}")

    def fetch_rates_range(
        self,
        symbol: str,
        timeframe: int,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV in [start, end).
        MT5 uses terminal timezone for datetime.
        """
        if mt5 is None:
            raise RuntimeError("MT5 not initialized.")
        self.ensure_symbol(symbol)

        rates = mt5.copy_rates_range(symbol, timeframe, start, end)
        if rates is None:
            err = mt5.last_error()
            raise RuntimeError(f"copy_rates_range returned None: {err}")
        if len(rates) == 0:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])

        df = pd.DataFrame(rates)
        # MT5 'time' is in seconds since epoch (UTC)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"tick_volume": "volume"})
        df = df[["time", "open", "high", "low", "close", "volume", "spread", "real_volume"]]
        return df

    @staticmethod
    def tf_name_to_mt5(tf_name: str) -> int:
        if mt5 is None:
            raise RuntimeError("MT5 not available.")
        mapping = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        if tf_name not in mapping:
            raise ValueError(f"Unsupported timeframe: {tf_name}")
        return mapping[tf_name]
