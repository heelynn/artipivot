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
        builder = build_root_graph(
            config_center=self._config_center,
            sub_agent_nodes=sub_agent_nodes,
        )
        return builder.compile(checkpointer=checkpointer, store=store)
