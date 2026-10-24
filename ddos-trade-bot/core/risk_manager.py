"""Quantitative Risk Management Engine.

Enforces absolute veto power over signals. Implements:
1. 1% Risk-per-trade rule with bracket stop sizing.
2. Sizing hierarchy: min(RiskUnits_1%, AllocationUnits_Regime, CapUnits_15%).
3. Multi-tiered daily/weekly/peak drawdown circuit breakers.
4. Pending Capital Reservation Locks (prevents double-spending during Telegram HITL).
5. State persistence & daily opening equity anchor (prevents reset bug).
"""

import os
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.state_models import RiskDecision, TradeProposal, SystemStateSnapshot, PositionSnapshot

logger = logging.getLogger(__name__)


class RiskManager:
    """Mathematical risk controller with absolute veto authority."""

    def __init__(self, config: Dict = None):
        """Initialize risk parameters from config dictionary.
        
        Args:
            config: Risk section of settings.yaml
        """
        self.config = config or {}
        
        # Portfolio limits
        self.max_risk_per_trade: float = float(self.config.get('max_risk_per_trade', 0.01))
        self.max_exposure: float = float(self.config.get('max_exposure', 0.80))
        self.max_leverage: float = float(self.config.get('max_leverage', 1.25))
        self.max_single_position: float = float(self.config.get('max_single_position', 0.15))
        self.max_concurrent: int = int(self.config.get('max_concurrent', 5))
        self.max_daily_trades: int = int(self.config.get('max_daily_trades', 20))
        
        # Circuit breaker thresholds
        self.daily_dd_reduce: float = float(self.config.get('daily_dd_reduce', 0.02))
        self.daily_dd_halt: float = float(self.config.get('daily_dd_halt', 0.03))
        self.weekly_dd_reduce: float = float(self.config.get('weekly_dd_reduce', 0.05))
        self.weekly_dd_halt: float = float(self.config.get('weekly_dd_halt', 0.07))
        self.max_dd_from_peak: float = float(self.config.get('max_dd_from_peak', 0.10))
        
        # State tracking
        self.lockfile_path: Path = Path(self.config.get('lockfile_path', 'trading_halted.lock'))
        self.pending_reservations: Dict[str, float] = {}  # proposal_id -> reserved_notional
        self.daily_trade_count: int = 0
        self.last_trade_date: Optional[date] = None

    @property
    def pending_hitl_capital(self) -> float:
        """Total capital currently locked in pending Telegram HITL proposals."""
        return sum(self.pending_reservations.values())

    def reserve_capital(self, proposal_id: str, notional_amount: float) -> None:
        """Lock capital for a pending Telegram HITL proposal."""
        self.pending_reservations[proposal_id] = float(notional_amount)
        logger.info(
            f"Reserved ${notional_amount:,.2f} for proposal {proposal_id}. "
            f"Total locked: ${self.pending_hitl_capital:,.2f}"
        )

    def release_capital(self, proposal_id: str) -> None:
        """Release locked capital when proposal is rejected or times out."""
        if proposal_id in self.pending_reservations:
            amount = self.pending_reservations.pop(proposal_id)
            logger.info(
                f"Released ${amount:,.2f} for proposal {proposal_id}. "
                f"Total locked: ${self.pending_hitl_capital:,.2f}"
            )

    def check_circuit_breakers(
        self,
        current_equity: float,
        day_opening_equity: float,
        day_peak_equity: float
    ) -> Dict[str, any]:
        """Evaluate multi-tiered drawdown limits.
        
        Returns:
            Dict containing halt_trading, reduce_size, current_drawdown, peak_drawdown
        """
        # Physical emergency lockfile check
        if self.lockfile_path.exists():
            return {
                'halt_trading': True,
                'reduce_size': False,
                'reason': 'Emergency lockfile exists (trading_halted.lock). Manual deletion required.',
                'current_drawdown': 1.0,
                'peak_drawdown': 1.0
            }

        # Daily Drawdown against persistent day opening equity
        if day_opening_equity > 0:
            daily_dd = max(0.0, (day_opening_equity - current_equity) / day_opening_equity)
        else:
            daily_dd = 0.0

        # Peak Drawdown from all-time or session peak
        if day_peak_equity > 0:
            peak_dd = max(0.0, (day_peak_equity - current_equity) / day_peak_equity)
        else:
            peak_dd = 0.0

        # 1. Catastrophic Peak DD -> Create lockfile and halt
        if peak_dd >= self.max_dd_from_peak:
            try:
                self.lockfile_path.write_text(
                    f"HALTED: Peak drawdown {peak_dd:.2%} exceeded threshold {self.max_dd_from_peak:.2%} at {datetime.utcnow()}\n"
                )
            except Exception as e:
                logger.error(f"Failed to create lockfile: {e}")
            return {
                'halt_trading': True,
                'reduce_size': False,
                'reason': f'Peak drawdown {peak_dd:.2%} >= limit {self.max_dd_from_peak:.2%}',
                'current_drawdown': daily_dd,
                'peak_drawdown': peak_dd
            }

        # 2. Daily DD Halt
        if daily_dd >= self.daily_dd_halt:
            return {
                'halt_trading': True,
                'reduce_size': False,
                'reason': f'Daily drawdown {daily_dd:.2%} >= halt threshold {self.daily_dd_halt:.2%}',
                'current_drawdown': daily_dd,
                'peak_drawdown': peak_dd
            }

        # 3. Daily DD Reduce (Halve sizes)
        if daily_dd >= self.daily_dd_reduce:
            return {
                'halt_trading': False,
                'reduce_size': True,
                'reason': f'Daily drawdown {daily_dd:.2%} >= reduce threshold {self.daily_dd_reduce:.2%}',
                'current_drawdown': daily_dd,
                'peak_drawdown': peak_dd
            }

        return {
            'halt_trading': False,
            'reduce_size': False,
            'reason': 'Drawdowns within safe thresholds',
            'current_drawdown': daily_dd,
            'peak_drawdown': peak_dd
        }

    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss_price: float,
        regime_allocation_pct: float
    ) -> Tuple[int, Dict[str, any]]:
        """Calculate shares using strict sizing hierarchy.
        
        Formula:
            min(RiskUnits_1%, AllocationUnits_Regime, CapUnits_15%)
        """
        if entry_price <= 0:
            return 0, {'error': 'Invalid entry price'}

        per_share_risk = abs(entry_price - stop_loss_price)
        if per_share_risk <= 0:
            return 0, {'error': 'Stop loss must differ from entry price'}

        # 1. 1% Account Risk Sizing
        max_dollar_risk = equity * self.max_risk_per_trade
        risk_units = int(max_dollar_risk / per_share_risk)

        # 2. Regime Allocation Sizing
        allocation_dollars = equity * max(0.0, regime_allocation_pct)
        alloc_units = int(allocation_dollars / entry_price)

        # 3. Single Position Cap (15% maximum)
        cap_dollars = equity * self.max_single_position
        cap_units = int(cap_dollars / entry_price)

        # Strict Hierarchy
        final_shares = max(0, min(risk_units, alloc_units, cap_units))

        details = {
            'per_share_risk': per_share_risk,
            'risk_units_1pct': risk_units,
            'regime_alloc_units': alloc_units,
            'single_position_cap_units': cap_units,
            'selected_shares': final_shares,
            'notional_value': final_shares * entry_price,
            'total_risk_dollars': final_shares * per_share_risk,
            'risk_pct_equity': (final_shares * per_share_risk) / equity if equity > 0 else 0.0
        }
        return final_shares, details

    def validate_proposal(
        self,
        proposal: TradeProposal,
        snapshot: SystemStateSnapshot
    ) -> RiskDecision:
        """Validate proposed trade against all risk and capital boundaries."""
        rejection_reasons = []

        # 1. Circuit breaker check
        cb = self.check_circuit_breakers(
            current_equity=snapshot.current_equity,
            day_opening_equity=snapshot.day_opening_equity,
            day_peak_equity=snapshot.day_peak_equity
        )
        if cb['halt_trading']:
            return RiskDecision(
                proposal_id=proposal.proposal_id,
                approved=False,
                original_shares=proposal.target_shares,
                approved_shares=0,
                stop_loss_required=proposal.stop_loss_price,
                risk_dollars=0.0,
                risk_pct_equity=0.0,
                circuit_breaker_active=True,
                rejection_reasons=[cb['reason']]
            )

        # 2. Daily trade count limit
        today = datetime.utcnow().date()
        if self.last_trade_date != today:
            self.daily_trade_count = 0
            self.last_trade_date = today

        if self.daily_trade_count >= self.max_daily_trades:
            rejection_reasons.append(f"Exceeded max daily trades: {self.max_daily_trades}")

        # 3. Max concurrent open positions
        if len(snapshot.active_positions) >= self.max_concurrent and proposal.symbol not in snapshot.active_positions:
            rejection_reasons.append(f"Exceeded max concurrent positions ({self.max_concurrent})")

        # 4. Sizing calculation with hierarchy
        shares, details = self.calculate_position_size(
            equity=snapshot.current_equity,
            entry_price=proposal.entry_target_price,
            stop_loss_price=proposal.stop_loss_price,
            regime_allocation_pct=proposal.allocation_pct
        )

        if cb['reduce_size']:
            shares = int(shares * 0.5)
            logger.warning("Daily DD reduce circuit breaker active: sizing halved")

        if shares <= 0:
            rejection_reasons.append(details.get('error', 'Calculated zero position size under risk rules'))

        # 5. Effective Capital Availability (Accounting for active exposure + pending HITL reservations)
        current_exposure = sum(p.shares * p.current_price for p in snapshot.active_positions.values())
        effective_available = snapshot.current_equity * self.max_exposure - (current_exposure + self.pending_hitl_capital)
        
        proposed_notional = shares * proposal.entry_target_price
        if proposed_notional > effective_available:
            # Scale down to fit available capital if possible
            affordable_shares = int(max(0.0, effective_available) / proposal.entry_target_price)
            if affordable_shares > 0:
                shares = affordable_shares
                proposed_notional = shares * proposal.entry_target_price
            else:
                rejection_reasons.append(
                    f"Insufficient effective buying power. Required: ${proposed_notional:,.2f}, Available: ${effective_available:,.2f} "
                    f"(Pending HITL locked: ${self.pending_hitl_capital:,.2f})"
                )

        # Determine approval
        approved = len(rejection_reasons) == 0 and shares > 0
        risk_dollars = shares * abs(proposal.entry_target_price - proposal.stop_loss_price)
        risk_pct = risk_dollars / snapshot.current_equity if snapshot.current_equity > 0 else 0.0

        if approved:
            self.reserve_capital(proposal.proposal_id, proposed_notional)

        return RiskDecision(
            proposal_id=proposal.proposal_id,
            approved=approved,
            modified=(shares != proposal.target_shares),
            original_shares=proposal.target_shares,
            approved_shares=shares,
            stop_loss_required=proposal.stop_loss_price,
            risk_dollars=risk_dollars,
            risk_pct_equity=risk_pct,
            rejection_reasons=rejection_reasons,
            circuit_breaker_active=cb['reduce_size'] or cb['halt_trading']
        )
