"""AgentContext — runtime context injected into graph nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

if TYPE_CHECKING:
    from artipivot.config.center import ConfigCenter


@dataclass
class AgentContext:
    """Runtime context — injected via context_schema, accessible via Runtime[AgentContext]."""

    agent_id: str
    user_id: str
    thread_id: str
    model: BaseChatModel
    available_tools: list[str] = field(default_factory=list)
    config_center: ConfigCenter | None = None
