"""HMM Regime Detection Engine.

Implements Hidden Markov Model for volatility regime classification.
Uses BIC model selection across candidate orders to identify market regimes.
"""

import logging
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
from hmmlearn import hmm

logger = logging.getLogger(__name__)


class HMMRegimeDetector:
    """Detects market volatility regimes using Hidden Markov Models."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize HMM regime detector.

        Args:
            config: Configuration dictionary with HMM parameters
        """
        self.config = config or {}
        self.n_candidates: List[int] = self.config.get('n_candidates', [3, 4, 5, 6, 7])
        self.n_init: int = int(self.config.get('n_init', 10))
        self.covariance_type: str = self.config.get('covariance_type', 'full')
        self.min_train_bars: int = int(self.config.get('min_train_bars', 252))
        self.flicker_window: int = int(self.config.get('flicker_window', 20))
        self.flicker_threshold: int = int(self.config.get('flicker_threshold', 4))
        self.min_confidence: float = float(self.config.get('min_confidence', 0.55))
        self.model: Optional[hmm.GaussianHMM] = None
        self.best_order: Optional[int] = None
        self.training_data: Optional[np.ndarray] = None

    def _prepare_features(self, data: Union[pd.Series, pd.DataFrame, np.ndarray]) -> np.ndarray:
        if isinstance(data, pd.Series):
            data = data.to_frame()
        if isinstance(data, pd.DataFrame):
            array = data.values
        elif isinstance(data, np.ndarray):
            array = data
        else:
            raise ValueError('Unsupported data type for HMM features')

        if array.ndim == 1:
            array = array.reshape(-1, 1)

        if np.isnan(array).any() or np.isinf(array).any():
            array = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)

        return array

    def _compute_bic(self, model: hmm.GaussianHMM, X: np.ndarray) -> float:
        n_samples, n_features = X.shape
        n_components = model.n_components
        log_likelihood = model.score(X)
        n_parameters = n_components * (n_components - 1) + (n_components - 1)
        n_parameters += n_components * n_features
        if self.covariance_type == 'full':
            n_parameters += n_components * n_features * (n_features + 1) / 2
        elif self.covariance_type == 'diag':
            n_parameters += n_components * n_features
        elif self.covariance_type == 'tied':
            n_parameters += n_features * (n_features + 1) / 2
        else:
            n_parameters += n_components * n_features

        bic = -2 * log_likelihood + n_parameters * np.log(n_samples)
        return float(bic)

    def fit(self, returns_data: Union[pd.Series, pd.DataFrame, np.ndarray]) -> hmm.GaussianHMM:
        """Fit HMM model to historical returns or feature data.

        Args:
            returns_data: Pandas Series, DataFrame, or numpy array of training features

        Returns:
            The best-fitted HMM model
        """
        X = self._prepare_features(returns_data)
        if len(X) < self.min_train_bars:
            raise ValueError(
                f"Insufficient training data: need {self.min_train_bars} bars, got {len(X)}"
            )

        best_bic = float('inf')
        best_model: Optional[hmm.GaussianHMM] = None

        for n_components in self.n_candidates:
            try:
                model = hmm.GaussianHMM(
                    n_components=n_components,
                    covariance_type=self.covariance_type,
                    n_iter=1000,
                    n_init=self.n_init,
                    random_state=42,
                    verbose=False,
                )
                model.fit(X)
                bic = self._compute_bic(model, X)
                logger.info(f"Fitted HMM({n_components}) BIC={bic:.2f}")
                if bic < best_bic:
                    best_bic = bic
                    best_model = model
                    self.best_order = n_components
            except Exception as exc:
                logger.warning(f"Failed to fit HMM({n_components}): {exc}")
                continue

        if best_model is None:
            raise RuntimeError("Unable to fit any HMM model")

        self.model = best_model
        self.training_data = X
        logger.info(f"Selected HMM order {self.best_order} with BIC={best_bic:.2f}")
        return best_model

    def detect_flicker(self, state_sequence: np.ndarray) -> bool:
        """Detect regime flicker in a sequence of states."""
        if len(state_sequence) < self.flicker_window:
            return False

        window = state_sequence[-self.flicker_window :]
        changes = np.sum(window[1:] != window[:-1])
        flicker = int(changes) > self.flicker_threshold
        if flicker:
            logger.warning(
                f"Regime flicker detected: {changes} changes in last {self.flicker_window} bars"
            )
        return flicker

    def predict_regime(self, recent_returns: Union[pd.Series, pd.DataFrame, np.ndarray]) -> Dict[str, Any]:
        """Predict current volatility regime and confidence.

        Args:
            recent_returns: Recent returns or feature vector for prediction

        Returns:
            Dictionary containing regime state, confidence score, and stability
        """
        if self.model is None:
            raise RuntimeError("HMM model has not been trained yet")

        X = self._prepare_features(recent_returns)
        if len(X) == 0:
            raise ValueError("No data provided for regime prediction")

        states = self.model.predict(X)
        try:
            posterior = self.model.predict_proba(X)
            confidence = float(np.mean(np.max(posterior, axis=1)))
        except Exception:
            confidence = float(np.tanh(self.model.score(X) / len(X)))

        stable = not self.detect_flicker(states)
        regime_state = int(states[-1])

        logger.debug(
            f"Predicted regime={regime_state} confidence={confidence:.4f} stable={stable}"
        )
        return {
            'state': regime_state,
            'confidence': confidence,
            'stable': stable,
            'sequence': states,
        }

