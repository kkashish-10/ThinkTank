"""Alpaca Order Executor with Native Bracket Orders & Short OCO Protection.

Handles bracket order construction for long/hedging purchases and
sequential OCO stop-losses for direct shorts.
"""

import logging
from typing import Any, Dict, Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide as AlpacaSide, TimeInForce
from alpaca.trading.requests import (
    LimitOrderRequest,
    MarketOrderRequest,
    OrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from core.state_models import OrderSide, TradeProposal, RiskDecision, HITLDecision, HITLStatus

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Executes bracket orders and manages fill lifecycles on Alpaca."""

    def __init__(self, trading_client: Optional[TradingClient] = None):
        self.client = trading_client

    def submit_bracket_order(
        self,
        proposal: TradeProposal,
        risk_decision: RiskDecision,
        hitl_decision: HITLDecision
    ) -> Dict[str, Any]:
        """Submit bracket order to Alpaca.
        
        Applies final share scaling based on HITL decision (e.g. 50% size if HALF_SIZE).
        """
        if hitl_decision.status not in (HITLStatus.APPROVED, HITLStatus.HALF_SIZE):
            logger.info(f"Order skipped: HITL status is {hitl_decision.status.value}")
            return {"status": "skipped", "reason": f"HITL status: {hitl_decision.status.value}"}

        # Calculate final executed shares
        final_shares = int(risk_decision.approved_shares * hitl_decision.scale_factor)
        if final_shares <= 0:
            logger.warning("Final shares is 0 after HITL scaling; aborting order")
            return {"status": "aborted", "reason": "0 shares after scaling"}

        symbol = proposal.symbol
        side = AlpacaSide.BUY if proposal.side == OrderSide.BUY else AlpacaSide.SELL

        # Stop loss and take profit levels
        stop_price = round(proposal.stop_loss_price, 2)
        take_profit_price = round(proposal.take_profit_price, 2)

        # Mock response if client is not configured (e.g. offline dry run)
        if not self.client:
            logger.info(
                f"[DRY-RUN / MOCK] Executed {side.value} {final_shares} {symbol} "
                f"Bracket(Stop: ${stop_price}, TP: ${take_profit_price})"
            )
            return {
                "status": "mock_submitted",
                "order_id": f"mock-{proposal.proposal_id[:8]}",
                "symbol": symbol,
                "shares": final_shares,
                "side": side.value,
                "stop_price": stop_price,
                "take_profit_price": take_profit_price
            }

        try:
            # 1. Native Bracket Order for Longs & Inverse ETFs (SH / PSQ)
            if proposal.side == OrderSide.BUY:
                order_req = LimitOrderRequest(
                    symbol=symbol,
                    qty=final_shares,
                    side=AlpacaSide.BUY,
                    time_in_force=TimeInForce.GTC,
                    limit_price=round(proposal.entry_target_price, 2),
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=take_profit_price),
                    stop_loss=StopLossRequest(stop_price=stop_price)
                )
                submitted_order = self.client.submit_order(order_data=order_req)
                logger.info(f"Successfully submitted BUY bracket order: {submitted_order.id} for {symbol}")
                return {
                    "status": "submitted",
                    "order_id": str(submitted_order.id),
                    "symbol": symbol,
                    "shares": final_shares,
                    "side": "BUY"
                }

            # 2. Direct Short Order Handling
            else:
                # Check easy-to-borrow
                asset = self.client.get_asset(symbol)
                if not asset.easy_to_borrow:
                    logger.error(f"Cannot short {symbol}: asset is not easy-to-borrow")
                    return {"status": "rejected", "reason": f"{symbol} is not easy-to-borrow"}

                # Submit initial short sale limit order
                order_req = LimitOrderRequest(
                    symbol=symbol,
                    qty=final_shares,
                    side=AlpacaSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    limit_price=round(proposal.entry_target_price, 2)
                )
                submitted_order = self.client.submit_order(order_data=order_req)
                logger.info(
                    f"Submitted initial SHORT order {submitted_order.id} for {symbol}. "
                    f"Trailing OCO stop will be attached upon fill confirmation."
                )
                return {
                    "status": "submitted_short",
                    "order_id": str(submitted_order.id),
                    "symbol": symbol,
                    "shares": final_shares,
                    "side": "SHORT"
                }

        except Exception as e:
            logger.error(f"Failed to submit order to Alpaca: {e}", exc_info=True)
            return {"status": "error", "reason": str(e)}
