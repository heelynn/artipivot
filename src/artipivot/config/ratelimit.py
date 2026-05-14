"""RateLimiter skeleton — P0 placeholder."""

from __future__ import annotations


class RateLimiter:
    """Rate limiter — P0 skeleton, no actual limiting."""

    def __init__(self) -> None:
        self._configs: dict = {}

    async def apply(self, collection: str, key: str, action: str, data: dict) -> None:
        self._configs[key] = data

    async def check(self, agent_id: str, user_id: str, tool_name: str | None = None) -> None:
        """P0: always passes."""
        pass
