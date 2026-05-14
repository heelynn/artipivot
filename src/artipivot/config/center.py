"""ConfigCenter — unified config entry point."""

from __future__ import annotations

from artipivot.config.prompts import PromptStore
from artipivot.config.ratelimit import RateLimiter
from artipivot.config.routing import RoutingConfig
from artipivot.storage.base import ChangeNotifier, DocumentStore


class ConfigCenter:
    """Dynamic configuration center — unified entry point."""

    def __init__(self, store: DocumentStore, notifier: ChangeNotifier) -> None:
        self._store = store
        self._notifier = notifier
        self.prompts = PromptStore()
        self.routing = RoutingConfig()
        self.rate_limits = RateLimiter()

    async def start(self) -> None:
        """Full load + subscribe to changes."""
        await self._load_all()
        await self._notifier.subscribe("prompt_configs", self.prompts.apply)
        await self._notifier.subscribe("routing_configs", self.routing.apply)
        await self._notifier.subscribe("ratelimit_configs", self.rate_limits.apply)
        await self._notifier.start()

    async def _load_all(self) -> None:
        for collection, component in [
            ("prompt_configs", self.prompts),
            ("routing_configs", self.routing),
            ("ratelimit_configs", self.rate_limits),
        ]:
            docs = await self._store.query(collection, {})
            for doc in docs:
                key = doc.get("_id", "")
                await component.apply(collection, key, "load", doc)
