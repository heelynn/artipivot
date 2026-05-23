"""Tests for circuit breaker integration."""

from __future__ import annotations

import pytest


class TestCircuitConfig:
    """Tests for YAML circuit config parsing."""

    def test_from_dict_defaults(self):
        from artipivot.gateway.agent_def import AgentDef

        ad = AgentDef.from_dict({
            "agent_id": "test",
        })
        assert ad.circuit.enabled is True
        assert ad.circuit.failure_threshold == 5
        assert ad.circuit.recovery_timeout == 60.0

    def test_from_dict_custom(self):
        from artipivot.gateway.agent_def import AgentDef

        ad = AgentDef.from_dict({
            "agent_id": "test",
            "circuit": {
                "enabled": False,
                "failure_threshold": 10,
                "recovery_timeout": 30.0,
            },
        })
        assert ad.circuit.enabled is False
        assert ad.circuit.failure_threshold == 10
        assert ad.circuit.recovery_timeout == 30.0

    def test_to_dict(self):
        from artipivot.gateway.agent_def import AgentDef

        ad = AgentDef.from_dict({
            "agent_id": "test",
            "circuit": {"enabled": True},
        })
        d = ad.to_dict()
        assert d["circuit"]["enabled"] is True
        assert d["circuit"]["failure_threshold"] == 5


class TestCircuitBreakerBehavior:
    """Tests for circuit breaker state machine."""

    @pytest.mark.asyncio
    async def test_circuit_open_after_threshold(self):
        from artipivot.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError

        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60.0)

        # Fail twice → should open
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(_raise_value_error)

        # Third call should be rejected by circuit breaker
        with pytest.raises(CircuitOpenError):
            await cb.call(_raise_value_error)

    @pytest.mark.asyncio
    async def test_circuit_closed_on_success(self):
        from artipivot.resilience.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.01)

        # Fail once
        with pytest.raises(ValueError):
            await cb.call(_raise_value_error)

        # Succeed — resets failure count
        result = await cb.call(_success_fn, "hello")
        assert result == "hello"
        assert cb.state == "closed"
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_disabled(self):
        """When circuit is disabled, model is not wrapped."""
        from artipivot.gateway.agent_def import CircuitConfig

        cfg = CircuitConfig(enabled=False)
        assert cfg.enabled is False


class TestCircuitWrappedModel:
    """Tests for _CircuitWrappedModel proxy."""

    @pytest.mark.asyncio
    async def test_wrapped_model_delegates_attributes(self):
        from artipivot.resilience.circuit_breaker import CircuitBreaker
        from artipivot.models.provider import _CircuitWrappedModel

        class FakeModel:
            async def ainvoke(self, messages):
                return {"response": "ok"}

            @property
            def model_name(self):
                return "fake-gpt"

        cb = CircuitBreaker("test", failure_threshold=3)
        wrapped = _CircuitWrappedModel(FakeModel(), cb)

        # Attribute delegation
        assert wrapped.model_name == "fake-gpt"

        # ainvoke goes through circuit
        result = await wrapped.ainvoke(["hello"])
        assert result == {"response": "ok"}

    @pytest.mark.asyncio
    async def test_wrapped_model_circuit_opens(self):
        from artipivot.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError
        from artipivot.models.provider import _CircuitWrappedModel

        class FailingModel:
            async def ainvoke(self, messages):
                raise ValueError("API down")

        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60.0)
        wrapped = _CircuitWrappedModel(FailingModel(), cb)

        # First call fails → circuit opens
        with pytest.raises(ValueError):
            await wrapped.ainvoke(["hello"])

        # Second call rejected by circuit
        with pytest.raises(CircuitOpenError):
            await wrapped.ainvoke(["hello"])


async def _raise_value_error(*args, **kwargs):
    raise ValueError("simulated failure")


async def _success_fn(result):
    return result
