"""ConfigCenter — unified config entry point."""

from __future__ import annotations

from artipivot.config.prompts import PromptStore
from artipivot.config.ratelimit import RateLimiter
from artipivot.config.routing import RoutingConfig
from artipivot.storage.base import ChangeNotifier, DocumentStore


class ConfigCenter:
    """Dynamic configuration center — unified entry point."""

    def __init__(
        self,
        store: DocumentStore,
        notifier: ChangeNotifier,
        *,
        on_routing_change=None,
    ) -> None:
        self._store = store
        self._notifier = notifier
        self._on_routing_change = on_routing_change
        self.prompts = PromptStore()
        self.routing = RoutingConfig()
        self.rate_limits = RateLimiter()

    def load_from_manifest(self, manifest) -> None:
        """Populate routing + prompts directly from an AgentManifest (no DocumentStore).

        Called at startup. After this, start() still subscribes to
        DocumentStore changes for runtime Admin API hot-reloads.
        """
        from artipivot.gateway.loader import AgentManifest

        for agent_def in manifest.agents.values():
            # Routing config
            if agent_def.intent_map:
                self.routing._configs[agent_def.agent_id] = {
                    "agent_id": agent_def.agent_id,
                    "confidence_threshold": agent_def.confidence_threshold,
                    "intents": [
                        {
                            "name": intent,
                            "sub_agent": sub_name,
                            "description": agent_def.intent_descriptions.get(intent, ""),
                        }
                        for intent, sub_name in agent_def.intent_map.items()
                    ],
                }

            # Prompt configs
            for node_name, template in agent_def.prompts.items():
                key = f"{agent_def.agent_id}:{node_name}"
                self.prompts._prompts[key] = {"_id": key, "system": template}

    async def start(self) -> None:
        """Load any existing DocumentStore configs + subscribe to runtime changes."""
        await self._load_all()
        await self._notifier.subscribe("prompt_configs", self.prompts.apply)
        await self._notifier.subscribe("routing_configs", self._routing_change_handler)
        await self._notifier.subscribe("ratelimit_configs", self.rate_limits.apply)
        await self._notifier.start()

    async def _routing_change_handler(
        self, collection: str, key: str, action: str, data: dict
    ) -> None:
        """Handle routing config change — update config + optional rebuild callback."""
        await self.routing.apply(collection, key, action, data)
        if self._on_routing_change:
            await self._on_routing_change(collection, key, action, data)

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
