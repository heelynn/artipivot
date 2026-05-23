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

        from langchain_core.tools import BaseTool
        from langchain_core.tools import tool as langchain_tool

        module = importlib.import_module(module_path)
        fn = getattr(module, fn_name)
        # If already a LangChain tool, rename and register directly
        if isinstance(fn, BaseTool):
            fn.name = name
            self._tools[name] = fn
            return
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

    async def load_from_store(
        self, store, *, include_builtins: bool = True
    ) -> None:
        """Load tool definitions from DocumentStore "tools" collection.

        For each tool record:
          - type="builtin": discover from builtin directory, match by name
          - type="module": dynamic import + @tool wrapper
        """
        builtin_pool: dict[str, BaseTool] = {}

        records = await store.query("tools", {})
        for record in records:
            name = record.get("name", "")
            tool_type = record.get("type", "builtin")
            status = record.get("status", "active")
            if status != "active" or not name:
                continue

            if tool_type == "builtin":
                if not include_builtins:
                    continue
                if not builtin_pool:
                    from artipivot.tools.builtin import discover
                    builtin_pool = discover()
                tool = builtin_pool.get(name)
                if tool is not None:
                    self.register(tool)
                else:
                    _log.warning("registry.unknown_builtin_tool", tool=name)

            elif tool_type == "module":
                module_path = record.get("module", "")
                fn_name = record.get("function", "")
                if not module_path or not fn_name:
                    _log.warning(
                        "registry.incomplete_module_tool",
                        tool=name,
                        module=module_path,
                        function=fn_name,
                    )
                    continue
                self.register_module(name, module_path, fn_name)

        _log.info("registry.loaded_from_store", count=len(records))

    # ── query ─────────────────────────────────────────────────

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_or_stub(self, name: str) -> BaseTool:
        """Get a tool by name, or generate a stub placeholder.

        The stub tool returns a message indicating the tool is not yet available.
        When the real tool is registered later, the stub is automatically replaced.
        """
        tool = self._tools.get(name)
        if tool is not None:
            return tool

        from langchain_core.tools import tool as langchain_tool

        @langchain_tool(name)
        def _stub(**kwargs) -> str:
            """[STUB] This tool is not yet available."""
            return f"[STUB] Tool '{name}' is not yet available. Try again later."

        self._tools[name] = _stub
        _log.info("registry.stub_created", tool=name)
        return _stub

    def reload_module(
        self, name: str, module_path: str, fn_name: str
    ) -> None:
        """Re-import and re-register a module-type tool (replaces stub or existing).

        Uses importlib.reload() to pick up code changes in the module.
        """
        import importlib
        import sys

        from langchain_core.tools import BaseTool
        from langchain_core.tools import tool as langchain_tool

        module = sys.modules.get(module_path)
        if module is not None:
            module = importlib.reload(module)
        else:
            module = importlib.import_module(module_path)

        fn = getattr(module, fn_name)
        # If already a LangChain tool, rename and register directly
        if isinstance(fn, BaseTool):
            fn.name = name
            replaced = name in self._tools
            self._tools[name] = fn
            _log.info("registry.reloaded", tool=name, replaced=replaced)
            return
        if not callable(fn):
            raise TypeError(
                f"Tool function must be callable, got {type(fn).__name__}"
            )
        wrapped = langchain_tool(name)(fn)
        replaced = name in self._tools
        self._tools[name] = wrapped
        _log.info(
            "registry.reloaded",
            tool=name,
            replaced=replaced,
        )

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry (including stubs)."""
        self._tools.pop(name, None)
        _log.info("registry.unregistered", tool=name)

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
