"""Observability — logging, tracing, and metrics.

Usage::

    from artipivot.observability import log, bind

    # Bind sub-agent context (once per sub-agent lifecycle)
    bind(sub_name="writer", strategy="react")
    bind(iteration=1)

    # Log events — context is auto-injected via contextvars
    log.info("sub_agent.start")
    log.info("llm.call", messages_count=5)
    log.debug("llm.input", messages=[...])
    log.error("gateway.error", error="timeout")
"""

import structlog

from artipivot.observability.logging import configure_logging, serialize
from artipivot.observability.trace import bind_trace_id, clear_trace, generate_trace_id

# Structlog native logger — all context from contextvars is auto-injected
log = structlog.get_logger("artipivot")

# Short alias for binding context
bind = structlog.contextvars.bind_contextvars

__all__ = [
    "configure_logging",
    "log",
    "bind",
    "serialize",
    "bind_trace_id",
    "clear_trace",
    "generate_trace_id",
]
