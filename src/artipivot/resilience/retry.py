"""RetryPolicy — exponential backoff with optional jitter."""

from __future__ import annotations

import asyncio
import random

import structlog

logger = structlog.get_logger("artipivot.resilience")


class RetryExhaustedError(Exception):
    """All retry attempts failed."""


class RetryPolicy:
    """Generic retry with exponential backoff.

    Usage:
        policy = RetryPolicy(max_retries=3)
        result = await policy.execute(my_async_fn, arg1, arg2)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions

    async def execute(self, fn, *args, **kwargs):
        """Execute fn with retry on transient failures."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except self.retryable_exceptions as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        "retry.attempt",
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        delay_ms=int(delay * 1000),
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

        raise RetryExhaustedError(
            f"All {self.max_retries + 1} attempts failed: {last_error}"
        ) from last_error

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff + optional jitter."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay *= random.uniform(0.5, 1.0)  # noqa: S311
        return delay
