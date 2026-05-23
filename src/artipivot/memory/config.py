"""Memory configuration data structures."""

from __future__ import annotations

from dataclasses import dataclass, field

from artipivot.storage.search import EmbeddingConfig


@dataclass
class SummarizeConfig:
    """Configuration for the summarize context window strategy.

    Attributes:
        model: Optional dedicated model for summarization (None = use agent's current model).
        prompt: Custom summary prompt (empty = built-in default).
        max_summary_chars: Maximum characters for the summary output.
    """

    model: str | None = None
    prompt: str = ""
    max_summary_chars: int = 2000


@dataclass
class TrimConfig:
    """Configuration for the trim context window strategy.

    Attributes:
        keep_system: Whether to preserve system messages.
        keep_first_n: Number of leading messages to always keep (e.g. opening greetings).
    """

    keep_system: bool = True
    keep_first_n: int = 0


@dataclass
class ContextWindowConfig:
    """Context window management configuration.

    Attributes:
        enabled: Master switch for context window compression.
        strategy: Compression strategy — none | summarize | trim | custom.
        trigger_tokens: Token count threshold to trigger compression.
        keep_messages: Always keep the most recent N messages.
        summarize: Strategy-specific config for summarize.
        trim: Strategy-specific config for trim.
        custom_handler: Python entry point for custom strategy ("module:function").
    """

    enabled: bool = False
    strategy: str = "none"  # none | summarize | trim | custom
    trigger_tokens: int = 100000
    keep_messages: int = 20
    summarize: SummarizeConfig = field(default_factory=SummarizeConfig)
    trim: TrimConfig = field(default_factory=TrimConfig)
    custom_handler: str | None = None

    # Legacy field kept for backward compatibility
    summary_model: str | None = None


@dataclass
class ProfileExtractionConfig:
    """Configuration for user profile extraction.

    Attributes:
        enabled: Whether to extract user profile.
        prompt: Custom extraction prompt (empty = built-in default).
    """

    enabled: bool = True
    prompt: str = ""


@dataclass
class KnowledgeExtractionConfig:
    """Configuration for knowledge fact extraction.

    Attributes:
        enabled: Whether to extract knowledge facts.
        prompt: Custom extraction prompt (empty = built-in default).
        max_facts: Maximum facts to extract per invocation.
    """

    enabled: bool = True
    prompt: str = ""
    max_facts: int = 5


@dataclass
class ExtractionConfig:
    """Configuration for memory extraction (writing to L3 store).

    Attributes:
        enabled: Whether to write extracted memories to L3 store.
        max_messages: Only look at the most recent N messages for extraction.
        max_chars_per_message: Truncate each message to this many characters.
        profile: Profile extraction settings.
        knowledge: Knowledge extraction settings.
        write_on: When to trigger extraction — every_request | every_n_messages | end_of_session | disabled.
        write_every_n: When write_on=every_n_messages, extract every N messages.
    """

    enabled: bool = False
    max_messages: int = 10
    max_chars_per_message: int = 300
    profile: ProfileExtractionConfig = field(default_factory=ProfileExtractionConfig)
    knowledge: KnowledgeExtractionConfig = field(default_factory=KnowledgeExtractionConfig)
    write_on: str = "every_request"
    write_every_n: int = 5


@dataclass
class RetentionConfig:
    """Memory lifecycle management.

    Attributes:
        profile_ttl_days: Days before profile entries expire (None = never).
        knowledge_ttl_days: Days before knowledge entries expire (None = never).
        max_items_per_namespace: Max items per namespace before LRU eviction (None = unlimited).
        dedup_enabled: Check similarity before writing knowledge to avoid duplicates.
    """

    profile_ttl_days: int | None = None
    knowledge_ttl_days: int | None = None
    max_items_per_namespace: int | None = None
    dedup_enabled: bool = False


@dataclass
class MemoryConfig:
    """Top-level memory configuration.

    Aggregates all memory-related settings: L2/L3 switches, embedding,
    context window, extraction, and retention.
    """

    l2: bool = True  # Enable session memory (checkpointer)
    l3: bool = True  # Enable long-term memory (store)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    context_window: ContextWindowConfig = field(default_factory=ContextWindowConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)

    @classmethod
    def from_dict(cls, data: dict) -> MemoryConfig:
        """Create MemoryConfig from a plain dict (e.g. parsed from YAML)."""
        emb = data.get("embedding", {})
        cw = data.get("context_window", {})
        ext = data.get("extraction", {})
        ret = data.get("retention", {})

        # Context window sub-configs
        cw_summarize = cw.get("summarize", {})
        cw_trim = cw.get("trim", {})

        # Extraction sub-configs
        ext_profile = ext.get("profile", {})
        ext_knowledge = ext.get("knowledge", {})

        return cls(
            l2=data.get("l2", True),
            l3=data.get("l3", True),
            embedding=EmbeddingConfig(
                enabled=emb.get("enabled", False),
            ),
            context_window=ContextWindowConfig(
                enabled=cw.get("enabled", False),
                strategy=cw.get("strategy", "none"),
                trigger_tokens=cw.get("trigger_tokens", 100000),
                keep_messages=cw.get("keep_messages", 20),
                summarize=SummarizeConfig(
                    model=cw_summarize.get("model"),
                    prompt=cw_summarize.get("prompt", ""),
                    max_summary_chars=cw_summarize.get("max_summary_chars", 2000),
                ),
                trim=TrimConfig(
                    keep_system=cw_trim.get("keep_system", True),
                    keep_first_n=cw_trim.get("keep_first_n", 2),
                ),
                custom_handler=cw.get("custom_handler"),
                # Legacy
                summary_model=cw.get("summary_model"),
            ),
            extraction=ExtractionConfig(
                enabled=ext.get("enabled", False),
                max_messages=ext.get("max_messages", 10),
                max_chars_per_message=ext.get("max_chars_per_message", 300),
                profile=ProfileExtractionConfig(
                    enabled=ext_profile.get("enabled", True),
                    prompt=ext_profile.get("prompt", ""),
                ),
                knowledge=KnowledgeExtractionConfig(
                    enabled=ext_knowledge.get("enabled", True),
                    prompt=ext_knowledge.get("prompt", ""),
                    max_facts=ext_knowledge.get("max_facts", 5),
                ),
                write_on=ext.get("write_on", "every_request"),
                write_every_n=ext.get("write_every_n", 5),
            ),
            retention=RetentionConfig(
                profile_ttl_days=ret.get("profile_ttl_days"),
                knowledge_ttl_days=ret.get("knowledge_ttl_days"),
                max_items_per_namespace=ret.get("max_items_per_namespace"),
                dedup_enabled=ret.get("dedup_enabled", False),
            ),
        )
