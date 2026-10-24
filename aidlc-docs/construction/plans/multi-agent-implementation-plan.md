# Detailed Multi-Agent Trading System Implementation Plan (Production Hardened)

**Target System**: `ddos-trade-bot` (ThinkTank Workspace)  
**Architecture**: Asynchronous Event-Driven Multi-Agent Framework  
**Verification & Front-End**: TradingView Visual Paper Trading via native Alpaca link + TradingView Webhook Alerts  
**Key Features**:
1. HMM Volatility Regime Detection (Sorted states, Forward-only algorithm) + Macro/Sentiment + Technical Indicators
2. Dynamic Allocation (Calm Bull, Choppy Neutral, Defensive Cash, Bear Hedging via Inverse ETFs `SH`/`PSQ` & Shorts)
3. Quantitative Risk Guardian with **Pending Capital Reservation Lock** and persistent opening equity
4. Human-in-the-Loop (HITL) Interactive Approval via Telegram with 0.3% price-drift guard
5. Hardened TradingView Integration (FastAPI Webhook + Cloudflare Tunnel + Rate Limiting + Native Alpaca Chart Visualization)
6. Robust Broker Execution (Bracket Orders, OCO Stops/Targets, Atomic WebSocket Event Matrix, 60s REST Reconciliation)

---

## Architecture & Directory Layout

```text
ddos-trade-bot/
├── agents/                           # Multi-Agent Subsystem
│   ├── __init__.py
│   ├── base_agent.py                 # Abstract base agent class & lifecycle
│   ├── quant_regime_agent.py         # Wraps HMM engine (sorted states, forward-only)
│   ├── technical_agent.py            # Trend, RSI, EMA, ATR, support/resistance
│   ├── macro_sentiment_agent.py      # Macro calendar, news sentiment, non-blocking fallback
│   ├── cio_portfolio_agent.py        # Thesis synthesizer & target allocator
│   ├── risk_guardian_agent.py        # Absolute veto, sizing hierarchy, capital reservation
│   ├── hitl_gateway_agent.py         # Telegram interactive approval with 0.3% drift guard
│   ├── execution_agent.py            # Alpaca bracket orders (long) & sequential OCO (short)
│   └── supervisor_agent.py           # Position monitoring, trailing stops, kill switch
├── core/
│   ├── __init__.py
│   ├── state_models.py               # Pydantic schemas: TradingState, Signal, Proposal
│   ├── orchestrator.py               # Async multi-agent workflow coordinator & deduplication
│   ├── hmm_engine.py                 # Forward-algorithm HMM, BIC selection, covariance sort
│   ├── regime_strategies.py          # Allocation mapping & bear hedging policies
│   └── risk_manager.py               # Mathematical formulas, circuit breakers & capital locks
├── broker/
│   ├── __init__.py
│   ├── alpaca_client.py              # Alpaca REST API & account interface
│   ├── order_executor.py             # Bracket order generator (OCO limit/stop)
│   └── position_tracker.py           # WebSocket event matrix & 60s REST reconciliation
├── hitl/
│   ├── __init__.py
│   ├── telegram_bot.py               # python-telegram-bot async long-polling
│   └── whatsapp_client.py            # Optional Twilio/Meta WhatsApp client
├── tradingview/                      # TradingView Integration Module
│   ├── __init__.py
│   ├── webhook_server.py             # FastAPI async webhook listener with rate limiting
│   ├── tunnel_manager.py             # Cloudflare Tunnel (cloudflared) auto-launcher
│   └── alert_parser.py               # Validates passphrase (secrets.compare_digest) & extracts alert
├── data/
│   ├── __init__.py
│   ├── market_data.py                # Alpaca historical & live bar fetching
│   └── feature_engineering.py        # Technical features, z-scores, ATR
├── backtest/
│   ├── __init__.py
│   ├── backtester.py                 # Walk-forward backtesting engine
│   ├── performance.py                # Sharpe, Sortino, drawdowns, benchmarks
│   └── stress_test.py                # Crash injection, gap tests, label shuffling
├── config/
│   ├── settings.yaml                 # System configuration
│   └── credentials.yaml.example
├── tests/
│   ├── test_state_models.py
│   ├── test_hmm_forward.py           # Zero look-ahead & sorted states test
│   ├── test_risk_guardian.py         # Sizing hierarchy, capital reservation & circuit breakers
│   ├── test_bear_hedging.py          # Cash preservation & inverse ETF tests
│   ├── test_telegram_hitl.py         # Mock Telegram callback & slippage drift tests
│   ├── test_tradingview_webhook.py   # Test TradingView alert authentication & rate limit
│   └── test_execution_brackets.py    # Alpaca bracket orders, partial fills & OCO tests
├── main.py                           # Application entry point
├── requirements.txt
└── .env.example
```

---

## 6 Production Hardening Specifications

### Specification 1: Inbound Webhook Delivery on Localhost (Cloudflare Tunnel)
- **Problem Solved**: TradingView cloud servers cannot route HTTP requests to `localhost:8080`.
- **Implementation**:
  - In `tradingview/tunnel_manager.py`: Provide automated launcher for Cloudflare Quick Tunnels:
    ```bash
    cloudflared tunnel --url http://localhost:8080
    ```
  - Outputs an ephemeral or named public HTTPS URL (e.g. `https://your-bot-relay.trycloudflare.com/webhook/tradingview`).
  - Paste this HTTPS URL directly into TradingView Alert settings (`Webhook URL` checkbox).

### Specification 2: Concurrent Alert Capital Reservation Lock
- **Problem Solved**: Simultaneous alerts at market open over-allocating buying power and causing margin rejections.
- **Implementation in `core/risk_manager.py`**:
  - Maintain thread-safe `pending_hitl_capital` state:
    $$\text{Effective Available Equity} = \text{Total Equity} - \text{Active Exposure} - \text{Pending HITL Capital}$$
  - When `CIO` generates an approved `TradeProposal`, the `RiskGuardian` checks against $\text{Effective Available Equity}$ and increments `pending_hitl_capital += proposed_notional`.
  - When the user taps `[REJECT]` on Telegram or the proposal times out, `pending_hitl_capital -= proposed_notional` is immediately released.
  - When the user taps `[APPROVE]`, the reservation converts into an active position upon fill.

### Specification 3: Dual-Trigger Deduplication & Idempotency
- **Problem Solved**: Duplicate Telegram alerts when both a TradingView Pine Script webhook and the bot's internal bar close schedule fire for the same stock.
- **Implementation in `core/orchestrator.py`**:
  - Compute `idempotency_key = f"{symbol}_{side}_{bar_timestamp}"`.
  - Maintain an in-memory 60-second sliding debounce cache per symbol.
  - If a signal for `symbol` with the same `side` arrives within 60 seconds of an existing pending proposal or open position, suppress the second signal and log: `"Duplicate signal suppressed by debounce filter"`.

### Specification 4: Atomic WebSocket Event Matrix & 60s REST Reconciliation
- **Problem Solved**: Alpaca partial fills, bracket cancellation drops, and network desynchronization.
- **Implementation in `broker/position_tracker.py`**:
  - Implement an atomic WebSocket message dispatcher:
    - `order_partially_filled`: Immediately update active position quantity to actual filled shares; adjust bracket stop tracking to filled units.
    - `order_canceled` / `order_expired`: Clean up open order tracking and release any associated capital lock.
    - `order_filled` on stop: Trigger full position closure cleanup, notify Telegram, and update daily P&L.
  - Implement a **60-Second REST Reconciliation Heartbeat**:
    - Every 60 seconds, query `alpaca.get_positions()` and compare against the internal memory map. If any discrepancy is detected, internal state automatically resynchronizes with Alpaca ground truth.

### Specification 5: TradingView Real-Time Data Feed Notice
- **Problem Solved**: Discrepancies between real-time Alpaca executions and delayed TradingView charts.
- **Guidance & Settings**:
  - Standard TradingView free accounts display US equity charts with a 15-minute delay (Cboe BZX exchange data).
  - Alpaca Paper executes orders against real-time exchange data.
  - For pixel-perfect visual verification on TradingView, ensure your TradingView account has real-time US equity data enabled ($3/mo NASDAQ/NYSE add-on), or paper trade tickers with free real-time data on TradingView (e.g., crypto, index futures, or major FX pairs).

### Specification 6: Public Webhook Security & DoS Protection
- **Problem Solved**: Protecting the public webhook port from port scanners, invalid payloads, and resource exhaustion.
- **Implementation in `tradingview/webhook_server.py`**:
  - **Constant-Time Passphrase Comparison**:
    ```python
    import secrets
    if not secrets.compare_digest(alert.passphrase, config["tradingview"]["webhook_passphrase"]):
        raise HTTPException(status_code=401, detail="Unauthorized")
    ```
  - **Rate Limiting**: Enforce a maximum rate of 30 requests/minute using FastAPI middleware.
  - **Pre-Validation**: Reject malformed payloads immediately at the HTTP layer before touching any agent logic or data structures.

---

## Complete Handover Checklist for Coding Agent

1. [ ] Install dependencies from updated `requirements.txt` (`fastapi`, `uvicorn`, `python-telegram-bot`, `alpaca-py`, `pydantic`).
2. [ ] Implement `core/state_models.py` with Pydantic v2 schemas.
3. [ ] Implement `core/hmm_engine.py` with manual Forward Algorithm and variance-sorted states.
4. [ ] Implement `core/risk_manager.py` with sizing hierarchy and `pending_hitl_capital` reservation locks.
5. [ ] Persist `session_date` and `day_opening_equity` in `data/state_snapshot.json` to prevent circuit breaker resets on mid-day restart.
6. [ ] Implement `tradingview/webhook_server.py` with `secrets.compare_digest` authentication and rate limiting.
7. [ ] Implement `tradingview/tunnel_manager.py` to launch Cloudflare Quick Tunnel (`cloudflared`).
8. [ ] Implement `core/orchestrator.py` with 60-second symbol debounce and idempotency checking.
9. [ ] Implement `hitl/telegram_bot.py` using async long polling with a 0.3% price-drift guard.
10. [ ] Implement `broker/order_executor.py` with bracket orders for longs/inverse ETFs and sequential OCO for shorts.
11. [ ] Implement `broker/position_tracker.py` with atomic WebSocket event matrix and 60-second REST reconciliation heartbeat.
12. [ ] Run the complete test suite:
    - `tests/test_tradingview_webhook.py` (Auth & rate limiting)
    - `tests/test_hmm_forward.py` (Zero look-ahead & sorted states)
    - `tests/test_risk_guardian.py` (Capital locks & circuit breakers)
    - `tests/test_telegram_hitl.py` (Mock callback & drift guard)
    - `tests/test_execution_brackets.py` (Alpaca brackets & partial fills)
