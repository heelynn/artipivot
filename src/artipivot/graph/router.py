"""Router nodes — classify intent and route by intent."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from artipivot.graph.context import AgentContext
from artipivot.graph.state import ArtiPivotState
from artipivot.config.center import ConfigCenter


# Default classify prompt
_DEFAULT_CLASSIFY_PROMPT = """You are an intent classifier. Classify the user message into one of the defined intents.
Return ONLY a JSON object with "intent" (string) and "confidence" (float 0.0-1.0).
If unsure, set confidence below 0.7.
"""


async def classify(
    state: ArtiPivotState, runtime, *, config_center: ConfigCenter
) -> dict:
    """Classify node — LLM structured output for intent recognition."""
    from langgraph.runtime import Runtime

    rt: Runtime[AgentContext] = runtime
    agent_id = rt.context.agent_id
    model = rt.context.model

    prompt_cfg = config_center.prompts.get(agent_id, "classify")
    system_prompt = prompt_cfg.get("system", _DEFAULT_CLASSIFY_PROMPT)

    messages = [
        SystemMessage(content=system_prompt),
        *state["messages"],
    ]

    response = await model.ainvoke(messages)

    try:
        result = json.loads(response.content)
        intent = result.get("intent", "general")
        confidence = float(result.get("confidence", 0.0))
    except (json.JSONDecodeError, ValueError):
        intent = "general"
        confidence = 0.0

    return {"intent": intent, "confidence": confidence}


def route_by_intent(
    state: ArtiPivotState, runtime, *, config_center: ConfigCenter
) -> str:
    """Conditional edge — route based on classified intent."""
    from langgraph.runtime import Runtime

    rt: Runtime[AgentContext] = runtime
    agent_id = rt.context.agent_id

    threshold = config_center.routing.get_threshold(agent_id)
    if state["confidence"] < threshold:
        return "clarify"

    intent_map = config_center.routing.get_intent_map(agent_id)
    return intent_map.get(state["intent"], "fallback")
