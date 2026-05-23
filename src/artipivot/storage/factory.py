"""BackendFactory ABC + built-in MemoryFactory.

PostgresFactory is kept as a reference implementation for developers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# Storage type constants
TYPE_CHECKPOINTER = "checkpointer"
TYPE_STORE = "store"
TYPE_DOCUMENT_STORE = "document_store"
TYPE_CHANGE_NOTIFIER = "change_notifier"

ALL_TYPES = frozenset({
    TYPE_CHECKPOINTER,
    TYPE_STORE,
    TYPE_DOCUMENT_STORE,
    TYPE_CHANGE_NOTIFIER,
})


class BackendFactory(ABC):
    """Abstract factory for storage backends.

    Each database technology implements one BackendFactory. Developers
    register their factory via ``register_persistent()``.

    Usage:
        class MyFactory(BackendFactory):
            name = "mydb"

            def supports(self, type: str) -> bool:
                return type in ALL_TYPES

            def create(self, type: str, config: dict) -> Any:
                ...
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique backend identifier, e.g. 'memory', 'postgres'."""
        ...

    @abstractmethod
    def supports(self, type: str) -> bool:
        """Return True if this factory can create the given storage type."""
        ...

    @property
    def supports_search(self) -> bool:
        """Whether this factory's store backend supports vector search (asearch).

        Default False. Override in factories that provide vector search.
        """
        return False

    @abstractmethod
    def create(self, type: str, config: dict) -> Any:
        """Create a backend instance for the given type.

        Args:
            type: One of TYPE_* constants.
            config: Backend-specific config dict (from environment variables).

        Returns:
            An instance of the appropriate backend.
        """
        ...

    def _check_supports(self, type: str) -> None:
        if not self.supports(type):
            raise ValueError(
                f"Backend '{self.name}' does not support type '{type}'"
            )


class MemoryFactory(BackendFactory):
    """Built-in memory backend — zero dependencies, all storage types."""

    @property
    def name(self) -> str:
        return "memory"

    def supports(self, type: str) -> bool:
        return type in ALL_TYPES

    def create(self, type: str, config: dict) -> Any:
        self._check_supports(type)

        if type == TYPE_CHECKPOINTER:
            from langgraph.checkpoint.memory import InMemorySaver
            return InMemorySaver()

        if type == TYPE_STORE:
            from langgraph.store.memory import InMemoryStore
            return InMemoryStore()

        if type == TYPE_DOCUMENT_STORE:
            from artipivot.storage.sqlite import SQLiteDocumentStore
            db_path = config.get("db_path", ".artipivot/data.db")
            return SQLiteDocumentStore(db_path=db_path)

        if type == TYPE_CHANGE_NOTIFIER:
            store = config.get("_document_store")
            if store is not None:
                from artipivot.storage.polling_notifier import PollingChangeNotifier
                return PollingChangeNotifier(store)
            from artipivot.storage.memory import InProcessNotifier
            return InProcessNotifier()

        raise ValueError(f"Unknown type: {type}")


class PostgresFactory(BackendFactory):
    """Reference persistent backend — PostgreSQL + pgvector.

    Developers can use this as a starting point or write their own.

    Requires: langgraph-checkpoint-postgres, asyncpg
    Config: reads DATABASE_URI from environment variables.
    """

    @property
    def name(self) -> str:
        return "postgres"

    def supports(self, type: str) -> bool:
        return type in ALL_TYPES

    @property
    def supports_search(self) -> bool:
        return True

    def create(self, type: str, config: dict) -> Any:
        self._check_supports(type)

        import os
        uri = config.get("uri") or os.environ.get("DATABASE_URI")
        if not uri:
            raise ValueError(
                "PostgreSQL URI required: set DATABASE_URI environment variable "
                "or pass uri= in config."
            )

        if type == TYPE_CHECKPOINTER:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            return AsyncPostgresSaver.from_conn_string(uri)

        if type == TYPE_STORE:
            from langgraph.store.postgres import PostgresStore
            index = config.get("index")
            return PostgresStore.from_conn_string(uri, index=index)

        if type == TYPE_DOCUMENT_STORE:
            from artipivot.storage.postgres import PostgresDocumentStore
            return PostgresDocumentStore(uri)

        if type == TYPE_CHANGE_NOTIFIER:
            from artipivot.storage.postgres import PostgresNotifier
            return PostgresNotifier(uri)

        raise ValueError(f"Unknown type: {type}")
