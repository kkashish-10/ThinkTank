"""Signal Generation Module.

Combines HMM regime detection and regime strategies to generate trading signals.
Integrates with risk management for final signal validation.
"""

import pandas as pd
from core.hmm_engine import HMMRegimeDetector
from core.regime_strategies import RegimeStrategyAllocator
from core.risk_manager import RiskManager


class SignalGenerator:
    """Generates trading signals from regime detection and strategies."""

    def __init__(self, hmm_detector, strategy_allocator, risk_manager):
        """Initialize signal generator with components.

        Args:
            hmm_detector: HMMRegimeDetector instance
            strategy_allocator: RegimeStrategyAllocator instance
            risk_manager: RiskManager instance
        """
        self.hmm_detector = hmm_detector
        self.strategy_allocator = strategy_allocator
        self.risk_manager = risk_manager

    def generate_signal(self, market_data, current_positions, account_state):
        """Generate trading signal based on regime and risk constraints.

        Args:
            market_data: Current OHLCV market data
            current_positions: Dict of current positions
            account_state: Account equity, peak equity, trade count

        Returns:
            Dictionary with signal type, symbols, sizes, and rationale
        """
        # Detect current regime
        regime_result = self.hmm_detector.predict_regime(market_data)

        if regime_result['confidence'] < self.hmm_detector.min_confidence:
            return {
                'action': 'hold',
                'rationale': f'Low regime confidence: {regime_result["confidence"]:.2f}',
                'regime': regime_result
            }

        if not regime_result['stable']:
            return {
                'action': 'hold',
                'rationale': 'Regime instability detected',
                'regime': regime_result
            }

        # Get allocation for current regime
        allocation = self.strategy_allocator.get_allocation(regime_result['state'])

        # Check risk limits
        risk_check = self.risk_manager.check_drawdown_limits(
            account_state['equity'],
            account_state['peak_equity'],
            len(current_positions)
        )

        if risk_check['halt_trading']:
            return {
                'action': 'halt',
                'rationale': f'Risk limits exceeded: drawdown {risk_check["current_drawdown"]:.2f}',
                'regime': regime_result
            }

        # Calculate position size
        position_size = self.risk_manager.calculate_position_size(
            account_state['equity'],
            allocation['allocation'],
            'SPY',  # Default symbol
            self.risk_manager.max_risk_per_trade
        )

        # Apply risk reduction if needed
        if risk_check['reduce_size']:
            position_size *= 0.5

        return {
            'action': 'trade',
            'symbol': 'SPY',
            'size': position_size * allocation['leverage'],
            'allocation': allocation['allocation'],
            'leverage': allocation['leverage'],
            'rationale': f'Regime {regime_result["state"]} detected with {regime_result["confidence"]:.2f} confidence',
            'regime': regime_result
        }

    def validate_signal(self, signal, current_positions):
        """Validate signal against risk constraints before execution.

        Args:
            signal: Generated trading signal
            current_positions: Dict of current positions

        Returns:
            Validated signal or None if risk constraints violated
        """
        if signal['action'] != 'trade':
            return signal

        # Validate trade against risk limits
        is_valid = self.risk_manager.validate_trade(
            signal['size'],
            current_positions,
            self.risk_manager.max_exposure
        )

        if not is_valid:
            return {
                'action': 'hold',
                'rationale': 'Risk validation failed',
                'original_signal': signal
            }

        return signal
