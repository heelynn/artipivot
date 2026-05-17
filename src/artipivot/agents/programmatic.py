"""Programmatic sub-agent — ReAct loop using LangGraph."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from langgraph.graph.state import CompiledStateGraph

from artipivot.agents.base import SubAgentDef
from artipivot.graph.context import AgentContext
from artipivot.graph.state import SubAgentState
from artipivot.observability import log, bind, serialize


def build_programmatic_subagent(
    sub_def: SubAgentDef,
    tool_node: ToolNode,
) -> CompiledStateGraph:
    """Build a ReAct-style sub-agent graph.

    Topology: START → llm_call → conditional(should_continue) → {tools, END}
               tools → llm_call (loop)
    """
    default_prompt = sub_def.system_prompt
    sub_name = sub_def.name
    started: dict = {"flag": False}

    async def llm_call(state: SubAgentState, runtime) -> dict:
        from langgraph.runtime import Runtime

        rt: Runtime[AgentContext] = runtime
        model = rt.context.model

        if not started["flag"]:
            started["flag"] = True
            bind(sub_name=sub_name, strategy="programmatic")
            log.info("sub_agent.start")

        # Runtime prompt lookup from ConfigCenter
        system_prompt = default_prompt
        ctx = rt.context
        if ctx.config_center:
            prompt_cfg = ctx.config_center.prompts.get(
                ctx.agent_id, "system", sub_name=sub_name
            )
            system_prompt = prompt_cfg.get("system", default_prompt)

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        if state.get("query"):
            messages.append(HumanMessage(content=state["query"]))
        messages.extend(state.get("messages", []))

        log.info("llm.call", messages_count=len(messages))
        log.debug("llm.input", messages=[serialize(m) for m in messages])

        response = await model.ainvoke(messages)

        tool_calls = getattr(response, "tool_calls", [])
        log.info("llm.response", tool_calls=len(tool_calls))
        log.debug("llm.output", response=serialize(response))

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
