"""Tests for SubAgentRegistry — independent sub-agent lifecycle."""

from __future__ import annotations

import pytest

from artipivot.agents.base import SubAgentDef
from artipivot.agents.declarative import DeclarativeSubAgentDef
from artipivot.graph.dsl import parse_graph_def
from artipivot.gateway.sub_agent_registry import SubAgentRegistry
from artipivot.tools.registry import ToolRegistry


def _make_tool_registry():
    from langchain_core.tools import tool

    @tool
    def web_search(query: str) -> str:
        """Search the web."""
        return f"results for {query}"

    @tool
    def code_exec(code: str) -> str:
        """Execute code."""
        return f"executed: {code}"

    reg = ToolRegistry()
    reg.register(web_search)
    reg.register(code_exec)
    return reg


class TestSubAgentRegistry:
    def test_register_and_get(self):
        from langgraph.graph import StateGraph, END, START
        from artipivot.graph.state import SubAgentState

        tools = _make_tool_registry()
        reg = SubAgentRegistry(tools)

        builder = StateGraph(SubAgentState)
        builder.add_node("a", lambda s: s)
        builder.add_edge(START, "a")
        builder.add_edge("a", END)
        graph = builder.compile()

        reg.register("my_sub", graph)
        assert reg.get("my_sub") is graph

    def test_get_nonexistent_returns_none(self):
        reg = SubAgentRegistry(ToolRegistry())
        assert reg.get("missing") is None

    def test_list_sub_agents(self):
        from langgraph.graph import StateGraph, END, START
        from artipivot.graph.state import SubAgentState

        reg = SubAgentRegistry(ToolRegistry())

        for name in ["a", "b", "c"]:
            builder = StateGraph(SubAgentState)
            builder.add_node("n", lambda s: s)
            builder.add_edge(START, "n")
            builder.add_edge("n", END)
            reg.register(name, builder.compile())

        assert sorted(reg.list_sub_agents()) == ["a", "b", "c"]


class TestSubAgentRegistryBuild:
    def test_build_programmatic(self):
        tools = _make_tool_registry()
        reg = SubAgentRegistry(tools)

        defn = SubAgentDef(name="writer", tools=["web_search"])
        graph = reg.build_and_register("writer", defn)

        assert graph is not None
        assert reg.get("writer") is graph

    def test_build_declarative(self):
        tools = _make_tool_registry()
        reg = SubAgentRegistry(tools)

        defn = DeclarativeSubAgentDef(
            name="coder",
            strategy="react",
            tools=["web_search", "code_exec"],
        )
        graph = reg.build_and_register("coder", defn)

        assert graph is not None
        assert reg.get("coder") is graph

    def test_build_dsl(self):
        tools = _make_tool_registry()

        reg = SubAgentRegistry(tools)
        gd = parse_graph_def(
            "pipeline",
            {
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "END"},
                ],
            },
        )
        graph = reg.build_and_register("pipeline", gd)

        assert graph is not None
        assert reg.get("pipeline") is graph


class TestSubAgentDeduplication:
    def test_same_definition_shares_graph(self):
        """Two sub-agents with identical definitions share the same compiled graph."""
        tools = _make_tool_registry()
        reg = SubAgentRegistry(tools)

        defn1 = SubAgentDef(name="writer_a", tools=["web_search"])
        defn2 = SubAgentDef(name="writer_b", tools=["web_search"])

        graph1 = reg.build_and_register("writer_a", defn1)
        graph2 = reg.build_and_register("writer_b", defn2)

        assert graph1 is graph2  # same object

    def test_different_tools_different_graph(self):
        """Different tool lists produce different compiled graphs."""
        tools = _make_tool_registry()
        reg = SubAgentRegistry(tools)

        defn1 = SubAgentDef(name="search_only", tools=["web_search"])
        defn2 = SubAgentDef(name="both_tools", tools=["web_search", "code_exec"])

        graph1 = reg.build_and_register("search_only", defn1)
        graph2 = reg.build_and_register("both_tools", defn2)

        assert graph1 is not graph2

    def test_same_declarative_strategy_shares(self):
        """Same strategy + same tools = shared graph."""
        tools = _make_tool_registry()
        reg = SubAgentRegistry(tools)

        defn1 = DeclarativeSubAgentDef(name="a", strategy="react", tools=["web_search"])
        defn2 = DeclarativeSubAgentDef(name="b", strategy="react", tools=["web_search"])

        graph1 = reg.build_and_register("a", defn1)
        graph2 = reg.build_and_register("b", defn2)

        assert graph1 is graph2

    def test_different_strategy_different_graph(self):
        """Different strategies produce different compiled graphs."""
        tools = _make_tool_registry()
        reg = SubAgentRegistry(tools)

        defn1 = DeclarativeSubAgentDef(name="react_agent", strategy="react", tools=["web_search"])
        defn2 = DeclarativeSubAgentDef(name="fc_agent", strategy="function_calling", tools=["web_search"])

        graph1 = reg.build_and_register("react_agent", defn1)
        graph2 = reg.build_and_register("fc_agent", defn2)

        assert graph1 is not graph2
