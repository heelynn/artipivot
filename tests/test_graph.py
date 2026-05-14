"""Tests for graph construction."""

from __future__ import annotations

import pytest

from artipivot.agents.base import SubAgentDef
from artipivot.agents.programmatic import build_programmatic_subagent
from artipivot.config.center import ConfigCenter
from artipivot.graph.factory import GraphFactory
from artipivot.graph.state import ArtiPivotState, SubAgentState
from artipivot.memory.checkpointer import create_checkpointer
from artipivot.memory.store import create_store
from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier
from artipivot.tools.builtin.code_exec import code_exec
from artipivot.tools.builtin.web_search import web_search
from artipivot.tools.registry import ToolRegistry


class TestGraphConstruction:
    def test_state_types(self):
        """Verify state types are TypedDicts."""
        assert "messages" in ArtiPivotState.__annotations__
        assert "messages" in SubAgentState.__annotations__
        assert "query" in SubAgentState.__annotations__

    @pytest.mark.asyncio
    async def test_build_root_graph(self):
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()

        await store.put("routing_configs", "test_agent", {
            "agent_id": "test_agent",
            "confidence_threshold": 0.7,
            "intents": [
                {"name": "code", "sub_agent": "code_writer"},
            ],
        })

        cc = ConfigCenter(store, notifier)
        await cc.start()

        factory = GraphFactory(cc)
        graph = factory.build("test_agent", checkpointer=create_checkpointer())
        assert graph is not None

    @pytest.mark.asyncio
    async def test_build_root_with_subgraph(self):
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()

        await store.put("routing_configs", "test_agent", {
            "agent_id": "test_agent",
            "confidence_threshold": 0.7,
            "intents": [
                {"name": "code", "sub_agent": "code_writer"},
            ],
        })

        cc = ConfigCenter(store, notifier)
        await cc.start()

        # Build sub-agent
        tool_reg = ToolRegistry()
        tool_reg.register(web_search)
        tool_node = tool_reg.get_tool_node(["web_search"])

        sub_def = SubAgentDef(
            name="code_writer",
            tools=["web_search"],
            system_prompt="Test",
        )
        sub_graph = build_programmatic_subagent(sub_def, tool_node)

        # Build main graph with subgraph
        factory = GraphFactory(cc)
        graph = factory.build(
            "test_agent",
            sub_agent_nodes={"code_writer": sub_graph},
            checkpointer=create_checkpointer(),
        )
        assert graph is not None


class TestSubAgent:
    @pytest.mark.asyncio
    async def test_build_programmatic_subagent(self):
        tool_reg = ToolRegistry()
        tool_reg.register(code_exec)
        tool_node = tool_reg.get_tool_node(["code_exec"])

        sub_def = SubAgentDef(
            name="test_agent",
            tools=["code_exec"],
            system_prompt="Test agent",
            max_iterations=3,
        )
        graph = build_programmatic_subagent(sub_def, tool_node)
        assert graph is not None
