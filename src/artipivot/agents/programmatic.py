"""Programmatic sub-agent — ReAct loop using LangGraph."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from langgraph.graph.state import CompiledStateGraph

from artipivot.agents.base import SubAgentDef
from artipivot.graph.context import AgentContext
from artipivot.graph.state import SubAgentState


def build_programmatic_subagent(
    sub_def: SubAgentDef,
    tool_node: ToolNode,
) -> CompiledStateGraph:
    """Build a ReAct-style sub-agent graph.

    Topology: START → llm_call → conditional(should_continue) → {tools, END}
               tools → llm_call (loop)
    """
    # Bind system prompt at build time
    system_prompt = sub_def.system_prompt

    async def llm_call(state: SubAgentState, runtime) -> dict:
        from langgraph.runtime import Runtime

        rt: Runtime[AgentContext] = runtime
        model = rt.context.model

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        if state.get("query"):
            messages.append(HumanMessage(content=state["query"]))
        messages.extend(state.get("messages", []))

        response = await model.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(state: SubAgentState) -> str:
        last_msg = state["messages"][-1] if state["messages"] else None
        if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        return END

    builder = StateGraph(SubAgentState)
    builder.add_node("llm_call", llm_call)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "llm_call")
    builder.add_conditional_edges("llm_call", should_continue)
    builder.add_edge("tools", "llm_call")

    return builder.compile()
