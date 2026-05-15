"""RateLimiter — multi-dimensional rate limiting with dynamic config."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

import structlog

from artipivot.storage.base import ChangeNotifier, DocumentStore

logger = structlog.get_logger("artipivot.config")


class RateLimitError(Exception):
    """Raised when a rate limit is exceeded."""


@dataclass
class RateLimitConfig:
    """Rate limit configuration — loaded from DocumentStore."""

    defaults: dict = field(default_factory=lambda: {
        "user_rpm": 60,
        "agent_rpm": 600,
        "tool_rpm": 120,
        "tool_timeout_ms": 30000,
    })
    agent_overrides: dict[str, dict] = field(default_factory=dict)
    tool_overrides: dict[str, dict] = field(default_factory=dict)

    def get_merged(
        self,
        agent_id: str | None = None,
        tool_name: str | None = None,
    ) -> dict:
        """Merge global defaults + agent override + tool override."""
        result = dict(self.defaults)
        if agent_id and agent_id in self.agent_overrides:
            result.update(self.agent_overrides[agent_id])
        if tool_name and tool_name in self.tool_overrides:
            result.update(self.tool_overrides[tool_name])
        return result


class _SlidingWindow:
    """In-memory sliding window counter — tracks requests per minute."""

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def count(self, key: str, window_sec: float = 60.0) -> int:
        """Count requests in the current window."""
        now = time.monotonic()
        cutoff = now - window_sec
        self._buckets[key] = [t for t in self._buckets[key] if t > cutoff]
        return len(self._buckets[key])

    def record(self, key: str) -> None:
        """Record a request."""
        self._buckets[key].append(time.monotonic())


class RateLimiter:
    """Multi-dimensional rate limiter — per-user, per-agent, per-tool."""

    def __init__(
        self,
        store: DocumentStore | None = None,
        notifier: ChangeNotifier | None = None,
    ) -> None:
        self._store = store
        self._notifier = notifier
        self._config = RateLimitConfig()
        self._window = _SlidingWindow()

    @property
    def config(self) -> RateLimitConfig:
        return self._config

    async def check(
        self,
        agent_id: str,
        user_id: str,
        tool_name: str | None = None,
    ) -> None:
        """Check rate limits — raise RateLimitError if exceeded."""
        limits = self._config.get_merged(agent_id, tool_name)

        # Per-user RPM
        user_rpm = limits.get("user_rpm", 60)
        user_key = f"user:{agent_id}:{user_id}"
        if self._window.count(user_key) >= user_rpm:
            raise RateLimitError(
                f"User {user_id} exceeded rate limit ({user_rpm} RPM) on agent {agent_id}"
            )

        # Per-agent RPM
        agent_rpm = limits.get("agent_rpm", 600)
        agent_key = f"agent:{agent_id}"
        if self._window.count(agent_key) >= agent_rpm:
            raise RateLimitError(
                f"Agent {agent_id} exceeded rate limit ({agent_rpm} RPM)"
            )

        # Per-tool RPM
        if tool_name:
            tool_rpm = limits.get("tool_rpm", 120)
            tool_key = f"tool:{tool_name}"
            if self._window.count(tool_key) >= tool_rpm:
                raise RateLimitError(
                    f"Tool {tool_name} exceeded rate limit ({tool_rpm} RPM)"
                )

        # All checks passed — record the request
        self._window.record(user_key)
        self._window.record(agent_key)
        if tool_name:
            self._window.record(tool_key)

    async def apply(
        self, collection: str, key: str, action: str, data: dict
    ) -> None:
        """ChangeNotifier callback — update rate limit config dynamically."""
        scope = data.get("scope", "")

        if scope == "global":
            self._config.defaults.update(data.get("overrides", data))
        elif scope == "agent":
            agent_id = data.get("agent_id", key)
            self._config.agent_overrides[agent_id] = data.get(
                "overrides", data
            )
        elif scope == "tool":
            tool_name = data.get("tool_name", key)
            self._config.tool_overrides[tool_name] = data.get(
                "overrides", data
            )

        logger.info("ratelimit.config_updated", scope=scope, key=key)
