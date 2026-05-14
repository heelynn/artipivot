"""Checkpointer factory — P0 uses InMemorySaver."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver


def create_checkpointer(backend: str = "memory"):
    """Create a checkpointer instance.

    P0 only supports 'memory' backend.
    """
    match backend:
        case "memory":
            return InMemorySaver()
        case _:
            raise ValueError(f"Unsupported checkpointer backend: {backend}")
