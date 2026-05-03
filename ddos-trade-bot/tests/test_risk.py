"""Unit tests for risk management module.

Tests position sizing, drawdown limits, trade validation, and risk constraints.
"""

import pytest
import pandas as pd
import numpy as np
from core.risk_manager import RiskManager


class TestRiskManager:
    """Test suite for RiskManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        config = {
            'max_risk_per_trade': 0.01,
            'max_exposure': 0.80,
            'max_leverage': 1.25,
            'max_single_position': 0.15,
            'max_concurrent': 5,
            'max_daily_trades': 20,
            'daily_dd_reduce': 0.02,
            'daily_dd_halt': 0.03,
            'weekly_dd_reduce': 0.05,
            'weekly_dd_halt': 0.07,
            'max_dd_from_peak': 0.10
        }
        self.risk_manager = RiskManager(config)

    def test_position_sizing(self):
        """Test position size calculation."""
        account_size = 100000
        allocation = 0.10
        risk_per_trade = 0.01

        position_size = self.risk_manager.calculate_position_size(
            account_size, allocation, 'SPY', risk_per_trade
        )

        # Expected: (100000 * 0.01) / 0.02 = 50000
        # But capped at max_single_position: 100000 * 0.15 = 15000
        assert position_size == 15000

        # Test with smaller allocation
        small_allocation = 0.05
        small_position = self.risk_manager.calculate_position_size(
            account_size, small_allocation, 'SPY', risk_per_trade
        )
        assert small_position == 50000  # Not capped

    def test_drawdown_limits(self):
        """Test daily/weekly drawdown limit enforcement."""
        # No drawdown
        result = self.risk_manager.check_drawdown_limits(100000, 100000, 3)
        assert not result['halt_trading']
        assert not result['reduce_size']
        assert result['current_drawdown'] == 0.0

        # Small drawdown - no action
        result = self.risk_manager.check_drawdown_limits(98000, 100000, 3)
        assert not result['halt_trading']
        assert not result['reduce_size']
        assert result['current_drawdown'] == 0.02

        # Reduce size threshold
        result = self.risk_manager.check_drawdown_limits(97000, 100000, 3)
        assert not result['halt_trading']
        assert result['reduce_size']
        assert result['current_drawdown'] == 0.03

        # Halt threshold
        result = self.risk_manager.check_drawdown_limits(90000, 100000, 3)
        assert result['halt_trading']
        assert result['reduce_size']
        assert result['current_drawdown'] == 0.10

        # Max positions exceeded
        result = self.risk_manager.check_drawdown_limits(100000, 100000, 6)
        assert result['max_positions_exceeded']

    def test_trade_validation(self):
        """Test trade validation against risk limits."""
        current_positions = {'SPY': 10000, 'QQQ': 5000}

        # Valid trade
        assert self.risk_manager.validate_trade(5000, current_positions, 0.80)

        # Too many positions
        full_positions = {f'SPY{i}': 1000 for i in range(5)}
        assert not self.risk_manager.validate_trade(1000, full_positions, 0.80)

        # Single position too large
        assert not self.risk_manager.validate_trade(20000, current_positions, 0.80)

        # Total exposure exceeded
        large_positions = {'SPY': 70000}
        assert not self.risk_manager.validate_trade(20000, large_positions, 0.80)

    def test_exposure_limits(self):
        """Test maximum exposure constraints."""
        # Within limits
        current_positions = {'SPY': 10000, 'QQQ': 10000}
        assert self.risk_manager.validate_trade(10000, current_positions, 0.80)

        # At limit
        at_limit_positions = {'SPY': 40000}
        assert self.risk_manager.validate_trade(40000, at_limit_positions, 0.80)

        # Over limit
        over_limit_positions = {'SPY': 50000}
        assert not self.risk_manager.validate_trade(30000, over_limit_positions, 0.80)
