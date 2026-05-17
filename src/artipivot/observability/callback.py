"""LangChain BaseCallbackHandler — auto-logs every node, LLM call, and tool call."""

from __future__ import annotations

import time
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

import structlog

from artipivot.observability.logging import serialize

log = structlog.get_logger("artipivot")

_MAX_LEN = 2000

# LangGraph internal nodes to skip — they add noise without value
_SKIP_NODES = frozenset({"_start", "_end", "__start__", "__end__", "EntryPoint", "ExitPoint"})


def _node_name(metadata: dict | None) -> str:
    """Extract LangGraph node name from callback metadata."""
    if not metadata:
        return ""
    # LangGraph injects langgraph_node into metadata
    return metadata.get("langgraph_node", "") or metadata.get("name", "")


class GraphLoggingCallback(BaseCallbackHandler):
    """Cross-cutting logging for LangGraph execution.

    Automatically logs:
    - ``node.start`` / ``node.end``   — every graph node with timing
    - ``llm.end``                     — every LLM call with token usage
    - ``tool.start`` / ``tool.end``   — every tool call with timing

    Business-semantic logs (intent, confidence, route decisions) stay in node code.
    """

    def __init__(self) -> None:
        self._timers: dict[UUID, float] = {}

    # ── Node (chain) lifecycle ──────────────────────────────

    def on_chain_start(
        self,
        serialized: dict,
        inputs: dict,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        **kwargs,
    ) -> None:
        name = _node_name(metadata)
        if not name or name in _SKIP_NODES:
            return
        self._timers[run_id] = time.perf_counter()
        log.debug("node.start", node=name)

    def on_chain_end(
        self,
        outputs: dict,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs,
    ) -> None:
        t0 = self._timers.pop(run_id, None)
        name = (kwargs.get("metadata") or {}).get("langgraph_node", "") if kwargs else ""
        if not name:
            return
        elapsed = int((time.perf_counter() - t0) * 1000) if t0 else -1
        log.debug("node.end", node=name, duration_ms=elapsed)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs,
    ) -> None:
        t0 = self._timers.pop(run_id, None)
        metadata = kwargs.get("metadata") or {}
        name = metadata.get("langgraph_node", "unknown")
        elapsed = int((time.perf_counter() - t0) * 1000) if t0 else -1
        log.error("node.error", node=name, duration_ms=elapsed, error=str(error)[:500])

    # ── LLM calls ──────────────────────────────────────────

    def on_chat_model_start(
        self,
        serialized: dict,
        messages: list,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        **kwargs,
    ) -> None:
        self._timers[run_id] = time.perf_counter()
        # Serialize messages for logging
        serialized_msgs = [serialize(m) for m in messages[0]] if messages else []
        full_input = str(serialized_msgs)
        log.debug("llm.input", messages=full_input)
        log.info("llm.input_summary", messages=full_input[:_MAX_LEN])

    def on_llm_end(
        self,
        response,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs,
    ) -> None:
        t0 = self._timers.pop(run_id, None)
        elapsed = int((time.perf_counter() - t0) * 1000) if t0 else -1

        # Extract token usage from LLMResult
        usage = {}
        try:
            if response.llm_output and isinstance(response.llm_output, dict):
                tu = response.llm_output.get("token_usage", {})
                usage = {
                    "input_tokens": tu.get("prompt_tokens", 0),
                    "output_tokens": tu.get("completion_tokens", 0),
                    "total_tokens": tu.get("total_tokens", 0),
                }
        except Exception:
            pass

        # Extract output content
        output_text = ""
        try:
            if response.generations and response.generations[0]:
                gen = response.generations[0][0]
                output_text = gen.text if hasattr(gen, "text") else str(gen)
        except Exception:
            pass

        log.debug("llm.end", duration_ms=elapsed, **usage, output=output_text)
        log.info("llm.end_summary", duration_ms=elapsed, **usage, output=output_text[:_MAX_LEN])

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs,
    ) -> None:
        self._timers.pop(run_id, None)
        log.error("llm.error", error=str(error)[:500])

    # ── Tool calls ──────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        inputs: dict | None = None,
        **kwargs,
    ) -> None:
        tool_name = serialized.get("name", "") or (metadata or {}).get("name", "unknown")
        self._timers[run_id] = time.perf_counter()
        log.info("tool.start", tool=tool_name)

    def on_tool_end(
        self,
        output,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs,
    ) -> None:
        t0 = self._timers.pop(run_id, None)
        elapsed = int((time.perf_counter() - t0) * 1000) if t0 else -1
        output_str = str(output)[:200] if output else ""
        log.info("tool.end", duration_ms=elapsed, output=output_str)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs,
    ) -> None:
        self._timers.pop(run_id, None)
        log.error("tool.error", error=str(error)[:500])
