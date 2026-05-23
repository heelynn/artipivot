"""Tests for the unified StorageProvider + StorageConfig."""

from __future__ import annotations

import pytest

from artipivot.storage.provider import StorageConfig, StorageProvider


class TestStorageConfig:
    """Tests for StorageConfig defaults."""

    def test_default_mode(self):
        cfg = StorageConfig()
        assert cfg.mode == "memory"

    def test_persistent_mode(self):
        cfg = StorageConfig(mode="persistent")
        assert cfg.mode == "persistent"


class TestStorageProvider:
    """Tests for StorageProvider lazy creation and health check."""

    def test_checkpointer_creation(self):
        p = StorageProvider(StorageConfig(mode="memory"))
        cp = p.checkpointer
        assert cp is not None
        assert type(cp).__name__ == "InMemorySaver"

    def test_store_creation(self):
        p = StorageProvider(StorageConfig(mode="memory"))
        s = p.store
        assert s is not None
        assert type(s).__name__ == "InMemoryStore"

    def test_document_store_creation(self):
        p = StorageProvider(StorageConfig(mode="memory"))
        ds = p.document_store
        assert ds is not None
        assert "DocumentStore" in type(ds).__name__

    def test_change_notifier_creation(self):
        p = StorageProvider(StorageConfig(mode="memory"))
        cn = p.change_notifier
        assert cn is not None
        assert "Notifier" in type(cn).__name__

    def test_caching(self):
        p = StorageProvider(StorageConfig(mode="memory"))
        cp1 = p.checkpointer
        cp2 = p.checkpointer
        assert cp1 is cp2

    @pytest.mark.asyncio
    async def test_setup(self):
        p = StorageProvider(StorageConfig(mode="memory"))
        await p.setup()
        assert p.checkpointer is not None

    @pytest.mark.asyncio
    async def test_health_check(self):
        p = StorageProvider(StorageConfig(mode="memory"))
        health = await p.health_check()
        assert health["checkpointer"] == "ok"
        assert health["store"] == "ok"
        assert health["document_store"] == "ok"
        assert health["change_notifier"] == "ok"

    def test_from_config(self):
        cfg = StorageConfig(mode="memory")
        p = StorageProvider.from_config(cfg)
        assert p.checkpointer is not None


class TestLegacyCheckpointerCompat:
    """Tests that legacy checkpointer.py functions still work."""

    def test_create_checkpointer_memory(self):
        from artipivot.memory.checkpointer import create_checkpointer

        cp = create_checkpointer(backend="memory")
        assert type(cp).__name__ == "InMemorySaver"

    def test_available_checkpointer_backends(self):
        from artipivot.memory.checkpointer import available_checkpointer_backends

        backends = available_checkpointer_backends()
        assert "memory" in backends


class TestLegacyStoreCompat:
    """Tests that legacy store.py functions still work."""

    def test_create_store_memory(self):
        from artipivot.memory.store import create_store

        s = create_store(backend="memory")
        assert type(s).__name__ == "InMemoryStore"

    def test_available_store_backends(self):
        from artipivot.memory.store import available_store_backends

        backends = available_store_backends()
        assert "memory" in backends
