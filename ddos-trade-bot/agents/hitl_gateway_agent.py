"""HITL Gateway Agent.

Integrates TelegramHITLGateway with the multi-agent pipeline.
Manages approval requests, price drift evaluation, and releases
reserved capital if a trade is rejected or times out.
"""

from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from hitl.telegram_bot import TelegramHITLGateway
from core.state_models import TradeProposal, RiskDecision, HITLDecision, HITLStatus


class HITLGatewayAgent(BaseAgent):
    """Manages trader approval gateway."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="HITLGatewayAgent", config=config)
        
        hitl_cfg = self.config.get("hitl", {})
        timeout_seconds = int(hitl_cfg.get("approval_timeout_seconds", 300))
        max_slippage = float(hitl_cfg.get("max_slippage_pct", 0.003))

        import os
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        self.gateway = TelegramHITLGateway(
            bot_token=bot_token,
            chat_id=chat_id,
            timeout_seconds=timeout_seconds,
            max_slippage_pct=max_slippage
        )

    async def initialize(self) -> None:
        """Start async Telegram polling."""
        await self.gateway.initialize()

    async def process(self, context: Dict[str, Any]) -> Optional[HITLDecision]:
        """Dispatch approval request to Telegram."""
        proposal: TradeProposal = context.get("proposal")
        decision: RiskDecision = context.get("risk_decision")
        current_market_price = float(context.get("current_price", proposal.entry_target_price if proposal else 0.0))

        if not proposal or not decision or not decision.approved:
            return None

        # Request user approval via Telegram
        hitl_decision = await self.gateway.request_approval(
            proposal=proposal,
            decision=decision,
            current_market_price=current_market_price
        )

        self.logger.info(
            f"HITL Decision for {proposal.symbol}: status={hitl_decision.status.value}, "
            f"scale_factor={hitl_decision.scale_factor}, by={hitl_decision.decided_by}"
        )
        return hitl_decision
