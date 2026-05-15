"""Tests for P5 MCP adapter."""

from __future__ import annotations

import pytest

from artipivot.tools.mcp_adapter import MCPRegistry, MCPToolAdapter, MCPToolInfo
from artipivot.tools.registry import ToolRegistry


class TestMCPToolInfo:
    def test_creation(self):
        info = MCPToolInfo(
            name="search",
            description="Search the web",
            input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
        )
        assert info.name == "search"
        assert info.description == "Search the web"


class TestMCPToolAdapter:
    def test_adapt_tools_with_stub(self):
        adapter = MCPToolAdapter("http://localhost:3000", "test_server")
        adapter.register_tools([
            MCPToolInfo(
                name="search",
                description="Search",
                input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
            ),
        ])
        tools = adapter.adapt_tools()
        assert len(tools) == 1
        assert tools[0].name == "search"

    @pytest.mark.asyncio
    async def test_stub_tool_call(self):
        adapter = MCPToolAdapter("http://localhost:3000")
        adapter.register_tools([
            MCPToolInfo(
                name="search",
                description="Search",
                input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
            ),
        ])
        tools = adapter.adapt_tools()
        result = await tools[0].ainvoke({"query": "test"})
        assert "search" in result
        assert "test" in result

    @pytest.mark.asyncio
    async def test_custom_call_fn(self):
        calls = []

        async def my_call_fn(tool_name, args):
            calls.append((tool_name, args))
            return f"result for {tool_name}"

        adapter = MCPToolAdapter("http://localhost:3000")
        adapter.register_tools([
            MCPToolInfo(
                name="calc",
                description="Calculate",
                input_schema={"properties": {"expr": {"type": "string"}}, "required": ["expr"]},
            ),
        ])
        tools = adapter.adapt_tools(call_fn=my_call_fn)
        result = await tools[0].ainvoke({"expr": "1+1"})
        assert result == "result for calc"
        assert calls == [("calc", {"expr": "1+1"})]


class TestMCPRegistry:
    def test_register_server(self):
        registry = ToolRegistry()
        mcp = MCPRegistry(registry)

        names = mcp.register_server(
            "remote",
            "http://localhost:3000",
            tools=[
                MCPToolInfo("search", "Search", {"properties": {"q": {"type": "string"}}, "required": ["q"]}),
                MCPToolInfo("calc", "Calculate", {"properties": {"e": {"type": "string"}}, "required": ["e"]}),
            ],
        )
        assert names == ["search", "calc"]
        assert "search" in registry.names
        assert "calc" in registry.names

    def test_list_servers(self):
        registry = ToolRegistry()
        mcp = MCPRegistry(registry)
        mcp.register_server("s1", "http://a", tools=[])
        mcp.register_server("s2", "http://b", tools=[])
        assert mcp.list_servers() == ["s1", "s2"]

    def test_get_server(self):
        registry = ToolRegistry()
        mcp = MCPRegistry(registry)
        mcp.register_server("remote", "http://localhost:3000", tools=[])
        server = mcp.get_server("remote")
        assert server is not None
        assert server.url == "http://localhost:3000"
        assert mcp.get_server("nonexistent") is None
