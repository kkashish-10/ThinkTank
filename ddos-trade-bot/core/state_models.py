"""Core State Models & Inter-Agent Data Contracts.

Defines Pydantic v2 schemas for all multi-agent communication,
signals, trade proposals, risk decisions, and system snapshots.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class RegimeType(str, Enum):
    """Market volatility regime classifications."""
    BULL_CALM = "BULL_CALM"              # Low vol, steady uptrend -> 95% + 1.25x leverage
    BULL_VOLATILE = "BULL_VOLATILE"      # Moderate vol with trend -> 95% + 1.0x leverage
    NEUTRAL_CHOPPY = "NEUTRAL_CHOPPY"    # Mid vol, sideways/range -> 60% + 40% cash
    BEAR_TURBULENT = "BEAR_TURBULENT"    # High vol, turbulent breakdown -> Defensive / Hedging


class MacroBias(str, Enum):
    """Macroeconomic and news sentiment bias."""
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"


class OrderSide(str, Enum):
    """Direction of trade order."""
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"


class HITLStatus(str, Enum):
    """Status of Human-in-the-Loop decision."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    HALF_SIZE = "HALF_SIZE"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    PRICE_DRIFT_ABORT = "PRICE_DRIFT_ABORT"


class MarketRegimeState(BaseModel):
    """Output from Quant Regime Agent."""
    regime_id: int
    regime_label: RegimeType
    confidence: float = Field(ge=0.0, le=1.0)
    state_probabilities: List[float] = Field(default_factory=list)
    is_confirmed: bool = True
    is_stable: bool = True
    flicker_count: int = 0
    volatility_rank: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TechnicalSignal(BaseModel):
    """Output from Technical Momentum Agent."""
    symbol: str
    direction: OrderSide
    conviction: float = Field(ge=0.0, le=1.0)
    current_price: float
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    rsi_14: Optional[float] = None
    atr_14: Optional[float] = None
    suggested_stop_loss: float
    suggested_take_profit: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MacroSentimentState(BaseModel):
    """Output from Macro & News Sentiment Agent."""
    bias: MacroBias = MacroBias.NEUTRAL
    blackout_active: bool = False
    headline_sentiment: float = 0.0
    active_events: List[str] = Field(default_factory=list)
    event_risk_warning: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TradeProposal(BaseModel):
    """Synthesized trade proposal from CIO Portfolio Agent."""
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    side: OrderSide
    allocation_pct: float
    target_shares: int
    notional_value: float
    entry_target_price: float
    stop_loss_price: float
    take_profit_price: float
    thesis_summary: str
    regime: MarketRegimeState
    macro: MacroSentimentState
    technical: TechnicalSignal
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RiskDecision(BaseModel):
    """Risk Guardian evaluation of a trade proposal."""
    proposal_id: str
    approved: bool
    modified: bool = False
    original_shares: int
    approved_shares: int
    stop_loss_required: float
    risk_dollars: float
    risk_pct_equity: float
    rejection_reasons: List[str] = Field(default_factory=list)
    circuit_breaker_active: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HITLDecision(BaseModel):
    """Human-in-the-Loop decision from Telegram."""
    proposal_id: str
    status: HITLStatus
    scale_factor: float = 1.0     # 1.0 for approve, 0.5 for half, 0.0 for reject
    decided_by: str = "USER"      # "USER" or "TIMEOUT"
    user_id: Optional[int] = None
    callback_timestamp: datetime = Field(default_factory=datetime.utcnow)


class PositionSnapshot(BaseModel):
    """Snapshot of an open position."""
    symbol: str
    shares: int
    side: OrderSide
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss_price: float
    take_profit_price: Optional[float] = None
    entry_time: datetime
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class SystemStateSnapshot(BaseModel):
    """Complete system recovery state persisted to disk."""
    session_date: str             # YYYY-MM-DD
    day_opening_equity: float
    day_peak_equity: float
    current_equity: float
    cash: float
    current_drawdown: float
    peak_drawdown: float
    pending_hitl_capital: float = 0.0
    active_positions: Dict[str, PositionSnapshot] = Field(default_factory=dict)
    active_circuit_breakers: List[str] = Field(default_factory=list)
    trading_halted: bool = False
    last_snapshot_time: datetime = Field(default_factory=datetime.utcnow)
