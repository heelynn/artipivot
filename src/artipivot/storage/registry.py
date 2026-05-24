"""Storage backend registry — mode name directly selects the factory.

Supported modes: memory (in-memory), sqlite (local file), postgres (remote).
"""

from __future__ import annotations

from artipivot.storage.factory import (
    BackendFactory,
    MemoryFactory,
    SqliteFactory,
    PostgresFactory,
)

# Built-in factories — mode name → factory
_BUILTIN: dict[str, BackendFactory] = {
    "memory": MemoryFactory(),
    "sqlite": SqliteFactory(),
}

# Additional factories registered at runtime (e.g. postgres)
_registered: dict[str, BackendFactory] = {}


def register_factory(factory: BackendFactory) -> None:
    """Register a storage backend factory at runtime."""
    _registered[factory.name] = factory


def resolve(mode: str, type_key: str) -> BackendFactory:
    """Resolve the factory for a given mode.

    Args:
        mode: "memory", "sqlite", "postgres", etc.
        type_key: One of the TYPE_* constants.

    Raises:
        ValueError: If mode is unknown or factory doesn't support the type.
    """
    factory = _registered.get(mode) or _BUILTIN.get(mode)
    if factory is None:
        raise ValueError(
            f"Unknown storage mode: '{mode}'. "
            f"Available: {sorted(_BUILTIN) + sorted(_registered)}"
        )
    if not factory.supports(type_key):
        raise ValueError(
            f"Backend '{factory.name}' does not support storage type '{type_key}'."
        )
    return factory


def available_backends(type_key: str | None = None) -> list[str]:
    """List available backend names."""
    names = []
    for name, f in {**_BUILTIN, **_registered}.items():
        if type_key is None or f.supports(type_key):
            names.append(name)
    return sorted(names)
