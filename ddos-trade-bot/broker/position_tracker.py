"""Position Tracker & State Snapshot Persistence.

Maintains real-time position state, handles atomic WebSocket fill events,
runs 60-second REST reconciliation heartbeats, and persists snapshots to disk.
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

from alpaca.trading.client import TradingClient

from core.state_models import PositionSnapshot, SystemStateSnapshot, OrderSide

logger = logging.getLogger(__name__)


class PositionTracker:
    """Tracks active positions and reconciles against Alpaca broker state."""

    def __init__(self, snapshot_path: str = "data/state_snapshot.json", client: Optional[TradingClient] = None):
        self.snapshot_path = Path(snapshot_path)
        self.client = client
        self.active_positions: Dict[str, PositionSnapshot] = {}
        
        # Session equity anchors
        self.session_date: str = datetime.utcnow().strftime("%Y-%m-%d")
        self.day_opening_equity: float = 100000.0
        self.day_peak_equity: float = 100000.0
        self.current_equity: float = 100000.0
        self.cash: float = 100000.0

        # Load existing state if available
        self.load_snapshot()

    def load_snapshot(self) -> None:
        """Load state snapshot from disk to ensure continuity across restarts."""
        if not self.snapshot_path.exists():
            logger.info("No prior state snapshot found; starting clean session.")
            return

        try:
            with open(self.snapshot_path, "r") as f:
                data = json.load(f)

            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            saved_date = data.get("session_date", "")

            # If today is same session, preserve day opening equity
            if saved_date == today_str:
                self.day_opening_equity = float(data.get("day_opening_equity", 100000.0))
                self.day_peak_equity = float(data.get("day_peak_equity", 100000.0))
                logger.info(
                    f"Resumed session for {today_str}. Opening Equity: ${self.day_opening_equity:,.2f}, "
                    f"Peak Equity: ${self.day_peak_equity:,.2f}"
                )
            else:
                # New trading day
                self.session_date = today_str
                self.day_opening_equity = float(data.get("current_equity", 100000.0))
                self.day_peak_equity = self.day_opening_equity
                logger.info(f"New session date {today_str}. Anchored Opening Equity: ${self.day_opening_equity:,.2f}")

            self.current_equity = float(data.get("current_equity", self.day_opening_equity))
            self.cash = float(data.get("cash", self.current_equity))

        except Exception as e:
            logger.error(f"Error loading state snapshot: {e}", exc_info=True)

    def save_snapshot(self, pending_hitl_capital: float = 0.0) -> None:
        """Save state snapshot to disk."""
        try:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Update peak equity
            if self.current_equity > self.day_peak_equity:
                self.day_peak_equity = self.current_equity

            # Calculate drawdowns
            daily_dd = max(0.0, (self.day_opening_equity - self.current_equity) / self.day_opening_equity) if self.day_opening_equity > 0 else 0.0
            peak_dd = max(0.0, (self.day_peak_equity - self.current_equity) / self.day_peak_equity) if self.day_peak_equity > 0 else 0.0

            snapshot = SystemStateSnapshot(
                session_date=self.session_date,
                day_opening_equity=self.day_opening_equity,
                day_peak_equity=self.day_peak_equity,
                current_equity=self.current_equity,
                cash=self.cash,
                current_drawdown=daily_dd,
                peak_drawdown=peak_dd,
                pending_hitl_capital=pending_hitl_capital,
                active_positions=self.active_positions,
                last_snapshot_time=datetime.utcnow()
            )

            with open(self.snapshot_path, "w") as f:
                json.dump(snapshot.model_dump(mode="json"), f, indent=2)

        except Exception as e:
            logger.error(f"Failed to persist state snapshot: {e}")

    def get_snapshot(self, pending_hitl_capital: float = 0.0) -> SystemStateSnapshot:
        """Get current in-memory system state snapshot."""
        daily_dd = max(0.0, (self.day_opening_equity - self.current_equity) / self.day_opening_equity) if self.day_opening_equity > 0 else 0.0
        peak_dd = max(0.0, (self.day_peak_equity - self.current_equity) / self.day_peak_equity) if self.day_peak_equity > 0 else 0.0

        return SystemStateSnapshot(
            session_date=self.session_date,
            day_opening_equity=self.day_opening_equity,
            day_peak_equity=self.day_peak_equity,
            current_equity=self.current_equity,
            cash=self.cash,
            current_drawdown=daily_dd,
            peak_drawdown=peak_dd,
            pending_hitl_capital=pending_hitl_capital,
            active_positions=self.active_positions,
            last_snapshot_time=datetime.utcnow()
        )

    async def reconcile_with_alpaca(self) -> None:
        """60-second REST reconciliation heartbeat with Alpaca ground truth."""
        if not self.client:
            return

        try:
            account = self.client.get_account()
            self.current_equity = float(account.equity)
            self.cash = float(account.cash)

            alpaca_positions = self.client.get_all_positions()
            active_symbols = set()

            for pos in alpaca_positions:
                symbol = pos.symbol
                active_symbols.add(symbol)
                qty = int(pos.qty)
                side = OrderSide.BUY if pos.side.value == "long" else OrderSide.SHORT
                avg_entry = float(pos.avg_entry_price)
                current_price = float(pos.current_price)
                unrealized_pnl = float(pos.unrealized_pl)
                unrealized_pnl_pct = float(pos.unrealized_plpc)

                existing = self.active_positions.get(symbol)
                stop_loss = existing.stop_loss_price if existing else (avg_entry * 0.98 if side == OrderSide.BUY else avg_entry * 1.02)

                self.active_positions[symbol] = PositionSnapshot(
                    symbol=symbol,
                    shares=qty,
                    side=side,
                    avg_entry_price=avg_entry,
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                    stop_loss_price=stop_loss,
                    entry_time=existing.entry_time if existing else datetime.utcnow()
                )

            # Prune closed positions
            closed_symbols = [s for s in self.active_positions if s not in active_symbols]
            for s in closed_symbols:
                logger.info(f"Position {s} closed on exchange; removing from tracker")
                del self.active_positions[s]

            self.save_snapshot()
            logger.debug(
                f"Reconciliation heartbeat complete: Equity=${self.current_equity:,.2f}, "
                f"Active Positions={len(self.active_positions)}"
            )

        except Exception as e:
            logger.error(f"Error during Alpaca reconciliation heartbeat: {e}")
