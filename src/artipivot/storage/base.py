"""Storage abstract interfaces — DocumentStore, ChangeNotifier, ArtifactStore."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


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


class ArtifactStore(ABC):
    """Abstract artifact store for plugin packages."""

    @abstractmethod
    async def upload(self, local_path: str, remote_key: str) -> str:
        """Upload a file, return its URL/path."""
        ...

    @abstractmethod
    async def download(self, remote_key: str, local_path: str) -> str:
        """Download a file, return local path."""
        ...
