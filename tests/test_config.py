"""Tests for config center."""

from __future__ import annotations

import pytest

from artipivot.config.center import ConfigCenter
from artipivot.config.prompts import PromptStore
from artipivot.config.routing import RoutingConfig
from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier


class TestPromptStore:
    @pytest.mark.asyncio
    async def test_get_and_apply(self):
        ps = PromptStore()
        await ps.apply("prompt_configs", "agent:classify", "load", {
            "_id": "agent:classify",
            "system": "You are a classifier.",
        })
        result = ps.get("agent", "classify")
        assert result["system"] == "You are a classifier."

    @pytest.mark.asyncio
    async def test_get_missing(self):
        ps = PromptStore()
        result = ps.get("agent", "nonexistent")
        assert result == {}


class TestRoutingConfig:
    @pytest.mark.asyncio
    async def test_intent_map(self):
        rc = RoutingConfig()
        await rc.apply("routing_configs", "code_agent", "load", {
            "agent_id": "code_agent",
            "confidence_threshold": 0.7,
            "intents": [
                {"name": "code_write", "sub_agent": "code_writer"},
                {"name": "debug", "sub_agent": "debugger"},
            ],
        })
        intent_map = rc.get_intent_map("code_agent")
        assert intent_map == {"code_write": "code_writer", "debug": "debugger"}

    @pytest.mark.asyncio
    async def test_threshold_default(self):
        rc = RoutingConfig()
        assert rc.get_threshold("nonexistent") == 0.7


class TestConfigCenter:
    @pytest.mark.asyncio
    async def test_start_loads_data(self):
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()

        await store.put("routing_configs", "code_agent", {
            "agent_id": "code_agent",
            "confidence_threshold": 0.8,
            "intents": [
                {"name": "code_write", "sub_agent": "code_writer"},
            ],
        })

        cc = ConfigCenter(store, notifier)
        await cc.start()

        assert cc.routing.get_threshold("code_agent") == 0.8
