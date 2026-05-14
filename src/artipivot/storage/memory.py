"""In-memory implementations of storage interfaces."""

from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from artipivot.storage.base import ArtifactStore, ChangeNotifier, DocumentStore


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


class InMemoryArtifactStore(ArtifactStore):
    """In-memory artifact store (stores in temp directory)."""

    def __init__(self, base_dir: str = ".artifacts") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    async def upload(self, local_path: str, remote_key: str) -> str:
        dest = self._base / remote_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, str(dest))
        return str(dest)

    async def download(self, remote_key: str, local_path: str) -> str:
        src = self._base / remote_key
        shutil.copy2(str(src), local_path)
        return local_path
