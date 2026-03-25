from __future__ import annotations

from typing import Any, Protocol


class BaseAgent(Protocol):
    """
    Standard interface for all intelligent agents in the network.
    """

    async def evaluate(self, event: Any, *args: Any, **kwargs: Any) -> Any:
        """
        Evaluate an incoming transaction event and return a structured assessment (e.g., AgentSignal).
        """
        ...
