"""Tests for gateway."""

from __future__ import annotations

import pytest

from artipivot.gateway.gateway import AgentGateway


class TestAgentGateway:
    def test_register(self):
        gw = AgentGateway(model_provider=None)
        # Can't register None, but should not crash on __init__
        assert gw._graphs == {}

    @pytest.mark.asyncio
    async def test_invoke_unknown_agent(self):
        from artipivot.models.provider import ModelProvider
        from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier

        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        provider = ModelProvider(store, notifier)
        gw = AgentGateway(model_provider=provider)

        with pytest.raises(ValueError, match="Unknown agent"):
            await gw.invoke("nonexistent", "hello", "t1")


class TestMemoryFactories:
    def test_create_checkpointer(self):
        from artipivot.memory.checkpointer import create_checkpointer
        cp = create_checkpointer("memory")
        assert cp is not None

    def test_create_checkpointer_invalid(self):
        from artipivot.memory.checkpointer import create_checkpointer
        with pytest.raises(ValueError, match="Unsupported"):
            create_checkpointer("postgres")

    def test_create_store(self):
        from artipivot.memory.store import create_store
        st = create_store("memory")
        assert st is not None

    def test_create_store_invalid(self):
        from artipivot.memory.store import create_store
        with pytest.raises(ValueError, match="Unsupported"):
            create_store("postgres")
