"""Memory extraction — extract profile and knowledge from conversations."""

from __future__ import annotations

import json
import logging
import uuid

from langchain_core.messages import HumanMessage

from artipivot.memory.config import ExtractionConfig
from artipivot.memory.namespace import knowledge_ns, profile_ns

log = logging.getLogger(__name__)

# Built-in prompts
_PROFILE_PROMPT = (
    "分析以下对话，提取用户画像信息（姓名、语言偏好、技术栈、项目等）。\n"
    "返回纯 JSON 对象，例如："
    '{"name": "张三", "language": "Python", "tech_stack": ["FastAPI"]}\n'
    "如果没有新的画像信息，返回 {}"
)

_KNOWLEDGE_PROMPT = (
    "分析以下对话，提取值得长期记住的知识事实。\n"
    '返回 JSON 数组，例如：["用户偏好测试驱动开发", "用户的项目使用 PostgreSQL"]\n'
    "如果没有新知识，返回 []"
)


async def extract_profile(
    messages: list,
    model,
    config: ExtractionConfig | None = None,
) -> dict | None:
    """Extract user profile updates from conversation."""
    cfg = config or ExtractionConfig()
    if not cfg.profile.enabled:
        return None

    conversation = _format_messages(messages, cfg)
    prompt = cfg.profile.prompt or _PROFILE_PROMPT
    prompt = f"{prompt}\n\n{conversation}"

    try:
        response = await model.ainvoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
        return result if result else None
    except (json.JSONDecodeError, Exception):
        return None


async def extract_knowledge(
    messages: list,
    model,
    config: ExtractionConfig | None = None,
) -> list[str]:
    """Extract knowledge facts worth remembering from conversation."""
    cfg = config or ExtractionConfig()
    if not cfg.knowledge.enabled:
        return []

    conversation = _format_messages(messages, cfg)
    prompt = cfg.knowledge.prompt or _KNOWLEDGE_PROMPT
    prompt = f"{prompt}\n\n{conversation}"

    try:
        response = await model.ainvoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
        if isinstance(result, list):
            facts = [item for item in result if isinstance(item, str)]
            return facts[: cfg.knowledge.max_facts]
        return []
    except (json.JSONDecodeError, Exception):
        return []


async def write_memory(
    store,
    agent_id: str,
    user_id: str,
    messages: list,
    model,
    config: ExtractionConfig | None = None,
) -> None:
    """Extract and write long-term memory to Store."""
    cfg = config or ExtractionConfig()
    if not cfg.enabled:
        return

    # Profile
    profile = await extract_profile(messages, model, cfg)
    if profile:
        ns = profile_ns(agent_id, user_id)
        existing = await store.aget(ns, "main")
        if existing and existing.value:
            merged = {**existing.value, **profile}
        else:
            merged = profile
        await store.aput(ns, "main", merged)

    # Knowledge
    facts = await extract_knowledge(messages, model, cfg)
    ns = knowledge_ns(agent_id, user_id)
    for fact in facts:
        await store.aput(ns, str(uuid.uuid4()), {"fact": fact})


def _format_messages(messages: list, config: ExtractionConfig | None = None) -> str:
    """Format messages for extraction prompt."""
    cfg = config or ExtractionConfig()
    lines = []
    for m in messages[-cfg.max_messages :]:
        role = type(m).__name__.replace("Message", "")
        content = m.content if hasattr(m, "content") else str(m)
        lines.append(f"{role}: {content[:cfg.max_chars_per_message]}")
    return "\n".join(lines)
