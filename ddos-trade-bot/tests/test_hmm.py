"""Unit tests for HMM regime detection module.

Tests model fitting, regime prediction, and model selection.
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.hmm_engine import HMMRegimeDetector


def make_synthetic_returns(n_per_regime: int = 100) -> pd.Series:
    rng = np.random.default_rng(42)
    regime_low = rng.normal(0.0001, 0.005, n_per_regime)
    regime_mid = rng.normal(0.0005, 0.01, n_per_regime)
    regime_high = rng.normal(-0.0002, 0.02, n_per_regime)
    returns = np.concatenate([regime_low, regime_mid, regime_high])
    dates = pd.date_range('2022-01-01', periods=len(returns), freq='D')
    return pd.Series(returns, index=dates)


class TestHMMRegimeDetector:
    """Test suite for HMMRegimeDetector class."""

    def test_fit_model(self):
        config = {
            'n_candidates': [2, 3],
            'n_init': 3,
            'covariance_type': 'full',
            'min_train_bars': 150,
        }
        detector = HMMRegimeDetector(config)
        returns = make_synthetic_returns(n_per_regime=80)

        model = detector.fit(returns)

        assert model is not None
        assert detector.best_order in [2, 3]
        assert hasattr(model, 'predict')

    def test_predict_regime(self):
        config = {
            'n_candidates': [3],
            'n_init': 3,
            'covariance_type': 'full',
            'min_train_bars': 150,
            'min_confidence': 0.1,
        }
        detector = HMMRegimeDetector(config)
        returns = make_synthetic_returns(n_per_regime=80)
        detector.fit(returns)

        recent = returns.tail(20)
        result = detector.predict_regime(recent)

        assert isinstance(result, dict)
        assert 'state' in result
        assert 'confidence' in result
        assert 'stable' in result
        assert isinstance(result['state'], int)
        assert 0 <= result['confidence'] <= 1

    def test_model_selection_bic(self):
        config = {
            'n_candidates': [2, 3, 4],
            'n_init': 2,
            'covariance_type': 'full',
            'min_train_bars': 150,
        }
        detector = HMMRegimeDetector(config)
        returns = make_synthetic_returns(n_per_regime=80)

        detector.fit(returns)
        assert detector.best_order in [2, 3, 4]
        assert detector.model is not None

    def test_stability_check(self):
        config = {
            'flicker_window': 10,
            'flicker_threshold': 2,
        }
        detector = HMMRegimeDetector(config)

        stable_seq = np.array([0, 0, 0, 0, 0, 0, 0, 1, 1, 1])
        flicker_seq = np.array([0, 1, 0, 1, 0, 1, 0, 1, 0, 1])

        assert detector.detect_flicker(stable_seq) is False
        assert detector.detect_flicker(flicker_seq) is True
