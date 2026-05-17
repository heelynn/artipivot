"""Tests for sub-agent strategies."""

from __future__ import annotations

import pytest

from artipivot.agents.base import SubAgentDef
from artipivot.agents.strategies import available_strategies, get_strategy
from artipivot.agents.strategies.base import Strategy
from artipivot.graph.state import SubAgentState
from artipivot.tools.builtin.web_search import web_search
from artipivot.tools.registry import ToolRegistry


def _tool_node():
    registry = ToolRegistry()
    registry.register(web_search)
    return registry.get_tool_node([web_search.name])


class TestStrategyRegistry:
    def test_available_strategies(self):
        # Import all strategies to trigger registration
        import artipivot.agents.strategies.react  # noqa: F401
        import artipivot.agents.strategies.function_calling  # noqa: F401

        names = available_strategies()
        assert "react" in names
        assert "function_calling" in names

    def test_get_strategy(self):
        import artipivot.agents.strategies.react  # noqa: F401

        s = get_strategy("react")
        assert isinstance(s, Strategy)

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy("nonexistent")


class TestReActStrategy:
    def test_build_graph(self):
        import artipivot.agents.strategies.react  # noqa: F401

        strategy = get_strategy("react")
        sub_def = SubAgentDef(
            name="test_agent",
            tools=["web_search"],
            system_prompt="test prompt",
            max_iterations=5,
        )
        graph = strategy.build(sub_def, _tool_node())
        assert graph is not None

    def test_graph_nodes(self):
        import artipivot.agents.strategies.react  # noqa: F401

        strategy = get_strategy("react")
        sub_def = SubAgentDef(name="test", tools=["web_search"])
        graph = strategy.build(sub_def, _tool_node())

        node_names = set(graph.get_graph().nodes.keys())
        # Should have llm_call, tools, plus START/END
        assert "llm_call" in node_names
        assert "tools" in node_names

    def test_config_max_iterations(self):
        import artipivot.agents.strategies.react  # noqa: F401

        strategy = get_strategy("react")
        sub_def = SubAgentDef(name="test", tools=["web_search"])
        graph = strategy.build(sub_def, _tool_node(), config={"max_iterations": 3})
        assert graph is not None


class TestFunctionCallingStrategy:
    def test_build_graph(self):
        import artipivot.agents.strategies.function_calling  # noqa: F401

        strategy = get_strategy("function_calling")
        sub_def = SubAgentDef(
            name="test_agent",
            tools=["web_search"],
            system_prompt="test",
        )
        graph = strategy.build(sub_def, _tool_node())
        assert graph is not None

    def test_graph_nodes(self):
        import artipivot.agents.strategies.function_calling  # noqa: F401

        strategy = get_strategy("function_calling")
        sub_def = SubAgentDef(name="test", tools=["web_search"])
        graph = strategy.build(sub_def, _tool_node())

        node_names = set(graph.get_graph().nodes.keys())
        assert "llm_call" in node_names
        assert "tools" in node_names

    def test_no_loop_back_edge(self):
        """Function Calling should NOT have tools → llm_call (no loop)."""
        import artipivot.agents.strategies.function_calling  # noqa: F401

        strategy = get_strategy("function_calling")
        sub_def = SubAgentDef(name="test", tools=["web_search"])
        graph = strategy.build(sub_def, _tool_node())

        g = graph.get_graph()
        # tools node should not have an edge back to llm_call
        edges_from_tools = [
            e for e in g.edges
            if hasattr(e, "source") and e.source == "tools"
        ]
        targets = [e.target for e in edges_from_tools]
        assert "llm_call" not in targets, "Function Calling must not loop back"
