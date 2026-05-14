"""TraceLogger — request-level trace_id binding."""

from __future__ import annotations

import uuid

import structlog


def generate_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def bind_trace_id(
    trace_id: str,
    *,
    agent_id: str | None = None,
    user_id: str | None = None,
    thread_id: str | None = None,
) -> None:
    """Bind request context to structlog contextvars."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        trace_id=trace_id,
        **{k: v for k, v in {
            "agent_id": agent_id,
            "user_id": user_id,
            "thread_id": thread_id,
        }.items() if v is not None},
    )


def clear_trace() -> None:
    """Clear request context."""
    structlog.contextvars.clear_contextvars()
