"""Storage backend registry — two slots: memory (built-in) + persistent (developer-registered).

YAML chooses between "memory" and "persistent" — technology-agnostic.
Developers register their persistent backend (postgres, milvus, etc.) via code.
"""

from __future__ import annotations

import logging
from typing import Any

from artipivot.storage.factory import ALL_TYPES, BackendFactory, MemoryFactory

log = logging.getLogger(__name__)

# Built-in memory factory — always available
_memory_factory = MemoryFactory()

# Persistent factory — registered by developer, None until registered
_persistent_factory: BackendFactory | None = None


def register_persistent(factory: BackendFactory) -> None:
    """Register the persistent storage backend factory.

    Call this once during application startup (before bootstrap).
    The factory decides the actual technology (postgres, milvus, etc.).

    Args:
        factory: A BackendFactory instance for the persistent backend.

    Raises:
        TypeError: If factory is not a BackendFactory instance.
    """
    global _persistent_factory

    if not isinstance(factory, BackendFactory):
        raise TypeError(f"Expected BackendFactory, got {type(factory).__name__}")

    _persistent_factory = factory
    log.info("Registered persistent storage backend: %s", factory.name)


def get_persistent() -> BackendFactory | None:
    """Return the registered persistent factory, or None."""
    return _persistent_factory


def resolve(mode: str, type_key: str) -> BackendFactory:
    """Resolve the factory for a given mode and storage type.

    Args:
        mode: "memory" or "persistent".
        type_key: One of the TYPE_* constants.

    Returns:
        A BackendFactory that supports the given type.

    Raises:
        ValueError: If mode is "persistent" but no factory registered,
                    or if the factory doesn't support the type.
    """
    if mode == "memory":
        return _memory_factory

    if mode == "persistent":
        if _persistent_factory is None:
            raise ValueError(
                "No persistent storage backend registered. "
                "Call register_persistent(factory) before bootstrap."
            )
        if not _persistent_factory.supports(type_key):
            raise ValueError(
                f"Persistent backend '{_persistent_factory.name}' does not "
                f"support storage type '{type_key}'."
            )
        return _persistent_factory

    raise ValueError(f"Unknown storage mode: '{mode}'. Use 'memory' or 'persistent'.")


def available_backends(type: str | None = None) -> list[str]:
    """List available backend names."""
    names = ["memory"]
    if _persistent_factory is not None:
        if type is None or _persistent_factory.supports(type):
            names.append(_persistent_factory.name)
    return names
