"""Multi-Agent Trading Orchestrator.

Coordinates agent execution, manages the 60-second deduplication debounce,
and coordinates the full cycle from sensing to Telegram HITL and Alpaca execution.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from agents import (
    QuantRegimeAgent,
    TechnicalAgent,
    MacroSentimentAgent,
    CIOPortfolioAgent,
    RiskGuardianAgent,
    HITLGatewayAgent,
    ExecutionAgent,
    SupervisorAgent,
)
from broker.order_executor import OrderExecutor
from broker.position_tracker import PositionTracker
from core.risk_manager import RiskManager
from core.state_models import (
    MarketRegimeState,
    MacroSentimentState,
    TechnicalSignal,
    TradeProposal,
    RiskDecision,
    HITLDecision,
    HITLStatus,
)
from tradingview.alert_parser import TradingViewAlert

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """Master workflow coordinator for the multi-agent trading system."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Core components
        self.risk_manager = RiskManager(config=self.config.get("risk", {}))
        self.position_tracker = PositionTracker(client=None)  # Can be injected with Alpaca TradingClient
        self.order_executor = OrderExecutor(trading_client=None)

        # Specialized agents
        self.quant_agent = QuantRegimeAgent(config=self.config)
        self.tech_agent = TechnicalAgent(config=self.config)
        self.macro_agent = MacroSentimentAgent(config=self.config)
        self.cio_agent = CIOPortfolioAgent(config=self.config)
        self.risk_agent = RiskGuardianAgent(config=self.config)
        self.risk_agent.risk_manager = self.risk_manager
        
        self.hitl_agent = HITLGatewayAgent(config=self.config)
        self.execution_agent = ExecutionAgent(
            config=self.config,
            order_executor=self.order_executor,
            risk_manager=self.risk_manager
        )
        self.supervisor_agent = SupervisorAgent(
            config=self.config,
            position_tracker=self.position_tracker,
            risk_manager=self.risk_manager
        )

        # 60-second symbol deduplication cache
        self.symbol_debounce_cache: Dict[str, datetime] = {}
        self.debounce_seconds: int = 60

    async def initialize(self) -> None:
        """Initialize all agents (e.g. Telegram polling)."""
        logger.info("Initializing MultiAgentOrchestrator...")
        await self.hitl_agent.initialize()
        logger.info("MultiAgentOrchestrator online.")

    def _is_debounced(self, symbol: str) -> bool:
        """Check if symbol was processed within the last 60 seconds."""
        now = datetime.utcnow()
        last_time = self.symbol_debounce_cache.get(symbol)
        if last_time and (now - last_time).total_seconds() < self.debounce_seconds:
            return True
        self.symbol_debounce_cache[symbol] = now
        return False

    async def process_external_tv_alert(self, alert: TradingViewAlert) -> Optional[Dict[str, Any]]:
        """Process an inbound TradingView alert webhook through the agent pipeline."""
        logger.info(f"Orchestrator received TradingView alert for {alert.ticker} ({alert.action.upper()})")

        # 1. Deduplication check
        if self._is_debounced(alert.ticker):
            logger.info(f"TradingView alert for {alert.ticker} suppressed by 60s debounce filter")
            return {"status": "suppressed", "reason": "debounce_filter"}

        # 2. Get current system state
        snapshot = self.position_tracker.get_snapshot(
            pending_hitl_capital=self.risk_manager.pending_hitl_capital
        )
        if snapshot.trading_halted:
            logger.warning(f"Trading halted; rejecting TradingView alert for {alert.ticker}")
            return {"status": "rejected", "reason": "trading_halted"}

        # 3. Technical agent evaluates alert
        tech_signal: TechnicalSignal = await self.tech_agent.process({"tv_alert": alert})

        # 4. Sensing: Evaluate Macro
        macro_state: MacroSentimentState = await self.macro_agent.process({})

        # 5. HMM Regime state
        # In live mode, we can use the latest classified regime
        # If not trained yet, provide fallback neutral regime
        try:
            regime_state = self.quant_agent.detector.predict_regime_state(
                [[0.0, 0.01], [0.005, 0.015]] # Placeholder if feature cache exists
            )
        except Exception:
            from core.state_models import RegimeType
            regime_state = MarketRegimeState(
                regime_id=0,
                regime_label=RegimeType.BULL_CALM,
                confidence=0.80
            )

        # 6. CIO Synthesis
        proposal: Optional[TradeProposal] = await self.cio_agent.process({
            "regime": regime_state,
            "macro": macro_state,
            "technical": tech_signal,
            "equity": snapshot.current_equity
        })
        if not proposal:
            return {"status": "declined_by_cio"}

        # 7. Risk Guardian Check & Capital Lock
        risk_decision: Optional[RiskDecision] = await self.risk_agent.process({
            "proposal": proposal,
            "snapshot": snapshot
        })
        if not risk_decision or not risk_decision.approved:
            return {"status": "vetoed_by_risk_guardian", "reasons": risk_decision.rejection_reasons if risk_decision else []}

        # 8. Telegram HITL Gateway
        hitl_decision: Optional[HITLDecision] = await self.hitl_agent.process({
            "proposal": proposal,
            "risk_decision": risk_decision,
            "current_price": alert.price
        })

        if not hitl_decision or hitl_decision.status not in (HITLStatus.APPROVED, HITLStatus.HALF_SIZE):
            # User rejected or timed out -> Release capital lock
            self.risk_manager.release_capital(proposal.proposal_id)
            return {"status": "rejected_by_hitl", "details": hitl_decision.status.value if hitl_decision else "unknown"}

        # 9. Broker Execution
        exec_result = await self.execution_agent.process({
            "proposal": proposal,
            "risk_decision": risk_decision,
            "hitl_decision": hitl_decision
        })

        # 10. Update positions and state
        await self.supervisor_agent.process({})
        return exec_result
