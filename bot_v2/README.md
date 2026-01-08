# Bot PhenCha V3

Trading bot framework for MetaTrader 5 with support for multiple strategies, risk management, and backtesting.

## Structure

```
bot_v1/
├── config/              # Configuration files
│   ├── settings.yaml    # Bot settings
│   ├── backtest.yaml    # Backtest configuration
│   ├── symbols.yaml     # Trading symbols configuration
│   └── telegram.yaml    # Telegram notification settings
│
├── data/                # Data fetching and caching
│   ├── mt5_fetcher.py   # MT5 data fetcher
│   ├── data_cache.py    # Data caching
│   └── resample.py      # Data resampling
│
├── indicators/          # Technical indicators
│   ├── atr.py           # ATR indicator
│   ├── rsi.py           # RSI indicator
│   └── bollinger.py     # Bollinger Bands
│
├── strategies/          # Trading strategies
│   ├── asia_mean_reversion.py  # Asia session mean reversion
│   └── london_orb.py    # London opening range breakout
│
├── risk/                # Risk management
│   ├── position_sizing.py  # Position sizing
│   ├── daily_risk.py    # Daily risk limits
│   └── trade_filters.py # Trade filters
│
├── execution/           # Order execution
│   ├── mt5_executor.py  # MT5 live execution
│   └── backtest_executor.py  # Backtest execution
│
├── backtest/            # Backtesting engine
│   ├── engine.py        # Backtest engine
│   ├── fill_model.py    # Fill models
│   ├── metrics.py       # Performance metrics
│   ├── report.py        # Report generation
│   └── scenarios.py     # Scenario testing
│
├── notification/        # Notifications
│   ├── telegram_client.py  # Telegram client
│   ├── templates.py     # Message templates
│   └── notifier.py      # Notification interface
│
├── reporting/           # Reporting and logging
│   ├── trade_logger.py  # Trade logging
│   ├── equity_curve.py  # Equity curve tracking
│   └── session_stats.py # Session statistics
│
├── utils/               # Utilities
│   ├── time_utils.py    # Time utilities
│   ├── math_utils.py    # Math utilities
│   └── logger.py        # Logging setup
│
├── runner_live.py       # Live trading runner
└── runner_backtest.py   # Backtest runner
```

## Installation

1. Install required packages:
```bash
pip install MetaTrader5 pandas numpy pyyaml requests pytz matplotlib
```

2. Configure MT5:
   - Install MetaTrader 5
   - Enable automated trading
   - Configure account credentials in config files

3. Configure Telegram (optional):
   - Get bot token from @BotFather
   - Get your chat ID
   - Update `config/telegram.yaml`

## Configuration

### Settings (`config/settings.yaml`)
- Bot mode (live/backtest/paper)
- Trading limits
- Time settings
- Logging configuration

### Symbols (`config/symbols.yaml`)
- Trading symbols
- Lot sizes
- Pip values

### Telegram (`config/telegram.yaml`)
- Bot token
- Chat ID
- Notification rules

## Usage

### Live Trading
```bash
python runner_live.py
```

### Backtesting
```bash
python runner_backtest.py
```

## Strategies

### Asia Mean Reversion
Mean reversion strategy for Asia trading session.

### London ORB
Opening Range Breakout strategy for London session.

## Risk Management

- Position sizing based on risk percentage
- Daily loss limits
- Maximum concurrent positions
- Trade filters (spread, volatility, time)

## Features

- ✅ Multiple trading strategies
- ✅ Risk management
- ✅ Backtesting engine
- ✅ Telegram notifications
- ✅ Trade logging
- ✅ Performance metrics
- ✅ Equity curve tracking
- ✅ Session statistics

## Notes

- This is a framework/skeleton. Implement actual strategy logic in strategy files.
- Test thoroughly in demo account before live trading.
- Always use proper risk management.

## License

Private use only.


