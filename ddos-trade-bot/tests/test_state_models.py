"""Unit tests for Pydantic state models and data contracts."""

import pytest
from datetime import datetime
from core.state_models import (
    MarketRegimeState,
    RegimeType,
    TradeProposal,
    RiskDecision,
    HITLDecision,
    HITLStatus,
    OrderSide,
    MacroSentimentState,
    TechnicalSignal,
)


def test_market_regime_state():
    state = MarketRegimeState(
        regime_id=0,
        regime_label=RegimeType.BULL_CALM,
        confidence=0.92,
        state_probabilities=[0.92, 0.05, 0.03],
        is_confirmed=True,
        is_stable=True,
        flicker_count=1
    )
    assert state.regime_label == RegimeType.BULL_CALM
    assert state.confidence == 0.92
    assert state.is_stable is True


def test_trade_proposal_validation():
    regime = MarketRegimeState(regime_id=0, regime_label=RegimeType.BULL_CALM, confidence=0.85)
    macro = MacroSentimentState()
    tech = TechnicalSignal(
        symbol="AAPL",
        direction=OrderSide.BUY,
        conviction=0.80,
        current_price=185.0,
        suggested_stop_loss=181.0,
        suggested_take_profit=193.0
    )
    proposal = TradeProposal(
        symbol="AAPL",
        side=OrderSide.BUY,
        allocation_pct=0.15,
        target_shares=50,
        notional_value=9250.0,
        entry_target_price=185.0,
        stop_loss_price=181.0,
        take_profit_price=193.0,
        thesis_summary="Bull regime breakout",
        regime=regime,
        macro=macro,
        technical=tech
    )
    assert proposal.symbol == "AAPL"
    assert proposal.notional_value == 9250.0
    assert len(proposal.proposal_id) > 10


def test_hitl_decision_enum():
    decision = HITLDecision(
        proposal_id="test-123",
        status=HITLStatus.HALF_SIZE,
        scale_factor=0.5,
        decided_by="USER"
    )
    assert decision.status == HITLStatus.HALF_SIZE
    assert decision.scale_factor == 0.5
