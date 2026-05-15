"""CoT (Chain-of-Thought) strategy — plan → execute → synthesize."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from artipivot.agents.base import SubAgentDef
from artipivot.agents.strategies import register_strategy
from artipivot.agents.strategies.base import Strategy
from artipivot.graph.context import AgentContext
from artipivot.graph.state import SubAgentState


class CoTStrategy(Strategy):
    """Chain-of-Thought — linear pipeline: plan → execute → synthesize."""

    def build(
        self,
        sub_def: SubAgentDef,
        tool_node: ToolNode,
        *,
        config: dict | None = None,
    ) -> CompiledStateGraph:
        cfg = config or {}
        max_plan_steps = cfg.get("max_plan_steps", 5)
        system_prompt = sub_def.system_prompt

        async def plan(st: SubAgentState, runtime) -> dict:
            from langgraph.runtime import Runtime

            rt: Runtime[AgentContext] = runtime
            model = rt.context.model

            messages = []
            if system_prompt:
                messages.append(
                    SystemMessage(
                        content=(
                            f"{system_prompt}\n\n"
                            "Analyze the task and output a JSON plan with up to "
                            f"{max_plan_steps} steps. Each step should have "
                            '"action" (description) and optionally "tool" (tool name).\n'
                            'Reply ONLY with a JSON array, e.g.: '
                            '[{"action": "search for X", "tool": "web_search"}]'
                        )
                    )
                )
            if st.get("query"):
                messages.append(HumanMessage(content=st["query"]))
            else:
                messages.extend(st.get("messages", []))

            response = await model.ainvoke(messages)
            plan_text = response.content if hasattr(response, "content") else str(response)

            # Try to parse the plan; if parsing fails, treat as single-step
            try:
                steps = json.loads(plan_text)
                if not isinstance(steps, list):
                    steps = [{"action": plan_text}]
            except (json.JSONDecodeError, TypeError):
                steps = [{"action": plan_text}]

            return {
                "messages": [response],
                "artifacts": [json.dumps(steps)],
            }

        async def execute(st: SubAgentState, runtime) -> dict:
            from langgraph.runtime import Runtime

            rt: Runtime[AgentContext] = runtime
            model = rt.context.model

            # Read plan from artifacts
            raw_plan = st.get("artifacts", [])[-1] if st.get("artifacts") else "[]"
            try:
                steps = json.loads(raw_plan)
            except (json.JSONDecodeError, TypeError):
                steps = []

            results = []
            for i, step in enumerate(steps):
                action = step.get("action", "")
                messages = [
                    SystemMessage(content=f"Execute step {i + 1}/{len(steps)}: {action}"),
                    HumanMessage(content=st.get("query", "")),
                ]
                response = await model.ainvoke(messages)
                results.append(
                    f"Step {i + 1}: {action}\nResult: {response.content if hasattr(response, 'content') else response}"
                )

            return {
                "messages": [
                    AIMessage(content="\n\n".join(results))
                ],
                "artifacts": results,
            }

        async def synthesize(st: SubAgentState, runtime) -> dict:
            from langgraph.runtime import Runtime

            rt: Runtime[AgentContext] = runtime
            model = rt.context.model

            artifacts = st.get("artifacts", [])
            summary_input = "\n\n".join(artifacts) if artifacts else "No results to summarize."

            messages = [
                SystemMessage(content="Summarize the following execution results into a clear, helpful response."),
                HumanMessage(content=summary_input),
            ]

            response = await model.ainvoke(messages)
            return {"messages": [response]}

        builder = StateGraph(SubAgentState)
        builder.add_node("plan", plan)
        builder.add_node("execute", execute)
        builder.add_node("synthesize", synthesize)
        builder.add_edge(START, "plan")
        builder.add_edge("plan", "execute")
        builder.add_edge("execute", "synthesize")
        builder.add_edge("synthesize", END)

        return builder.compile()


register_strategy("cot", CoTStrategy)
