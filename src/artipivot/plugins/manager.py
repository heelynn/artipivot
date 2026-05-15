"""PluginManager — plugin metadata CRUD via DocumentStore."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from artipivot.storage.base import ChangeNotifier, DocumentStore


@dataclass
class PluginDocument:
    """Plugin metadata — stored in DocumentStore 'plugins' collection."""

    plugin_type: str  # "sub_agent" | "tool" | "pipeline"
    name: str
    version: str
    agent_id: str  # owning main agent
    manifest: dict  # full config (strategy/tools/prompts/etc.)
    status: str = "active"  # active | inactive | deprecated
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "plugin_type": self.plugin_type,
            "name": self.name,
            "version": self.version,
            "agent_id": self.agent_id,
            "manifest": self.manifest,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PluginDocument:
        return cls(
            plugin_type=data["plugin_type"],
            name=data["name"],
            version=data["version"],
            agent_id=data["agent_id"],
            manifest=data.get("manifest", {}),
            status=data.get("status", "active"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    @property
    def key(self) -> str:
        """DocumentStore key — '{plugin_type}:{agent_id}:{name}'."""
        return f"{self.plugin_type}:{self.agent_id}:{self.name}"


class PluginManager:
    """Plugin metadata management — DocumentStore CRUD + auto-notify."""

    def __init__(
        self, store: DocumentStore, notifier: ChangeNotifier
    ) -> None:
        self._store = store
        self._notifier = notifier

    async def publish(self, plugin: PluginDocument) -> None:
        """Publish a plugin → DocumentStore.put + auto notify."""
        now = datetime.now(timezone.utc).isoformat()
        if not plugin.created_at:
            plugin.created_at = now
        plugin.updated_at = now
        plugin.status = "active"

        data = plugin.to_dict()
        await self._store.put("plugins", plugin.key, data)
        await self._notifier.notify("plugins", plugin.key, "upsert", data)

    async def deprecate(self, plugin_type: str, name: str, agent_id: str) -> None:
        """Mark a plugin as deprecated."""
        key = f"{plugin_type}:{agent_id}:{name}"
        doc = await self._store.get("plugins", key)
        if doc is None:
            raise ValueError(f"Plugin not found: {key}")

        doc["status"] = "deprecated"
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._store.put("plugins", key, doc)
        await self._notifier.notify("plugins", key, "deprecate", doc)

    async def list_plugins(
        self,
        *,
        agent_id: str | None = None,
        plugin_type: str | None = None,
        status: str | None = "active",
    ) -> list[PluginDocument]:
        """Query plugins with optional filters."""
        filter_dict: dict = {}
        if plugin_type:
            filter_dict["plugin_type"] = plugin_type
        if agent_id:
            filter_dict["agent_id"] = agent_id
        if status:
            filter_dict["status"] = status

        docs = await self._store.query("plugins", filter_dict)
        return [PluginDocument.from_dict(d) for d in docs]

    async def get_plugin(
        self, plugin_type: str, name: str, agent_id: str
    ) -> PluginDocument | None:
        """Get a single plugin by type/name/agent."""
        key = f"{plugin_type}:{agent_id}:{name}"
        doc = await self._store.get("plugins", key)
        if doc is None:
            return None
        return PluginDocument.from_dict(doc)
