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
        # Manifest format: {"intents": [{"name": ..., "sub_agent": ...}, ...]}
        if "intents" in cfg:
            return {i["name"]: i["sub_agent"] for i in cfg["intents"]}
        # API format: {"intent_map": {"chat": "time_helper", ...}}
        raw = cfg.get("intent_map", {})
        return {k: (v["target"] if isinstance(v, dict) else v) for k, v in raw.items()}

    def get_intent_descriptions(self, agent_id: str) -> dict[str, str]:
        """Return intent name → description mapping (empty string if no description)."""
        cfg = self._configs.get(agent_id, {})
        if "intents" in cfg:
            return {i["name"]: i.get("description", "") for i in cfg["intents"]}
        raw = cfg.get("intent_map", {})
        return {k: (v.get("description", "") if isinstance(v, dict) else "") for k, v in raw.items()}

    def get_threshold(self, agent_id: str) -> float:
        return self._configs.get(agent_id, {}).get("confidence_threshold", 0.7)

    async def apply(self, collection: str, key: str, action: str, data: dict) -> None:
        with self._lock:
            agent_id = data.get("agent_id", key)
            if action == "delete":
                self._configs.pop(agent_id, None)
            else:
                self._configs[agent_id] = data
