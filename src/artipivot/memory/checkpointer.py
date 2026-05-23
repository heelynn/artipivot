"""Checkpointer factory — delegates to unified storage registry.

Legacy functions retained for backward compatibility.
New code should use StorageProvider directly.
"""

from __future__ import annotations

import warnings
from typing import Any

from artipivot.storage.factory import TYPE_CHECKPOINTER, MemoryFactory
from artipivot.storage.registry import get_persistent, resolve


def register_checkpointer_backend(name: str, factory: Any) -> None:
    """Register a checkpointer backend factory.

    .. deprecated:: Use :func:`artipivot.storage.registry.register_persistent` instead.
    """
    warnings.warn(
        "register_checkpointer_backend() is deprecated — "
        "use artipivot.storage.registry.register_persistent()",
        DeprecationWarning,
        stacklevel=2,
    )


def create_checkpointer(backend: str = "memory", **kwargs) -> Any:
    """Create a checkpointer from a registered backend.

    Delegates to the unified storage registry.
    """
    if backend == "memory":
        return MemoryFactory().create(TYPE_CHECKPOINTER, kwargs)
    # persistent
    persistent = get_persistent()
    if persistent is None:
        raise ValueError("No persistent backend registered")
    return persistent.create(TYPE_CHECKPOINTER, kwargs)


def available_checkpointer_backends() -> list[str]:
    """List backend names that support checkpointer."""
    from artipivot.storage.registry import available_backends
    return available_backends(TYPE_CHECKPOINTER)


async def setup_checkpointer(checkpointer) -> None:
    """Initialize database tables if needed (no-op for InMemory)."""
    if hasattr(checkpointer, "setup"):
        result = checkpointer.setup()
        if hasattr(result, "__await__"):
            await result
