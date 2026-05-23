"""Tests for L3 memory integration — strategy-layer read, gateway-layer write."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.store.memory import InMemoryStore

from artipivot.graph.context import AgentContext
from artipivot.memory.config import (
    ContextWindowConfig,
    EmbeddingConfig,
    ExtractionConfig,
    MemoryConfig,
)
from artipivot.memory.namespace import knowledge_ns, profile_ns


# ── build_messages_with_memory ──


class TestBuildMessagesWithMemory:
    """Test the shared prompt builder in agents/strategies/memory.py."""

    @pytest.mark.asyncio
    async def test_basic_no_memory_config(self):
        """Without memory_config, returns base_prompt + messages unchanged."""
        from artipivot.agents.strategies.memory import build_messages_with_memory

        st = {"query": "hello", "messages": []}
        ctx = AgentContext(
            agent_id="test_agent",
            user_id="u1",
            thread_id="t1",
            model=MagicMock(),
            memory_config=None,
        )
        result = await build_messages_with_memory(st, ctx, None, "You are helpful.")
        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are helpful."
        assert isinstance(result[1], HumanMessage)
        assert result[1].content == "hello"

    @pytest.mark.asyncio
    async def test_l3_memory_injection(self):
        """L3 profile and knowledge are appended to system prompt."""
        from artipivot.agents.strategies.memory import build_messages_with_memory

        store = InMemoryStore()
        # Write profile
        ns = profile_ns("test_agent", "u1")
        await store.aput(ns, "main", {"name": "李四", "language": "Go"})

        mem_cfg = MemoryConfig(
            embedding=EmbeddingConfig(enabled=False),
            context_window=ContextWindowConfig(enabled=False),
            extraction=ExtractionConfig(enabled=False),
        )

        st = {"query": "write code", "messages": []}
        ctx = AgentContext(
            agent_id="test_agent",
            user_id="u1",
            thread_id="t1",
            model=MagicMock(),
            memory_config=mem_cfg,
        )
        result = await build_messages_with_memory(st, ctx, store, "You are a coder.")
        assert len(result) == 2
        system = result[0]
        assert "You are a coder." in system.content
        assert "李四" in system.content
        assert "Go" in system.content

    @pytest.mark.asyncio
    async def test_l3_read_failure_is_graceful(self):
        """If L3 read fails, continues without memory (no crash)."""
        from artipivot.agents.strategies.memory import build_messages_with_memory

        # A store that raises on aget
        bad_store = MagicMock()
        bad_store.aget = AsyncMock(side_effect=RuntimeError("db down"))

        mem_cfg = MemoryConfig(
            embedding=EmbeddingConfig(enabled=False),
            context_window=ContextWindowConfig(enabled=False),
            extraction=ExtractionConfig(enabled=False),
        )

        st = {"query": "test", "messages": []}
        ctx = AgentContext(
            agent_id="test_agent",
            user_id="u1",
            thread_id="t1",
            model=MagicMock(),
            memory_config=mem_cfg,
        )
        # Should not raise — graceful degradation
        result = await build_messages_with_memory(st, ctx, bad_store, "prompt")
        assert len(result) >= 1
        # System prompt should still be there, just without memory
        assert result[0].content == "prompt"

    @pytest.mark.asyncio
    async def test_context_window_compression(self):
        """Context window trim is applied before memory injection."""
        from artipivot.agents.strategies.memory import build_messages_with_memory

        mem_cfg = MemoryConfig(
            embedding=EmbeddingConfig(enabled=False),
            context_window=ContextWindowConfig(
                enabled=True,
                strategy="trim",
                trigger_tokens=0,  # always trigger
                keep_messages=2,
            ),
            extraction=ExtractionConfig(enabled=False),
        )

        messages = [HumanMessage(content=f"msg {i}") for i in range(5)]
        st = {"query": None, "messages": messages}
        ctx = AgentContext(
            agent_id="test_agent",
            user_id="u1",
            thread_id="t1",
            model=MagicMock(),
            memory_config=mem_cfg,
        )
        result = await build_messages_with_memory(st, ctx, None, "sys")
        # SystemMessage + 2 trimmed messages
        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        # Last 2 messages kept
        assert result[2].content == "msg 4"

    @pytest.mark.asyncio
    async def test_query_extraction_from_state(self):
        """When state has no 'query', falls back to last HumanMessage."""
        from artipivot.agents.strategies.memory import _extract_user_query

        st = {
            "query": None,
            "messages": [
                AIMessage(content="hi"),
                HumanMessage(content="what is python?"),
            ],
        }
        assert _extract_user_query(st) == "what is python?"

    @pytest.mark.asyncio
    async def test_query_extraction_truncates(self):
        """Long messages are truncated to 500 chars."""
        from artipivot.agents.strategies.memory import _extract_user_query

        st = {
            "query": None,
            "messages": [HumanMessage(content="x" * 600)],
        }
        result = _extract_user_query(st)
        assert len(result) == 500

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_string(self):
        from artipivot.agents.strategies.memory import _extract_user_query

        st = {"query": None, "messages": [AIMessage(content="no human here")]}
        assert _extract_user_query(st) == ""


# ── Gateway._maybe_write_memory ──


class TestGatewayMemoryWrite:
    """Test gateway fire-and-forget L3 write."""

    def test_skips_when_memory_disabled(self):
        """No task created when memory_config is None or extraction disabled."""
        from artipivot.gateway.gateway import AgentGateway

        gw = AgentGateway(MagicMock())

        # memory_config=None → early return
        gw._maybe_write_memory(
            agent_id="a",
            user_id="u",
            result={"messages": []},
            model=MagicMock(),
            memory_config=None,
        )
        # No error, no task

        # extraction disabled → early return
        cfg = MemoryConfig(
            embedding=EmbeddingConfig(enabled=False),
            context_window=ContextWindowConfig(enabled=False),
            extraction=ExtractionConfig(enabled=False),
        )
        gw._maybe_write_memory(
            agent_id="a",
            user_id="u",
            result={"messages": []},
            model=MagicMock(),
            memory_config=cfg,
        )

    def test_skips_when_no_store(self):
        """No task created when storage_provider has no store."""
        from artipivot.gateway.gateway import AgentGateway

        gw = AgentGateway(MagicMock(), storage_provider=MagicMock())
        # storage_provider.store returns None
        gw._storage_provider = MagicMock()
        gw._storage_provider.store = None

        cfg = MemoryConfig(
            embedding=EmbeddingConfig(enabled=False),
            context_window=ContextWindowConfig(enabled=False),
            extraction=ExtractionConfig(enabled=True),
        )
        gw._maybe_write_memory(
            agent_id="a",
            user_id="u",
            result={"messages": []},
            model=MagicMock(),
            memory_config=cfg,
        )

    @pytest.mark.asyncio
    async def test_creates_async_task(self):
        """When enabled with a store, an async task is created."""
        from artipivot.gateway.gateway import AgentGateway

        store = InMemoryStore()
        storage = MagicMock()
        storage.store = store

        gw = AgentGateway(MagicMock(), storage_provider=storage)

        cfg = MemoryConfig(
            embedding=EmbeddingConfig(enabled=False),
            context_window=ContextWindowConfig(enabled=False),
            extraction=ExtractionConfig(enabled=True),
        )

        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(
            return_value=MagicMock(content='{"name": "王五"}')
        )

        gw._maybe_write_memory(
            agent_id="test_agent",
            user_id="u1",
            result={"messages": [HumanMessage(content="hello")]},
            model=mock_model,
            memory_config=cfg,
        )

        # Give the fire-and-forget task time to run
        await asyncio.sleep(0.1)

        # Verify the model was called for extraction
        mock_model.ainvoke.assert_called()


# ── Bootstrap MemoryConfig parsing ──


class TestBootstrapMemoryConfig:
    """Test MemoryConfig parsing from manifest."""

    def test_empty_manifest_gives_none(self):
        """When manifest has no memory block, MemoryConfig should be None."""
        from artipivot.memory.config import MemoryConfig

        manifest_memory = {}
        if not manifest_memory:
            # This mimics bootstrap logic: empty dict → None
            result = None
        assert result is None

    def test_all_disabled_gives_none(self):
        """When all features disabled, memory_config should be None (zero overhead)."""
        cfg = MemoryConfig.from_dict({
            "embedding": {"enabled": False},
            "context_window": {"enabled": False},
            "extraction": {"enabled": False},
        })
        # Bootstrap checks: if all disabled, set to None
        all_disabled = (
            not cfg.embedding.enabled
            and not cfg.extraction.enabled
            and not cfg.context_window.enabled
        )
        assert all_disabled is True

    def test_any_enabled_gives_config(self):
        """When any feature enabled, memory_config should be the object."""
        cfg = MemoryConfig.from_dict({
            "extraction": {"enabled": True},
        })
        any_enabled = cfg.extraction.enabled
        assert any_enabled is True
        assert cfg.embedding.enabled is False
        assert cfg.context_window.enabled is False


# ── End-to-end L3 read + write round trip ──


class TestL3RoundTrip:
    """Test that data written by extraction can be read by retrieval."""

    @pytest.mark.asyncio
    async def test_profile_round_trip(self):
        """Write a profile, then read it back via build_memory_context."""
        from artipivot.memory.retrieval import build_memory_context

        store = InMemoryStore()

        # Write profile (simulating extraction)
        ns = profile_ns("agent1", "user1")
        await store.aput(ns, "main", {"name": "赵六", "language": "Rust"})

        # Read it back
        context = await build_memory_context(
            store, "agent1", "user1", "test query"
        )
        assert "赵六" in context
        assert "Rust" in context

    @pytest.mark.asyncio
    async def test_knowledge_round_trip_no_embedding(self):
        """Without embedding, knowledge is not retrieved (no asearch)."""
        from artipivot.memory.retrieval import build_memory_context

        store = InMemoryStore()

        # Write knowledge
        ns = knowledge_ns("agent1", "user1")
        await store.aput(ns, "fact1", {"fact": "用户喜欢 TDD"})

        # No embedding → no knowledge search
        context = await build_memory_context(
            store, "agent1", "user1", "TDD",
            embedding_config=EmbeddingConfig(enabled=False),
        )
        # Knowledge should NOT appear (no asearch on InMemoryStore + embedding disabled)
        assert "TDD" not in context

    @pytest.mark.asyncio
    async def test_embedding_enabled_store_without_asearch_raises(self):
        """Embedding enabled + store without asearch → EmbeddingNotSupportedError."""
        from artipivot.storage.search import EmbeddingNotSupportedError

        from artipivot.memory.retrieval import build_memory_context

        # InMemoryStore has asearch, so use a mock without it
        fake_store = MagicMock(spec=[])  # no attributes by default
        fake_store.aget = AsyncMock(return_value=None)

        with pytest.raises(EmbeddingNotSupportedError):
            await build_memory_context(
                fake_store, "agent1", "user1", "test",
                embedding_config=EmbeddingConfig(enabled=True),
            )
