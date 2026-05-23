"""Memory retrieval — build context from Store for prompt injection."""

from __future__ import annotations

import json

from artipivot.memory.config import EmbeddingConfig
from artipivot.memory.namespace import knowledge_ns, profile_ns
from artipivot.storage.search import resolve_search_strategy


async def build_memory_context(
    store,
    agent_id: str,
    user_id: str,
    query: str,
    embedding_config: EmbeddingConfig | None = None,
) -> str:
    """Read long-term memory from Store and format for prompt injection.

    Returns a formatted string ready to append to system prompt, or empty string.

    Raises:
        EmbeddingNotSupportedError: if embedding is enabled but store lacks asearch.
    """
    cfg = embedding_config or EmbeddingConfig()
    parts: list[str] = []

    # 1. User profile (always plain text lookup)
    try:
        ns = profile_ns(agent_id, user_id)
        profile = await store.aget(ns, "main")
        if profile and profile.value:
            parts.append(f"[用户画像]\n{json.dumps(profile.value, ensure_ascii=False)}")
    except Exception:
        pass

    # 2. Knowledge search — only when embedding is enabled and backend supports it
    strategy = resolve_search_strategy(store, cfg)
    # strategy is "semantic" or "none"; raises if backend doesn't support asearch

    if strategy == "semantic":
        try:
            ns = knowledge_ns(agent_id, user_id)
            results = await store.asearch(ns, query=query, limit=3)
            if results:
                facts = [
                    r.value.get("fact", "")
                    for r in results
                    if r.value and r.value.get("fact")
                ]
                if facts:
                    parts.append("[相关知识]\n" + "\n".join(f"- {f}" for f in facts))
        except Exception:
            pass

    return "\n\n".join(parts) if parts else ""
