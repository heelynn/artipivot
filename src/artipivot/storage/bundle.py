"""StorageBundle — unified factory for storage components."""

from __future__ import annotations

from dataclasses import dataclass, field

from artipivot.storage.base import ArtifactStore, ChangeNotifier, DocumentStore


@dataclass
class StorageConfig:
    """Storage backend configuration."""

    document_backend: str = "memory"
    notifier_backend: str = "memory"
    artifact_backend: str = "memory"
    options: dict = field(default_factory=dict)


class StorageBundle:
    """Unified storage component factory — creates all three from config."""

    def __init__(self, config: StorageConfig) -> None:
        self.config = config
        self.document_store: DocumentStore = self._create_document_store(config)
        self.change_notifier: ChangeNotifier = self._create_notifier(config)
        self.artifact_store: ArtifactStore = self._create_artifact_store(config)

    @staticmethod
    def _create_document_store(config: StorageConfig) -> DocumentStore:
        opts = config.options.get("document", {})
        match config.document_backend:
            case "memory":
                from artipivot.storage.memory import InMemoryDocumentStore

                return InMemoryDocumentStore()
            case _:
                raise ValueError(
                    f"Unknown document backend: {config.document_backend}"
                )

    @staticmethod
    def _create_notifier(config: StorageConfig) -> ChangeNotifier:
        match config.notifier_backend:
            case "memory":
                from artipivot.storage.memory import InProcessNotifier

                return InProcessNotifier()
            case _:
                raise ValueError(
                    f"Unknown notifier backend: {config.notifier_backend}"
                )

    @staticmethod
    def _create_artifact_store(config: StorageConfig) -> ArtifactStore:
        opts = config.options.get("artifact", {})
        match config.artifact_backend:
            case "memory":
                from artipivot.storage.memory import InMemoryArtifactStore

                base_dir = opts.get("base_dir", ".artifacts")
                return InMemoryArtifactStore(base_dir=base_dir)
            case _:
                raise ValueError(
                    f"Unknown artifact backend: {config.artifact_backend}"
                )

    @classmethod
    def from_config(cls, config: StorageConfig) -> StorageBundle:
        """Create a StorageBundle from a StorageConfig."""
        return cls(config)
