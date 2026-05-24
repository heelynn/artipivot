"""AgentRegistry — multi-agent lifecycle management."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from artipivot.gateway.agent_def import AgentDef
from artipivot.gateway.gateway import AgentGateway
from artipivot.graph.factory import GraphFactory
from artipivot.observability import log
from artipivot.tools.registry import ToolRegistry


class AgentRegistry:
    """Multi-agent registry — builds graphs from AgentDef and registers to Gateway."""

    def __init__(
        self,
        gateway: AgentGateway,
        graph_factory: GraphFactory,
        tool_registry: ToolRegistry,
        *,
        model_provider=None,
        sub_agent_registry=None,
    ) -> None:
        self._gateway = gateway
        self._factory = graph_factory
        self._tools = tool_registry
        self._model_provider = model_provider
        self._sub_agent_registry = sub_agent_registry
        self._defs: dict[str, AgentDef] = {}

    def register_def(
        self,
        agent_def: AgentDef,
        *,
        checkpointer=None,
        store=None,
    ) -> None:
        """Register an AgentDef: resolve sub-agents + build main graph + register to Gateway."""
        sub_agent_nodes = self._resolve_sub_agents(agent_def, checkpointer=checkpointer)
        self._enrich_with_global_sub_agents(sub_agent_nodes)

        graph = self._factory.build(
            agent_id=agent_def.agent_id,
            sub_agent_nodes=sub_agent_nodes,
            checkpointer=checkpointer,
            store=store,
        )

        self._gateway.register(agent_def.agent_id, graph)
        self._defs[agent_def.agent_id] = agent_def

        # Pass circuit config to ModelProvider for LLM call protection
        if self._model_provider is not None and hasattr(self._model_provider, "set_circuit_config"):
            self._model_provider.set_circuit_config(agent_def.agent_id, agent_def.circuit)

        log.info(
            "registry.agent_registered",
            agent_id=agent_def.agent_id,
            sub_agents=list(sub_agent_nodes.keys()),
        )

    def get_def(self, agent_id: str) -> AgentDef | None:
        """Get AgentDef by agent_id."""
        return self._defs.get(agent_id)

    def list_agents(self) -> list[str]:
        """List all registered agent_ids."""
        return list(self._defs)

    async def rebuild_agent(
        self,
        agent_id: str,
        *,
        checkpointer=None,
        store=None,
    ) -> None:
        """Rebuild and re-register a single agent graph (for hot-reload).

        Uses rebuild_guard to serialize concurrent rebuilds of the same agent.
        The old graph continues serving in-flight requests via reference semantics.
        """
        agent_def = self._defs.get(agent_id)
        if agent_def is None:
            raise ValueError(f"Agent not found: {agent_id}")

        async with self._gateway.rebuild_guard(agent_id):
            sub_agent_nodes = self._resolve_sub_agents(
                agent_def, checkpointer=checkpointer
            )
            self._enrich_with_global_sub_agents(sub_agent_nodes)
            graph = self._factory.build(
                agent_id=agent_id,
                sub_agent_nodes=sub_agent_nodes,
                checkpointer=checkpointer,
                store=store,
            )
            self._gateway.register(agent_id, graph)
            log.info(
                "registry.agent_rebuilt",
                agent_id=agent_id,
                sub_agents=list(sub_agent_nodes.keys()),
            )

    def _enrich_with_global_sub_agents(
        self, sub_agent_nodes: dict[str, CompiledStateGraph]
    ) -> None:
        """Add all globally registered sub-agents for route validation.

        Route validation requires every intent target to have a sub-agent
        graph. Some targets may point to global (public) sub-agents not
        explicitly listed in sub_agent_refs. This method adds them.
        """
        if self._sub_agent_registry is None:
            return
        for name in self._sub_agent_registry.list_sub_agents():
            if name not in sub_agent_nodes:
                graph = self._sub_agent_registry.get(name)
                if graph is not None:
                    sub_agent_nodes[name] = graph

    def _resolve_sub_agents(
        self, agent_def: AgentDef, *, checkpointer=None
    ) -> dict[str, CompiledStateGraph]:
        """Resolve sub-agents by name from SubAgentRegistry.

        Backward compatible: if SubAgentRegistry is not set, falls back to
        building from old-style dicts.
        """
        if self._sub_agent_registry is None:
            return self._build_sub_agents_legacy(agent_def, checkpointer=checkpointer)

        result: dict[str, CompiledStateGraph] = {}

        for name in agent_def.sub_agent_refs:
            graph = self._resolve_one_sub_agent(
                agent_def, name, checkpointer=checkpointer
            )
            # Display name: strip agent_id prefix for result keys
            display_name = name
            result[display_name] = graph

        return result

    def _resolve_one_sub_agent(
        self, agent_def: AgentDef, name: str, *, checkpointer=None
    ) -> CompiledStateGraph:
        """Resolve a single sub-agent by name with namespace priority.

        Resolution order:
        1. Direct registry lookup by the given name (may be namespaced)
        2. For simple names: check agent_id__name (agent private) before public pool
        3. Check inline definitions in agent_def
        4. Auto-stub
        """
        agent_id = agent_def.agent_id

        # 1. Direct lookup (handles namespaced names like "agent_id__name")
        graph = self._sub_agent_registry.get(name)
        if graph is not None:
            return graph

        # 2. For simple (non-namespaced) names: check private namespace first,
        #    then public pool
        if "__" not in name:
            ns_name = f"{agent_id}__{name}"
            graph = self._sub_agent_registry.get(ns_name)
            if graph is not None:
                return graph

        # 3. Check inline definitions (both simple and namespaced names)
        defn = self._find_def(agent_def, name)
        if defn is None and "__" not in name:
            defn = self._find_def(agent_def, f"{agent_id}__{name}")
        if defn is not None:
            reg_name = defn.name if hasattr(defn, 'name') and defn.name else name
            graph = self._sub_agent_registry.build_and_register(
                reg_name, defn, checkpointer=checkpointer,
            )
            return graph

        # 4. Not found → auto-stub
        stub_name = name  # Use the given name for the stub
        log.info(
            "registry.sub_agent_stubbed",
            name=stub_name,
            agent_id=agent_id,
        )
        return self._sub_agent_registry.get_or_stub(stub_name)

        return result

    def _find_def(self, agent_def: AgentDef, name: str):
        """Find a sub-agent definition from old-style dicts."""
        if name in agent_def.sub_agents:
            return agent_def.sub_agents[name]
        if name in agent_def.declarative_sub_agents:
            return agent_def.declarative_sub_agents[name]
        if name in agent_def.graph_sub_agents:
            return agent_def.graph_sub_agents[name]
        return None

    def _build_sub_agents_legacy(
        self, agent_def: AgentDef, *, checkpointer=None
    ) -> dict[str, CompiledStateGraph]:
        """Legacy path — build directly without SubAgentRegistry."""
        from artipivot.agents.declarative import build_declarative_subagent
        from artipivot.agents.programmatic import build_programmatic_subagent
        from artipivot.graph.dsl import build_dsl_graph

        result: dict[str, CompiledStateGraph] = {}

        for name, sub_def in agent_def.sub_agents.items():
            tool_node = self._tools.get_tool_node(sub_def.tools)
            result[name] = build_programmatic_subagent(sub_def, tool_node)

        for name, defn in agent_def.declarative_sub_agents.items():
            tool_node = self._tools.get_tool_node(defn.tools)
            result[name] = build_declarative_subagent(defn, tool_node)

        for name, graph_def in agent_def.graph_sub_agents.items():
            result[name] = build_dsl_graph(
                graph_def,
                tool_registry=self._tools,
                compiled_sub_agents=result,
                checkpointer=checkpointer,
                model_provider=self._model_provider,
            )

        return result
