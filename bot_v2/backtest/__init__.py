"""Backtest Module"""

from .engine import run_backtest_dummy
from .metrics import compute_metrics
from .fill_model import FillModel, FillModelSimulator
from .report import BacktestReport
# from .scenarios import ScenarioRunner  # Commented out - needs BacktestEngine

__all__ = [
    'run_backtest_dummy',
    'compute_metrics',
    'FillModel',
    'FillModelSimulator',
    'BacktestReport',
    # 'ScenarioRunner'
]


