"""Function Calling strategy — single LLM call, optionally followed by one tool execution."""

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


class FunctionCallingStrategy(Strategy):
    """Function Calling — one-shot: LLM decides whether to call a tool, then returns."""

    def build(
        self,
        sub_def: SubAgentDef,
        tool_node: ToolNode,
        *,
        config: dict | None = None,
    ) -> CompiledStateGraph:
        system_prompt = sub_def.system_prompt

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
