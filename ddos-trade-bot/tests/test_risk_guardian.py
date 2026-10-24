"""Unit tests for RiskManager and RiskGuardianAgent."""

import pytest
from core.risk_manager import RiskManager
from core.state_models import (
    TradeProposal,
    SystemStateSnapshot,
    MarketRegimeState,
    MacroSentimentState,
    TechnicalSignal,
    RegimeType,
    OrderSide,
)


@pytest.fixture
def risk_manager():
    config = {
        'max_risk_per_trade': 0.01,
        'max_exposure': 0.80,
        'max_single_position': 0.15,
        'max_concurrent': 5,
        'max_daily_trades': 20,
        'daily_dd_reduce': 0.02,
        'daily_dd_halt': 0.03,
        'max_dd_from_peak': 0.10,
        'lockfile_path': 'test_trading_halted.lock'
    }
    return RiskManager(config)


def test_sizing_hierarchy(risk_manager):
    """Test min(RiskUnits_1%, AllocationUnits, CapUnits_15%)."""
    equity = 100000.0
    entry_price = 100.0
    stop_loss = 95.0  # $5 risk per share
    
    # 1% risk of 100k = $1,000 / $5 = 200 shares ($20,000 notional)
    # 15% cap of 100k = $15,000 / $100 = 150 shares
    # Regime alloc 95% = 950 shares
    # Hierarchy should choose 150 shares (capped at 15%)
    shares, details = risk_manager.calculate_position_size(
        equity=equity,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
        regime_allocation_pct=0.95
    )
    assert shares == 150
    assert details['single_position_cap_units'] == 150
    assert details['risk_units_1pct'] == 200


def test_capital_reservation_lock(risk_manager):
    """Test that pending HITL capital is locked and released properly."""
    assert risk_manager.pending_hitl_capital == 0.0
    
    # Reserve $12,000
    risk_manager.reserve_capital("prop-1", 12000.0)
    assert risk_manager.pending_hitl_capital == 12000.0
    
    # Reserve another $8,000
    risk_manager.reserve_capital("prop-2", 8000.0)
    assert risk_manager.pending_hitl_capital == 20000.0
    
    # Release prop-1
    risk_manager.release_capital("prop-1")
    assert risk_manager.pending_hitl_capital == 8000.0
    
    # Release prop-2
    risk_manager.release_capital("prop-2")
    assert risk_manager.pending_hitl_capital == 0.0


def test_circuit_breaker_daily_dd(risk_manager):
    """Test daily drawdown triggers."""
    # Safe: 1% drawdown
    cb = risk_manager.check_circuit_breakers(current_equity=99000, day_opening_equity=100000, day_peak_equity=100000)
    assert cb['halt_trading'] is False
    assert cb['reduce_size'] is False
    
    # Reduce size: 2.5% drawdown
    cb_reduce = risk_manager.check_circuit_breakers(current_equity=97500, day_opening_equity=100000, day_peak_equity=100000)
    assert cb_reduce['halt_trading'] is False
    assert cb_reduce['reduce_size'] is True
    
    # Halt day: 3.5% drawdown
    cb_halt = risk_manager.check_circuit_breakers(current_equity=96500, day_opening_equity=100000, day_peak_equity=100000)
    assert cb_halt['halt_trading'] is True
