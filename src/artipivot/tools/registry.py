"""ToolRegistry — global tool pool with auto-discovery and permission filtering."""

from __future__ import annotations

import structlog

from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from artipivot.gateway.loader import ToolDef

_log = structlog.get_logger("artipivot.tools")


class ToolRegistry:
    """Global tool pool with auto-discovery and permission-based filtering."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ── registration ──────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Register a tool by its name."""
        self._tools[tool.name] = tool

    def register_module(
        self, name: str, module_path: str, fn_name: str
    ) -> None:
        """Dynamically import a function and register it as a LangChain tool."""
        import importlib

        from langchain_core.tools import tool as langchain_tool

        module = importlib.import_module(module_path)
        fn = getattr(module, fn_name)
        if not callable(fn):
            raise TypeError(
                f"Tool function must be callable, got {type(fn).__name__}"
            )
        wrapped = langchain_tool(name)(fn)
        self._tools[name] = wrapped

    def register_from_manifest(
        self, tool_defs: list[ToolDef], *, include_builtins: bool = True
    ) -> None:
        """Discover and register all tools declared in the manifest.

        Handles builtin (auto-scan) and module (dynamic import) types.
        """
        builtin_pool: dict[str, BaseTool] = {}

        for td in tool_defs:
            if td.type == "builtin":
                if not include_builtins:
                    continue
                # lazy discover on first builtin hit
                if not builtin_pool:
                    from artipivot.tools.builtin import discover
                    builtin_pool = discover()
                tool = builtin_pool.get(td.name)
                if tool is not None:
                    self.register(tool)
                else:
                    _log.warning("registry.unknown_builtin_tool", tool=td.name)

            elif td.type == "module":
                self.register_module(td.name, td.module, td.function)

    # ── query ─────────────────────────────────────────────────

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
