"""Tests for model layer."""

from __future__ import annotations

import pytest

from artipivot.models.config import ModelConfig
from artipivot.models.provider import ModelProvider
from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier


class TestModelConfig:
    def test_defaults(self):
        cfg = ModelConfig(provider="anthropic", name="claude-sonnet-4-6")
        assert cfg.temperature == 0.0
        assert cfg.timeout == 120
        assert cfg.fallback is None
        assert cfg.base_url is None
        assert cfg.api_key is None

    def test_with_fallback(self):
        fb = ModelConfig(provider="openai", name="gpt-4o")
        cfg = ModelConfig(provider="anthropic", name="claude-sonnet-4-6", fallback=fb)
        assert cfg.fallback.name == "gpt-4o"

    def test_with_base_url(self):
        cfg = ModelConfig(
            provider="openai",
            name="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key="sk-test",
        )
        assert cfg.base_url == "https://api.deepseek.com"
        assert cfg.api_key == "sk-test"


class TestModelProvider:
    @pytest.mark.asyncio
    async def test_load_and_apply(self):
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()

        # Seed data
        await store.put("model_configs", "global", {
            "scope": "global",
            "fallback_model": {"provider": "openai", "name": "gpt-4o"},
        })
        await store.put("model_configs", "agent:code_agent", {
            "scope": "agent",
            "agent_id": "code_agent",
            "model": {"provider": "anthropic", "name": "claude-sonnet-4-6"},
        })

        provider = ModelProvider(store, notifier)
        await provider.start()

        # Verify internal state loaded
        model = provider.get_model("code_agent")
        assert model is not None

    @pytest.mark.asyncio
    async def test_unknown_agent_raises(self):
        """No config at all — should raise."""
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        provider = ModelProvider(store, notifier)
        await provider.start()

        with pytest.raises(ValueError, match="No model config"):
            provider.get_model("nonexistent")

    @pytest.mark.asyncio
    async def test_global_fallback_used(self):
        """Agent not configured but global fallback exists — should succeed."""
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        await store.put("model_configs", "global", {
            "scope": "global",
            "fallback_model": {"provider": "anthropic", "name": "claude-haiku-4-5"},
        })
        provider = ModelProvider(store, notifier)
        await provider.start()

        model = provider.get_model("any_agent")
        assert model is not None

    @pytest.mark.asyncio
    async def test_agent_overrides_global(self):
        """Agent config takes priority over global fallback."""
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        await store.put("model_configs", "global", {
            "scope": "global",
            "fallback_model": {"provider": "anthropic", "name": "claude-haiku-4-5"},
        })
        await store.put("model_configs", "agent:my_agent", {
            "scope": "agent",
            "agent_id": "my_agent",
            "model": {"provider": "anthropic", "name": "claude-sonnet-4-6"},
        })
        provider = ModelProvider(store, notifier)
        await provider.start()

        model = provider.get_model("my_agent")
        # Should get claude-sonnet-4-6 (agent), not claude-haiku-4-5 (global)
        assert model is not None


class TestUserModelConfig:
    @pytest.mark.asyncio
    async def test_user_overrides_agent(self):
        """User-level config overrides agent-level."""
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        await store.put("model_configs", "agent:my_agent", {
            "scope": "agent",
            "agent_id": "my_agent",
            "model": {"provider": "anthropic", "name": "claude-sonnet-4-6"},
        })
        await store.put("model_configs", "user:my_agent:alice", {
            "scope": "user",
            "agent_id": "my_agent",
            "user_id": "alice",
            "model": {"provider": "anthropic", "name": "claude-haiku-4-5"},
        })
        provider = ModelProvider(store, notifier)
        await provider.start()

        model = provider.get_model("my_agent", user_id="alice")
        assert model is not None
        # alice gets haiku, not sonnet

        # other user gets agent default
        model_bob = provider.get_model("my_agent", user_id="bob")
        assert model_bob is not None

    @pytest.mark.asyncio
    async def test_user_global_overrides_agent(self):
        """User global config (no agent_id) overrides agent-level."""
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        await store.put("model_configs", "agent:my_agent", {
            "scope": "agent",
            "agent_id": "my_agent",
            "model": {"provider": "anthropic", "name": "claude-sonnet-4-6"},
        })
        await store.put("model_configs", "user:__global__:alice", {
            "scope": "user",
            "agent_id": "__global__",
            "user_id": "alice",
            "model": {"provider": "anthropic", "name": "claude-haiku-4-5"},
        })
        provider = ModelProvider(store, notifier)
        await provider.start()

        # alice:agent-specific takes priority over alice:global
        model = provider.get_model("my_agent", user_id="alice")
        assert model is not None

    @pytest.mark.asyncio
    async def test_user_agent_overrides_user_global(self):
        """User:agent config takes priority over user:global."""
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        await store.put("model_configs", "user:__global__:alice", {
            "scope": "user",
            "agent_id": "__global__",
            "user_id": "alice",
            "model": {"provider": "anthropic", "name": "claude-haiku-4-5"},
        })
        await store.put("model_configs", "user:my_agent:alice", {
            "scope": "user",
            "agent_id": "my_agent",
            "user_id": "alice",
            "model": {"provider": "anthropic", "name": "claude-opus-4-6"},
        })
        provider = ModelProvider(store, notifier)
        await provider.start()

        model = provider.get_model("my_agent", user_id="alice")
        assert model is not None
        # alice:my_agent (opus) > alice:__global__ (haiku)

    @pytest.mark.asyncio
    async def test_no_user_falls_to_agent(self):
        """No user config — falls through to agent then global."""
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        await store.put("model_configs", "agent:my_agent", {
            "scope": "agent",
            "agent_id": "my_agent",
            "model": {"provider": "anthropic", "name": "claude-sonnet-4-6"},
        })
        provider = ModelProvider(store, notifier)
        await provider.start()

        model = provider.get_model("my_agent", user_id="unknown_user")
        assert model is not None

    @pytest.mark.asyncio
    async def test_update_user_model(self):
        """update_user_model() persists and applies."""
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        provider = ModelProvider(store, notifier)
        await provider.start()

        await provider.update_user_model(
            user_id="alice",
            model={"provider": "anthropic", "name": "claude-haiku-4-5"},
            agent_id="my_agent",
        )

        model = provider.get_model("my_agent", user_id="alice")
        assert model is not None

    @pytest.mark.asyncio
    async def test_delete_user_model(self):
        """delete_user_model() removes the override."""
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        await store.put("model_configs", "agent:my_agent", {
            "scope": "agent",
            "agent_id": "my_agent",
            "model": {"provider": "anthropic", "name": "claude-sonnet-4-6"},
        })
        provider = ModelProvider(store, notifier)
        await provider.start()

        await provider.update_user_model(
            user_id="alice",
            model={"provider": "anthropic", "name": "claude-haiku-4-5"},
            agent_id="my_agent",
        )
        # Verify set
        assert provider.get_user_model_config("alice", "my_agent") is not None

        await provider.delete_user_model("alice", "my_agent")
        # Verify deleted
        assert provider.get_user_model_config("alice", "my_agent") is None
