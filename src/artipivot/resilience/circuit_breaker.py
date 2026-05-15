"""CircuitBreaker — three-state machine for external dependency protection."""

from __future__ import annotations

import asyncio
import time

import structlog

logger = structlog.get_logger("artipivot.resilience")


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open."""


class CircuitBreaker:
    """Circuit breaker — closed/open/half_open three-state machine.

    State transitions:
        closed  → open      (failure_count >= failure_threshold)
        open    → half_open (recovery_timeout elapsed)
        half_open → closed  (success)
        half_open → open    (failure)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.state: str = "closed"
        self.failure_count: int = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.last_failure_time: float | None = None
        self._lock = asyncio.Lock()
        self._half_open_calls: int = 0

    async def call(self, fn, *args, **kwargs):
        """Execute fn through the circuit breaker."""
        async with self._lock:
            await self._check_state()

        try:
            result = await fn(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure(e)
            raise

    async def _check_state(self) -> None:
        """Check and potentially transition state before a call."""
        if self.state == "closed":
            return

        if self.state == "open":
            if (
                self.last_failure_time is not None
                and time.monotonic() - self.last_failure_time > self.recovery_timeout
            ):
                self.state = "half_open"
                self._half_open_calls = 0
                logger.warning("circuit.half_open", circuit=self.name)
                return
            raise CircuitOpenError(
                f"Circuit breaker [{self.name}] is open"
            )

        if self.state == "half_open":
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitOpenError(
                    f"Circuit breaker [{self.name}] is half_open and at capacity"
                )
            self._half_open_calls += 1

    async def _on_success(self) -> None:
        """Handle a successful call."""
        async with self._lock:
            self.failure_count = 0
            if self.state == "half_open":
                self.state = "closed"
                logger.info("circuit.closed", circuit=self.name)

    async def _on_failure(self, error: Exception) -> None:
        """Handle a failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()

            if self.state == "half_open":
                self.state = "open"
                logger.error(
                    "circuit.reopened",
                    circuit=self.name,
                    error=str(error),
                )
                return

            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.error(
                    "circuit.opened",
                    circuit=self.name,
                    failures=self.failure_count,
                    error=str(error),
                )

    def reset(self) -> None:
        """Manually reset to closed state."""
        self.state = "closed"
        self.failure_count = 0
        self.last_failure_time = None
        self._half_open_calls = 0


class CircuitRegistry:
    """Per-provider circuit breaker registry."""

    def __init__(self) -> None:
        self._circuits: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> CircuitBreaker:
        if name not in self._circuits:
            self._circuits[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return self._circuits[name]

    def get_state(self, name: str) -> str:
        cb = self._circuits.get(name)
        if cb is None:
            return "unknown"
        return cb.state

    def reset(self, name: str) -> None:
        cb = self._circuits.get(name)
        if cb:
            cb.reset()

    def all_states(self) -> dict[str, str]:
        return {name: cb.state for name, cb in self._circuits.items()}
