"""Store factory — pluggable backend registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Backend factory registry: name → callable(**kwargs) -> BaseStore
_store_backends: dict[str, Callable[..., Any]] = {}


def register_store_backend(name: str, factory: Callable[..., Any]) -> None:
    """Register a store backend factory.

    Args:
        name: Backend identifier (e.g. "memory", "postgres", "mongodb").
        factory: Callable that accepts **kwargs and returns a store instance.
    """
    _store_backends[name] = factory


def create_store(backend: str = "memory", **kwargs):
    """Create a store from a registered backend.

    Raises:
        ValueError: If the backend is not registered.
    """
    factory = _store_backends.get(backend)
    if factory is None:
        available = list(_store_backends)
        raise ValueError(f"Unknown store backend: {backend}, available: {available}")
    return factory(**kwargs)


def available_store_backends() -> list[str]:
    """List registered store backend names."""
    return list(_store_backends)


async def setup_store(store) -> None:
    """Initialize database tables and indexes if needed (no-op for InMemory)."""
    if hasattr(store, "setup"):
        await store.setup()


# ── Built-in backends ──


def _memory_store(**kwargs):
    from langgraph.store.memory import InMemoryStore

    return InMemoryStore()


def _postgres_store(**kwargs):
    import os

    uri = kwargs.get("uri") or os.environ.get("DATABASE_URI")
    if not uri:
        raise ValueError("PostgreSQL URI required: pass uri= or set DATABASE_URI")
    from langgraph.store.postgres import PostgresStore

    index = kwargs.get("index")
    return PostgresStore.from_conn_string(uri, index=index)


register_store_backend("memory", _memory_store)
register_store_backend("postgres", _postgres_store)
