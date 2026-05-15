"""Node-level error handlers — classify, sub-agent, tool fault tolerance."""

from __future__ import annotations

import asyncio

from langchain_core.messages import ToolMessage
from langgraph.errors import NodeError
from langgraph.types import Command

from artipivot.graph.state import ArtiPivotState, SubAgentState


def on_classify_error(state: ArtiPivotState, error: NodeError) -> Command:
    """classify node error handler — timeout or LLM failure → fallback/respond."""
    original = error.error

    if isinstance(original, TimeoutError | asyncio.TimeoutError):
        return Command(
            update={"intent": "fallback", "confidence": 0.0},
            goto="fallback",
        )

    # LLM or other errors → fallback with low confidence
    return Command(
        update={"intent": "fallback", "confidence": 0.0},
        goto="fallback",
    )


def on_sub_agent_error(state: ArtiPivotState, error: NodeError) -> Command:
    """Sub-agent node error handler — route to respond with error message."""
    return Command(
        update={
            "messages": [
                {
                    "role": "assistant",
                    "content": "Sorry, an error occurred while processing. Please try again.",
                }
            ]
        },
        goto="respond",
    )


def on_tool_error(state: SubAgentState, error: NodeError) -> dict:
    """Tool node error handler — return error message, don't break sub-agent loop."""
    # Best-effort: try to get the tool_call_id from the last AI message
    tool_call_id = ""
    for msg in reversed(state.get("messages", [])):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_call_id = msg.tool_calls[-1].get("id", "")
            break

    return {
        "messages": [
            ToolMessage(
                content=f"Tool execution failed: {error.error}",
                tool_call_id=tool_call_id or "unknown",
                status="error",
            )
        ]
    }
