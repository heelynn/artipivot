"""Checkpointer factory — pluggable backend registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Backend factory registry: name → callable(**kwargs) -> BaseCheckpointSaver
_checkpointer_backends: dict[str, Callable[..., Any]] = {}


def register_checkpointer_backend(name: str, factory: Callable[..., Any]) -> None:
    """Register a checkpointer backend factory.

    Args:
        name: Backend identifier (e.g. "memory", "postgres", "mongodb").
        factory: Callable that accepts **kwargs and returns a checkpointer instance.
    """
    _checkpointer_backends[name] = factory


def create_checkpointer(backend: str = "memory", **kwargs):
    """Create a checkpointer from a registered backend.

    Raises:
        ValueError: If the backend is not registered.
    """
    factory = _checkpointer_backends.get(backend)
    if factory is None:
        available = list(_checkpointer_backends)
        raise ValueError(f"Unknown checkpointer backend: {backend}, available: {available}")
    return factory(**kwargs)


def available_checkpointer_backends() -> list[str]:
    """List registered checkpointer backend names."""
    return list(_checkpointer_backends)


async def setup_checkpointer(checkpointer) -> None:
    """Initialize database tables if needed (no-op for InMemory)."""
    if hasattr(checkpointer, "setup"):
        await checkpointer.setup()


# ── Built-in backends ──


def _memory_checkpointer(**kwargs):
    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


def _postgres_checkpointer(**kwargs):
    import os

    uri = kwargs.get("uri") or os.environ.get("DATABASE_URI")
    if not uri:
        raise ValueError("PostgreSQL URI required: pass uri= or set DATABASE_URI")
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    return AsyncPostgresSaver.from_conn_string(uri)


register_checkpointer_backend("memory", _memory_checkpointer)
register_checkpointer_backend("postgres", _postgres_checkpointer)
