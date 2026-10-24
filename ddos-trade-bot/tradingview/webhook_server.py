"""FastAPI Webhook Listener for TradingView Alerts.

Receives, authenticates, rate-limits, and forwards TradingView alerts
into the Multi-Agent orchestrator pipeline.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status

from tradingview.alert_parser import TradingViewAlert, verify_passphrase

logger = logging.getLogger(__name__)


class WebhookRateLimiter:
    """In-memory rate limiter to prevent DoS attacks on public tunnel."""

    def __init__(self, max_requests_per_minute: int = 30):
        self.max_requests = max_requests_per_minute
        self.requests = defaultdict(list)

    def check_rate_limit(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=1)
        self.requests[client_ip] = [t for t in self.requests[client_ip] if t > cutoff]
        if len(self.requests[client_ip]) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded (max 30 requests/minute)"
            )
        self.requests[client_ip].append(now)


def create_tradingview_app(
    expected_passphrase: str,
    alert_callback: Optional[Callable[[TradingViewAlert], any]] = None
) -> FastAPI:
    """Create FastAPI application for TradingView webhooks."""
    app = FastAPI(title="TradingView Webhook Gateway", docs_url=None, redoc_url=None)
    limiter = WebhookRateLimiter(max_requests_per_minute=30)

    @app.get("/health")
    def health_check():
        return {"status": "online", "timestamp": datetime.utcnow().isoformat()}

    @app.post("/webhook/tradingview", dependencies=[Depends(limiter.check_rate_limit)])
    def receive_tradingview_alert(alert: TradingViewAlert):
        # 1. Constant-time passphrase authentication
        if not verify_passphrase(alert.passphrase, expected_passphrase):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid secret passphrase"
            )

        logger.info(
            f"Valid TradingView alert received: {alert.action.upper()} {alert.ticker} "
            f"@ ${alert.price:.2f} (SL: {alert.stop_loss}, TP: {alert.take_profit})"
        )

        # 2. Forward to multi-agent orchestrator queue
        if alert_callback:
            if asyncio.iscoroutinefunction(alert_callback):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(alert_callback(alert))
                except RuntimeError:
                    asyncio.run(alert_callback(alert))
            else:
                alert_callback(alert)

        return {
            "status": "accepted",
            "ticker": alert.ticker,
            "action": alert.action,
            "timestamp": datetime.utcnow().isoformat()
        }

    return app
