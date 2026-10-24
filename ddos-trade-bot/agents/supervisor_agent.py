"""Supervisor Agent.

Continuous monitoring agent responsible for:
1. Monitoring open position drawdowns and trailing stops.
2. Checking emergency kill switches.
3. Invoking periodic 60-second broker REST reconciliation.
4. Persisting session snapshots to disk.
"""

from typing import Any, Dict

from agents.base_agent import BaseAgent
from broker.position_tracker import PositionTracker
from core.risk_manager import RiskManager
from core.state_models import SystemStateSnapshot


class SupervisorAgent(BaseAgent):
    """Monitors active positions, trailing stops, and system safety."""

    def __init__(
        self,
        config: Dict[str, Any] = None,
        position_tracker: PositionTracker = None,
        risk_manager: RiskManager = None
    ):
        super().__init__(name="SupervisorAgent", config=config)
        self.tracker = position_tracker or PositionTracker()
        self.risk_manager = risk_manager or RiskManager(config=self.config.get("risk", {}))

    async def process(self, context: Dict[str, Any]) -> SystemStateSnapshot:
        """Evaluate open positions and run reconciliation."""
        # 1. Run 60-second broker reconciliation
        await self.tracker.reconcile_with_alpaca()

        # 2. Get current snapshot
        pending_capital = self.risk_manager.pending_hitl_capital if self.risk_manager else 0.0
        snapshot = self.tracker.get_snapshot(pending_hitl_capital=pending_capital)

        # 3. Check circuit breakers on live positions
        cb = self.risk_manager.check_circuit_breakers(
            current_equity=snapshot.current_equity,
            day_opening_equity=snapshot.day_opening_equity,
            day_peak_equity=snapshot.day_peak_equity
        )

        if cb["halt_trading"]:
            self.logger.critical(f"EMERGENCY CIRCUIT BREAKER ACTIVATED: {cb['reason']}")
            snapshot.trading_halted = True

        # 4. Save updated state
        self.tracker.save_snapshot(pending_hitl_capital=pending_capital)
        return snapshot
