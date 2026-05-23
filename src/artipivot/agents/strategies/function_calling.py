"""Function Calling strategy — single LLM call, optionally followed by one tool execution."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from artipivot.agents.base import SubAgentDef
from artipivot.agents.strategies import register_strategy
from artipivot.agents.strategies.base import Strategy
from artipivot.agents.strategies.memory import build_messages_with_memory
from artipivot.graph.context import AgentContext
from artipivot.graph.state import SubAgentState
from artipivot.observability import log, bind


class FunctionCallingStrategy(Strategy):
    """Function Calling — one-shot: LLM decides whether to call a tool, then returns."""

    def build(
        self,
        sub_def: SubAgentDef,
        tool_node: ToolNode,
        *,
        config: dict | None = None,
    ) -> CompiledStateGraph:
        default_prompt = sub_def.system_prompt
        sub_name = sub_def.name
        started: dict = {"flag": False}
        tools = list(tool_node.tools_by_name.values())

        async def llm_call(st: SubAgentState, runtime) -> dict:
            from langgraph.runtime import Runtime

            rt: Runtime[AgentContext] = runtime
            model = rt.context.bound_model(tools)

            if not started["flag"]:
                started["flag"] = True
                bind(sub_name=sub_name, strategy="function_calling")
                log.info("sub_agent.start")

            # Runtime prompt lookup from ConfigCenter
            system_prompt = default_prompt
            ctx = rt.context
            if ctx.config_center:
                prompt_cfg = ctx.config_center.prompts.get(
                    ctx.agent_id, "system", sub_name=sub_name
                )
                system_prompt = prompt_cfg.get("system", default_prompt)

            # Build messages with L3 memory + context window compression
            store = getattr(rt, "store", None)
            messages = await build_messages_with_memory(st, ctx, store, system_prompt)

            log.info("llm.call", messages_count=len(messages))

            response = await model.ainvoke(messages)

            tool_calls = getattr(response, "tool_calls", [])
            tool_call_names = [tc.get("name", "") for tc in tool_calls] if tool_calls else []
            log.info("llm.response", has_tool_calls=bool(tool_calls), tool_calls=tool_call_names)

            log.info("sub_agent.end")

            return {"messages": [response]}

        def should_use_tool(st: SubAgentState) -> str:
            last_msg = st["messages"][-1] if st["messages"] else None
            if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                return "tools"
            return END

        builder = StateGraph(SubAgentState)
        builder.add_node("llm_call", llm_call)
        builder.add_node("tools", tool_node)
        builder.add_edge(START, "llm_call")
        builder.add_conditional_edges("llm_call", should_use_tool)
        # Key difference from ReAct: tools → END (no loop back)
        builder.add_edge("tools", END)

        return builder.compile()


register_strategy("function_calling", FunctionCallingStrategy)
