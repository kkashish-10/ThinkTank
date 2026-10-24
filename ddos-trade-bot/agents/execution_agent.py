"""Execution Agent.

Routes user-approved proposals to the OrderExecutor, verifies bracket
orders on Alpaca, and reconciles capital reservation locks.
"""

from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from broker.order_executor import OrderExecutor
from core.risk_manager import RiskManager
from core.state_models import TradeProposal, RiskDecision, HITLDecision, HITLStatus


class ExecutionAgent(BaseAgent):
    """Executes trades through OrderExecutor."""

    def __init__(self, config: Dict[str, Any] = None, order_executor: Optional[OrderExecutor] = None, risk_manager: Optional[RiskManager] = None):
        super().__init__(name="ExecutionAgent", config=config)
        self.executor = order_executor or OrderExecutor()
        self.risk_manager = risk_manager

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute approved proposal with bracket protection."""
        proposal: TradeProposal = context.get("proposal")
        risk_decision: RiskDecision = context.get("risk_decision")
        hitl_decision: HITLDecision = context.get("hitl_decision")

        if not proposal or not risk_decision or not hitl_decision:
            return {"status": "skipped", "reason": "Missing inputs for execution"}

        try:
            # Execute on broker
            result = self.executor.submit_bracket_order(
                proposal=proposal,
                risk_decision=risk_decision,
                hitl_decision=hitl_decision
            )

            self.logger.info(f"Execution result for {proposal.symbol}: {result}")
            return result

        finally:
            # Release pending HITL capital reservation once execution completes or fails
            if self.risk_manager:
                self.risk_manager.release_capital(proposal.proposal_id)
