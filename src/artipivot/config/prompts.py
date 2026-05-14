"""PromptStore — dynamic prompt management."""

from __future__ import annotations

import threading


class PromptStore:
    """Prompt storage — loaded from DocumentStore, hot-updated via ChangeNotifier."""

    def __init__(self) -> None:
        self._prompts: dict[str, dict] = {}
        self._lock = threading.RLock()

    def get(
        self, agent_id: str, node: str, sub_name: str | None = None
    ) -> dict:
        key = f"{agent_id}:{sub_name}:{node}" if sub_name else f"{agent_id}:{node}"
        return self._prompts.get(key, {})

    async def apply(self, collection: str, key: str, action: str, data: dict) -> None:
        with self._lock:
            pk = data.get("_id", key)
            self._prompts[pk] = data
