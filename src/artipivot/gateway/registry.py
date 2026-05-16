"""AgentRegistry — multi-agent lifecycle management."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from artipivot.agents.declarative import build_declarative_subagent
from artipivot.agents.programmatic import build_programmatic_subagent
from artipivot.gateway.agent_def import AgentDef
from artipivot.gateway.gateway import AgentGateway
from artipivot.graph.dsl import GraphDef, build_dsl_graph
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
    ) -> None:
        self._gateway = gateway
        self._factory = graph_factory
        self._tools = tool_registry
        self._transforms = transform_registry or TransformRegistry()
        self._defs: dict[str, AgentDef] = {}

    def register_def(
        self,
        agent_def: AgentDef,
        *,
        checkpointer=None,
        store=None,
    ) -> None:
        """Register an AgentDef: build sub-agents + main graph + register to Gateway."""
        sub_agent_nodes = self._build_sub_agents(agent_def)

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

    def _build_sub_agents(self, agent_def: AgentDef) -> dict[str, CompiledStateGraph]:
        """Build all sub-agent graphs from an AgentDef."""
        result: dict[str, CompiledStateGraph] = {}

        # Programmatic sub-agents
        for name, sub_def in agent_def.sub_agents.items():
            tool_node = self._tools.get_tool_node(sub_def.tools)
            result[name] = build_programmatic_subagent(sub_def, tool_node)

        # Declarative sub-agents
        for name, defn in agent_def.declarative_sub_agents.items():
            tool_node = self._tools.get_tool_node(defn.tools)
            result[name] = build_declarative_subagent(defn, tool_node)

        # DSL graph sub-agents
        for name, graph_def in agent_def.graph_sub_agents.items():
            result[name] = build_dsl_graph(
                graph_def,
                tool_registry=self._tools,
                transform_registry=self._transforms,
                compiled_sub_agents=result,  # allow sub_agent refs to earlier sub-agents
            )

        return result
