"""RoutingConfig — dynamic routing rules."""

from __future__ import annotations

import threading


class RoutingConfig:
    """Routing rules — changes trigger graph rebuild."""

    def __init__(self) -> None:
        self._configs: dict[str, dict] = {}
        self._lock = threading.RLock()

    def get_intent_map(self, agent_id: str) -> dict[str, str]:
        cfg = self._configs.get(agent_id, {})
        return {i["name"]: i["sub_agent"] for i in cfg.get("intents", [])}

    def get_threshold(self, agent_id: str) -> float:
        return self._configs.get(agent_id, {}).get("confidence_threshold", 0.7)

    async def apply(self, collection: str, key: str, action: str, data: dict) -> None:
        with self._lock:
            agent_id = data.get("agent_id", key)
            self._configs[agent_id] = data
