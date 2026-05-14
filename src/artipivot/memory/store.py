"""Store factory — P0 uses InMemoryStore."""

from __future__ import annotations

from langgraph.store.memory import InMemoryStore


def create_store(backend: str = "memory"):
    """Create a store instance.

    P0 only supports 'memory' backend.
    """
    match backend:
        case "memory":
            return InMemoryStore()
        case _:
            raise ValueError(f"Unsupported store backend: {backend}")
