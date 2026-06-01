"""ReAct strategy — think → ToolNode → think loop."""

from __future__ import annotations

import time

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


class ReActStrategy(Strategy):
    """ReAct — LLM reasons, acts via tools, observes, and repeats."""

    def build(
        self,
        sub_def: SubAgentDef,
        tool_node: ToolNode,
        *,
        config: dict | None = None,
        checkpointer=None,
    ) -> CompiledStateGraph:
        cfg = config or {}
        max_iterations = cfg.get("max_iterations", sub_def.max_iterations)
        default_prompt = sub_def.system_prompt
        sub_name = sub_def.name
        state: dict = {"iterations": 0, "max_iterations": max_iterations, "start_time": None}
        tools = list(tool_node.tools_by_name.values())

        async def llm_call(st: SubAgentState, runtime) -> dict:
            from langgraph.runtime import Runtime

            rt: Runtime[AgentContext] = runtime
            model = rt.context.bound_model(tools)

            if state["start_time"] is None:
                state["start_time"] = time.perf_counter()
                bind(sub_name=sub_name, strategy="react")
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

            bind(iteration=state["iterations"])
            log.info("llm.call", messages_count=len(messages))

            response = await model.ainvoke(messages)

            tool_calls = getattr(response, "tool_calls", [])
            log.info("llm.response", tool_calls=len(tool_calls), has_content=bool(response.content))

            state["iterations"] += 1
            return {"messages": [response]}

        def should_continue(st: SubAgentState) -> str:
            if state["iterations"] >= state["max_iterations"]:
                return END
            last_msg = st["messages"][-1] if st["messages"] else None
            if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                return "tools"
            return END

        builder = StateGraph(SubAgentState)
        builder.add_node("llm_call", llm_call)
        builder.add_node("tools", tool_node)
        builder.add_edge(START, "llm_call")
        builder.add_conditional_edges("llm_call", should_continue)
        builder.add_edge("tools", "llm_call")

        return builder.compile(checkpointer=checkpointer)


register_strategy("react", ReActStrategy)
