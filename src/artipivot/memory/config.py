"""Memory configuration data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EmbeddingConfig:
    """Embedding model configuration — disabled by default."""

    enabled: bool = False
    provider: str = "openai"
    model: str = "text-embedding-3-small"
    dims: int = 1536
    base_url: str | None = None
    api_key: str | None = None


@dataclass
class ContextWindowConfig:
    """Context window management configuration."""

    strategy: str = "none"  # none | summarize | trim
    trigger_tokens: int = 100000
    keep_messages: int = 20
    summary_model: str | None = None


@dataclass
class MemoryConfig:
    """Top-level memory configuration."""

    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    context_window: ContextWindowConfig = field(default_factory=ContextWindowConfig)

    @classmethod
    def from_dict(cls, data: dict) -> MemoryConfig:
        emb = data.get("embedding", {})
        cw = data.get("context_window", {})
        return cls(
            embedding=EmbeddingConfig(
                enabled=emb.get("enabled", False),
                provider=emb.get("provider", "openai"),
                model=emb.get("model", "text-embedding-3-small"),
                dims=emb.get("dims", 1536),
                base_url=emb.get("base_url"),
                api_key=emb.get("api_key"),
            ),
            context_window=ContextWindowConfig(
                strategy=cw.get("strategy", "none"),
                trigger_tokens=cw.get("trigger_tokens", 100000),
                keep_messages=cw.get("keep_messages", 20),
                summary_model=cw.get("summary_model"),
            ),
        )
