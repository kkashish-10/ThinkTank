"""HMM Volatility Regime Detection Engine (Pure NumPy / Filtered Forward Pass).

Implements Gaussian Hidden Markov Model for volatility regime classification:
1. Pure NumPy/SciPy implementation ensuring zero C-compiler dependency on Python 3.14.
2. Filtered Forward Algorithm only (strictly prevents look-ahead bias from Viterbi).
3. Variance-Sorted State Ordering: Ensures State 0 is always calmest and State K-1 is most turbulent.
4. Automatic BIC model order selection across candidates (e.g. 3, 4, 5).
5. Regime stability checks and flicker rate detection.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy.special import logsumexp
from scipy.stats import multivariate_normal

from core.state_models import MarketRegimeState, RegimeType

logger = logging.getLogger(__name__)


class GaussianHMM:
    """Gaussian Hidden Markov Model with Forward-only inference and EM training."""

    def __init__(self, n_components: int = 3, n_iter: int = 100, tol: float = 1e-4, random_state: int = 42):
        self.n_components = n_components
        self.n_iter = n_iter
        self.tol = tol
        self.random_state = random_state
        
        self.startprob_: Optional[np.ndarray] = None  # (K,)
        self.transmat_: Optional[np.ndarray] = None   # (K, K)
        self.means_: Optional[np.ndarray] = None      # (K, D)
        self.covars_: Optional[np.ndarray] = None     # (K, D, D)
        self.n_features_: Optional[int] = None

    def _init_params(self, X: np.ndarray) -> None:
        """Initialize parameters using quantiles / kmeans-like clustering."""
        rng = np.random.RandomState(self.random_state)
        n_samples, n_features = X.shape
        self.n_features_ = n_features
        K = self.n_components

        # Initial probabilities: uniform
        self.startprob_ = np.full(K, 1.0 / K)

        # Transition matrix: high self-transition probability (sticky regimes)
        self.transmat_ = np.full((K, K), (1.0 - 0.85) / (K - 1))
        np.fill_diagonal(self.transmat_, 0.85)

        # Initialize means: split samples along principal axis or quantiles
        variances = np.var(X, axis=0)
        primary_dim = int(np.argmax(variances))
        sorted_indices = np.argsort(X[:, primary_dim])
        chunks = np.array_split(sorted_indices, K)

        self.means_ = np.zeros((K, n_features))
        self.covars_ = np.zeros((K, n_features, n_features))

        min_covar = 1e-3
        for k in range(K):
            sub_X = X[chunks[k]]
            self.means_[k] = np.mean(sub_X, axis=0) if len(sub_X) > 0 else np.mean(X, axis=0)
            cov = np.cov(sub_X, rowvar=False) if len(sub_X) > n_features else np.cov(X, rowvar=False)
            if cov.ndim == 0:
                cov = np.array([[cov]])
            cov += np.eye(n_features) * min_covar
            self.covars_[k] = cov

    def _compute_log_likelihood(self, X: np.ndarray) -> np.ndarray:
        """Compute log emission probabilities log B_k(x_t). Shape: (T, K)."""
        T = len(X)
        K = self.n_components
        log_frameprob = np.zeros((T, K))
        min_covar = 1e-4

        for k in range(K):
            cov = self.covars_[k] + np.eye(self.n_features_) * min_covar
            try:
                mvn = multivariate_normal(mean=self.means_[k], cov=cov, allow_singular=True)
                log_frameprob[:, k] = mvn.logpdf(X)
            except Exception:
                # Fallback to diagonal variance if numerical singularity occurs
                diag_cov = np.diag(np.diag(cov)) + np.eye(self.n_features_) * min_covar
                mvn = multivariate_normal(mean=self.means_[k], cov=diag_cov, allow_singular=True)
                log_frameprob[:, k] = mvn.logpdf(X)

        return log_frameprob

    def forward_pass(self, X: np.ndarray) -> Tuple[float, np.ndarray]:
        """Perform forward pass computing filtered probabilities.
        
        Returns:
            log_likelihood: Total sequence log likelihood
            alpha: Log forward variables, shape (T, K)
        """
        T = len(X)
        K = self.n_components
        log_frameprob = self._compute_log_likelihood(X)
        log_startprob = np.log(np.maximum(self.startprob_, 1e-12))
        log_transmat = np.log(np.maximum(self.transmat_, 1e-12))

        log_alpha = np.zeros((T, K))
        log_alpha[0] = log_startprob + log_frameprob[0]

        for t in range(1, T):
            trans_scores = logsumexp(log_alpha[t - 1][:, np.newaxis] + log_transmat, axis=0)
            log_alpha[t] = trans_scores + log_frameprob[t]

        log_likelihood = float(logsumexp(log_alpha[-1]))
        return log_likelihood, log_alpha

    def fit(self, X: np.ndarray) -> "GaussianHMM":
        """Fit Gaussian HMM using vectorized Baum-Welch (EM) algorithm."""
        self._init_params(X)
        T, D = X.shape
        K = self.n_components
        prev_ll = -np.inf

        for iteration in range(self.n_iter):
            # 1. E-step: Forward & Backward pass
            log_ll, log_alpha = self.forward_pass(X)
            if np.isnan(log_ll) or np.isinf(log_ll):
                break

            # Vectorized Backward pass
            log_frameprob = self._compute_log_likelihood(X)
            log_transmat = np.log(np.maximum(self.transmat_, 1e-12))
            log_beta = np.zeros((T, K))
            log_beta[-1] = 0.0

            for t in range(T - 2, -1, -1):
                log_beta[t] = logsumexp(log_transmat + log_frameprob[t + 1] + log_beta[t + 1], axis=1)

            # Posterior gamma_t(i) = P(S_t = i | X)
            log_gamma = log_alpha + log_beta
            log_gamma -= logsumexp(log_gamma, axis=1, keepdims=True)
            gamma = np.exp(log_gamma)

            # Vectorized Xi: P(S_t = i, S_{t+1} = j | X)
            log_xi = log_alpha[:-1, :, np.newaxis] + log_transmat[np.newaxis, :, :] + log_frameprob[1:, np.newaxis, :] + log_beta[1:, np.newaxis, :]
            log_xi -= logsumexp(log_xi, axis=(1, 2), keepdims=True)
            xi = np.exp(log_xi)

            # 2. M-step: Update parameters
            self.startprob_ = gamma[0] / np.sum(gamma[0])
            self.transmat_ = np.sum(xi, axis=0) / np.maximum(np.sum(gamma[:-1], axis=0)[:, np.newaxis], 1e-12)
            self.transmat_ /= np.sum(self.transmat_, axis=1, keepdims=True)

            gamma_sum = np.maximum(np.sum(gamma, axis=0), 1e-12)
            for k in range(K):
                # Update means
                self.means_[k] = np.sum(gamma[:, k][:, np.newaxis] * X, axis=0) / gamma_sum[k]
                # Update covariances
                diff = X - self.means_[k]
                weighted_diff = gamma[:, k][:, np.newaxis] * diff
                cov = (weighted_diff.T @ diff) / gamma_sum[k]
                cov += np.eye(D) * 1e-4  # Regularization to prevent singularity
                self.covars_[k] = cov

            # Convergence check
            if abs(log_ll - prev_ll) < self.tol:
                break
            prev_ll = log_ll

        # Post-training: Sort states by trace of covariance (volatility order ascending)
        self._sort_states()
        return self

    def _sort_states(self) -> None:
        """Sort states so that State 0 = Lowest Volatility, State K-1 = Highest Volatility."""
        volatilities = [np.trace(cov) for cov in self.covars_]
        order = np.argsort(volatilities)

        self.startprob_ = self.startprob_[order]
        self.transmat_ = self.transmat_[order][:, order]
        self.means_ = self.means_[order]
        self.covars_ = self.covars_[order]

    def score(self, X: np.ndarray) -> float:
        """Compute sequence log likelihood."""
        log_ll, _ = self.forward_pass(X)
        return log_ll

    def predict_filtered_proba(self, X: np.ndarray) -> np.ndarray:
        """Compute filtered forward state probabilities P(S_t | x_1:t) WITHOUT look-ahead bias."""
        _, log_alpha = self.forward_pass(X)
        # Normalize each time step
        log_filtered = log_alpha - logsumexp(log_alpha, axis=1, keepdims=True)
        return np.exp(log_filtered)


class HMMRegimeDetector:
    """Production-grade regime detector with BIC model selection and stability filtering."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.n_candidates: List[int] = self.config.get('n_candidates', [3, 4, 5])
        self.n_init: int = int(self.config.get('n_init', 5))
        self.min_train_bars: int = int(self.config.get('min_train_bars', 252))
        self.stability_bars: int = int(self.config.get('stability_bars', 3))
        self.flicker_window: int = int(self.config.get('flicker_window', 20))
        self.flicker_threshold: int = int(self.config.get('flicker_threshold', 4))
        self.min_confidence: float = float(self.config.get('min_confidence', 0.55))

        self.model: Optional[GaussianHMM] = None
        self.best_order: Optional[int] = None
        self.recent_state_history: List[int] = []

    def _prepare_features(self, data: Union[pd.Series, pd.DataFrame, np.ndarray]) -> np.ndarray:
        if isinstance(data, pd.Series):
            data = data.to_frame()
        if isinstance(data, pd.DataFrame):
            array = data.values
        elif isinstance(data, np.ndarray):
            array = data
        else:
            raise ValueError(f"Unsupported data type for HMM: {type(data)}")

        if array.ndim == 1:
            array = array.reshape(-1, 1)

        array = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)
        return array

    def _compute_bic(self, model: GaussianHMM, X: np.ndarray) -> float:
        """Compute Bayesian Information Criterion: BIC = -2*ln(L) + p*ln(T)."""
        n_samples, n_features = X.shape
        K = model.n_components
        log_likelihood = model.score(X)
        # Parameters: startprob (K-1), transmat (K*(K-1)), means (K*D), covars (K*D*(D+1)/2)
        n_params = (K - 1) + K * (K - 1) + K * n_features + K * n_features * (n_features + 1) // 2
        bic = -2.0 * log_likelihood + n_params * np.log(n_samples)
        return float(bic)

    def fit(self, features_data: Union[pd.Series, pd.DataFrame, np.ndarray]) -> GaussianHMM:
        """Fit HMM with BIC model selection."""
        X = self._prepare_features(features_data)
        if len(X) < self.min_train_bars:
            raise ValueError(f"Insufficient training bars: need {self.min_train_bars}, got {len(X)}")

        best_bic = float('inf')
        best_model: Optional[GaussianHMM] = None

        for n_comp in self.n_candidates:
            for seed in range(self.n_init):
                try:
                    candidate = GaussianHMM(n_components=n_comp, n_iter=100, random_state=42 + seed)
                    candidate.fit(X)
                    bic = self._compute_bic(candidate, X)
                    if bic < best_bic:
                        best_bic = bic
                        best_model = candidate
                        self.best_order = n_comp
                except Exception as e:
                    logger.debug(f"HMM({n_comp}, seed={seed}) fit failed: {e}")

        if best_model is None:
            raise RuntimeError("Failed to fit any candidate Gaussian HMM")

        self.model = best_model
        logger.info(f"Selected HMM order K={self.best_order} with BIC={best_bic:.2f}")
        return self.model

    def predict_regime_state(self, features_data: Union[pd.Series, pd.DataFrame, np.ndarray]) -> MarketRegimeState:
        """Predict regime using strict Forward Algorithm (online causal inference)."""
        if self.model is None:
            raise RuntimeError("HMM model is not fitted yet")

        X = self._prepare_features(features_data)
        filtered_probas = self.model.predict_filtered_proba(X)
        current_probas = filtered_probas[-1]

        regime_id = int(np.argmax(current_probas))
        confidence = float(current_probas[regime_id])

        # Track history for flicker & stability
        self.recent_state_history.append(regime_id)
        if len(self.recent_state_history) > 100:
            self.recent_state_history.pop(0)

        # 1. Flicker rate check (changes in last N bars)
        flicker_count = 0
        if len(self.recent_state_history) >= self.flicker_window:
            window = self.recent_state_history[-self.flicker_window:]
            flicker_count = int(np.sum(np.array(window[1:]) != np.array(window[:-1])))
        is_stable = flicker_count <= self.flicker_threshold

        # 2. Confirmation check (3-bar persistence)
        is_confirmed = True
        if len(self.recent_state_history) >= self.stability_bars:
            last_n = self.recent_state_history[-self.stability_bars:]
            is_confirmed = all(s == regime_id for s in last_n)

        # 3. Map sorted state to RegimeType
        # Note: States are sorted ascending by variance (0: Calmest -> K-1: Turbulent)
        K = self.model.n_components
        vol_rank = regime_id / max(1, K - 1)

        if vol_rank <= 0.25:
            regime_label = RegimeType.BULL_CALM
        elif vol_rank <= 0.50:
            regime_label = RegimeType.BULL_VOLATILE
        elif vol_rank <= 0.75:
            regime_label = RegimeType.NEUTRAL_CHOPPY
        else:
            regime_label = RegimeType.BEAR_TURBULENT

        return MarketRegimeState(
            regime_id=regime_id,
            regime_label=regime_label,
            confidence=confidence,
            state_probabilities=current_probas.tolist(),
            is_confirmed=is_confirmed,
            is_stable=is_stable,
            flicker_count=flicker_count,
            volatility_rank=vol_rank
        )
