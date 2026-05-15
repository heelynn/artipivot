"""Tests for P5 rate limiter."""

from __future__ import annotations

import pytest

from artipivot.config.ratelimit import RateLimitConfig, RateLimitError, RateLimiter
from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier


class TestRateLimitConfig:
    def test_defaults(self):
        config = RateLimitConfig()
        merged = config.get_merged()
        assert merged["user_rpm"] == 60
        assert merged["agent_rpm"] == 600
        assert merged["tool_rpm"] == 120

    def test_agent_override(self):
        config = RateLimitConfig(
            agent_overrides={"code_agent": {"user_rpm": 30}},
        )
        merged = config.get_merged(agent_id="code_agent")
        assert merged["user_rpm"] == 30
        # Non-overridden defaults remain
        assert merged["agent_rpm"] == 600

    def test_tool_override(self):
        config = RateLimitConfig(
            tool_overrides={"code_exec": {"tool_rpm": 10}},
        )
        merged = config.get_merged(tool_name="code_exec")
        assert merged["tool_rpm"] == 10

    def test_merged_layers(self):
        config = RateLimitConfig(
            agent_overrides={"agent_a": {"user_rpm": 30}},
            tool_overrides={"tool_x": {"tool_rpm": 5}},
        )
        merged = config.get_merged(agent_id="agent_a", tool_name="tool_x")
        assert merged["user_rpm"] == 30
        assert merged["tool_rpm"] == 5


class TestRateLimiter:
    @pytest.fixture
    def rl(self):
        return RateLimiter()

    @pytest.mark.asyncio
    async def test_check_passes_within_limit(self, rl):
        await rl.check("agent_a", "user_1")  # Should not raise

    @pytest.mark.asyncio
    async def test_check_blocks_user_over_limit(self, rl):
        rl.config.defaults["user_rpm"] = 2
        await rl.check("agent_a", "user_1")
        await rl.check("agent_a", "user_1")
        with pytest.raises(RateLimitError, match="exceeded rate limit"):
            await rl.check("agent_a", "user_1")

    @pytest.mark.asyncio
    async def test_check_blocks_agent_over_limit(self, rl):
        rl.config.defaults["agent_rpm"] = 2
        await rl.check("agent_a", "user_1")
        await rl.check("agent_a", "user_2")
        with pytest.raises(RateLimitError, match="Agent"):
            await rl.check("agent_a", "user_3")

    @pytest.mark.asyncio
    async def test_check_blocks_tool_over_limit(self, rl):
        rl.config.defaults["tool_rpm"] = 1
        await rl.check("agent_a", "user_1", tool_name="code_exec")
        with pytest.raises(RateLimitError, match="Tool"):
            await rl.check("agent_a", "user_1", tool_name="code_exec")

    @pytest.mark.asyncio
    async def test_different_users_independent(self, rl):
        rl.config.defaults["user_rpm"] = 1
        await rl.check("agent_a", "user_1")
        await rl.check("agent_a", "user_2")  # Different user, should pass

    @pytest.mark.asyncio
    async def test_dynamic_config_update(self, rl):
        await rl.apply("ratelimit_configs", "agent:code_agent", "update", {
            "scope": "agent",
            "agent_id": "code_agent",
            "overrides": {"user_rpm": 1},
        })
        merged = rl.config.get_merged(agent_id="code_agent")
        assert merged["user_rpm"] == 1

    @pytest.mark.asyncio
    async def test_apply_global_scope(self, rl):
        await rl.apply("ratelimit_configs", "global", "update", {
            "scope": "global",
            "user_rpm": 100,
        })
        assert rl.config.defaults["user_rpm"] == 100
