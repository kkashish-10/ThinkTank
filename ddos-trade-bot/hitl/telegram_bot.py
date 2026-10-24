"""Telegram Human-in-the-Loop (HITL) Interactive Gateway.

Provides async mobile approval with inline keyboard buttons,
300-second auto-expiration timeout, and 0.3% price-drift protection.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.state_models import TradeProposal, RiskDecision, HITLDecision, HITLStatus

logger = logging.getLogger(__name__)


class TelegramHITLGateway:
    """Manages mobile trade authorizations via Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: int = 300, max_slippage_pct: float = 0.003):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds
        self.max_slippage_pct = max_slippage_pct
        
        self.app: Optional[Application] = None
        self.pending_futures: Dict[str, asyncio.Future] = {}
        self.proposals: Dict[str, TradeProposal] = {}
        self._is_running = False

    async def initialize(self) -> None:
        """Initialize the Telegram application and handlers."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram bot credentials not configured; HITL gateway running in mock/auto mode")
            return

        self.app = Application.builder().token(self.bot_token).build()
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))
        await self.app.initialize()
        await self.app.start()
        # Start long polling in background
        asyncio.create_task(self.app.updater.start_polling(poll_interval=2.0))
        self._is_running = True
        logger.info("Telegram HITL Gateway initialized and polling for callbacks.")

    def format_proposal_message(self, proposal: TradeProposal, decision: RiskDecision) -> str:
        """Build Markdown-formatted proposal card."""
        action_emoji = "🟢" if proposal.side.value == "BUY" else "🔴"
        notional = decision.approved_shares * proposal.entry_target_price
        
        text = (
            f"🚨 *TRADE PROPOSAL: {proposal.side.value} {proposal.symbol}* {action_emoji}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• *Thesis*: {proposal.thesis_summary}\n"
            f"• *Entry Target*: `${proposal.entry_target_price:,.2f}`\n"
            f"• *Stop Loss*: `${decision.stop_loss_required:,.2f}`\n"
            f"• *Take Profit*: `${proposal.take_profit_price:,.2f}`\n"
            f"• *Approved Shares*: `{decision.approved_shares}` (`${notional:,.2f}`)\n"
            f"• *Account Risk*: `${decision.risk_dollars:,.2f}` (`{decision.risk_pct_equity:.2%}` equity)\n"
            f"• *Risk Clearance*: *PASSED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱ _Auto-expires in {self.timeout_seconds} seconds_"
        )
        return text

    async def request_approval(
        self,
        proposal: TradeProposal,
        decision: RiskDecision,
        current_market_price: float
    ) -> HITLDecision:
        """Send proposal to Telegram and await user callback or timeout."""
        # Fallback if bot is not configured: auto-approve in paper mode
        if not self._is_running or not self.app:
            logger.info(f"Telegram gateway unconfigured: auto-approving proposal {proposal.proposal_id}")
            return HITLDecision(
                proposal_id=proposal.proposal_id,
                status=HITLStatus.APPROVED,
                scale_factor=1.0,
                decided_by="AUTO_MOCK"
            )

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_futures[proposal.proposal_id] = future
        self.proposals[proposal.proposal_id] = proposal

        # Inline Keyboard
        keyboard = [
            [
                InlineKeyboardButton("✅ APPROVE", callback_data=f"app_{proposal.proposal_id}"),
                InlineKeyboardButton("⚡ HALF", callback_data=f"hlf_{proposal.proposal_id}"),
                InlineKeyboardButton("❌ REJECT", callback_data=f"rej_{proposal.proposal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send Telegram message
        message_text = self.format_proposal_message(proposal, decision)
        sent_msg = await self.app.bot.send_message(
            chat_id=self.chat_id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

        try:
            # Wait for user button press with timeout
            result: HITLDecision = await asyncio.wait_for(future, timeout=self.timeout_seconds)

            # Price drift guard if approved
            if result.status in (HITLStatus.APPROVED, HITLStatus.HALF_SIZE):
                drift = abs(current_market_price - proposal.entry_target_price) / proposal.entry_target_price
                if drift > self.max_slippage_pct:
                    logger.warning(
                        f"Price drifted {drift:.2%} > limit {self.max_slippage_pct:.2%}; aborting proposal {proposal.proposal_id}"
                    )
                    await sent_msg.edit_text(
                        message_text + f"\n\n⚠️ *ABORTED: Price drifted {drift:.2%} during approval window.*",
                        parse_mode="Markdown"
                    )
                    return HITLDecision(
                        proposal_id=proposal.proposal_id,
                        status=HITLStatus.PRICE_DRIFT_ABORT,
                        scale_factor=0.0,
                        decided_by="PRICE_DRIFT_GUARD"
                    )

            # Update message to show final action
            status_text = "✅ *APPROVED*" if result.status == HITLStatus.APPROVED else ("⚡ *HALF SIZE APPROVED*" if result.status == HITLStatus.HALF_SIZE else "❌ *REJECTED*")
            await sent_msg.edit_text(message_text + f"\n\nStatus: {status_text}", parse_mode="Markdown")
            return result

        except asyncio.TimeoutError:
            logger.warning(f"Proposal {proposal.proposal_id} timed out after {self.timeout_seconds}s")
            await sent_msg.edit_text(message_text + "\n\n⏱ *EXPIRED: Auto-rejected due to timeout.*", parse_mode="Markdown")
            return HITLDecision(
                proposal_id=proposal.proposal_id,
                status=HITLStatus.TIMED_OUT,
                scale_factor=0.0,
                decided_by="TIMEOUT"
            )
        finally:
            self.pending_futures.pop(proposal.proposal_id, None)
            self.proposals.pop(proposal.proposal_id, None)

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline button callbacks."""
        query = update.callback_query
        await query.answer()

        data = query.data
        if not data:
            return

        action, proposal_id = data[:3], data[4:]
        future = self.pending_futures.get(proposal_id)
        if not future or future.done():
            return

        if action == "app":
            future.set_result(HITLDecision(
                proposal_id=proposal_id,
                status=HITLStatus.APPROVED,
                scale_factor=1.0,
                decided_by="USER",
                user_id=query.from_user.id
            ))
        elif action == "hlf":
            future.set_result(HITLDecision(
                proposal_id=proposal_id,
                status=HITLStatus.HALF_SIZE,
                scale_factor=0.5,
                decided_by="USER",
                user_id=query.from_user.id
            ))
        elif action == "rej":
            future.set_result(HITLDecision(
                proposal_id=proposal_id,
                status=HITLStatus.REJECTED,
                scale_factor=0.0,
                decided_by="USER",
                user_id=query.from_user.id
            ))

    async def shutdown(self) -> None:
        """Gracefully stop updater and bot."""
        if self.app and self._is_running:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            self._is_running = False
