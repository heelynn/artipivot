"""ConfigService — unified CRUD for tools, sub-agents, and agents.

Wraps DocumentStore (already a strategy selected by ARTIPIVOT_STORAGE_MODE)
with entity-specific methods and format conversion logic.
"""

from __future__ import annotations

import structlog

from artipivot.storage.base import ChangeNotifier, DocumentStore

_log = structlog.get_logger("artipivot.config")


class ConfigService:
    """Unified configuration management service.

    Encapsulates all entity CRUD operations behind a clean interface.
    The underlying DocumentStore is injected — its implementation
    (InMemory, SQLite, Postgres) is determined by ARTIPIVOT_STORAGE_MODE.
    """

    def __init__(self, store: DocumentStore, notifier: ChangeNotifier) -> None:
        self._store = store
        self._notifier = notifier

    # ── Tools ──────────────────────────────────────────────────

    async def list_tools(self) -> list[dict]:
        return await self._store.query("tools", {})

    async def get_tool(self, name: str) -> dict | None:
        return await self._store.get("tools", name)

    async def save_tool(self, name: str, data: dict) -> None:
        await self._store.put("tools", name, data)
        await self._notifier.notify("tools", name, "upsert", data)
        _log.info("config.tool_saved", name=name)

    async def delete_tool(self, name: str) -> None:
        existing = await self._store.get("tools", name)
        if existing is None:
            raise KeyError(f"Tool '{name}' not found")
        await self._store.delete("tools", name)
        await self._notifier.notify("tools", name, "delete", {"name": name})
        _log.info("config.tool_deleted", name=name)

    # ── Sub-Agents ─────────────────────────────────────────────

    async def list_sub_agents(self) -> list[dict]:
        records = await self._store.query("sub_agents", {})
        return [
            {
                "name": r.get("name"),
                "strategy": r.get("strategy", "react"),
                "tools": r.get("tools", []),
                "system_prompt": r.get("system_prompt", ""),
                "strategy_config": r.get("strategy_config", {}),
                "graph": r.get("graph"),
                "status": r.get("status", "active"),
            }
            for r in records
        ]

    async def get_sub_agent(self, name: str) -> dict | None:
        return await self._store.get("sub_agents", name)

    async def save_sub_agent(self, name: str, data: dict) -> None:
        await self._store.put("sub_agents", name, data)
        await self._notifier.notify("sub_agents", name, "upsert", data)
        _log.info("config.sub_agent_saved", name=name)

    async def delete_sub_agent(self, name: str) -> None:
        existing = await self._store.get("sub_agents", name)
        if existing is None:
            raise KeyError(f"Sub-agent '{name}' not found")
        await self._store.delete("sub_agents", name)
        await self._notifier.notify("sub_agents", name, "delete", {"name": name})
        _log.info("config.sub_agent_deleted", name=name)

    # ── Agents ─────────────────────────────────────────────────

    async def list_agents(self) -> list[str]:
        records = await self._store.query("agents", {})
        return sorted(r.get("agent_id", "") for r in records if r.get("agent_id"))

    async def get_agent(self, agent_id: str) -> dict | None:
        data = await self._store.get("agents", agent_id)
        if data is None:
            return None
        # Flatten routing for frontend compatibility
        routing = data.get("routing", {})
        raw_intents = routing.get("intents", {})
        intent_map = {}
        intent_descriptions = {}
        for intent, value in raw_intents.items():
            if isinstance(value, str):
                intent_map[intent] = value
            elif isinstance(value, dict):
                intent_map[intent] = value.get("target", "")
                desc = value.get("description")
                if desc:
                    intent_descriptions[intent] = desc
        return {
            **data,
            "confidence_threshold": routing.get("confidence_threshold", 0.7),
            "intent_map": intent_map,
            "intent_descriptions": intent_descriptions,
        }

    async def get_agent_circuit(self, agent_id: str) -> dict | None:
        data = await self._store.get("agents", agent_id)
        if data is None:
            return None
        circuit = data.get("circuit", {})
        return {
            "agent_id": agent_id,
            "circuit": {
                "enabled": circuit.get("enabled", True),
                "failure_threshold": circuit.get("failure_threshold", 5),
                "recovery_timeout": circuit.get("recovery_timeout", 60.0),
            },
        }

    async def save_agent(self, agent_id: str, data: dict) -> None:
        """Save agent config. Accepts dict in from_dict-compatible format."""
        # Ensure routing is properly nested for from_dict compatibility
        if "routing" not in data:
            data["routing"] = {
                "intents": data.pop("intent_map", {}),
                "confidence_threshold": data.pop("confidence_threshold", 0.7),
            }
        await self._store.put("agents", agent_id, data)
        await self._notifier.notify("agents", agent_id, "upsert", data)
        _log.info("config.agent_saved", agent_id=agent_id)

    async def update_agent_fields(self, agent_id: str, updates: dict) -> list[str]:
        """Update specific fields of an agent. Returns list of updated field names."""
        data = await self._store.get("agents", agent_id)
        if data is None:
            raise KeyError(f"Agent '{agent_id}' not found")

        updated: list[str] = []
        routing = data.get("routing", {})

        if "model" in updates:
            data["model"] = updates["model"]
            updated.append("model")
        if "confidence_threshold" in updates:
            routing["confidence_threshold"] = updates["confidence_threshold"]
            data["routing"] = routing
            updated.append("confidence_threshold")
        if "intent_map" in updates:
            # Support both flat {intent: target} and rich {intent: {target, description}}
            raw = updates["intent_map"]
            normalized = {}
            for k, v in raw.items():
                if isinstance(v, str):
                    normalized[k] = {"target": v}
                elif isinstance(v, dict):
                    normalized[k] = v
            routing["intents"] = normalized
            data["routing"] = routing
            updated.append("intent_map")
        if "prompts" in updates:
            data["prompts"] = updates["prompts"]
            updated.append("prompts")
        if "tools" in updates:
            data["tools"] = updates["tools"]
            updated.append("tools")
        if "sub_agent_refs" in updates:
            data["sub_agent_refs"] = updates["sub_agent_refs"]
            updated.append("sub_agent_refs")
        if "circuit" in updates:
            circuit = data.get("circuit", {})
            c = updates["circuit"]
            if "enabled" in c:
                circuit["enabled"] = c["enabled"]
            if "failure_threshold" in c:
                circuit["failure_threshold"] = c["failure_threshold"]
            if "recovery_timeout" in c:
                circuit["recovery_timeout"] = c["recovery_timeout"]
            data["circuit"] = circuit
            updated.append("circuit")
        if "memory" in updates:
            data["memory"] = updates["memory"]
            updated.append("memory")

        if updated:
            await self._store.put("agents", agent_id, data)
            await self._notifier.notify("agents", agent_id, "upsert", data)
            _log.info("config.agent_updated", agent_id=agent_id, fields=updated)

        return updated

    async def delete_agent(self, agent_id: str) -> None:
        existing = await self._store.get("agents", agent_id)
        if existing is None:
            raise KeyError(f"Agent '{agent_id}' not found")
        await self._store.delete("agents", agent_id)
        await self._notifier.notify("agents", agent_id, "delete", {"agent_id": agent_id})
        _log.info("config.agent_deleted", agent_id=agent_id)
