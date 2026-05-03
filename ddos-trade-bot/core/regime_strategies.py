"""Regime-Based Portfolio Allocation Strategies.

Maps volatility regimes to portfolio allocations and leverage settings.
Implements trend-aware allocation adjustments.
"""

import pandas as pd
import numpy as np


class RegimeStrategyAllocator:
    """Maps market regimes to portfolio allocations."""

    def __init__(self, config):
        """Initialize allocator with regime strategy configuration.

        Args:
            config: Configuration dictionary with allocation parameters
        """
        self.config = config or {}
        self.low_vol_allocation = self.config.get('low_vol_allocation', 0.95)
        self.mid_vol_allocation_trend = self.config.get('mid_vol_allocation_trend', 0.95)
        self.mid_vol_allocation_no_trend = self.config.get('mid_vol_allocation_no_trend', 0.60)
        self.high_vol_allocation = self.config.get('high_vol_allocation', 0.60)
        self.low_vol_leverage = self.config.get('low_vol_leverage', 1.25)
        self.rebalance_threshold = self.config.get('rebalance_threshold', 0.10)
        self.uncertainty_size_mult = self.config.get('uncertainty_size_mult', 0.50)

    def get_allocation(self, regime, trend_signal=None):
        """Get portfolio allocation for current regime.

        Args:
            regime: Current market regime (0, 1, 2, etc)
            trend_signal: Optional trend signal for fine-tuning allocation

        Returns:
            Dictionary with position allocations and leverage
        """
        # Map regime to allocation strategy
        if regime == 0:  # Low volatility regime
            allocation = self.low_vol_allocation
            leverage = self.low_vol_leverage
        elif regime == 1:  # Medium volatility regime
            if trend_signal and trend_signal > 0:
                allocation = self.mid_vol_allocation_trend
            else:
                allocation = self.mid_vol_allocation_no_trend
            leverage = 1.0
        elif regime == 2:  # High volatility regime
            allocation = self.high_vol_allocation
            leverage = 1.0
        else:  # Unknown regime - conservative approach
            allocation = self.uncertainty_size_mult * self.high_vol_allocation
            leverage = 1.0

        return {
            'allocation': allocation,
            'leverage': leverage,
            'regime': regime,
            'trend_adjusted': trend_signal is not None
        }

    def rebalance_needed(self, current_allocation, target_allocation, threshold):
        """Check if rebalancing is needed based on allocation drift.

        Args:
            current_allocation: Current portfolio allocation
            target_allocation: Target allocation for current regime
            threshold: Drift threshold for rebalancing trigger

        Returns:
            Boolean indicating if rebalancing is needed
        """
        if current_allocation is None or target_allocation is None:
            return True

        # Calculate allocation drift
        drift = abs(current_allocation - target_allocation) / target_allocation
        return drift > threshold
