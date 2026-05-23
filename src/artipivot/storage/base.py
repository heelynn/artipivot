"""Storage abstract interfaces — DocumentStore, ChangeNotifier."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class DocumentStore(ABC):
    """Abstract document store for plugin metadata, configs, etc."""

    @abstractmethod
    async def get(self, collection: str, key: str) -> dict | None:
        """Get a document by key. Returns None if not found."""
        ...

    @abstractmethod
    async def put(self, collection: str, key: str, data: dict) -> None:
        """Put a document. Upsert semantics."""
        ...

    @abstractmethod
    async def delete(self, collection: str, key: str) -> None:
        """Delete a document by key."""
        ...

    @abstractmethod
    async def query(self, collection: str, filter: dict) -> list[dict]:
        """Query documents matching filter. Empty filter returns all."""
        ...

    # ── notification methods (for PollingChangeNotifier) ──
    # Not abstract — stores that don't support polling simply don't implement these.
    # PollingChangeNotifier uses getattr + iscoroutinefunction to detect both sync/async.

    def insert_notification(
        self, collection: str, key: str, action: str, data: dict
    ) -> None:
        """Insert a notification record (sync or async)."""
        raise NotImplementedError

    def query_notifications(
        self, collection: str, since: str
    ) -> list[dict]:
        """Query notifications since a timestamp (sync or async)."""
        raise NotImplementedError

    def cleanup_notifications(self, retention_hours: float = 1.0) -> int:
        """Delete old notifications. Returns deleted count (sync or async)."""
        raise NotImplementedError


class ChangeNotifier(ABC):
    """Abstract change notification mechanism."""

    @abstractmethod
    async def subscribe(self, collection: str, callback: Callable) -> None:
        """Subscribe to changes in a collection.

        callback signature: async callback(collection: str, key: str, action: str, data: dict)
        """
        ...

    @abstractmethod
    async def notify(self, collection: str, key: str, action: str, data: dict) -> None:
        """Notify subscribers of a change."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the notifier."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the notifier."""
        ...
