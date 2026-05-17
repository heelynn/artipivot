"""Root graph builder — single main graph construction."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from artipivot.config.center import ConfigCenter
from artipivot.graph.context import AgentContext
from artipivot.graph.router import classify, route_by_intent
from artipivot.graph.state import ArtiPivotState


async def clarify_node(state: ArtiPivotState, runtime) -> dict:
    """Ask user for clarification when confidence is low."""
    return {
        "messages": [
            {
                "role": "assistant",
                "content": "抱歉，我不太确定您的意思，请再描述一下您的需求？",
            }
        ]
    }


async def fallback_node(state: ArtiPivotState, runtime) -> dict:
    """Fallback response for unrecognized intents."""
    return {
        "messages": [
            {
                "role": "assistant",
                "content": "抱歉，我暂时无法处理这个请求，请尝试换一种描述方式？",
            }
        ]
    }


async def respond_node(state: ArtiPivotState, runtime) -> dict:
    """Format final output — passes through sub-agent response."""
    # If the last message is already from the assistant, just pass through
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

    # Bind config_center for the classify node
    async def _classify(state, runtime):
        return await classify(state, runtime, config_center=config_center)

    def _route(state, runtime):
        return route_by_intent(state, runtime, config_center=config_center)

    # Add fixed nodes
    builder.add_node("classify", _classify)
    builder.add_node("clarify", clarify_node)
    builder.add_node("fallback", fallback_node)
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
