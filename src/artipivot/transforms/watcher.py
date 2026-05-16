"""TransformWatcher -- subscribe to transform config changes, hot-reload functions."""

from __future__ import annotations

import structlog

from artipivot.storage.base import ChangeNotifier
from artipivot.transforms.registry import TransformRegistry

logger = structlog.get_logger("artipivot.transforms")


class TransformWatcher:
    """Transform change watcher -- subscribes to ChangeNotifier, hot-reloads.

    Unlike PluginWatcher, this does NOT trigger a GraphRebuilder.
    It only swaps function references in the registry, so the next graph
    invocation picks up the new function automatically.
    """

    def __init__(
        self,
        notifier: ChangeNotifier,
        registry: TransformRegistry,
    ) -> None:
        self._notifier = notifier
        self._registry = registry

    async def start(self) -> None:
        """Subscribe to 'transform_configs' collection changes."""
        await self._notifier.subscribe("transform_configs", self._on_change)

    async def apply(
        self, collection: str, key: str, action: str, data: dict
    ) -> None:
        """Public callback for ChangeNotifier subscriptions."""
        await self._on_change(collection, key, action, data)

    async def _on_change(
        self, collection: str, key: str, action: str, data: dict
    ) -> None:
        """Handle transform config change notification."""
        name = data.get("name") or key

        if action in ("delete", "remove"):
            try:
                self._registry.unregister(name)
            except KeyError:
                pass
            return

        # upsert / update / load -- re-import and re-register
        module_path = data.get("module")
        fn_name = data.get("function")
        if not module_path or not fn_name:
            logger.warning("change_missing_fields", name=name, action=action)
            return

        try:
            self._registry.register_module(
                name, module_path, fn_name, source="hot_reload"
            )
        except (ImportError, AttributeError):
            logger.warning(
                "hot_reload_failed", name=name, module=module_path, function=fn_name
            )
