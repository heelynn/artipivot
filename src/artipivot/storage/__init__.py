"""Unified storage layer — backends, factories, and provider."""

from artipivot.storage.base import ChangeNotifier, DocumentStore
from artipivot.storage.bundle import StorageBundle
from artipivot.storage.factory import (
    ALL_TYPES,
    TYPE_CHANGE_NOTIFIER,
    TYPE_CHECKPOINTER,
    TYPE_DOCUMENT_STORE,
    TYPE_STORE,
    BackendFactory,
)
from artipivot.storage.provider import StorageConfig, StorageProvider
from artipivot.storage.registry import register_factory, resolve, available_backends
from artipivot.storage.search import (
    EmbeddingConfig,
    EmbeddingNotSupportedError,
    resolve_search_strategy,
)

__all__ = [
    # ABC
    "DocumentStore",
    "ChangeNotifier",
    # Factory
    "BackendFactory",
    "ALL_TYPES",
    "TYPE_CHECKPOINTER",
    "TYPE_STORE",
    "TYPE_DOCUMENT_STORE",
    "TYPE_CHANGE_NOTIFIER",
    # Provider
    "StorageConfig",
    "StorageProvider",
    "StorageBundle",
    # Registry
    "register_factory",
    "resolve",
    "available_backends",
    # Search
    "EmbeddingConfig",
    "EmbeddingNotSupportedError",
    "resolve_search_strategy",
]
