"""AgentContext — runtime context injected into graph nodes."""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel


@dataclass
class AgentContext:
    """Runtime context — injected via context_schema, accessible via Runtime[AgentContext]."""

    agent_id: str
    user_id: str
    thread_id: str
    model: BaseChatModel
    available_tools: list[str] = field(default_factory=list)
