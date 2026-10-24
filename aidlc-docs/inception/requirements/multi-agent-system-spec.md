# Multi-Agent Trading System Specification (ThinkTank / ddos-trade-bot)

## 1. System Vision & Objective
Build an autonomous, collaborative **Multi-Agent Quantitative Trading Workflow** capable of executing trades on behalf of the user on Alpaca (Paper/Live) while requiring **Human-in-the-Loop (HITL) approval via Telegram / WhatsApp** before any capital is committed. The system combines statistical machine learning (HMM regime detection) with fundamental/macro intelligence, technical momentum, strict quantitative risk constraints, and dynamic hedging/shorting strategies during confirmed bear regimes.

---

## 2. Multi-Agent Architecture & Topology

```mermaid
flowchart TD
    subgraph SENSING["1. Sensing & Intelligence Layer"]
        HMM[Quant & Regime Agent\nHMM Volatility & Trend Classifier]
        MACRO[Macro & Sentiment Agent\nNews, Fed, CPI, Earnings Sentiment]
        TECH[Technical Momentum Agent\nEMA, RSI, ATR, Support/Resistance]
    end

    subgraph STRATEGY["2. Synthesis & Portfolio Layer"]
        CIO[Chief Investment Officer / Portfolio Agent\nSynthesizes signals, formulates thesis & target weights]
    end

    subgraph RISK["3. Risk & Governance Layer"]
        RISK_GUARD[Risk Guardian Agent - Absolute Veto\nPosition limits, 1% risk rule, circuit breakers]
    end

    subgraph HITL["4. Human-in-the-Loop Gateway"]
        TELEGRAM[HITL Approval Agent\nInteractive Telegram/WhatsApp Bot with Inline Buttons]
        USER((Trader / User\n[Approve] [Reject] [Half Size]))
    end

    subgraph EXECUTION["5. Execution & Settlement Layer"]
        EXEC[Execution Broker Agent\nAlpaca Bracket Orders, Limit/Market fills]
        TRACK[Position & State Tracker\nLive WebSocket sync, P&L, Slippage monitor]
    end

    subgraph SUPERVISOR["6. Supervisor & Safety Guardian"]
        SUP[Supervisor Agent\nEmergency Kill Switch, Trailing Stops, Health Monitoring]
    end

    HMM & MACRO & TECH -->|Agent Insights & Scores| CIO
    CIO -->|Proposed Portfolio Allocation| RISK_GUARD
    RISK_GUARD -->|Approved Proposal with Bracket Stops| TELEGRAM
    RISK_GUARD -.->|Vetoed / Modified| CIO
    TELEGRAM <-->|Alert & Response| USER
    TELEGRAM -->|User Approved Order Payload| EXEC
    EXEC --> TRACK
    TRACK --> SUP
    SUP -.->|Emergency Halt / Lockout| EXEC
```

---

## 3. Specialized Agent Roles & Responsibilities

### Agent 1: Quant / Regime Agent (HMM Engine)
- **Role**: Quantitative statistical classifier.
- **Methodology**: Gaussian HMM fitted across rolling features (returns, realized volatility, ADX, ATR).
- **Inference**: Strict filtered Forward Algorithm only ($P(\text{state}_t \mid \text{obs}_{1:t})$) to eliminate look-ahead bias.
- **Output**: Market regime classification (Bull Calm, Bull Volatile, Choppy/Neutral, Bear Turbulent) with probability confidence score $[0.0, 1.0]$ and flicker/stability metrics.

### Agent 2: Macro & Sentiment Agent
- **Role**: Evaluates systemic macroeconomic conditions and news catalysts.
- **Data Sources**: Economic calendar (FOMC, CPI, Jobs reports), financial news sentiment (Finnhub / NewsAPI / LLM analysis).
- **Output**: Macro Bias (`RISK_ON`, `NEUTRAL`, `RISK_OFF`) and event blackout warnings (e.g., "FOMC rate decision in 2 hours - freeze new entries").

### Agent 3: Technical & Price Action Agent
- **Role**: Micro-structure and multi-timeframe price action analysis on the asset universe (`SPY`, `QQQ`, `AAPL`, `NVDA`, `MSFT`, etc.).
- **Indicators**: 50/200 EMA trend alignment, RSI divergence, ATR-based volatility channels, Key Support/Resistance levels.
- **Output**: Instrument-level signal (`LONG`, `SHORT`, `FLAT`), entry trigger price, initial stop-loss level (e.g., $2 \times \text{ATR}$ or below swing low).

### Agent 4: Chief Investment Officer (CIO) / Portfolio Strategy Agent
- **Role**: Lead synthesizer and allocator.
- **Responsibilities**:
  - Gathers outputs from Quant, Macro, and Technical agents.
  - Resolves conflicting signals (e.g., Technicals Bullish, but Macro is Risk-Off and HMM is Bear Turbulent $\rightarrow$ CIO declares No Trade or Hedges).
  - Determines directional thesis:
    - **Bull Regime**: Long equities + mega-cap tech, 80–95% portfolio exposure.
    - **Neutral / Choppy Regime**: Capital preservation (40–60% cash), selective high-conviction longs.
    - **Confirmed Bear Regime**:
      - *Hedging*: Long inverse ETFs (e.g. `SH`, `PSQ`) or sector hedges.
      - *Shorting*: Selective short exposure on weak momentum names with strict stops.
      - *Cash Preservation*: Move 70–100% to cash / ultra-short Treasury yields (`BIL`/`SGOV`).
- **Output**: Structured Proposed Orders: `Symbol`, `Side (BUY/SELL/SHORT)`, `Allocation%`, `Entry Target`, `Stop Loss`, `Take Profit`, `Thesis Summary`.

### Agent 5: Risk Guardian Agent (Absolute Veto)
- **Role**: Enforces mathematical risk controls and survival constraints before any proposal can reach the trader.
- **Rules**:
  - **1% Max Risk per Trade**: Position size $= \frac{\text{Equity} \times 0.01}{|\text{Entry} - \text{Stop Loss}|}$.
  - **Max Single Position**: $\le 15\%$ of portfolio equity.
  - **Max Total Portfolio Exposure**: $\le 80\%$ (or $100\%$ if inverse hedge is applied).
  - **Max Concurrent Positions**: $\le 5$ simultaneous tickers.
  - **Circuit Breakers**:
    - Daily Drawdown $> 2\% \rightarrow$ Cut sizes 50%.
    - Daily Drawdown $> 3\% \rightarrow$ Halt new trades for the day.
    - Weekly Drawdown $> 5\% \rightarrow$ Halt new trades for the week.
    - Peak Drawdown $> 10\% \rightarrow$ Emergency lockfile creation (`trading_halted.lock`) and SMS/Telegram emergency ping.

### Agent 6: Human-in-the-Loop (HITL) Approval Agent
- **Role**: Dispatches interactive trade proposals directly to your mobile phone via **Telegram Bot API** (or WhatsApp webhook).
- **Message Format**:
  ```text
  🚨 TRADE PROPOSAL: BUY AAPL
  ━━━━━━━━━━━━━━━━━━━━━━━━━
  • Thesis: HMM Calm Bull (Conf: 88%) + Technical Breakout > 50 EMA
  • Macro Status: Risk-On (No high-impact events today)
  • Proposed Entry: $185.50
  • Stop Loss: $181.80 (Risk: $3.70 / 1.0% portfolio risk)
  • Target Profit: $193.00 (R:R 2.0x)
  • Sizing: 42 shares ($7,791.00 / 7.8% of portfolio)
  • Risk Checks: ALL PASSED (Daily DD: 0.2%)
  ━━━━━━━━━━━━━━━━━━━━━━━━━
  [✅ APPROVE]   [⚡ HALF SIZE]   [❌ REJECT]
  ```
- **Behavior**:
  - Listens asynchronously for callback queries.
  - **Timeout Policy**: If no approval is received within configurable window (e.g., 5 minutes or bar close), the proposal auto-expires and is cancelled for safety.
  - **Two-Factor Safety**: Live trading requires active tap on confirmation button.

### Agent 7: Execution & Broker Agent
- **Role**: Interfaces with Alpaca API.
- **Order Routing**:
  - Places **Bracket Orders** (Entry Limit/Market + OCO Stop Loss & Take Profit) to guarantee risk boundaries are physically set at the exchange.
  - Handles slippage protection (cancels unfilled limit orders after 30s and re-evaluates).
- **Reconciliation**:
  - Syncs fills via WebSocket connection.
  - Maintains `state_snapshot.json` to guarantee crash recovery without duplicate orders.

---

## 4. Bear Market & Hedging Framework

Unlike the original "always long" specification, the updated system incorporates active bear market management:

| Market Regime | HMM Classification | Macro & Technical State | Strategy Action | Permitted Leverage |
| :--- | :--- | :--- | :--- | :--- |
| **Low Volatility Bull** | Calm Bull ($\sigma < \text{p33}$) | Bullish Trend | **Long Core Equities** (SPY, QQQ, Leaders) | Up to $1.25\times$ |
| **Moderate Volatility** | Neutral / Mixed | Choppy / Range-bound | **Selective Longs + 40-50% Cash Buffer** | $1.0\times$ (No margin) |
| **High Volatility Spikes** | Turbulent ($\sigma > \text{p67}$) | Breakdown / Indeterminate | **Defensive Cash Preservation (70-100% Cash)** | $1.0\times$ |
| **Confirmed Bear Regime** | Sustained Bear State | Price $< 200 \text{ EMA}$, Risk-Off Macro | **Hedging via Inverse ETFs (`SH`, `PSQ`) or Direct Shorts** with strict $1.5 \times \text{ATR}$ stops | Max $0.5\times$ short exposure |

---

## 5. Technology Stack & Framework

1. **Agent Orchestration**: Lightweight asynchronous event-driven workflow (using Python `asyncio` + Pydantic state schemas, compatible with LangGraph or lightweight native state machine).
2. **Quantitative Engine**: `hmmlearn`, `scipy`, `pandas`, `ta` library for indicators.
3. **HITL Messaging**: `python-telegram-bot` (Telegram Bot API) with inline keyboard callbacks; optional Twilio WhatsApp client.
4. **Broker API**: `alpaca-py` (v2 REST API and WebSocket market data/trade updates).
5. **Data Persistence & Audit**: SQLite / JSON state snapshots for session recovery and trade audit trails.
