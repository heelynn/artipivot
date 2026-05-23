"""In-memory and in-process implementations of storage interfaces."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from artipivot.storage.base import ChangeNotifier, DocumentStore


class InMemoryDocumentStore(DocumentStore):
    """In-memory document store for development."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict]] = defaultdict(dict)

    async def get(self, collection: str, key: str) -> dict | None:
        return self._data[collection].get(key)

    async def put(self, collection: str, key: str, data: dict) -> None:
        self._data[collection][key] = data

    async def delete(self, collection: str, key: str) -> None:
        self._data[collection].pop(key, None)

    async def query(self, collection: str, filter: dict) -> list[dict]:
        docs = list(self._data[collection].values())
        if not filter:
            return docs
        return [
            doc for doc in docs
            if all(doc.get(k) == v for k, v in filter.items())
        ]


class InProcessNotifier(ChangeNotifier):
    """In-process change notifier for development."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    async def subscribe(self, collection: str, callback: Callable) -> None:
        self._subscribers[collection].append(callback)

    async def notify(self, collection: str, key: str, action: str, data: dict) -> None:
        for cb in self._subscribers.get(collection, []):
            await cb(collection, key, action, data)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass
