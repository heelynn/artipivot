"""MCP adapter — adapt MCP Server tools into LangChain BaseTool."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, create_model

from artipivot.tools.registry import ToolRegistry


class MCPToolInfo:
    """Describes a single MCP tool discovered from a server."""

    def __init__(self, name: str, description: str, input_schema: dict) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema


def _build_args_schema(tool_info: MCPToolInfo) -> type[BaseModel]:
    """Build a Pydantic model from MCP tool's JSON Schema input."""
    properties = tool_info.input_schema.get("properties", {})
    required = tool_info.input_schema.get("required", [])

    fields: dict[str, Any] = {}
    for fname, fschema in properties.items():
        field_type = str
        default = ... if fname in required else None
        fields[fname] = (field_type, default)

    if not fields:
        fields["_placeholder"] = (str, None)

    return create_model(f"{tool_info.name}_args", **fields)


class MCPToolAdapter:
    """Adapts MCP Server tools into LangChain BaseTool instances."""

    def __init__(self, server_url: str, server_name: str | None = None) -> None:
        self._url = server_url
        self._name = server_name or server_url
        self._tools: list[MCPToolInfo] = []

    @property
    def url(self) -> str:
        return self._url

    @property
    def name(self) -> str:
        return self._name

    def register_tools(self, tool_infos: list[MCPToolInfo]) -> None:
        """Register discovered tool info (called after discovery or manually)."""
        self._tools = tool_infos

    def adapt_tools(self, call_fn=None) -> list[BaseTool]:
        """Convert registered MCP tool infos into LangChain BaseTool instances.

        Args:
            call_fn: Async callable(tool_name, arguments) -> str.
                     If None, returns a placeholder implementation.
        """
        result: list[BaseTool] = []
        for info in self._tools:
            tool = self._wrap_tool(info, call_fn)
            result.append(tool)
        return result

    def _wrap_tool(
        self, info: MCPToolInfo, call_fn=None
    ) -> BaseTool:
        """Wrap a single MCP tool info into a LangChain BaseTool."""
        from langchain_core.tools import tool as tool_decorator

        args_schema = _build_args_schema(info)
        tool_name = info.name
        url = self._url

        if call_fn is not None:

            @tool_decorator(tool_name, description=info.description, args_schema=args_schema)
            async def wrapped(**kwargs) -> str:
                return await call_fn(tool_name, kwargs)

        else:

            @tool_decorator(tool_name, description=info.description, args_schema=args_schema)
            async def wrapped(**kwargs) -> str:
                return f"[MCP stub] {tool_name} called with {kwargs} via {url}"

        wrapped.name = tool_name  # type: ignore[attr-defined]
        return wrapped


class MCPRegistry:
    """Registry for MCP Server connections — discovers and registers tools."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry
        self._servers: dict[str, MCPToolAdapter] = {}

    def register_server(
        self,
        name: str,
        url: str,
        tools: list[MCPToolInfo] | None = None,
        call_fn=None,
    ) -> list[str]:
        """Register an MCP server and adapt its tools into the ToolRegistry.

        Args:
            name: Server identifier.
            url: MCP Server URL.
            tools: Pre-discovered tool infos (or None for manual setup).
            call_fn: Async callable for tool execution.

        Returns:
            List of registered tool names.
        """
        adapter = MCPToolAdapter(url, name)
        if tools:
            adapter.register_tools(tools)

        adapted = adapter.adapt_tools(call_fn)
        for t in adapted:
            self._tool_registry.register(t)

        self._servers[name] = adapter
        return [t.name for t in adapted]

    def get_server(self, name: str) -> MCPToolAdapter | None:
        return self._servers.get(name)

    def list_servers(self) -> list[str]:
        return list(self._servers)
