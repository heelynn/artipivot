"""PluginWatcher — subscribe to plugin changes, auto-trigger graph rebuild."""

from __future__ import annotations

from artipivot.plugins.rebuilder import GraphRebuilder
from artipivot.storage.base import ChangeNotifier


class PluginWatcher:
    """Plugin change watcher — subscribes to ChangeNotifier, triggers rebuild."""

    def __init__(
        self,
        notifier: ChangeNotifier,
        rebuilder: GraphRebuilder,
    ) -> None:
        self._notifier = notifier
        self._rebuilder = rebuilder

    async def start(self) -> None:
        """Subscribe to 'plugins' collection changes."""
        await self._notifier.subscribe("plugins", self._on_plugin_change)

    async def _on_plugin_change(
        self, collection: str, key: str, action: str, data: dict
    ) -> None:
        """Handle plugin change notification."""
        agent_id = data.get("agent_id")
        if not agent_id:
            return
        await self._rebuilder.rebuild_agent(agent_id)
