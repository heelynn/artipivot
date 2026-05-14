"""ToolRegistry — global tool pool with permission filtering."""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode


class ToolRegistry:
    """Global tool pool with permission-based filtering."""

    def __init__(self, tools: dict[str, BaseTool] | None = None) -> None:
        self._tools: dict[str, BaseTool] = dict(tools) if tools else {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool by its name."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_for_agent(self, allowed: list[str]) -> list[BaseTool]:
        """Get tools filtered by permission whitelist."""
        return [self._tools[n] for n in allowed if n in self._tools]

    def get_tool_node(self, allowed: list[str]) -> ToolNode:
        """Build a ToolNode with permission-filtered tools."""
        return ToolNode(self.get_for_agent(allowed))

    @property
    def all_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    @property
    def names(self) -> list[str]:
        return list(self._tools.keys())
