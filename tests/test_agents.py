"""Tests for agents."""

from __future__ import annotations

import pytest

from artipivot.agents.base import SubAgentDef
from artipivot.agents.programmatic import build_programmatic_subagent
from artipivot.tools.builtin.web_search import web_search
from artipivot.tools.registry import ToolRegistry


class TestSubAgentDef:
    def test_creation(self):
        defn = SubAgentDef(
            name="test",
            tools=["web_search"],
            system_prompt="Test",
            max_iterations=5,
        )
        assert defn.name == "test"
        assert defn.tools == ["web_search"]
        assert defn.max_iterations == 5


class TestProgrammaticSubagent:
    @pytest.mark.asyncio
    async def test_build(self):
        reg = ToolRegistry()
        reg.register(web_search)
        tool_node = reg.get_tool_node(["web_search"])

        defn = SubAgentDef(name="test", tools=["web_search"])
        graph = build_programmatic_subagent(defn, tool_node)
        assert graph is not None
