"""
Base node abstract class for all pipeline nodes.

Every internal and external node must implement __call__
which takes the shared AgentState and returns an updated copy.
"""

from abc import ABC, abstractmethod

from app.state.schema import AgentState


class BaseNode(ABC):
    """Abstract base class for pipeline graph nodes."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def __call__(self, state: AgentState) -> dict:
        """
        Execute node logic and return state updates.

        Returns a dict of state keys to update (LangGraph merges
        the returned dict into the existing state).
        """
        ...
