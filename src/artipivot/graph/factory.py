"""GraphFactory — build main graphs by agent_id."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from artipivot.config.center import ConfigCenter
from artipivot.graph.root import build_root_graph


class GraphFactory:
    """Build independent main graphs by agent_id."""

    def __init__(self, config_center: ConfigCenter) -> None:
        self._config_center = config_center

    def build(
        self,
        agent_id: str,
        sub_agent_nodes: dict[str, object] | None = None,
        checkpointer=None,
        store=None,
    ) -> CompiledStateGraph:
        """Build a compiled main graph for the given agent."""
        # Validate routing config against provided sub-agents
        if sub_agent_nodes:
            self._validate_routing(agent_id, sub_agent_nodes)

        builder = build_root_graph(
            config_center=self._config_center,
            sub_agent_nodes=sub_agent_nodes,
        )
        return builder.compile(checkpointer=checkpointer, store=store)

    def _validate_routing(
        self, agent_id: str, sub_agent_nodes: dict[str, object]
    ) -> None:
        """Verify that routing config's intent targets match provided sub-agents."""
        intent_map = self._config_center.routing.get_intent_map(agent_id)
        for intent, sub_name in intent_map.items():
            if sub_name not in sub_agent_nodes:
                raise ValueError(
                    f"Routing config for '{agent_id}' maps intent '{intent}' "
                    f"to sub-agent '{sub_name}', but no sub-agent graph provided. "
                    f"Available: {list(sub_agent_nodes)}"
                )
