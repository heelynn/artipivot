"""StorageBundle — backward-compatible wrapper around StorageProvider.

.. deprecated::
    Use :class:`StorageProvider` directly for new code.
    StorageBundle is retained as a thin convenience wrapper.
"""

from __future__ import annotations

import warnings
from typing import Any

from artipivot.storage.base import ChangeNotifier, DocumentStore
from artipivot.storage.provider import StorageConfig, StorageProvider


class StorageBundle:
    """Backward-compatible storage factory — delegates to StorageProvider.

    Use StorageProvider directly in new code.
    """

    def __init__(self, config: StorageConfig) -> None:
        warnings.warn(
            "StorageBundle is deprecated — use StorageProvider directly",
            DeprecationWarning,
            stacklevel=2,
        )
        self.config = config
        self._provider = StorageProvider(config)

    @property
    def document_store(self) -> DocumentStore:
        return self._provider.document_store

    @property
    def change_notifier(self) -> ChangeNotifier:
        return self._provider.change_notifier

    @classmethod
    def from_config(cls, config: StorageConfig) -> StorageBundle:
        """Create a StorageBundle from a StorageConfig."""
        return cls(config)

    # Expose provider for migration paths
    @property
    def provider(self) -> StorageProvider:
        """Underlying StorageProvider instance."""
        return self._provider
