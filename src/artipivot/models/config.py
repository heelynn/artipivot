"""ModelConfig dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """Model configuration for an agent or sub-agent."""

    provider: str  # "anthropic" | "openai" | "openai_compatible" | "anthropic_compatible" | ...
    name: str  # "claude-sonnet-4-6" | "gpt-4o" | "deepseek-chat" | ...
    temperature: float = 0.0
    timeout: int = 120
    max_tokens: int | None = None
    base_url: str | None = None  # 自定义 API 地址（适配兼容供应商）
    api_key: str | None = None   # 显式 key（优先级高于环境变量）
    fallback: ModelConfig | None = field(default=None, repr=False)
