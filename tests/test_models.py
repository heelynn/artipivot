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
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        provider = ModelProvider(store, notifier)
        await provider.start()

        with pytest.raises(ValueError, match="No model config"):
            provider.get_model("nonexistent")
