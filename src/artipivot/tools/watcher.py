"""ToolWatcher — subscribe to tool changes via ChangeNotifier, trigger reload."""

from __future__ import annotations

import structlog

from artipivot.storage.base import ChangeNotifier
from artipivot.tools.reloader import ToolReloader

logger = structlog.get_logger(__name__)


class ToolWatcher:
    """Subscribe to "tools" collection changes, auto-trigger ToolReloader."""

    def __init__(
        self,
        notifier: ChangeNotifier,
        reloader: ToolReloader,
    ) -> None:
        self._notifier = notifier
        self._reloader = reloader

    async def start(self) -> None:
        """Subscribe to 'tools' collection changes."""
        await self._notifier.subscribe("tools", self._on_change)

    async def _on_change(
        self, collection: str, key: str, action: str, data: dict
    ) -> None:
        """Handle tool record change notification."""
        name = data.get("name") or key
        if not name:
            return

        if action in ("delete", "remove"):
            await self._reloader.remove_tool(name)
            return

        # upsert / update
        await self._reloader.reload_one_tool(name, data)
