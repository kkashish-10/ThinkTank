#!/usr/bin/env python3
"""Multi-Agent Trading System - Main Entry Point.

Starts the asynchronous Multi-Agent Orchestrator, Telegram HITL Gateway,
FastAPI TradingView Webhook listener, and Alpaca Paper Trading connection.

Usage:
    python main.py --mode paper              # Full Multi-Agent Paper Trading
    python main.py --mode live               # Live Trading (requires confirmation)
    python main.py --mode webhook-only       # Start only TradingView webhook server
    python main.py --test-hitl               # Test Telegram interactive approval card
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
import uvicorn
import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("ddos-trade-bot")

from core.orchestrator import MultiAgentOrchestrator
from tradingview.webhook_server import create_tradingview_app
from tradingview.tunnel_manager import TunnelManager


def load_config(config_path: str = "config/settings.yaml") -> dict:
    """Load configuration YAML file."""
    path = Path(config_path)
    if not path.exists():
        logger.error(f"Config file not found at: {config_path}")
        sys.exit(1)
    with open(path, "r") as f:
        return yaml.safe_load(f)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Multi-Agent Trading System (ThinkTank)")
    parser.add_argument(
        "--mode",
        choices=["paper", "live", "webhook-only", "backtest"],
        default="paper",
        help="Operating mode (default: paper)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.yaml",
        help="Path to settings.yaml"
    )
    parser.add_argument(
        "--test-hitl",
        action="store_true",
        help="Send a test trade proposal to Telegram to verify HITL buttons"
    )
    parser.add_argument(
        "--tunnel",
        action="store_true",
        help="Auto-launch Cloudflare Tunnel for TradingView webhooks"
    )
    return parser.parse_args()


async def run_system(args, config):
    """Asynchronous entry point for the Multi-Agent Trading System."""
    # 1. Initialize Orchestrator
    orchestrator = MultiAgentOrchestrator(config)
    await orchestrator.initialize()

    # 2. Test Telegram HITL if requested
    if args.test_hitl:
        logger.info("Dispatching test proposal to Telegram...")
        from core.state_models import (
            TradeProposal, RiskDecision, MarketRegimeState,
            MacroSentimentState, TechnicalSignal, RegimeType, OrderSide
        )
        dummy_regime = MarketRegimeState(regime_id=0, regime_label=RegimeType.BULL_CALM, confidence=0.88)
        dummy_macro = MacroSentimentState()
        dummy_tech = TechnicalSignal(
            symbol="SPY",
            direction=OrderSide.BUY,
            conviction=0.85,
            current_price=510.50,
            suggested_stop_loss=505.0,
            suggested_take_profit=521.0
        )
        dummy_proposal = TradeProposal(
            symbol="SPY",
            side=OrderSide.BUY,
            allocation_pct=0.15,
            target_shares=20,
            notional_value=10210.0,
            entry_target_price=510.50,
            stop_loss_price=505.0,
            take_profit_price=521.0,
            thesis_summary="Test Signal: HMM Bull Calm Breakout",
            regime=dummy_regime,
            macro=dummy_macro,
            technical=dummy_tech
        )
        dummy_decision = RiskDecision(
            proposal_id=dummy_proposal.proposal_id,
            approved=True,
            original_shares=20,
            approved_shares=20,
            stop_loss_required=505.0,
            risk_dollars=110.0,
            risk_pct_equity=0.0011
        )
        logger.info("Awaiting interactive response on Telegram (tap Approve, Half, or Reject)...")
        hitl_res = await orchestrator.hitl_agent.process({
            "proposal": dummy_proposal,
            "risk_decision": dummy_decision,
            "current_price": 510.50
        })
        logger.info(f"Test HITL response received: {hitl_res.status.value if hitl_res else 'None'}")
        return

    # 3. Live Trading Safety Confirmation
    if args.mode == "live":
        print("\n" + "=" * 60)
        print("⚠️  WARNING: LIVE TRADING MODE REQUESTED")
        print("Real capital is at risk. All orders will be sent to Alpaca LIVE.")
        print("=" * 60)
        confirm = input("Type 'YES I UNDERSTAND THE RISKS' to proceed: ")
        if confirm.strip() != "YES I UNDERSTAND THE RISKS":
            print("Confirmation failed. Aborting.")
            sys.exit(0)

    # 4. Optional Cloudflare Tunnel launch
    tunnel_mgr = None
    if args.tunnel:
        tv_port = int(config.get("tradingview", {}).get("webhook_port", 8080))
        tunnel_mgr = TunnelManager(local_port=tv_port)
        tunnel_mgr.start_cloudflare_tunnel()

    # 5. Launch FastAPI Webhook Listener for TradingView
    tv_cfg = config.get("tradingview", {})
    tv_port = int(tv_cfg.get("webhook_port", 8080))
    tv_passphrase = tv_cfg.get("webhook_passphrase", "thinktank_secure_passphrase")

    app = create_tradingview_app(
        expected_passphrase=tv_passphrase,
        alert_callback=orchestrator.process_external_tv_alert
    )

    logger.info(f"Starting TradingView Webhook server on port {tv_port}...")
    server_config = uvicorn.Config(app=app, host="0.0.0.0", port=tv_port, log_level="warning")
    server = uvicorn.Server(server_config)

    try:
        await server.serve()
    finally:
        if tunnel_mgr:
            tunnel_mgr.stop()
        await orchestrator.hitl_agent.gateway.shutdown()
        logger.info("System safely shut down.")


def main():
    """CLI entry point."""
    args = parse_arguments()
    config = load_config(args.config)
    try:
        asyncio.run(run_system(args, config))
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (Ctrl+C).")


if __name__ == "__main__":
    main()
