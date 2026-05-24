"""AgentGateway — multi-agent dispatch layer."""

from __future__ import annotations

import asyncio
import time

import structlog
from langgraph.graph.state import CompiledStateGraph

from artipivot.graph.context import AgentContext
from artipivot.models.provider import ModelProvider
from artipivot.observability import log
from artipivot.observability import otel
from artipivot.observability.callback import GraphLoggingCallback
from artipivot.observability.trace import bind_trace_id, clear_trace, generate_trace_id


def _model_name(model) -> str:
    """Extract model name from a LangChain BaseChatModel instance."""
    return getattr(model, "model", None) or getattr(model, "model_name", "unknown")


def _truncate(text: str, limit: int = 200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


class AgentGateway:
    """Multi-agent dispatch layer — routes requests by agent_id."""

    def __init__(
        self,
        model_provider: ModelProvider,
        *,
        config_center=None,
        storage_provider=None,
    ) -> None:
        self._graphs: dict[str, CompiledStateGraph] = {}
        self._model_provider = model_provider
        self._config_center = config_center
        self._storage_provider = storage_provider
        self._callback = GraphLoggingCallback()
        self._rebuild_locks: dict[str, asyncio.Lock] = {}

    def register(self, agent_id: str, graph: CompiledStateGraph) -> None:
        """Register a compiled graph for an agent."""
        self._graphs[agent_id] = graph

    def unregister(self, agent_id: str) -> None:
        """Remove an agent's graph from the gateway."""
        self._graphs.pop(agent_id, None)
        self._rebuild_locks.pop(agent_id, None)

    def list_agent_ids(self) -> list[str]:
        """Return all registered agent IDs."""
        return list(self._graphs.keys())

    def rebuild_guard(self, agent_id: str):
        """Async context manager that serializes rebuilds per agent_id.

        Usage:
            async with gateway.rebuild_guard(agent_id):
                new_graph = build_new_graph()
                gateway.register(agent_id, new_graph)
        """
        lock = self._rebuild_locks.setdefault(agent_id, asyncio.Lock())

        class _Guard:
            def __init__(self, _lock):
                self._lock = _lock

            async def __aenter__(self):
                await self._lock.acquire()

            async def __aexit__(self, *args):
                self._lock.release()

        return _Guard(lock)

    async def invoke(
        self,
        agent_id: str,
        message: str,
        thread_id: str,
        *,
        user_id: str = "default_user",
        memory_config=None,
    ) -> dict:
        """Invoke a single turn on the agent's graph."""
        if agent_id not in self._graphs:
            raise ValueError(f"Unknown agent: {agent_id}")

        graph = self._graphs[agent_id]
        full_thread_id = f"{agent_id}:{thread_id}"
        trace_id = generate_trace_id()

        bind_trace_id(
            trace_id,
            agent_id=agent_id,
            user_id=user_id,
            thread_id=full_thread_id,
        )

        log.info("gateway.request", message=_truncate(message))
        t0 = time.perf_counter()

        model = self._model_provider.get_model(agent_id, user_id=user_id)
        structlog.contextvars.bind_contextvars(model_name=_model_name(model))

        config = {
            "configurable": {"thread_id": full_thread_id},
            "callbacks": [self._callback],
        }

        try:
            result = await graph.ainvoke(
                {"messages": [{"role": "user", "content": message}]},
                config,
                context=AgentContext(
                    agent_id=agent_id,
                    user_id=user_id,
                    thread_id=full_thread_id,
                    model=model,
                    config_center=self._config_center,
                    memory_config=memory_config,
                ),
            )
            elapsed = int((time.perf_counter() - t0) * 1000)
            msg_count = len(result.get("messages", [])) if isinstance(result, dict) else 0

            # Extract last assistant message as response summary
            reply = ""
            if isinstance(result, dict) and result.get("messages"):
                for m in reversed(result["messages"]):
                    if getattr(m, "type", None) == "ai" or getattr(m, "role", None) == "assistant":
                        reply = getattr(m, "content", "")
                        break

            # Extract route info from result
            intent = result.get("intent") if isinstance(result, dict) else None
            confidence = result.get("confidence") if isinstance(result, dict) else None
            parsed = result.get("parsed") if isinstance(result, dict) else None

            log.info(
                "gateway.complete",
                duration_ms=elapsed,
                messages_count=msg_count,
                reply=_truncate(reply),
                intent=intent,
                confidence=confidence,
                parsed=parsed,
            )
            otel.record_request_duration(elapsed, agent_id=agent_id)

            # L3 async write — fire and forget
            self._maybe_write_memory(
                agent_id=agent_id,
                user_id=user_id,
                result=result,
                model=model,
                memory_config=memory_config,
            )

            return result
        except Exception as e:
            elapsed = int((time.perf_counter() - t0) * 1000)
            log.error("gateway.error", duration_ms=elapsed, error=str(e))
            raise
        finally:
            clear_trace()

    async def stream(
        self,
        agent_id: str,
        message: str,
        thread_id: str,
        *,
        user_id: str = "default_user",
        memory_config=None,
        stream_mode: str = "messages",
    ):
        """Stream responses from the agent's graph.

        Args:
            stream_mode: LangGraph stream mode. Default "messages" yields
                (message_chunk, metadata) tuples for token-level streaming.
                Use "values" for full state snapshots per node.
        """
        if agent_id not in self._graphs:
            raise ValueError(f"Unknown agent: {agent_id}")

        graph = self._graphs[agent_id]
        full_thread_id = f"{agent_id}:{thread_id}"
        trace_id = generate_trace_id()

        bind_trace_id(trace_id, agent_id=agent_id, user_id=user_id, thread_id=full_thread_id)

        log.info("gateway.request", mode="stream", stream_mode=stream_mode, message=_truncate(message))
        t0 = time.perf_counter()

        model = self._model_provider.get_model(agent_id, user_id=user_id)
        structlog.contextvars.bind_contextvars(model_name=_model_name(model))

        config = {
            "configurable": {"thread_id": full_thread_id},
            "callbacks": [self._callback],
        }

        ctx = AgentContext(
            agent_id=agent_id,
            user_id=user_id,
            thread_id=full_thread_id,
            model=model,
            config_center=self._config_center,
            memory_config=memory_config,
        )

        try:
            async for chunk in graph.astream(
                {"messages": [{"role": "user", "content": message}]},
                config,
                context=ctx,
                stream_mode=stream_mode,
            ):
                yield chunk
            elapsed = int((time.perf_counter() - t0) * 1000)
            log.info("gateway.complete", duration_ms=elapsed, mode="stream")
            otel.record_request_duration(elapsed, agent_id=agent_id)
        except Exception as e:
            elapsed = int((time.perf_counter() - t0) * 1000)
            log.error("gateway.error", duration_ms=elapsed, mode="stream", error=str(e))
            raise
        finally:
            clear_trace()

    def _maybe_write_memory(
        self,
        *,
        agent_id: str,
        user_id: str,
        result: dict,
        model,
        memory_config,
    ) -> None:
        """Fire-and-forget L3 memory extraction if enabled."""
        if not memory_config or not memory_config.extraction.enabled:
            return

        store = None
        if self._storage_provider:
            store = self._storage_provider.store

        if not store:
            return

        messages = result.get("messages", []) if isinstance(result, dict) else []

        async def _do_write():
            from artipivot.memory.extraction import write_memory
            try:
                await write_memory(
                    store, agent_id, user_id, messages, model,
                    memory_config.extraction,
                )
            except Exception:
                log.warning("L3 memory extraction failed", exc_info=True)

        asyncio.create_task(_do_write())
