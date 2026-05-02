# HMM Regime-Based Trading Bot: Technical Specification

**Project Name:** `ddos-trade-bot`
**Core Objective:** Develop an automated trading system that utilizes Hidden Markov Models (HMM) as a volatility classifier to dictate portfolio allocation and risk management.

---

## PHASE 1: Project Scaffolding & Environment Setup

### Directory Structure
```text
ddos-trade-bot/
├── config/
│   ├── settings.yaml          # All configurable parameters
│   └── credentials.yaml.example
├── core/
│   ├── __init__.py
│   ├── hmm_engine.py         # HMM regime detection engine
│   ├── regime_strategies.py  # Vol-based allocation strategies
│   ├── risk_manager.py       # Position sizing, leverage, drawdown limits
│   └── signal_generator.py   # Combines HMM + strategy into signals
├── broker/
│   ├── __init__.py
│   ├── alpaca_client.py      # Alpaca API wrapper
│   ├── order_executor.py     # Order placement, modification, cancellation
│   └── position_tracker.py   # Track open positions, P&L
├── data/
│   ├── __init__.py
│   ├── market_data.py        # Real-time and historical data fetching
│   └── feature_engineering.py # Technical indicators, feature computation
├── monitoring/
│   ├── __init__.py
│   ├── logger.py             # Structured logging
│   ├── dashboard.py          # Terminal-based live dashboard
│   └── alerts.py             # Email/webhook alerts for critical events
├── backtest/
│   ├── __init__.py
│   ├── backtester.py         # Walk-forward allocation backtester
│   ├── performance.py        # Sharpe, drawdown, regime breakdown, benchmarks
│   └── stress_test.py        # Crash injection, gap simulation
├── tests/
│   ├── test_hmm.py
│   ├── test_look_ahead.py    # Verify no look-ahead bias
│   ├── test_strategies.py
│   ├── test_risk.py
│   └── test_orders.py
├── main.py                   # Entry point
├── requirements.txt
├── .env.example
└── README.md
```

Initial Configuration
requirements.txt:

- hmmlearn

- alpaca-trade-api

- alpaca-py

- pandas, numpy, scipy

- ta (technical analysis library)

- scikit-learn

- pyyaml

- python-dotenv

- websocket-client

- schedule

- rich (for terminal dashboard)

settings.yaml Structure:
Create with ALL parameters, grouped by section, with defaults and comments:

- broker: paper_trading: true, symbols: [SPY, QQQ, AAPL, MSFT, AMZN, GOOGL, NVDA, META, TSLA, AMD], timeframe: 1Day

- hmm: n_candidates: [3, 4, 5, 6, 7], n_init: 10, covariance_type: full, min_train_bars: 252, stability_bars: 3, flicker_window: 20, flicker_threshold: 4, min_confidence: 0.55

- strategy: low_vol_allocation: 0.95, mid_vol_allocation_trend: 0.95, mid_vol_allocation_no_trend: 0.60, high_vol_allocation: 0.60, low_vol_leverage: 1.25, rebalance_threshold: 0.10, uncertainty_size_mult: 0.50

- risk: max_risk_per_trade: 0.01, max_exposure: 0.80, max_leverage: 1.25, max_single_position: 0.15, max_concurrent: 5, max_daily_trades: 20, daily_dd_reduce: 0.02, daily_dd_halt: 0.03, weekly_dd_reduce: 0.05, weekly_dd_halt: 0.07, max_dd_from_peak: 0.10

- backtest: slippage_pct: 0.0005, initial_capital: 100000, train_window: 252, test_window: 126, step_size: 126, risk_free_rate: 0.045

- monitoring: dashboard_refresh_seconds: 5, alert_rate_limit_minutes: 15

Environment (.env):
```text
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_PAPER=true
````

### PHASE 2: HMM Regime Detection Engine

DESIGN PHILOSOPHY:
 The HMM is a VOLATILITY CLASSIFIER. It detects whether the market is in a calm, moderate, or turbulent volatility environment. It does NOT predict price direction. The strategy layer uses the volatility classification to set portfolio allocation — be fully invested when conditions are calm, reduce when turbulent.

1. Gaussian HMM with Automatic Model Selection
- Test n_components = [3, 4, 5, 6, 7] during training.
- For each candidate, train and compute BIC (Bayesian Information Criterion): BIC = -2 * log_likelihood + n_params * log(n_samples)
- Select lowest BIC score (simplest model that explains the data).
- Run multiple random initializations per candidate (n_init=10).
- Log ALL candidate BIC scores and which was selected.
- Labeling (Sorted by mean return ascending):
    - Lowest return $\rightarrow$ CRASH / BEAR
    - Highest return $\rightarrow$ BULL / EUPHORIA
    - Assign labels based on selected count (e.g., 3 regimes: BEAR, NEUTRAL, BULL; 4 regimes: CRASH, BEAR, BULL, EUPHORIA, etc.).
    - IMPORTANT: Labels are sorted by return for human readability. But the STRATEGY layer sorts by VOLATILITY independently. The labels don't drive strategy decisions.

2. Observable Features (Inputs to HMM)
Compute from OHLCV in data/feature_engineering.py as pure functions:

- Returns: log returns over 1, 5, 20 periods

- Volatility: realized vol (20-period rolling std), vol ratio (5-period / 20-period)

- Volume: normalized volume (z-score vs 50-period mean), volume trend (slope of 10-period SMA)

- Trend: ADX (14-period), slope of 50-period SMA

- Mean Reversion: RSI(14) z-score, distance from 200 SMA as % of price

- Momentum: ROC 10 and 20 period

- Range: normalized ATR (14-period ATR / close)

- Standardization: Standardize ALL features with rolling z-scores (252-period lookback).

3. Model Training
- hmmlearn.GaussianHMM, covariance_type="full"

- Minimum 2 years daily data (504 trading days)

- Expanding window retraining: retrain at configurable intervals

- Store model with pickle + metadata (n_regimes, bic, training_date, labels)

- Log: likelihood, BIC, convergence, iterations

4. Regime Detection — NO LOOK-AHEAD BIAS
*** THIS IS THE MOST IMPORTANT TECHNICAL DETAIL. ***
DO NOT use model.predict(). predict() runs the Viterbi algorithm which processes the ENTIRE sequence and revises past states using future data. This is look-ahead bias that makes backtests unrealistically good.

INSTEAD implement FORWARD ALGORITHM ONLY (filtered inference):
```
def predict_regime_filtered(self, features_up_to_now):
    """
    Compute P(state_t | observations_1:t) using forward algorithm.
    Uses ONLY past and present data. No future data.
    """
    # Use model's startprob_, transmat_, means_, covars_
    # Implement forward pass manually:
    # 1. alpha_0 = startprob * emission_prob(obs_0)
    # 2. alpha_t = (alpha_{t-1} @ transmat) * emission_prob(obs_t)
    # 3. Normalize at each step (work in log space)
    # 4. alpha_T = filtered distribution at current time
    # Cache previous alpha for efficiency in live/backtest loop
```
Mandatory Test (tests/test_look_ahead.py): Verify regime_short == regime_long.

5. Regime Stability Filter & Metadata
- Regime change only "confirmed" after persisting N bars (default 3).

- During transition: keep previous regime, reduce sizes by 25%.

- Track flicker rate (changes per 20 bars). If > threshold (4), force uncertainty mode.

- Regime Metadata:

    - RegimeInfo dataclass: regime_id, regime_name, expected_return, expected_volatility, recommended_strategy_type, max_leverage_allowed, max_position_size_pct, min_confidence_to_act.

    - RegimeState dataclass: label, state_id, probability, state_probabilities, timestamp, is_confirmed, consecutive_bars.

- Log regime changes as WARNING. Log confirmations as INFO.

### PHASE 3: Volatility-Based Allocation Strategy

DESIGN INSIGHT:
 The HMM excels at detecting VOLATILITY ENVIRONMENTS, not market direction. Stocks trend upward roughly 70% of the time in low-volatility periods. The worst drawdowns cluster in high-volatility spikes.
So the strategy is simple:
- Low vol $\rightarrow$ be fully invested (calm markets trend up)
- Mid vol $\rightarrow$ stay invested if trend intact, reduce if not
- High vol $\rightarrow$ reduce but stay partially invested (catch V-shaped rebounds)
ALWAYS LONG. NEVER SHORT. Shorting destroys returns due to upward drift and V-shaped recoveries.

THREE STRATEGY CLASSES (based on volatility rank):
- LowVolBullStrategy (lowest third of regimes by expected_volatility):

    - Direction: LONG

    - Allocation: 95% of portfolio

    - Leverage: 1.25x (modest leverage in calm conditions)

    - Stop: max(price - 3 ATR, 50 EMA - 0.5 ATR)

- MidVolCautiousStrategy (middle third):

    - Direction: LONG

    - If price > 50 EMA: allocation 95%, leverage 1.0x

    - If price < 50 EMA: allocation 60%, leverage 1.0x

    - Stop: 50 EMA - 0.5 ATR

- HighVolDefensiveStrategy (top third):

    - Direction: LONG (NOT short)

    - Allocation: 60% of portfolio

    - Leverage: 1.0x

    - Stop: 50 EMA - 1.0 ATR (wider for volatile conditions)

Strategy Orchestrator & Logic
- Volatility Rank Mapping: Map each regime's vol rank to a strategy. position = rank / (n_regimes - 1). <= 0.33 $\rightarrow$ LowVolBull, >= 0.67 $\rightarrow$ HighVolDefensive, else $\rightarrow$ MidVolCautious. Independent of return labels.
- Confidence & Uncertainty: Minimum confidence threshold: 0.55. Uncertainty mode triggers when prob < threshold, or is_flickering=True. In uncertainty mode: halve all position sizes, force leverage to 1.0x. Append "[UNCERTAINTY — size halved]" to reasoning.
- Rebalancing: Only rebalance when target allocation differs from current by >10% to prevent churn.
- Implementation: BaseStrategy ABC, StrategyOrchestrator, Signal dataclass (symbol, direction, confidence, entry_price, stop_loss, take_profit, position_size_pct, leverage, regime data, timestamp, reasoning). Keep backward-compatible aliases for classes.

PHASE 4: Walk-Forward Backtesting & Validation
This is an ALLOCATION-BASED walk-forward backtester. It sets a target portfolio allocation each bar based on the detected volatility regime and rebalances when the allocation changes meaningfully.

1. Walk-Forward Optimization Engine (backtester.py)
    - Rolling windows: In-Sample (IS): 252 trading days. Out-of-Sample (OOS): 126 trading days. Step size: 126 trading days.

    - Bar-by-bar Execution:

        - Compute features using ONLY data up to current bar.

        - Run filtered HMM (forward algorithm).

        - Get strategy signal target allocation. If changed >10%, rebalance.

        - Mark to market: equity = cash + shares * price

    - Allocation Math (must be exactly correct):

    ```code 
        equity = cash + shares * current_price
        target_shares = int(equity * target_allocation / current_price)
        delta = target_shares - current_shares
        cash -= delta * price
        shares = target_shares

    ```
    When leverage > 1.0, target_allocation > 1.0, so target_shares * price > equity, making cash negative. This is margin.
    - Realistic Simulation: Slippage 0.05% per rebalance, Rebalancing threshold 10%, Fill delay 1 bar, No individual trade stops in backtester, Commission $0 default.

2. Performance Metrics (performance.py)
    - Core: Total return (%), CAGR, Sharpe ratio, Sortino ratio, Calmar ratio, Max drawdown (% and duration), Win rate, avg win/loss, profit factor, total trades, avg holding period.

    - Regime-specific (table format): Regime | % Time In | Return Contribution | Avg Trade P&L | Win Rate | Sharpe

    - Confidence-bucketed: < 50%, 50-60%, 60-70%, 70%+

    - Benchmark comparisons (--compare flag): Buy-and-hold, 200 SMA trend, Random entry + same risk management (100 Monte Carlo seeds).

    - Worst-case: worst day, worst week, worst month, max consecutive losses, longest time underwater.

    - Output: Rich formatted tables to terminal. Save CSVs (equity_curve, trade_log, regime_history, benchmark_comparison).

3. Stress Testing (stress_test.py)
    - Crash injection: insert -5% to -15% single-day gaps at 10 random points. Run 100 Monte Carlo simulations. Report mean max loss, worst case, % where circuit breaker fired.

    - Gap risk: insert overnight gaps of 2-5x ATR at random points.

    - Regime misclassification: deliberately shuffle regime labels to verify risk management contains damage.


PHASE 5: Risk Management Layer
The risk manager operates INDEPENDENTLY of the HMM. It has ABSOLUTE VETO POWER over any signal.

1. Portfolio-Level Limits
    - Max total exposure: 80% of portfolio (20% cash minimum). Note: with 1.25x leverage, notional exposure exceeds equity but margin stays within limits.

    - Max single position: 15%

    - Max correlated exposure: 30% in one sector

    - Max concurrent positions: 5

    - Max daily trades: 20

    - Max portfolio leverage: 1.25x

2. Circuit Breakers (fire on actual P&L, independent of regime)
    - Daily DD > 2%: reduce all sizes 50% rest of day

    - Daily DD > 3%: close ALL positions, halt rest of day

    - Weekly DD > 5%: reduce all sizes 50% rest of week

    - Weekly DD > 7%: close ALL, halt rest of week

    - Peak DD > 10%: halt ALL trading, write trading_halted.lock file requiring manual deletion to resume.

    - Log every trigger.

3. Position-Level Risk
    - Every position MUST have a stop loss — system refuses orders without one.

    - Max risk per trade: 1% of portfolio. Position size = (portfolio * 0.01) / abs(entry - stop_loss)

    - Cap at regime max, then portfolio max (15%). Minimum position: $100.

    - GAP RISK: overnight positions assume 3x stop gap-through. Overnight size = min(normal, size where 3x gap = 2% of portfolio)

4. Leverage Rules
    - Default: 1.0x. Only low-vol regimes may use up to 1.25x.

    - Force 1.0x if: regime uncertain, any circuit breaker active, 3+ positions open, high flicker rate.

5. Order Validation & Correlation
    - Order Validation: Check buying power, tradeable status, bid-ask spread < 0.5%. Block duplicates (within 60 seconds). Log every rejection with structured reason.
    - Correlation Check: 60-day rolling correlation with existing positions. > 0.7 $\rightarrow$ reduce size 50%. > 0.85 $\rightarrow$ reject trade.

Implementation Objects
RiskManager: validate_signal(signal, portfolio_state) -> RiskDecision, RiskDecision, PortfolioState, CircuitBreaker. All thresholds from settings.yaml.
    

PHASE 6: Alpaca Broker Integration
1. broker/alpaca_client.py
    - alpaca-py SDK wrapper. Credentials from .env (NEVER hardcoded).

    - Endpoints: Paper (DEFAULT) vs Live.

    - If paper_trading: false, require confirmation: "⚠️ LIVE TRADING MODE. Type 'YES I UNDERSTAND THE RISKS' to confirm:"

    - Methods: get_account(), get_positions(), get_order_history(), is_market_open(), get_clock(), get_available_margin(). Health check on startup, auto-reconnect with exponential backoff.


2. broker/order_executor.py
    - submit_order(signal): LIMIT orders by default (+/- 0.1% of current price), cancel after 30s if unfilled, optionally retry at market.
    - submit_bracket_order(signal): entry + stop + take_profit via Alpaca OCO.
    - modify_stop(): only tighten, never widen. cancel_order(), close_position().
    - Unique trade_id linking signal $\rightarrow$ risk_decision $\rightarrow$ order $\rightarrow$ fill.

3. broker/position_tracker.py
    - WebSocket subscription for instant fill notifications. Update PortfolioState and CircuitBreaker on every fill.

    - Per-position tracking: entry time/price, current price, unrealized P&L, stop level, holding period, regime at entry vs current. Sync with Alpaca on startup.
   
   
4. data/market_data.py
Historical and real-time data fetching, WebSockets for spread checks. Graceful handling of gaps (weekends, holidays, halts).

PHASE 7: Main Loop & OrchestrationSTARTUP:Load config, connect to Alpaca, verify account.Check market hours (wait or exit if closed).Load or train HMM (if model >7 days old or missing, retrain).Initialize risk manager with current portfolio from Alpaca.Initialize position tracker, sync positions.Check for state_snapshot.json (recovery from previous session).Start WebSocket data feeds.Print system state, log "System online".MAIN LOOP (each bar close, default 5-min bars):New bar from WebSocket.Compute features (rolling window, no future data).Filtered HMM prediction (forward algorithm only).Regime stability check (3-bar persistence).Flicker rate check $\rightarrow$ uncertainty mode if high.StrategyOrchestrator: target allocation per symbol.For each signal: risk_manager.validate_signal() $\rightarrow$ approved / modified / rejected.Update trailing stops per regime.Circuit breaker check.Dashboard refresh.Weekly: retrain HMM.SHUTDOWN (SIGINT/SIGTERM):Close WebSocket connections.Do NOT close positions (stops in place).Save state_snapshot.json. Print session summary.

PHASE 8: Monitoring, Alerts & Dashboard
Error Handling & CLI
Error Handling: Alpaca API: 3 retries, exponential backoff. HMM error: hold current regime. Data feed drop: pause signals, keep stops active. Unhandled: log traceback, save state, alert.

CLI Flags: --dry-run (no orders), --backtest (walk-forward), --train-only, --stress-test, --compare (benchmark comparisons), --dashboard (show for running instance).

Monitoring Package
logger.py: Structured JSON logging. Rotating files (10MB, 30 days): main.log, trades.log, alerts.log, regime.log. Includes: timestamp, regime, probability, equity, positions, daily_pnl.

dashboard.py (rich library): Real-time terminal tracking. Shows: REGIME (label, probability, stability, flicker), PORTFOLIO (equity, daily P&L, allocation, leverage), POSITIONS (symbol, long/short, price, return, stop, time in trade), RECENT SIGNALS, RISK STATUS (DD, peak DD), SYSTEM (Data, API latency, HMM age, PAPER/LIVE flag). Refreshes every 5 seconds.

alerts.py: Triggers on regime change, circuit breaker, large P&L, feed down, API lost, HMM retrained, flicker exceeded. Delivery via console, log, email/webhook (optional). Rate limit: 1 per event type per 15 minutes.

PHASE 9: Integration Testing & Documentation1. Testsa. End-to-end dry run: data $\rightarrow$ HMM $\rightarrow$ strategy $\rightarrow$ risk $\rightarrow$ simulated orders.b. Look-ahead bias: test_look_ahead.py passes, backtest identical with different end dates.c. Risk stress: extreme signals capped, rapid-fire blocked, no-stop rejected.d. Alpaca paper: place bracket order, modify stop, cancel, verify clean state.e. Recovery: kill process, restart, verify state recovery and no double-entry.2. Documentation & SettingsREADME.md: Philosophy ("risk management > signal generation"), Architecture diagram, Quick start (6 steps), CLI reference, Configuration guide, FAQ (forward algorithm, BIC selection, live trading switch), Disclaimer (educational, no guaranteed profits, paper trade first).settings.yaml: Complete, documented, production-ready defaults for paper trading.






