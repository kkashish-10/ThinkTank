"""Risk Guardian Agent.

Acts as the independent veto layer. Validates proposals against
strict mathematical sizing hierarchies, capital reservation locks,
and circuit breakers before forwarding to the HITL Gateway.
"""

from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from core.risk_manager import RiskManager
from core.state_models import TradeProposal, RiskDecision, SystemStateSnapshot


class RiskGuardianAgent(BaseAgent):
    """Enforces mathematical risk controls and circuit breakers."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="RiskGuardianAgent", config=config)
        self.risk_manager = RiskManager(config=self.config.get("risk", {}))

    async def process(self, context: Dict[str, Any]) -> Optional[RiskDecision]:
        """Validate proposal against risk boundaries."""
        proposal: TradeProposal = context.get("proposal")
        snapshot: SystemStateSnapshot = context.get("snapshot")

        if not proposal:
            return None

        if not snapshot:
            self.logger.error("Missing SystemStateSnapshot; rejecting proposal for safety")
            return RiskDecision(
                proposal_id=proposal.proposal_id,
                approved=False,
                original_shares=proposal.target_shares,
                approved_shares=0,
                stop_loss_required=proposal.stop_loss_price,
                risk_dollars=0.0,
                risk_pct_equity=0.0,
                rejection_reasons=["Missing portfolio state snapshot"]
            )

        decision = self.risk_manager.validate_proposal(proposal, snapshot)

        if decision.approved:
            self.logger.info(
                f"Proposal APPROVED: {decision.approved_shares} shares of {proposal.symbol} "
                f"(Risk: ${decision.risk_dollars:,.2f} / {decision.risk_pct_equity:.2%} equity)"
            )
        else:
            self.logger.warning(
                f"Proposal VETOED for {proposal.symbol}: {', '.join(decision.rejection_reasons)}"
            )

        return decision
