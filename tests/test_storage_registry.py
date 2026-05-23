"""Tests for the unified storage registry (two-slot: memory + persistent)."""

from __future__ import annotations

import pytest

from artipivot.storage.factory import (
    ALL_TYPES,
    TYPE_CHECKPOINTER,
    TYPE_STORE,
    BackendFactory,
    MemoryFactory,
    PostgresFactory,
)
from artipivot.storage.registry import (
    available_backends,
    get_persistent,
    register_persistent,
    resolve,
)


class TestRegistry:
    """Tests for resolve() and register_persistent()."""

    def test_resolve_memory(self):
        f = resolve("memory", TYPE_CHECKPOINTER)
        assert isinstance(f, MemoryFactory)
        assert f.name == "memory"

    def test_resolve_memory_all_types(self):
        for t in ALL_TYPES:
            f = resolve("memory", t)
            assert isinstance(f, MemoryFactory)

    def test_resolve_persistent_without_registration_raises(self):
        with pytest.raises(ValueError, match="No persistent storage backend registered"):
            resolve("persistent", TYPE_CHECKPOINTER)

    def test_resolve_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown storage mode"):
            resolve("cloud", TYPE_CHECKPOINTER)

    def test_register_persistent_and_resolve(self):
        register_persistent(PostgresFactory())
        try:
            f = resolve("persistent", TYPE_CHECKPOINTER)
            assert isinstance(f, PostgresFactory)
            assert f.name == "postgres"
        finally:
            # Reset persistent slot for other tests
            import artipivot.storage.registry as reg
            reg._persistent_factory = None

    def test_register_persistent_type_error(self):
        with pytest.raises(TypeError, match="Expected BackendFactory"):
            register_persistent("not a factory")  # type: ignore

    def test_get_persistent_returns_none_initially(self):
        assert get_persistent() is None

    def test_get_persistent_after_registration(self):
        register_persistent(PostgresFactory())
        try:
            f = get_persistent()
            assert isinstance(f, PostgresFactory)
        finally:
            import artipivot.storage.registry as reg
            reg._persistent_factory = None

    def test_available_backends_default(self):
        backends = available_backends()
        assert "memory" in backends

    def test_available_backends_with_persistent_registered(self):
        register_persistent(PostgresFactory())
        try:
            backends = available_backends()
            assert "memory" in backends
            assert "postgres" in backends
        finally:
            import artipivot.storage.registry as reg
            reg._persistent_factory = None

    def test_available_backends_filtered_by_type(self):
        backends = available_backends(TYPE_CHECKPOINTER)
        assert "memory" in backends

    def test_resolve_persistent_unsupported_type_raises(self):
        class LimitedFactory(BackendFactory):
            @property
            def name(self):
                return "limited"

            def supports(self, type: str) -> bool:
                return type == TYPE_CHECKPOINTER

            def create(self, type: str, config: dict):
                return object()

        register_persistent(LimitedFactory())
        try:
            with pytest.raises(ValueError, match="does not support"):
                resolve("persistent", TYPE_STORE)
        finally:
            import artipivot.storage.registry as reg
            reg._persistent_factory = None


class TestMemoryFactory:
    """Tests for MemoryFactory."""

    def test_supports_all_types(self):
        f = MemoryFactory()
        for t in ALL_TYPES:
            assert f.supports(t), f"MemoryFactory should support {t}"

    def test_supports_search_false(self):
        f = MemoryFactory()
        assert f.supports_search is False

    def test_create_checkpointer(self):
        f = MemoryFactory()
        cp = f.create(TYPE_CHECKPOINTER, {})
        assert type(cp).__name__ == "InMemorySaver"

    def test_create_store(self):
        f = MemoryFactory()
        s = f.create(TYPE_STORE, {})
        assert type(s).__name__ == "InMemoryStore"

class TestPostgresFactory:
    """Tests for PostgresFactory."""

    def test_supports_all_types(self):
        f = PostgresFactory()
        for t in ALL_TYPES:
            assert f.supports(t), f"PostgresFactory should support {t}"

    def test_supports_search_true(self):
        f = PostgresFactory()
        assert f.supports_search is True

    def test_create_without_uri_raises(self):
        f = PostgresFactory()
        with pytest.raises(ValueError, match="URI required"):
            f.create(TYPE_CHECKPOINTER, {})


class TestSearchStrategy:
    """Tests for resolve_search_strategy."""

    def test_disabled(self):
        from artipivot.storage.search import EmbeddingConfig, resolve_search_strategy

        store = object()
        cfg = EmbeddingConfig(enabled=False)
        assert resolve_search_strategy(store, cfg) == "none"

    def test_semantic_with_asearch(self):
        from artipivot.storage.search import EmbeddingConfig, resolve_search_strategy

        class FakeStore:
            async def asearch(self, *a, **kw):
                pass

        cfg = EmbeddingConfig(enabled=True)
        assert resolve_search_strategy(FakeStore(), cfg) == "semantic"

    def test_raises_without_asearch(self):
        from artipivot.storage.search import (
            EmbeddingConfig,
            EmbeddingNotSupportedError,
            resolve_search_strategy,
        )

        cfg = EmbeddingConfig(enabled=True)
        with pytest.raises(EmbeddingNotSupportedError, match="does not support asearch"):
            resolve_search_strategy(object(), cfg)
