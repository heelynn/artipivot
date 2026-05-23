"""Store factory — delegates to unified storage registry.

Legacy functions retained for backward compatibility.
New code should use StorageProvider directly.
"""

from __future__ import annotations

import warnings
from typing import Any

from artipivot.storage.factory import TYPE_STORE, MemoryFactory
from artipivot.storage.registry import get_persistent


def register_store_backend(name: str, factory: Any) -> None:
    """Register a store backend factory.

    .. deprecated:: Use :func:`artipivot.storage.registry.register_persistent` instead.
    """
    warnings.warn(
        "register_store_backend() is deprecated — "
        "use artipivot.storage.registry.register_persistent()",
        DeprecationWarning,
        stacklevel=2,
    )


def create_store(backend: str = "memory", **kwargs) -> Any:
    """Create a store from a registered backend.

    Delegates to the unified storage registry.
    """
    if backend == "memory":
        return MemoryFactory().create(TYPE_STORE, kwargs)
    # persistent
    persistent = get_persistent()
    if persistent is None:
        raise ValueError("No persistent backend registered")
    return persistent.create(TYPE_STORE, kwargs)


def available_store_backends() -> list[str]:
    """List backend names that support store."""
    from artipivot.storage.registry import available_backends
    return available_backends(TYPE_STORE)


async def setup_store(store) -> None:
    """Initialize database tables and indexes if needed (no-op for InMemory)."""
    if hasattr(store, "setup"):
        result = store.setup()
        if hasattr(result, "__await__"):
            await result
