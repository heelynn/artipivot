"""GraphRebuilder — hot rebuild agent graphs on plugin/routing changes."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from artipivot.agents.declarative import build_declarative_subagent
from artipivot.agents.programmatic import build_programmatic_subagent
from artipivot.gateway.agent_def import AgentDef
from artipivot.gateway.gateway import AgentGateway
from artipivot.graph.factory import GraphFactory
from artipivot.plugins.manager import PluginDocument, PluginManager
from artipivot.tools.registry import ToolRegistry


class GraphRebuilder:
    """Hot rebuild agent graphs — rebuild + atomic swap in Gateway."""

    def __init__(
        self,
        gateway: AgentGateway,
        graph_factory: GraphFactory,
        tool_registry: ToolRegistry,
        plugin_manager: PluginManager,
    ) -> None:
        self._gateway = gateway
        self._factory = graph_factory
        self._tools = tool_registry
        self._plugins = plugin_manager

    async def rebuild_agent(
        self,
        agent_id: str,
        *,
        checkpointer=None,
        store=None,
    ) -> None:
        """Rebuild an agent's graph from current plugins and atomic-swap in Gateway."""
        # 1. Collect all active plugins for this agent
        plugins = await self._plugins.list_plugins(
            agent_id=agent_id, status="active"
        )

        # 2. Build sub-agent graphs from plugins
        sub_agent_nodes = self._build_sub_agents(plugins)

        # 3. Build routing intent_map from sub_agent plugins
        intent_map = {}
        for p in plugins:
            if p.plugin_type == "sub_agent":
                routing = p.manifest.get("routing", {})
                for intent, target in routing.get("intents", {}).items():
                    intent_map[intent] = target

        # 4. Build main graph
        graph = self._factory.build(
            agent_id=agent_id,
            sub_agent_nodes=sub_agent_nodes if sub_agent_nodes else None,
            checkpointer=checkpointer,
            store=store,
        )

        # 5. Atomic swap in Gateway
        self._gateway.register(agent_id, graph)

    def _build_sub_agents(
        self, plugins: list[PluginDocument]
    ) -> dict[str, CompiledStateGraph]:
        """Build sub-agent graphs from plugin manifests."""
        result: dict[str, CompiledStateGraph] = {}
        for p in plugins:
            if p.plugin_type != "sub_agent":
                continue

            manifest = p.manifest
            strategy = manifest.get("strategy")
            tool_names = manifest.get("tools", [])
            tool_node = self._tools.get_tool_node(tool_names)

            if strategy:
                from artipivot.agents.declarative import DeclarativeSubAgentDef
                from artipivot.agents.base import SubAgentDef

                defn = DeclarativeSubAgentDef(
                    name=p.name,
                    strategy=strategy,
                    tools=tool_names,
                    system_prompt=manifest.get("system_prompt", ""),
                    strategy_config=manifest.get("strategy_config", {}),
                )
                result[p.name] = build_declarative_subagent(defn, tool_node)
            else:
                from artipivot.agents.base import SubAgentDef

                sub_def = SubAgentDef(
                    name=p.name,
                    tools=tool_names,
                    system_prompt=manifest.get("system_prompt", ""),
                    max_iterations=manifest.get("max_iterations", 10),
                )
                result[p.name] = build_programmatic_subagent(sub_def, tool_node)

        return result
