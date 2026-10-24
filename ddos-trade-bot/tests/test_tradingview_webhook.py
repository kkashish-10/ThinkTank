"""Unit tests for TradingView webhook server, rate limiter, and alert parser."""

import pytest
from fastapi import HTTPException
from tradingview.alert_parser import TradingViewAlert, verify_passphrase
from tradingview.webhook_server import WebhookRateLimiter, create_tradingview_app
from core.state_models import OrderSide


def test_passphrase_verification():
    assert verify_passphrase("correct_secret", "correct_secret") is True
    assert verify_passphrase("wrong_secret", "correct_secret") is False
    assert verify_passphrase("", "correct_secret") is False


def test_alert_side_mapping():
    alert_buy = TradingViewAlert(
        passphrase="key",
        ticker="SPY",
        action="BUY",
        price=500.0
    )
    assert alert_buy.to_order_side() == OrderSide.BUY

    alert_short = TradingViewAlert(
        passphrase="key",
        ticker="NVDA",
        action="SHORT",
        price=120.0
    )
    assert alert_short.to_order_side() == OrderSide.SHORT


def test_rate_limiter_exceeded():
    limiter = WebhookRateLimiter(max_requests_per_minute=2)

    class DummyClient:
        host = "127.0.0.1"

    class DummyRequest:
        client = DummyClient()

    req = DummyRequest()
    # First 2 requests pass
    limiter.check_rate_limit(req)
    limiter.check_rate_limit(req)
    # 3rd request raises 429
    with pytest.raises(HTTPException) as exc_info:
        limiter.check_rate_limit(req)
    assert exc_info.value.status_code == 429


def test_endpoint_logic_direct():
    received_alerts = []

    def mock_callback(alert):
        received_alerts.append(alert)

    app = create_tradingview_app(expected_passphrase="my_secret_token", alert_callback=mock_callback)

    endpoint_func = None
    for route in app.routes:
        if getattr(route, "path", None) == "/webhook/tradingview":
            endpoint_func = route.endpoint
            break

    assert endpoint_func is not None

    # 1. Test unauthorized attempt
    bad_alert = TradingViewAlert(
        passphrase="wrong_token",
        ticker="AAPL",
        action="BUY",
        price=185.0
    )
    with pytest.raises(HTTPException) as exc_info:
        endpoint_func(bad_alert)
    assert exc_info.value.status_code == 401

    # 2. Test authorized attempt
    good_alert = TradingViewAlert(
        passphrase="my_secret_token",
        ticker="AAPL",
        action="BUY",
        price=185.50
    )
    res = endpoint_func(good_alert)
    assert res["status"] == "accepted"
    assert len(received_alerts) == 1
    assert received_alerts[0].ticker == "AAPL"
