"""Multi-Agent Trading Subsystem.

Exports all specialized agents:
- BaseAgent
- QuantRegimeAgent
- TechnicalAgent
- MacroSentimentAgent
- CIOPortfolioAgent
- RiskGuardianAgent
- HITLGatewayAgent
- ExecutionAgent
- SupervisorAgent
"""

from agents.base_agent import BaseAgent
from agents.quant_regime_agent import QuantRegimeAgent
from agents.technical_agent import TechnicalAgent
from agents.macro_sentiment_agent import MacroSentimentAgent
from agents.cio_portfolio_agent import CIOPortfolioAgent
from agents.risk_guardian_agent import RiskGuardianAgent
from agents.hitl_gateway_agent import HITLGatewayAgent
from agents.execution_agent import ExecutionAgent
from agents.supervisor_agent import SupervisorAgent

__all__ = [
    "BaseAgent",
    "QuantRegimeAgent",
    "TechnicalAgent",
    "MacroSentimentAgent",
    "CIOPortfolioAgent",
    "RiskGuardianAgent",
    "HITLGatewayAgent",
    "ExecutionAgent",
    "SupervisorAgent",
]
