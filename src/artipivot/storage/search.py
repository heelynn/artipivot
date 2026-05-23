"""Embedding toggle and search strategy resolution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EmbeddingConfig:
    """Embedding toggle for vector retrieval.

    A single boolean — the actual embedding model and vector operations
    are handled by the store backend itself (e.g. PostgresStore + pgvector).
    Set enabled=True only when using a store backend that supports asearch.

    Attributes:
        enabled: Whether to use the store's asearch for semantic retrieval.
    """

    enabled: bool = False


class EmbeddingNotSupportedError(RuntimeError):
    """Raised when embedding is enabled but the store backend lacks asearch."""

    def __init__(self, store_type: str) -> None:
        super().__init__(
            f"Embedding is enabled but store backend '{store_type}' does not "
            f"support asearch. Either switch to a backend that supports vector "
            f"search (e.g. postgres), or set embedding.enabled=false."
        )
        self.store_type = store_type


def resolve_search_strategy(
    store: object,
    embedding_config: EmbeddingConfig,
) -> str:
    """Decide retrieval strategy at runtime.

    Returns:
        - "semantic": embedding enabled + backend supports asearch
        - "none": embedding disabled

    Raises:
        EmbeddingNotSupportedError: embedding enabled but backend lacks asearch.
    """
    if not embedding_config.enabled:
        return "none"

    if hasattr(store, "asearch"):
        return "semantic"

    raise EmbeddingNotSupportedError(type(store).__name__)
