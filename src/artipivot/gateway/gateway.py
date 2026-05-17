"""AgentGateway — multi-agent dispatch layer."""

from __future__ import annotations

import time

from langgraph.graph.state import CompiledStateGraph

from artipivot.graph.context import AgentContext
from artipivot.models.provider import ModelProvider
from artipivot.observability import log
from artipivot.observability import otel
from artipivot.observability.trace import bind_trace_id, clear_trace, generate_trace_id


class AgentGateway:
    """Multi-agent dispatch layer — routes requests by agent_id."""

    def __init__(
        self,
        model_provider: ModelProvider,
        *,
        config_center=None,
    ) -> None:
        self._graphs: dict[str, CompiledStateGraph] = {}
        self._model_provider = model_provider
        self._config_center = config_center

    def register(self, agent_id: str, graph: CompiledStateGraph) -> None:
        """Register a compiled graph for an agent."""
        self._graphs[agent_id] = graph

    async def invoke(
        self,
        agent_id: str,
        message: str,
        thread_id: str,
        *,
        user_id: str = "default_user",
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

        log.info("gateway.request")
        t0 = time.perf_counter()

        model = self._model_provider.get_model(agent_id, user_id=user_id)

        config = {"configurable": {"thread_id": full_thread_id}}

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
                ),
            )
            elapsed = int((time.perf_counter() - t0) * 1000)
            msg_count = len(result.get("messages", [])) if isinstance(result, dict) else 0
            log.info("gateway.complete", duration_ms=elapsed, messages_count=msg_count)
            otel.record_request_duration(elapsed, agent_id=agent_id)
            return result
        except Exception as e:
            elapsed = int((time.perf_counter() - t0) * 1000)
            log.error("gateway.error", duration_ms=elapsed, error=str(e))
            raise
        finally:
            clear_trace()

    async def stream(self, agent_id: str, message: str, thread_id: str, *, user_id: str = "default_user"):
        """Stream responses from the agent's graph."""
        if agent_id not in self._graphs:
            raise ValueError(f"Unknown agent: {agent_id}")

        graph = self._graphs[agent_id]
        full_thread_id = f"{agent_id}:{thread_id}"
        trace_id = generate_trace_id()

        bind_trace_id(trace_id, agent_id=agent_id, user_id=user_id, thread_id=full_thread_id)

        log.info("gateway.request", mode="stream")
        t0 = time.perf_counter()

        model = self._model_provider.get_model(agent_id, user_id=user_id)
        config = {"configurable": {"thread_id": full_thread_id}}

        try:
            async for chunk in graph.astream(
                {"messages": [{"role": "user", "content": message}]},
                config,
                context=AgentContext(
                    agent_id=agent_id,
                    user_id=user_id,
                    thread_id=full_thread_id,
                    model=model,
                    config_center=self._config_center,
                ),
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
