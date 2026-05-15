"""Tests for declarative sub-agent engine and YAML loader."""

from __future__ import annotations

import pytest

from artipivot.agents.declarative import (
    DeclarativeSubAgentDef,
    build_declarative_subagent,
)
from artipivot.agents.loader import load_sub_agent_defs
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
            strategy="cot",
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

    def test_cot(self):
        defn = DeclarativeSubAgentDef(
            name="test",
            strategy="cot",
            tools=["web_search"],
        )
        graph = build_declarative_subagent(defn, _tool_node())
        assert graph is not None
        node_names = set(graph.get_graph().nodes.keys())
        assert "plan" in node_names
        assert "execute" in node_names
        assert "synthesize" in node_names

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


class TestSubAgentLoader:
    def test_load_from_yaml(self, tmp_path):
        yaml_content = """
sub_agents:
  code_writer:
    strategy: react
    tools:
      - web_search
    system_prompt: "You are a coding assistant."
    strategy_config:
      max_iterations: 5
"""
        (tmp_path / "sub_agents.yaml").write_text(yaml_content)
        result = load_sub_agent_defs(tmp_path)

        assert "code_writer" in result
        defn = result["code_writer"]
        assert defn.strategy == "react"
        assert defn.tools == ["web_search"]
        assert defn.system_prompt == "You are a coding assistant."
        assert defn.strategy_config == {"max_iterations": 5}

    def test_load_missing_file(self, tmp_path):
        result = load_sub_agent_defs(tmp_path)
        assert result == {}

    def test_load_empty_yaml(self, tmp_path):
        (tmp_path / "sub_agents.yaml").write_text("")
        result = load_sub_agent_defs(tmp_path)
        assert result == {}

    def test_load_multiple_agents(self, tmp_path):
        yaml_content = """
sub_agents:
  writer:
    strategy: react
    tools:
      - web_search
  reviewer:
    strategy: cot
    tools:
      - web_search
    strategy_config:
      max_plan_steps: 3
"""
        (tmp_path / "sub_agents.yaml").write_text(yaml_content)
        result = load_sub_agent_defs(tmp_path)

        assert len(result) == 2
        assert result["writer"].strategy == "react"
        assert result["reviewer"].strategy == "cot"
        assert result["reviewer"].strategy_config["max_plan_steps"] == 3
