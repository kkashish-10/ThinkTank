"""TradingView Webhook Alert Schema & Parser.

Parses and validates incoming JSON alerts from TradingView Pine Script.
Uses secrets.compare_digest for constant-time passphrase verification.
"""

import secrets
from typing import Optional
from pydantic import BaseModel, Field

from core.state_models import OrderSide


class TradingViewAlert(BaseModel):
    """Payload sent by TradingView Pine Script alert."""
    passphrase: str = Field(description="Shared secret passphrase configured in TradingView alert message")
    ticker: str = Field(description="Trading symbol, e.g. 'AAPL' or 'SPY'")
    action: str = Field(description="Action: 'buy', 'sell', 'short', 'exit'")
    price: float = Field(gt=0.0, description="Trigger price on TradingView")
    stop_loss: Optional[float] = Field(default=None, description="Optional stop loss price from indicator")
    take_profit: Optional[float] = Field(default=None, description="Optional take profit price from indicator")
    timeframe: Optional[str] = Field(default="1Day", description="Chart timeframe")
    strategy_name: Optional[str] = Field(default="TradingView_PineScript", description="Name of sending strategy")
    comment: Optional[str] = Field(default=None, description="Custom comment or rationale")

    def to_order_side(self) -> OrderSide:
        """Map action string to OrderSide enum."""
        act = self.action.strip().upper()
        if act in ("BUY", "LONG"):
            return OrderSide.BUY
        elif act in ("SELL", "EXIT_LONG"):
            return OrderSide.SELL
        elif act in ("SHORT", "SELL_SHORT"):
            return OrderSide.SHORT
        return OrderSide.BUY


def verify_passphrase(received_passphrase: str, expected_passphrase: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    if not received_passphrase or not expected_passphrase:
        return False
    return secrets.compare_digest(received_passphrase.strip(), expected_passphrase.strip())
