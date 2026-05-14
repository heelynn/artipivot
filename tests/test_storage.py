"""Tests for storage layer."""

from __future__ import annotations

import pytest

from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier


class TestInMemoryDocumentStore:
    @pytest.mark.asyncio
    async def test_put_and_get(self, store: InMemoryDocumentStore):
        await store.put("col", "k1", {"name": "test"})
        result = await store.get("col", "k1")
        assert result == {"name": "test"}

    @pytest.mark.asyncio
    async def test_get_missing(self, store: InMemoryDocumentStore):
        result = await store.get("col", "missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert(self, store: InMemoryDocumentStore):
        await store.put("col", "k1", {"v": 1})
        await store.put("col", "k1", {"v": 2})
        result = await store.get("col", "k1")
        assert result == {"v": 2}

    @pytest.mark.asyncio
    async def test_delete(self, store: InMemoryDocumentStore):
        await store.put("col", "k1", {"name": "test"})
        await store.delete("col", "k1")
        assert await store.get("col", "k1") is None

    @pytest.mark.asyncio
    async def test_query_all(self, store: InMemoryDocumentStore):
        await store.put("col", "k1", {"type": "a", "name": "x"})
        await store.put("col", "k2", {"type": "b", "name": "y"})
        results = await store.query("col", {})
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_filter(self, store: InMemoryDocumentStore):
        await store.put("col", "k1", {"type": "a", "name": "x"})
        await store.put("col", "k2", {"type": "b", "name": "y"})
        results = await store.query("col", {"type": "a"})
        assert len(results) == 1
        assert results[0]["name"] == "x"


class TestInProcessNotifier:
    @pytest.mark.asyncio
    async def test_subscribe_and_notify(self):
        notifier = InProcessNotifier()
        received = []

        async def callback(collection, key, action, data):
            received.append((collection, key, action, data))

        await notifier.subscribe("col", callback)
        await notifier.notify("col", "k1", "put", {"name": "test"})

        assert len(received) == 1
        assert received[0] == ("col", "k1", "put", {"name": "test"})

    @pytest.mark.asyncio
    async def test_start_stop(self):
        notifier = InProcessNotifier()
        await notifier.start()
        await notifier.stop()
