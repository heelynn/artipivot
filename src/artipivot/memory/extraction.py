"""Memory extraction — extract profile and knowledge from conversations."""

from __future__ import annotations

import json
import uuid

from langchain_core.messages import HumanMessage, SystemMessage

from artipivot.memory.namespace import knowledge_ns, profile_ns


async def extract_profile(messages: list, model) -> dict | None:
    """Extract user profile updates from conversation."""
    conversation = _format_messages(messages)
    prompt = (
        "分析以下对话，提取用户画像信息（姓名、语言偏好、技术栈、项目等）。\n"
        "返回纯 JSON 对象，例如："
        '{"name": "张三", "language": "Python", "tech_stack": ["FastAPI"]}\n'
        "如果没有新的画像信息，返回 {}"
        f"\n\n{conversation}"
    )

    try:
        response = await model.ainvoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)
        # Strip markdown code blocks if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
        return result if result else None
    except (json.JSONDecodeError, Exception):
        return None


async def extract_knowledge(messages: list, model) -> list[str]:
    """Extract knowledge facts worth remembering from conversation."""
    conversation = _format_messages(messages)
    prompt = (
        "分析以下对话，提取值得长期记住的知识事实。\n"
        '返回 JSON 数组，例如：["用户偏好测试驱动开发", "用户的项目使用 PostgreSQL"]\n'
        "如果没有新知识，返回 []"
        f"\n\n{conversation}"
    )

    try:
        response = await model.ainvoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
        if isinstance(result, list):
            return [item for item in result if isinstance(item, str)]
        return []
    except (json.JSONDecodeError, Exception):
        return []


async def write_memory(store, agent_id: str, user_id: str, messages: list, model) -> None:
    """Extract and write long-term memory to Store."""
    # Profile
    profile = await extract_profile(messages, model)
    if profile:
        ns = profile_ns(agent_id, user_id)
        existing = await store.aget(ns, "main")
        if existing and existing.value:
            merged = {**existing.value, **profile}
        else:
            merged = profile
        await store.aput(ns, "main", merged)

    # Knowledge
    facts = await extract_knowledge(messages, model)
    ns = knowledge_ns(agent_id, user_id)
    for fact in facts:
        await store.aput(ns, str(uuid.uuid4()), {"fact": fact})


def _format_messages(messages: list) -> str:
    """Format messages for extraction prompt."""
    lines = []
    for m in messages[-10:]:  # Only use recent messages
        role = type(m).__name__.replace("Message", "")
        content = m.content if hasattr(m, "content") else str(m)
        lines.append(f"{role}: {content[:300]}")
    return "\n".join(lines)
