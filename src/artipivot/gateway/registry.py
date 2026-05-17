"""AgentRegistry — multi-agent lifecycle management."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from artipivot.gateway.agent_def import AgentDef
from artipivot.gateway.gateway import AgentGateway
from artipivot.graph.factory import GraphFactory
from artipivot.tools.registry import ToolRegistry
from artipivot.transforms.registry import TransformRegistry


class AgentRegistry:
    """Multi-agent registry — builds graphs from AgentDef and registers to Gateway."""

    def __init__(
        self,
        gateway: AgentGateway,
        graph_factory: GraphFactory,
        tool_registry: ToolRegistry,
        *,
        transform_registry: TransformRegistry | None = None,
        model_provider=None,
        sub_agent_registry=None,
    ) -> None:
        self._gateway = gateway
        self._factory = graph_factory
        self._tools = tool_registry
        self._transforms = transform_registry or TransformRegistry()
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

        graph = self._factory.build(
            agent_id=agent_def.agent_id,
            sub_agent_nodes=sub_agent_nodes,
            checkpointer=checkpointer,
            store=store,
        )

        self._gateway.register(agent_def.agent_id, graph)
        self._defs[agent_def.agent_id] = agent_def

    def get_def(self, agent_id: str) -> AgentDef | None:
        """Get AgentDef by agent_id."""
        return self._defs.get(agent_id)

    def list_agents(self) -> list[str]:
        """List all registered agent_ids."""
        return list(self._defs)

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
            graph = self._sub_agent_registry.get(name)
            if graph is not None:
                result[name] = graph
                continue

            # Backward compat: auto-build from old-style dicts if present
            defn = self._find_def(agent_def, name)
            if defn is not None:
                graph = self._sub_agent_registry.build_and_register(
                    name, defn, checkpointer=checkpointer,
                )
                result[name] = graph
            else:
                raise ValueError(
                    f"Sub-agent '{name}' not found in registry and no definition in AgentDef"
                )

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
                transform_registry=self._transforms,
                compiled_sub_agents=result,
                checkpointer=checkpointer,
                model_provider=self._model_provider,
            )

        return result
