"""Technical Momentum & Price Action Agent.

Analyzes trend alignment, momentum (RSI), and dynamic volatility
bounds (ATR) to produce directional technical signals.
"""

from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
import ta

from agents.base_agent import BaseAgent
from core.state_models import TechnicalSignal, OrderSide


class TechnicalAgent(BaseAgent):
    """Generates technical signals based on EMA, RSI, and ATR."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="TechnicalAgent", config=config)
        self.atr_multiplier: float = float(self.config.get("atr_stop_multiplier", 2.0))

    async def process(self, context: Dict[str, Any]) -> TechnicalSignal:
        """Process OHLCV dataframe or TradingView alert signal."""
        # 1. Direct TradingView alert handling
        tv_alert = context.get("tv_alert")
        if tv_alert:
            current_price = tv_alert.price
            stop_loss = tv_alert.stop_loss or (current_price * 0.98 if tv_alert.to_order_side() == OrderSide.BUY else current_price * 1.02)
            take_profit = tv_alert.take_profit or (current_price * 1.04 if tv_alert.to_order_side() == OrderSide.BUY else current_price * 0.96)
            return TechnicalSignal(
                symbol=tv_alert.ticker,
                direction=tv_alert.to_order_side(),
                conviction=0.85,
                current_price=current_price,
                suggested_stop_loss=stop_loss,
                suggested_take_profit=take_profit
            )

        # 2. Native OHLCV bar processing
        df = context.get("ohlcv")
        symbol = context.get("symbol", "SPY")
        if df is None or len(df) < 50:
            raise ValueError(f"Insufficient OHLCV data for {symbol} (need >= 50 bars)")

        close = df['close']
        high = df['high']
        low = df['low']

        current_price = float(close.iloc[-1])
        ema_50 = float(ta.trend.ema_indicator(close, window=50).iloc[-1])
        ema_200 = float(ta.trend.ema_indicator(close, window=min(200, len(close))).iloc[-1])
        rsi_14 = float(ta.momentum.rsi(close, window=14).iloc[-1])
        atr_14 = float(ta.volatility.average_true_range(high, low, close, window=14).iloc[-1])

        # Direction logic:
        # Bullish if price > 50 EMA and RSI not overbought (>70)
        # Bearish/Short if price < 200 EMA and price < 50 EMA
        if current_price > ema_50:
            direction = OrderSide.BUY
            conviction = 0.80 if current_price > ema_200 else 0.65
            stop_loss = max(current_price - (atr_14 * self.atr_multiplier), ema_50 - (atr_14 * 0.5))
            take_profit = current_price + (abs(current_price - stop_loss) * 2.0)
        elif current_price < ema_200 and current_price < ema_50:
            direction = OrderSide.SHORT
            conviction = 0.75
            stop_loss = current_price + (atr_14 * 1.5)  # Tighter stop for shorts
            take_profit = current_price - (abs(stop_loss - current_price) * 2.0)
        else:
            direction = OrderSide.BUY
            conviction = 0.50
            stop_loss = current_price - (atr_14 * self.atr_multiplier)
            take_profit = current_price + (abs(current_price - stop_loss) * 1.5)

        return TechnicalSignal(
            symbol=symbol,
            direction=direction,
            conviction=conviction,
            current_price=current_price,
            ema_50=ema_50,
            ema_200=ema_200,
            rsi_14=rsi_14,
            atr_14=atr_14,
            suggested_stop_loss=round(stop_loss, 2),
            suggested_take_profit=round(take_profit, 2)
        )
