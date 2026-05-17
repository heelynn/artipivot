"""AgentContext — runtime context injected into graph nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from artipivot.config.center import ConfigCenter


@dataclass
class AgentContext:
    """Runtime context — injected via context_schema, accessible via Runtime[AgentContext]."""

    agent_id: str
    user_id: str
    thread_id: str
    model: BaseChatModel
    available_tools: list[BaseTool] = field(default_factory=list)
    config_center: ConfigCenter | None = None

    def bound_model(self, tools: list[BaseTool] | None = None) -> BaseChatModel:
        """Return model with tools bound. Falls back to context tools if none given."""
        effective = tools if tools is not None else self.available_tools
        return self.model.bind_tools(effective) if effective else self.model
