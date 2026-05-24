"""StorageProvider — unified facade for all storage backends."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from artipivot.storage.factory import (
    TYPE_CHANGE_NOTIFIER,
    TYPE_CHECKPOINTER,
    TYPE_DOCUMENT_STORE,
    TYPE_STORE,
)
from artipivot.storage.registry import resolve

log = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """Technology-agnostic storage configuration.

    Attributes:
        mode: "memory" (ephemeral) or "sqlite" (local file persistence).
        db_path: SQLite database file path (only used when mode="sqlite").
    """

    mode: str = "memory"
    db_path: str = ".artipivot/data.db"


class StorageProvider:
    """Unified storage facade — one config creates all backends.

    Usage:
        config = StorageConfig(mode="persistent")
        provider = StorageProvider(config)
        await provider.setup()
        checkpointer = provider.checkpointer
        store = provider.store

    Attributes:
        types: Tuple of TYPE_* constants this provider should manage.
               Defaults to all four. Config providers typically only need
               DOCUMENT_STORE + CHANGE_NOTIFIER; memory providers only
               need CHECKPOINTER + STORE.
    """

    CONFIG_TYPES = (TYPE_DOCUMENT_STORE, TYPE_CHANGE_NOTIFIER)
    MEMORY_TYPES = (TYPE_CHECKPOINTER, TYPE_STORE)
    ALL_TYPES = (TYPE_CHECKPOINTER, TYPE_STORE, TYPE_DOCUMENT_STORE, TYPE_CHANGE_NOTIFIER)

    def __init__(
        self,
        config: StorageConfig,
        types: tuple[str, ...] | None = None,
    ) -> None:
        self._config = config
        self._types = types or self.ALL_TYPES
        self._backends: dict[str, Any] = {}

    # ── Public API ──

    @classmethod
    def from_config(cls, config: StorageConfig) -> StorageProvider:
        """Create a StorageProvider from a StorageConfig."""
        return cls(config)

    async def setup(self) -> None:
        """Initialize all backends (create tables, indexes, etc.).

        Safe to call multiple times — skips already-initialized backends.
        """
        for type_key in self._types:
            backend = self._get_or_create(type_key)
            if backend is None:
                continue
            if hasattr(backend, "setup"):
                try:
                    result = backend.setup()
                    if hasattr(result, "__await__"):
                        await result
                except Exception:
                    log.warning(
                        "Failed to setup %s backend, will retry on first use",
                        type_key,
                        exc_info=True,
                    )

    async def health_check(self) -> dict[str, str]:
        """Return health status for each backend type."""
        result: dict[str, str] = {}
        for type_key in self._types:
            try:
                backend = self._get_or_create(type_key)
                if backend is None:
                    result[type_key] = "error: not available"
                    continue
                if hasattr(backend, "health_check"):
                    check = backend.health_check()
                    if hasattr(check, "__await__"):
                        await check
                result[type_key] = "ok"
            except Exception as e:
                result[type_key] = f"error: {e}"
        return result

    # ── Lazy-loaded backend properties ──

    @property
    def checkpointer(self) -> Any:
        """LangGraph checkpointer instance."""
        return self._get_or_create(TYPE_CHECKPOINTER)

    @property
    def store(self) -> Any:
        """LangGraph store instance."""
        return self._get_or_create(TYPE_STORE)

    @property
    def document_store(self) -> Any:
        """Document store instance."""
        return self._get_or_create(TYPE_DOCUMENT_STORE)

    @property
    def change_notifier(self) -> Any:
        """Change notifier instance."""
        return self._get_or_create(TYPE_CHANGE_NOTIFIER)

    # ── Internal ──

    def _get_or_create(self, type_key: str) -> Any:
        """Get cached backend or create via registry."""
        if type_key in self._backends:
            return self._backends[type_key]

        try:
            factory = resolve(self._config.mode, type_key)
        except ValueError:
            log.debug("No backend for type '%s' in mode '%s'", type_key, self._config.mode)
            return None

        if not factory.supports(type_key):
            return None

        config: dict[str, Any] = {"db_path": self._config.db_path}
        # PollingChangeNotifier needs DocumentStore for polling
        if type_key == TYPE_CHANGE_NOTIFIER:
            doc_store = self._get_or_create(TYPE_DOCUMENT_STORE)
            if doc_store is not None:
                config["_document_store"] = doc_store

        backend = factory.create(type_key, config)
        self._backends[type_key] = backend

        if type_key == TYPE_STORE and not factory.supports_search:
            log.info(
                "Backend '%s' does not support vector search (asearch).",
                factory.name,
            )

        return backend
