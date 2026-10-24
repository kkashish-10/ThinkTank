"""Chief Investment Officer (CIO) / Portfolio Strategy Agent.

Synthesizes outputs from Quant Regime, Macro, and Technical agents
to produce directional proposals and portfolio allocations, including
cash preservation, inverse ETF hedging (SH/PSQ), and bear shorts.
"""

from typing import Any, Dict, Optional
import logging

from agents.base_agent import BaseAgent
from core.state_models import (
    TradeProposal,
    MarketRegimeState,
    MacroSentimentState,
    TechnicalSignal,
    RegimeType,
    MacroBias,
    OrderSide,
)

logger = logging.getLogger(__name__)


class CIOPortfolioAgent(BaseAgent):
    """Chief Investment Officer synthesizing signals into unified trade proposals."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="CIOPortfolioAgent", config=config)
        
        # Strategy allocation parameters
        strat_cfg = self.config.get("strategy", {})
        self.low_vol_alloc = float(strat_cfg.get("low_vol_allocation", 0.95))
        self.mid_vol_trend_alloc = float(strat_cfg.get("mid_vol_allocation_trend", 0.95))
        self.mid_vol_no_trend_alloc = float(strat_cfg.get("mid_vol_allocation_no_trend", 0.60))
        self.high_vol_alloc = float(strat_cfg.get("high_vol_allocation", 0.60))
        self.min_consensus_score = float(self.config.get("multi_agent", {}).get("min_agent_consensus", 0.65))

        # Bear market settings
        bear_cfg = self.config.get("bear_regime", {})
        self.allow_cash_preservation = bool(bear_cfg.get("allow_cash_preservation", True))
        self.allow_inverse_hedging = bool(bear_cfg.get("allow_inverse_etf_hedging", True))
        self.inverse_etfs = bear_cfg.get("inverse_etf_symbols", ["SH", "PSQ"])
        self.allow_direct_shorting = bool(bear_cfg.get("allow_direct_shorting", False))
        self.max_short_exposure = float(bear_cfg.get("max_short_exposure", 0.30))

    async def process(self, context: Dict[str, Any]) -> Optional[TradeProposal]:
        """Synthesize Quant, Macro, and Technical findings into a TradeProposal."""
        regime: MarketRegimeState = context.get("regime")
        macro: MacroSentimentState = context.get("macro")
        tech: TechnicalSignal = context.get("technical")

        if not regime or not tech:
            self.logger.warning("Missing regime or technical signal; skipping proposal")
            return None

        # 1. Macro Blackout Check
        if macro and macro.blackout_active:
            self.logger.warning("Macro event blackout active: CIO declining new positions")
            return None

        # 2. Consensus Score Calculation
        # Confidence in regime (0..1) + Technical conviction (0..1)
        macro_score = 0.5 if not macro else (1.0 if macro.bias == MacroBias.RISK_ON else (0.2 if macro.bias == MacroBias.RISK_OFF else 0.5))
        consensus_score = (regime.confidence * 0.4) + (tech.conviction * 0.4) + (macro_score * 0.2)

        if consensus_score < self.min_consensus_score:
            self.logger.info(
                f"Consensus score {consensus_score:.2f} below minimum threshold {self.min_consensus_score:.2f}; holding"
            )
            return None

        target_symbol = tech.symbol
        target_side = tech.direction
        allocation_pct = 0.0
        thesis_parts = []

        # 3. Dynamic Regime Allocation & Bear Hedging
        if regime.regime_label == RegimeType.BULL_CALM:
            allocation_pct = self.low_vol_alloc
            target_side = OrderSide.BUY
            thesis_parts.append(f"HMM Bull Calm (Conf: {regime.confidence:.0%}) -> Maximum Long Exposure")

        elif regime.regime_label == RegimeType.BULL_VOLATILE:
            allocation_pct = self.mid_vol_trend_alloc if tech.direction == OrderSide.BUY else self.mid_vol_no_trend_alloc
            target_side = OrderSide.BUY
            thesis_parts.append(f"HMM Bull Volatile -> Controlled Long Exposure ({allocation_pct:.0%})")

        elif regime.regime_label == RegimeType.NEUTRAL_CHOPPY:
            allocation_pct = self.mid_vol_no_trend_alloc
            thesis_parts.append(f"HMM Neutral Choppy -> Selective Allocation with Cash Buffer ({allocation_pct:.0%})")

        elif regime.regime_label == RegimeType.BEAR_TURBULENT:
            # Confirmed Bear / Turbulent regime
            if self.allow_inverse_hedging and target_symbol in ["SPY", "QQQ"]:
                # Switch to Inverse ETF
                hedge_symbol = "SH" if target_symbol == "SPY" else "PSQ"
                target_symbol = hedge_symbol
                target_side = OrderSide.BUY  # Buying inverse ETF is a long order
                allocation_pct = min(self.max_short_exposure, 0.25)
                thesis_parts.append(f"HMM Bear Turbulent -> Active Hedge via Inverse ETF {hedge_symbol} ({allocation_pct:.0%})")
            elif self.allow_direct_shorting and tech.direction == OrderSide.SHORT:
                target_side = OrderSide.SHORT
                allocation_pct = min(self.max_short_exposure, 0.15)
                thesis_parts.append(f"HMM Bear Turbulent -> Direct Short Exposure on {target_symbol} ({allocation_pct:.0%})")
            else:
                # Cash preservation
                self.logger.info("HMM Bear Turbulent: Shifting to defensive Cash Preservation (No Trade)")
                return None

        # Build thesis summary
        thesis_parts.append(f"Technical {tech.direction.value} conviction: {tech.conviction:.0%}")
        thesis_summary = " | ".join(thesis_parts)

        # Estimate preliminary target shares (Risk Guardian will enforce final sizing hierarchy)
        current_equity = context.get("equity", 100000.0)
        target_shares = int((current_equity * allocation_pct) / tech.current_price)

        proposal = TradeProposal(
            symbol=target_symbol,
            side=target_side,
            allocation_pct=allocation_pct,
            target_shares=target_shares,
            notional_value=target_shares * tech.current_price,
            entry_target_price=tech.current_price,
            stop_loss_price=tech.suggested_stop_loss,
            take_profit_price=tech.suggested_take_profit or (tech.current_price * 1.05),
            thesis_summary=thesis_summary,
            regime=regime,
            macro=macro or MacroSentimentState(),
            technical=tech
        )

        self.logger.info(
            f"Generated Proposal: {proposal.side.value} {proposal.symbol} "
            f"@ ${proposal.entry_target_price:.2f} (Alloc: {proposal.allocation_pct:.0%})"
        )
        return proposal
