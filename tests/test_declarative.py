"""Tests for declarative sub-agent engine."""

from __future__ import annotations

import pytest

from artipivot.agents.declarative import (
    DeclarativeSubAgentDef,
    build_declarative_subagent,
)
from artipivot.tools.builtin.web_search import web_search
from artipivot.tools.registry import ToolRegistry


def _tool_node():
    registry = ToolRegistry()
    registry.register(web_search)
    return registry.get_tool_node([web_search.name])


class TestDeclarativeSubAgentDef:
    def test_create(self):
        defn = DeclarativeSubAgentDef(
            name="test",
            strategy="react",
            tools=["web_search"],
            system_prompt="hello",
            strategy_config={"max_iterations": 3},
        )
        assert defn.strategy == "react"
        assert defn.strategy_config["max_iterations"] == 3

    def test_defaults(self):
        defn = DeclarativeSubAgentDef(
            name="test",
            strategy="react",
            tools=["web_search"],
        )
        assert defn.system_prompt == ""
        assert defn.strategy_config == {}


class TestBuildDeclarativeSubagent:
    def test_react(self):
        defn = DeclarativeSubAgentDef(
            name="test",
            strategy="react",
            tools=["web_search"],
            strategy_config={"max_iterations": 3},
        )
        graph = build_declarative_subagent(defn, _tool_node())
        assert graph is not None
        assert "llm_call" in set(graph.get_graph().nodes.keys())

    def test_function_calling(self):
        defn = DeclarativeSubAgentDef(
            name="test",
            strategy="function_calling",
            tools=["web_search"],
        )
        graph = build_declarative_subagent(defn, _tool_node())
        assert graph is not None

    def test_unknown_strategy_raises(self):
        defn = DeclarativeSubAgentDef(
            name="test",
            strategy="nonexistent",
            tools=["web_search"],
        )
        with pytest.raises(ValueError, match="Unknown strategy"):
            build_declarative_subagent(defn, _tool_node())
