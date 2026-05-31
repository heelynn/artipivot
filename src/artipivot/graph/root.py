"""Root graph builder — single main graph construction."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from artipivot.config.center import ConfigCenter
from artipivot.graph.context import AgentContext
from artipivot.graph.router import classify, route_by_intent
from artipivot.graph.state import ArtiPivotState


async def respond_node(state: ArtiPivotState, runtime) -> dict:
    """Format final output — passes through sub-agent response."""
    if state["messages"] and state["messages"][-1].type == "ai":
        return {}
    return {}


def build_root_graph(
    config_center: ConfigCenter,
    sub_agent_nodes: dict[str, object] | None = None,
) -> StateGraph:
    """Build the main graph for a single agent.

    Args:
        config_center: Config center for routing/prompt config.
        sub_agent_nodes: Map of sub_agent_name → compiled subgraph.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    builder = StateGraph(ArtiPivotState, context_schema=AgentContext)

    # Bind config_center for classify / clarify / fallback nodes
    async def _classify(state, runtime):
        return await classify(state, runtime, config_center=config_center)

    def _route(state, runtime):
        return route_by_intent(state, runtime, config_center=config_center)

    async def _clarify(state, runtime):
        from langgraph.runtime import Runtime
        rt: Runtime[AgentContext] = runtime
        agent_id = rt.context.agent_id
        msg = config_center.get_default_response(agent_id, "clarify")
        return {"messages": [{"role": "assistant", "content": msg}]}

    async def _fallback(state, runtime):
        from langgraph.runtime import Runtime
        rt: Runtime[AgentContext] = runtime
        agent_id = rt.context.agent_id
        msg = config_center.get_default_response(agent_id, "fallback")
        return {"messages": [{"role": "assistant", "content": msg}]}

    # Add fixed nodes
    builder.add_node("classify", _classify)
    builder.add_node("clarify", _clarify)
    builder.add_node("fallback", _fallback)
    builder.add_node("respond", respond_node)

    # Add sub-agent nodes
    sub_names = []
    if sub_agent_nodes:
        for name, subgraph in sub_agent_nodes.items():
            builder.add_node(name, subgraph)
            builder.add_edge(name, "respond")
            sub_names.append(name)

    # Fixed edges
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", _route)
    builder.add_edge("clarify", END)
    builder.add_edge("fallback", "respond")
    builder.add_edge("respond", END)

    return builder
