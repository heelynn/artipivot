"""Strategy ABC — all sub-agent strategies implement this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from artipivot.agents.base import SubAgentDef


class Strategy(ABC):
    """Sub-agent strategy — each strategy produces a different graph topology."""

    @abstractmethod
    def build(
        self,
        sub_def: SubAgentDef,
        tool_node: ToolNode,
        *,
        config: dict | None = None,
    ) -> CompiledStateGraph:
        """Build a compiled sub-agent graph for this strategy."""
        ...
