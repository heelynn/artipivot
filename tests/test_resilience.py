"""Tests for P5 resilience — CircuitBreaker, RetryPolicy, error handlers."""

from __future__ import annotations

import asyncio

import pytest

from artipivot.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitRegistry,
)
from artipivot.resilience.retry import RetryExhaustedError, RetryPolicy


# ── CircuitBreaker ──


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_closed_passes(self):
        cb = CircuitBreaker("test")
        result = await cb.call(lambda: asyncio.sleep(0, result="ok"))
        assert result == "ok"
        assert cb.state == "closed"

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=2)

        async def fail():
            raise RuntimeError("boom")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(fail)

        assert cb.state == "open"

    @pytest.mark.asyncio
    async def test_open_rejects(self):
        cb = CircuitBreaker("test", failure_threshold=1)

        async def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cb.call(fail)

        assert cb.state == "open"
        with pytest.raises(CircuitOpenError):
            await cb.call(lambda: asyncio.sleep(0, result="ok"))

    @pytest.mark.asyncio
    async def test_half_open_after_recovery(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.0)

        async def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cb.call(fail)
        assert cb.state == "open"

        # recovery_timeout=0 → immediate transition to half_open
        result = await cb.call(lambda: asyncio.sleep(0, result="ok"))
        assert result == "ok"
        assert cb.state == "closed"

    @pytest.mark.asyncio
    async def test_half_open_reopens_on_failure(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.0)

        async def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cb.call(fail)

        # half_open → fail → open
        with pytest.raises(RuntimeError):
            await cb.call(fail)
        assert cb.state == "open"

    @pytest.mark.asyncio
    async def test_reset(self):
        cb = CircuitBreaker("test", failure_threshold=1)

        async def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cb.call(fail)
        assert cb.state == "open"

        cb.reset()
        assert cb.state == "closed"
        result = await cb.call(lambda: asyncio.sleep(0, result="ok"))
        assert result == "ok"


class TestCircuitRegistry:
    def test_get_or_create(self):
        reg = CircuitRegistry()
        cb = reg.get_or_create("provider_a")
        assert cb.name == "provider_a"

        # Same name returns same instance
        assert reg.get_or_create("provider_a") is cb

    def test_get_state(self):
        reg = CircuitRegistry()
        assert reg.get_state("unknown") == "unknown"

        cb = reg.get_or_create("test")
        assert reg.get_state("test") == "closed"

    def test_all_states(self):
        reg = CircuitRegistry()
        reg.get_or_create("a")
        reg.get_or_create("b")
        states = reg.all_states()
        assert states == {"a": "closed", "b": "closed"}


# ── RetryPolicy ──


class TestRetryPolicy:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        policy = RetryPolicy(max_retries=3)
        calls = 0

        async def fn():
            nonlocal calls
            calls += 1
            return "ok"

        result = await policy.execute(fn)
        assert result == "ok"
        assert calls == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        policy = RetryPolicy(
            max_retries=2,
            base_delay=0.01,
            jitter=False,
            retryable_exceptions=(RuntimeError,),
        )
        calls = 0

        async def fn():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("transient")
            return "ok"

        result = await policy.execute(fn)
        assert result == "ok"
        assert calls == 3

    @pytest.mark.asyncio
    async def test_exhausted_raises(self):
        policy = RetryPolicy(
            max_retries=1,
            base_delay=0.01,
            retryable_exceptions=(RuntimeError,),
        )

        async def fn():
            raise RuntimeError("always fails")

        with pytest.raises(RetryExhaustedError):
            await policy.execute(fn)

    @pytest.mark.asyncio
    async def test_non_retryable_skipped(self):
        policy = RetryPolicy(
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )

        async def fn():
            raise RuntimeError("not retryable")

        with pytest.raises(RuntimeError):
            await policy.execute(fn)

    def test_calculate_delay(self):
        policy = RetryPolicy(base_delay=1.0, max_delay=10.0, exponential_base=2.0, jitter=False)
        assert policy._calculate_delay(0) == 1.0
        assert policy._calculate_delay(1) == 2.0
        assert policy._calculate_delay(2) == 4.0
        # Capped at max_delay
        assert policy._calculate_delay(10) == 10.0


# ── Error handlers ──


class TestErrorHandlers:
    def test_classify_error_returns_fallback(self):
        from langgraph.errors import NodeError

        from artipivot.resilience.error_handlers import on_classify_error

        state = {"messages": [], "intent": None, "confidence": 0.0, "active_agent": None, "metadata": {}}
        error = NodeError(node="classify", error=RuntimeError("llm down"))
        cmd = on_classify_error(state, error)
        assert cmd.goto == "fallback"
        assert cmd.update["intent"] == "fallback"

    def test_classify_timeout_returns_fallback(self):
        from langgraph.errors import NodeError

        from artipivot.resilience.error_handlers import on_classify_error

        state = {"messages": [], "intent": None, "confidence": 0.0, "active_agent": None, "metadata": {}}
        error = NodeError(node="classify", error=TimeoutError("timed out"))
        cmd = on_classify_error(state, error)
        assert cmd.goto == "fallback"

    def test_sub_agent_error_returns_respond(self):
        from langgraph.errors import NodeError

        from artipivot.resilience.error_handlers import on_sub_agent_error

        state = {"messages": [], "intent": None, "confidence": 0.0, "active_agent": None, "metadata": {}}
        error = NodeError(node="writer", error=RuntimeError("crash"))
        cmd = on_sub_agent_error(state, error)
        assert cmd.goto == "respond"
        assert "messages" in cmd.update

    def test_tool_error_returns_tool_message(self):
        from langchain_core.messages import AIMessage

        from artipivot.resilience.error_handlers import on_tool_error

        state = {
            "messages": [
                AIMessage(content="", tool_calls=[{"id": "tc_1", "name": "search", "args": {}}]),
            ],
            "query": "",
            "artifacts": [],
        }
        from langgraph.errors import NodeError

        error = NodeError(node="tools", error=RuntimeError("tool failed"))
        result = on_tool_error(state, error)
        assert len(result["messages"]) == 1
        assert result["messages"][0].status == "error"
