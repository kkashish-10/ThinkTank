# HMM Regime-Based Trading Bot

An automated trading system that uses Hidden Markov Models (HMM) as a volatility classifier to dictate portfolio allocation and risk management.

**Project Status**: Phase 1 Complete - Project Scaffolding & Environment Setup

## Overview

The trading bot implements a sophisticated approach to portfolio management:

1. **Regime Detection** - Uses Hidden Markov Models to classify market volatility into discrete regimes (low, medium, high volatility)
2. **Regime-Based Allocation** - Maps each volatility regime to specific portfolio allocations and leverage levels
3. **Risk Management** - Enforces strict position sizing, leverage limits, and drawdown controls
4. **Live Trading & Backtesting** - Full backtesting with walk-forward analysis and live paper/live trading capability

## Project Structure

```
ddos-trade-bot/
├── config/                     # Configuration files
│   ├── settings.yaml          # All trading parameters
│   └── credentials.yaml.example
├── core/                       # Core trading engine
│   ├── hmm_engine.py          # HMM regime detection
│   ├── regime_strategies.py   # Allocation strategies
│   ├── risk_manager.py        # Risk controls
│   └── signal_generator.py    # Signal generation
├── broker/                     # Broker integration
│   ├── alpaca_client.py       # Alpaca API wrapper
│   ├── order_executor.py      # Order management
│   └── position_tracker.py    # Position tracking
├── data/                       # Data handling
│   ├── market_data.py         # Data fetching
│   └── feature_engineering.py # Technical indicators
├── monitoring/                 # Monitoring & alerts
│   ├── logger.py              # Structured logging
│   ├── dashboard.py           # Live dashboard
│   └── alerts.py              # Alert system
├── backtest/                   # Backtesting
│   ├── backtester.py          # Walk-forward backtester
│   ├── performance.py         # Performance analysis
│   └── stress_test.py         # Stress testing
├── tests/                      # Test suite
│   ├── test_hmm.py
│   ├── test_look_ahead.py     # Look-ahead bias verification
│   ├── test_strategies.py
│   ├── test_risk.py
│   └── test_orders.py
├── main.py                     # Entry point
├── requirements.txt
├── .env.example
└── README.md
```

## Quick Start

### 1. Clone and Setup

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy example configuration files
cp config/credentials.yaml.example config/credentials.yaml
cp .env.example .env

# Edit your credentials
# config/credentials.yaml - Alpaca API keys
# .env - Environment variables
```

### 3. Run Backtest

```bash
python main.py --mode backtest \
  --start-date 2023-01-01 \
  --end-date 2024-01-01 \
  --config config/settings.yaml
```

### 4. Paper Trading

```bash
python main.py --mode paper --config config/settings.yaml
```

### 5. Run Tests

```bash
pytest tests/ -v --cov=.
```

## Configuration Guide

All trading parameters are in `config/settings.yaml`:

- **broker** - Alpaca connection and symbols
- **hmm** - HMM model parameters for regime detection
- **strategy** - Allocation rules by regime
- **risk** - Position sizing, leverage, and drawdown limits
- **backtest** - Backtesting parameters (slippage, initial capital, windows)
- **monitoring** - Dashboard refresh rate, alert limits

See [config/settings.yaml](config/settings.yaml) for detailed parameter descriptions.

## Dependencies

- **hmmlearn** - Hidden Markov Model implementation
- **alpaca-py** - Alpaca broker API
- **pandas/numpy/scipy** - Data manipulation and numerical computing
- **ta** - Technical analysis indicators
- **scikit-learn** - Machine learning utilities
- **pyyaml** - Configuration file parsing
- **python-dotenv** - Environment variable loading
- **websocket-client** - WebSocket support for streaming data
- **schedule** - Job scheduling
- **rich** - Terminal dashboard and formatting

## Phase 1 Completion Status

✅ **Complete**

### Delivered

- [x] Full directory structure with 7 core modules
- [x] 20 Python module stubs with comprehensive docstrings
- [x] Configuration files (settings.yaml with all parameters)
- [x] Credential templates (credentials.yaml.example)
- [x] Environment template (.env.example)
- [x] Dependencies specification (requirements.txt)
- [x] Main entry point (main.py)
- [x] Comprehensive README and setup instructions
- [x] Standard .gitignore for Python projects
- [x] Test suite structure (5 test modules)

### Project is ready for Phase 2: HMM Regime Detection Engine Implementation

## Next Steps (Phase 2)

- Implement HMM model fitting and regime detection
- Implement feature engineering (volatility, trend indicators)
- Implement regime-based strategy allocation
- Implement risk management and position sizing
- Run comprehensive backtests and analysis

## Notes

- **Paper Trading**: Set `ALPACA_PAPER=true` in .env for safe testing
- **Live Trading**: Only enable with thoroughly tested strategies
- **Credentials**: Never commit actual credentials; use .env and credentials.yaml
- **Backtesting**: Walk-forward testing prevents look-ahead bias

## Support

For issues or questions, refer to the docstrings in individual modules or the technical specification document.

---

**Created**: May 2, 2026  
**Last Updated**: May 2, 2026  
**Status**: Phase 1 Complete
