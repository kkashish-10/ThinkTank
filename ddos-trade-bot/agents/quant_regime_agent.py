"""Quant Regime Agent.

Wraps the Gaussian HMM detector, performing filtered forward classification
to output the current volatility regime state.
"""

from typing import Any, Dict
import pandas as pd

from agents.base_agent import BaseAgent
from core.hmm_engine import HMMRegimeDetector
from core.state_models import MarketRegimeState


class QuantRegimeAgent(BaseAgent):
    """Detects volatility regime using filtered Forward-only HMM."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="QuantRegimeAgent", config=config)
        self.detector = HMMRegimeDetector(config=self.config.get("hmm", {}))

    def train(self, features: pd.DataFrame) -> None:
        """Fit HMM with model order selection."""
        self.logger.info("Training HMM volatility classifier...")
        self.detector.fit(features)
        self.logger.info("HMM training complete.")

    async def process(self, context: Dict[str, Any]) -> MarketRegimeState:
        """Classify current regime from recent feature bars."""
        features = context.get("features")
        if features is None or len(features) == 0:
            raise ValueError("No feature data provided for QuantRegimeAgent")

        regime_state = self.detector.predict_regime_state(features)
        self.logger.info(
            f"Regime: {regime_state.regime_label.value} (ID: {regime_state.regime_id}), "
            f"Confidence: {regime_state.confidence:.2%}, Stable: {regime_state.is_stable}"
        )
        return regime_state
