"""ReAct strategy — think → ToolNode → think loop."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from artipivot.agents.base import SubAgentDef
from artipivot.agents.strategies import register_strategy
from artipivot.agents.strategies.base import Strategy
from artipivot.graph.context import AgentContext
from artipivot.graph.state import SubAgentState


class ReActStrategy(Strategy):
    """ReAct — LLM reasons, acts via tools, observes, and repeats."""

    def build(
        self,
        sub_def: SubAgentDef,
        tool_node: ToolNode,
        *,
        config: dict | None = None,
    ) -> CompiledStateGraph:
        cfg = config or {}
        max_iterations = cfg.get("max_iterations", sub_def.max_iterations)
        system_prompt = sub_def.system_prompt
        # iteration counter stored in node closure
        state: dict = {"iterations": 0, "max_iterations": max_iterations}

        async def llm_call(st: SubAgentState, runtime) -> dict:
            from langgraph.runtime import Runtime

            rt: Runtime[AgentContext] = runtime
            model = rt.context.model

            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            if st.get("query"):
                messages.append(HumanMessage(content=st["query"]))
            messages.extend(st.get("messages", []))

            response = await model.ainvoke(messages)

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

        return builder.compile()


register_strategy("react", ReActStrategy)
