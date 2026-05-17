"""Tests for P3 multi-agent system."""

from __future__ import annotations

import pytest

from artipivot.agents.base import SubAgentDef
from artipivot.agents.declarative import DeclarativeSubAgentDef
from artipivot.gateway.agent_def import AgentDef
from artipivot.memory.config import MemoryConfig


# ── Step 26: AgentDef ──


class TestAgentDef:
    def test_create_minimal(self):
        ad = AgentDef(agent_id="test_agent")
        assert ad.agent_id == "test_agent"
        assert ad.model == {}
        assert ad.confidence_threshold == 0.7
        assert ad.intent_map == {}
        assert ad.sub_agents == {}
        assert ad.declarative_sub_agents == {}
        assert ad.tools == []
        assert ad.prompts == {}
        assert isinstance(ad.memory_config, MemoryConfig)

    def test_create_full(self):
        ad = AgentDef(
            agent_id="code_agent",
            model={"provider": "anthropic", "name": "claude-sonnet-4-6"},
            confidence_threshold=0.8,
            intent_map={"code_write": "code_writer"},
            sub_agents={"code_writer": SubAgentDef(name="code_writer", tools=["web_search"])},
            tools=["web_search", "code_exec"],
            prompts={"classify": "Classify intent."},
        )
        assert ad.agent_id == "code_agent"
        assert ad.confidence_threshold == 0.8
        assert "code_writer" in ad.sub_agents
        assert len(ad.tools) == 2

    def test_from_dict(self):
        data = {
            "agent_id": "research_agent",
            "model": {"provider": "openai", "name": "gpt-4o"},
            "routing": {
                "confidence_threshold": 0.6,
                "intents": {"search": "researcher", "summarize": "researcher"},
            },
            "sub_agents": {
                "researcher": {
                    "strategy": "cot",
                    "tools": ["web_search"],
                    "system_prompt": "You are a research assistant.",
                    "strategy_config": {"max_plan_steps": 3},
                },
            },
            "prompts": {"classify": "Classify."},
            "memory": {"embedding": {"enabled": False}},
        }
        ad = AgentDef.from_dict(data)
        assert ad.agent_id == "research_agent"
        assert ad.model["provider"] == "openai"
        assert ad.confidence_threshold == 0.6
        assert ad.intent_map["search"] == "researcher"
        assert "researcher" in ad.declarative_sub_agents
        assert ad.declarative_sub_agents["researcher"].strategy == "cot"
        assert ad.memory_config.embedding.enabled is False

    def test_to_dict(self):
        ad = AgentDef(
            agent_id="test",
            model={"provider": "anthropic"},
            intent_map={"a": "sub_a"},
            sub_agents={"sub_a": SubAgentDef(name="sub_a", tools=[])},
            declarative_sub_agents={
                "sub_b": DeclarativeSubAgentDef(
                    name="sub_b", strategy="react", tools=["web_search"]
                )
            },
        )
        d = ad.to_dict()
        assert d["agent_id"] == "test"
        assert d["intent_map"]["a"] == "sub_a"
        assert "sub_a" in d["sub_agents"]
        assert "sub_b" in d["declarative_sub_agents"]
        assert d["declarative_sub_agents"]["sub_b"]["strategy"] == "react"

    def test_from_dict_defaults(self):
        ad = AgentDef.from_dict({"agent_id": "minimal"})
        assert ad.agent_id == "minimal"
        assert ad.model == {}
        assert ad.confidence_threshold == 0.7
        assert ad.intent_map == {}


# ── Step 27: AgentRegistry ──


class TestAgentRegistry:
    def _make_registry(self):
        from artipivot.config.center import ConfigCenter
        from artipivot.gateway.gateway import AgentGateway
        from artipivot.gateway.registry import AgentRegistry
        from artipivot.graph.factory import GraphFactory
        from artipivot.models.provider import ModelProvider
        from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier
        from artipivot.tools.registry import ToolRegistry
        from artipivot.tools.builtin.web_search import web_search

        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        provider = ModelProvider(store, notifier)
        config_center = ConfigCenter(store, notifier)
        gateway = AgentGateway(model_provider=provider, config_center=config_center)
        factory = GraphFactory(config_center)
        tools = ToolRegistry()
        tools.register(web_search)

        return AgentRegistry(gateway, factory, tools)

    def test_register_def_and_list(self):
        reg = self._make_registry()
        ad = AgentDef(
            agent_id="test_agent",
            sub_agents={"writer": SubAgentDef(name="writer", tools=["web_search"])},
        )
        reg.register_def(ad)
        assert "test_agent" in reg.list_agents()
        assert reg.get_def("test_agent") is ad

    def test_register_multiple(self):
        reg = self._make_registry()
        ad1 = AgentDef(agent_id="agent_a", sub_agents={"sa": SubAgentDef(name="sa", tools=["web_search"])})
        ad2 = AgentDef(agent_id="agent_b", sub_agents={"sb": SubAgentDef(name="sb", tools=["web_search"])})
        reg.register_def(ad1)
        reg.register_def(ad2)
        assert len(reg.list_agents()) == 2
        assert "agent_a" in reg.list_agents()
        assert "agent_b" in reg.list_agents()

    def test_get_def_unknown(self):
        reg = self._make_registry()
        assert reg.get_def("nonexistent") is None

    def test_register_with_declarative(self):
        """Declarative sub-agents with strategy are built via strategy engine."""
        reg = self._make_registry()
        ad = AgentDef(
            agent_id="decl_agent",
            declarative_sub_agents={
                "writer": DeclarativeSubAgentDef(
                    name="writer",
                    strategy="function_calling",
                    tools=["web_search"],
                )
            },
        )
        reg.register_def(ad)
        assert "decl_agent" in reg.list_agents()


# ── Step 28: GraphFactory validation ──


class TestGraphFactoryValidate:
    def _make_factory(self):
        from artipivot.config.center import ConfigCenter
        from artipivot.graph.factory import GraphFactory
        from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier

        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        config_center = ConfigCenter(store, notifier)
        return GraphFactory(config_center)

    def test_build_without_sub_agents(self):
        """No sub-agents → no validation needed → succeeds."""
        factory = self._make_factory()
        graph = factory.build("test_agent")
        assert graph is not None

    def test_build_with_matching_sub_agents(self):
        """Routing config intent targets match sub-agents → succeeds."""
        factory = self._make_factory()
        # No routing config loaded → empty intent_map → no mismatch
        from langgraph.graph import START, END, StateGraph
        from artipivot.graph.state import ArtiPivotState

        sub = StateGraph(ArtiPivotState)
        sub.add_node("noop", lambda s, r: {})
        sub.add_edge(START, "noop")
        sub.add_edge("noop", END)
        compiled = sub.compile()

        graph = factory.build("test_agent", sub_agent_nodes={"my_sub": compiled})
        assert graph is not None


# ── Step 29: YAML loader ──


class TestAgentLoader:
    def test_load_from_yaml(self, tmp_path):
        from artipivot.gateway.loader import load_agent_defs

        yaml_content = """
agents:
  code_agent:
    model:
      provider: anthropic
      name: claude-sonnet-4-6
    routing:
      confidence_threshold: 0.7
      intents:
        code_write: code_writer
    sub_agents:
      code_writer:
        strategy: react
        tools: [web_search, code_exec]
        system_prompt: "You are a coding assistant."
        strategy_config:
          max_iterations: 5
    prompts:
      classify: "Classify intent."
"""
        agents_file = tmp_path / "agents.yaml"
        agents_file.write_text(yaml_content)

        defs = load_agent_defs(tmp_path)
        assert "code_agent" in defs
        ad = defs["code_agent"]
        assert ad.agent_id == "code_agent"
        assert ad.model["provider"] == "anthropic"
        assert ad.confidence_threshold == 0.7
        assert ad.intent_map["code_write"] == "code_writer"
        assert "code_writer" in ad.declarative_sub_agents
        assert ad.declarative_sub_agents["code_writer"].strategy == "react"

    def test_load_no_file(self, tmp_path):
        from artipivot.gateway.loader import load_agent_defs

        defs = load_agent_defs(tmp_path)
        assert defs == {}

    def test_load_empty_yaml(self, tmp_path):
        from artipivot.gateway.loader import load_agent_defs

        (tmp_path / "agents.yaml").write_text("")
        defs = load_agent_defs(tmp_path)
        assert defs == {}

    def test_load_multiple_agents(self, tmp_path):
        from artipivot.gateway.loader import load_agent_defs

        yaml_content = """
agents:
  agent_a:
    model:
      provider: openai
      name: gpt-4o
    routing:
      intents:
        search: searcher
    sub_agents:
      searcher:
        strategy: cot
        tools: [web_search]

  agent_b:
    model:
      provider: anthropic
      name: claude-sonnet-4-6
    routing:
      intents:
        code: coder
    sub_agents:
      coder:
        strategy: react
        tools: [code_exec]
"""
        (tmp_path / "agents.yaml").write_text(yaml_content)
        defs = load_agent_defs(tmp_path)
        assert len(defs) == 2
        assert "agent_a" in defs
        assert "agent_b" in defs
        assert defs["agent_a"].model["provider"] == "openai"
        assert defs["agent_b"].model["provider"] == "anthropic"


# ── Step 30: Isolation verification ──


class TestMultiAgentIsolation:
    def _setup_multi_agent(self):
        from artipivot.config.center import ConfigCenter
        from artipivot.gateway.gateway import AgentGateway
        from artipivot.gateway.registry import AgentRegistry
        from artipivot.graph.factory import GraphFactory
        from artipivot.models.provider import ModelProvider
        from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier
        from artipivot.tools.registry import ToolRegistry
        from artipivot.tools.builtin.web_search import web_search
        from artipivot.tools.builtin.code_exec import code_exec

        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        provider = ModelProvider(store, notifier)
        config_center = ConfigCenter(store, notifier)
        gateway = AgentGateway(model_provider=provider, config_center=config_center)
        factory = GraphFactory(config_center)
        tools = ToolRegistry({"web_search": web_search, "code_exec": code_exec})

        registry = AgentRegistry(gateway, factory, tools)

        # Register two agents with different sub-agents
        ad1 = AgentDef(
            agent_id="code_agent",
            sub_agents={"writer": SubAgentDef(name="writer", tools=["web_search", "code_exec"])},
        )
        ad2 = AgentDef(
            agent_id="research_agent",
            sub_agents={"searcher": SubAgentDef(name="searcher", tools=["web_search"])},
        )
        registry.register_def(ad1)
        registry.register_def(ad2)

        return gateway, registry

    def test_state_isolation(self):
        """Different agents have separate graph instances."""
        gw, reg = self._setup_multi_agent()
        # Each agent has its own compiled graph
        assert "code_agent" in gw._graphs
        assert "research_agent" in gw._graphs
        assert gw._graphs["code_agent"] is not gw._graphs["research_agent"]

    def test_agent_def_isolation(self):
        """Each agent has its own AgentDef with different configs."""
        gw, reg = self._setup_multi_agent()
        def1 = reg.get_def("code_agent")
        def2 = reg.get_def("research_agent")
        assert def1 is not def2
        assert def1.agent_id != def2.agent_id

    @pytest.mark.asyncio
    async def test_thread_id_isolation(self):
        """Gateway prefixes thread_id with agent_id."""
        import unittest.mock as mock

        gw, reg = self._setup_multi_agent()

        # Mock model_provider to return a fake model
        fake_model = mock.AsyncMock()
        gw._model_provider.get_model = mock.Mock(return_value=fake_model)

        graph_mock = mock.AsyncMock()
        graph_mock.ainvoke.return_value = {"messages": []}
        gw._graphs["code_agent"] = graph_mock
        gw._graphs["research_agent"] = graph_mock

        await gw.invoke("code_agent", "hello", "t1")
        config = graph_mock.ainvoke.call_args[0][1]
        assert config["configurable"]["thread_id"] == "code_agent:t1"

        await gw.invoke("research_agent", "hello", "t1")
        config = graph_mock.ainvoke.call_args[0][1]
        assert config["configurable"]["thread_id"] == "research_agent:t1"

    def test_namespace_isolation(self):
        """Memory namespaces are agent-scoped."""
        from artipivot.memory.namespace import knowledge_ns, profile_ns

        ns1 = profile_ns("code_agent", "user1")
        ns2 = profile_ns("research_agent", "user1")
        assert ns1 != ns2
        assert ns1 == ("code_agent", "user1", "profile")
        assert ns2 == ("research_agent", "user1", "profile")

    def test_model_isolation(self):
        """AgentDefs can specify different models."""
        ad1 = AgentDef(agent_id="a", model={"provider": "anthropic", "name": "claude-sonnet-4-6"})
        ad2 = AgentDef(agent_id="b", model={"provider": "openai", "name": "gpt-4o"})
        assert ad1.model != ad2.model
        assert ad1.model["provider"] == "anthropic"
        assert ad2.model["provider"] == "openai"

    def test_tool_isolation(self):
        """Each agent's sub-agents have their own tool set."""
        from artipivot.tools.registry import ToolRegistry
        from artipivot.tools.builtin.web_search import web_search
        from artipivot.tools.builtin.code_exec import code_exec

        tools = ToolRegistry({"web_search": web_search, "code_exec": code_exec})

        # code_agent sub-agent gets both tools
        code_tools = tools.get_for_agent(["web_search", "code_exec"])
        assert len(code_tools) == 2

        # research_agent sub-agent only gets web_search
        research_tools = tools.get_for_agent(["web_search"])
        assert len(research_tools) == 1
        assert research_tools[0].name == "web_search"
