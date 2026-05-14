"""State definitions for the main graph and sub-agent graphs."""

from __future__ import annotations

import operator
from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ArtiPivotState(TypedDict):
    """Main graph state — shared across all nodes."""

    messages: Annotated[list[AnyMessage], add_messages]
    intent: str | None
    confidence: float
    active_agent: str | None
    metadata: dict


class SubAgentState(TypedDict):
    """Sub-agent graph state."""

    messages: Annotated[list[AnyMessage], add_messages]
    query: str
    artifacts: Annotated[list[str], operator.add]
