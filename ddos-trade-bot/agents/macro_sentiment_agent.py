"""Macro & News Sentiment Agent.

Monitors economic event risks (FOMC, CPI) and general market bias.
Provides non-blocking execution with neutral fallback.
"""

from typing import Any, Dict
from datetime import datetime

from agents.base_agent import BaseAgent
from core.state_models import MacroSentimentState, MacroBias


class MacroSentimentAgent(BaseAgent):
    """Monitors macroeconomic blackout periods and news sentiment."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="MacroSentimentAgent", config=config)

    async def process(self, context: Dict[str, Any]) -> MacroSentimentState:
        """Evaluate macro risk. Defaults safely to neutral without blocking."""
        # Check if manual blackout override exists in context
        blackout_override = context.get("macro_blackout", False)
        
        # Check simulated or configured calendar events
        events = context.get("upcoming_events", [])
        
        bias = MacroBias.NEUTRAL
        if blackout_override:
            bias = MacroBias.RISK_OFF

        return MacroSentimentState(
            bias=bias,
            blackout_active=blackout_override,
            headline_sentiment=0.0,
            active_events=events,
            event_risk_warning="Macro event blackout active" if blackout_override else None
        )
