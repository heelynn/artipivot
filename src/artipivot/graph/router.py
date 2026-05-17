"""Router nodes — classify intent and route by intent."""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from artipivot.graph.context import AgentContext
from artipivot.graph.state import ArtiPivotState
from artipivot.config.center import ConfigCenter
from artipivot.observability import log
from artipivot.observability import otel


# Default classify prompt — robust few-shot prompt that works across domains
_DEFAULT_CLASSIFY_PROMPT = """\
You are an intent classifier. Your ONLY job is to read the user message and \
classify it into exactly one of the allowed intents listed below.

## Allowed intents
{intents}

## Scoring criteria
仅评估用户意图是否清晰指向某个 allowed intent，不评估意图要执行的具体内容。
- 0.8–1.0：用户意图明确，与某个 allowed intent 高度匹配
- 0.5–0.8：用户意图可推断，但表述模糊或存在歧义
- 0.0–0.5：无法判断用户意图，或消息为寒暄/无意义内容

## Rules
1. 先在 reasoning 中完成以下思考：
   - 提取：用户消息中表达意图的关键词是什么？实际要处理的内容是什么？
   - 匹配：意图关键词指向哪个 intent？
   - 评分：仅按意图指向的清晰度评分，不考虑内容是否有意义。
2. Choose the single best-matching intent from the list above.
3. 按上述标准评估 confidence，严格打分，不要虚高。
4. Respond with ONLY a JSON object — no markdown, no explanation, no extra text.
5. JSON schema: {{"reasoning": "<思考过程>", "intent": "<one of the allowed intents>", "confidence": <0.0-1.0>}}

Now classify the user message. Return ONLY the JSON object.\
"""


async def classify(
    state: ArtiPivotState, runtime, *, config_center: ConfigCenter
) -> dict:
    """Classify node — LLM structured output for intent recognition."""
    from langgraph.runtime import Runtime

    rt: Runtime[AgentContext] = runtime
    agent_id = rt.context.agent_id
    model = rt.context.model

    # Resolve system prompt — supports both dict (from PromptStore) and str (from YAML)
    # Empty string / empty dict → falls back to built-in default
    prompt_cfg = config_center.prompts.get(agent_id, "classify")
    if isinstance(prompt_cfg, dict):
        system_prompt = prompt_cfg.get("system", "") or _DEFAULT_CLASSIFY_PROMPT
    elif isinstance(prompt_cfg, str) and prompt_cfg:
        system_prompt = prompt_cfg
    else:
        system_prompt = _DEFAULT_CLASSIFY_PROMPT

    # Replace {intents} placeholder with actual intent names + descriptions
    intent_map = config_center.routing.get_intent_map(agent_id)
    intent_descriptions = config_center.routing.get_intent_descriptions(agent_id)
    if intent_map:
        lines = []
        for name in intent_map:
            desc = intent_descriptions.get(name, "")
            if desc:
                lines.append(f"- {name}: {desc}")
            else:
                lines.append(f"- {name}")
        intents_str = "\n".join(lines)
    else:
        intents_str = "general"
    system_prompt = system_prompt.replace("{intents}", intents_str)

    messages = [
        SystemMessage(content=system_prompt),
        *state["messages"],
    ]

    # Extract user message for logging (last HumanMessage)
    user_msg = ""
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            user_msg = str(m.content)
            break

    log.debug(
        "classify.llm_input",
        system_prompt=system_prompt[:200],
        user_message=user_msg[:200],
        messages_count=len(messages),
    )

    response = await model.ainvoke(messages)

    log.debug("classify.llm_output", raw_response=response.content[:500])

    raw = response.content.strip()

    # Strip markdown code fences that some LLMs wrap around JSON
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)
    raw = raw.strip()

    # Extract first JSON object from response (handles trailing text)
    json_match = re.search(r"\{[^{}]*\}", raw)

    parsed = True
    try:
        json_str = json_match.group(0) if json_match else raw
        result = json.loads(json_str)
        reasoning = result.get("reasoning", "")
        intent = result.get("intent", "general")
        confidence = float(result.get("confidence", 0.0))
    except (json.JSONDecodeError, ValueError):
        parsed = False
        intent = raw if raw else "general"
        confidence = 0.5
        log.warning(
            "classify.parse_failure",
            raw_response=raw[:300],
            error="LLM did not return valid JSON",
        )

    threshold = config_center.routing.get_threshold(agent_id)
    log.info(
        "classify.result",
        reasoning=reasoning[:500],
        intent=intent[:200],
        confidence=confidence,
        threshold=threshold,
        parsed=parsed,
    )
    otel.record_intent(intent, confidence=confidence)

    return {"intent": intent, "confidence": confidence, "parsed": parsed}


def route_by_intent(
    state: ArtiPivotState, runtime, *, config_center: ConfigCenter
) -> str:
    """Conditional edge — route based on classified intent."""
    from langgraph.runtime import Runtime

    rt: Runtime[AgentContext] = runtime
    agent_id = rt.context.agent_id

    threshold = config_center.routing.get_threshold(agent_id)
    if state["confidence"] < threshold:
        # Distinguish parse failure from genuine low confidence
        reason = "parse_failure" if not state.get("parsed", True) else "below_threshold"
        log.info(
            "route.fallback",
            intent=state["intent"][:200],
            confidence=state["confidence"],
            reason=reason,
            route="clarify",
        )
        return "clarify"

    intent_map = config_center.routing.get_intent_map(agent_id)
    target = intent_map.get(state["intent"], "fallback")
    log.info("route.decision", intent=state["intent"][:200], target=target)
    return target
