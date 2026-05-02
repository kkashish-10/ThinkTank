#!/usr/bin/env python3
"""
HMM Regime-Based Trading Bot - Main Entry Point

This module serves as the entry point for the automated trading system.
It initializes all components (HMM engine, broker client, strategy, etc.)
and starts the trading loop or backtesting process.

Usage:
    python main.py --mode backtest --start-date 2023-01-01 --end-date 2024-01-01
    python main.py --mode paper                    # Paper trading
    python main.py --mode live                     # Live trading (careful!)
"""

import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path
import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path='config/settings.yaml'):
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to settings.yaml
        
    Returns:
        Configuration dictionary
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def parse_arguments():
    """Parse command-line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='HMM Regime-Based Trading Bot'
    )
    parser.add_argument(
        '--mode',
        choices=['backtest', 'paper', 'live'],
        default='backtest',
        help='Trading mode'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        default='2023-01-01',
        help='Backtest start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        default=datetime.now().strftime('%Y-%m-%d'),
        help='Backtest end date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='config/settings.yaml',
        help='Path to settings.yaml'
    )
    
    return parser.parse_args()


def main():
    """Main entry point for the trading bot.
    
    This function:
    1. Loads configuration
    2. Parses command-line arguments
    3. Initializes all trading components
    4. Runs the appropriate mode (backtest/paper/live)
    """
    logger.info("Starting HMM Regime-Based Trading Bot")
    
    args = parse_arguments()
    
    try:
        # Load configuration
        config = load_config(args.config)
        logger.info(f"Configuration loaded from {args.config}")
        
        # TODO: Phase 2 - Implement actual trading logic
        # For now, this is a placeholder
        logger.info(f"Mode: {args.mode}")
        logger.info(f"Config symbols: {config['broker']['symbols']}")
        
        if args.mode == 'backtest':
            logger.info(f"Backtest period: {args.start_date} to {args.end_date}")
            # TODO: Initialize backtester and run
            
        elif args.mode == 'paper':
            logger.info("Starting paper trading mode")
            # TODO: Initialize paper trading client
            
        elif args.mode == 'live':
            logger.warning("LIVE TRADING MODE - Use with caution!")
            # TODO: Initialize live trading client with additional safeguards
            
    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
