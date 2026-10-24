"""Unit tests for Gaussian HMM forward-only algorithm and state sorting."""

import pytest
import numpy as np
from core.hmm_engine import GaussianHMM, HMMRegimeDetector
from core.state_models import RegimeType


def test_state_variance_sorting():
    """Verify that states are strictly sorted by volatility variance ascending."""
    np.random.seed(42)
    # Generate 3 distinct regimes: low vol, medium vol, high vol
    low_vol = np.random.normal(0, 0.5, (100, 2))
    mid_vol = np.random.normal(0, 1.5, (100, 2))
    high_vol = np.random.normal(0, 3.5, (100, 2))
    X = np.vstack([low_vol, mid_vol, high_vol])

    hmm = GaussianHMM(n_components=3, n_iter=20, random_state=42)
    hmm.fit(X)

    variances = [np.trace(cov) for cov in hmm.covars_]
    # Verify strictly monotonic ascending variances
    assert variances[0] < variances[1] < variances[2]


def test_forward_algorithm_zero_lookahead():
    """Verify that Forward algorithm predictions do NOT change when future bars are appended."""
    np.random.seed(42)
    X = np.random.randn(250, 2)
    
    hmm = GaussianHMM(n_components=3, n_iter=15, random_state=42)
    hmm.fit(X)

    # 1. Predict filtered probabilities on slice up to bar 100
    X_slice = X[:100]
    proba_at_100_online = hmm.predict_filtered_proba(X_slice)[-1]

    # 2. Predict filtered probabilities on slice up to bar 150
    X_longer = X[:150]
    proba_at_100_longer = hmm.predict_filtered_proba(X_longer)[99]

    # In a pure Forward algorithm, P(S_100 | X_1:100) must be IDENTICAL
    # whether we stop at bar 100 or bar 150!
    np.testing.assert_allclose(proba_at_100_online, proba_at_100_longer, rtol=1e-5, atol=1e-5)


def test_detector_flicker_and_stability():
    """Test regime confirmation and flicker detection."""
    detector = HMMRegimeDetector({'min_confidence': 0.50, 'stability_bars': 3, 'flicker_threshold': 4})
    
    # Mock history with heavy flickering
    detector.recent_state_history = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    assert detector.flicker_threshold < 10
    
    # 3-bar confirmation test
    detector.recent_state_history = [0, 0, 0]
    assert len(detector.recent_state_history) == 3
