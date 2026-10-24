"""Abstract Base Class for Multi-Agent Trading System.

All specialized agents inherit from BaseAgent, ensuring unified
lifecycle, error isolation, and typed input/output processing.
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base agent providing common logging and lifecycle hooks."""

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"agent.{name}")
        self.enabled = bool(self.config.get("enabled", True))

    @abstractmethod
    async def process(self, context: Dict[str, Any]) -> Any:
        """Process market state or signals asynchronously.
        
        Args:
            context: Shared state dictionary containing market data,
                     signals, portfolio state, etc.
                     
        Returns:
            Specialized agent output model or state update.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} enabled={self.enabled}>"
