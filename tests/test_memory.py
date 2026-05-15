"""Tests for memory system — config, namespace, context window, extraction, retrieval."""

from __future__ import annotations

import pytest

from artipivot.memory.config import (
    ContextWindowConfig,
    EmbeddingConfig,
    MemoryConfig,
)
from artipivot.memory.context_window import ContextWindowManager
from artipivot.memory.namespace import (
    agent_memory_ns,
    knowledge_ns,
    preferences_ns,
    profile_ns,
)


# ── Config ──


class TestEmbeddingConfig:
    def test_defaults_disabled(self):
        cfg = EmbeddingConfig()
        assert cfg.enabled is False
        assert cfg.provider == "openai"
        assert cfg.model == "text-embedding-3-small"
        assert cfg.dims == 1536
        assert cfg.base_url is None
        assert cfg.api_key is None

    def test_enabled_with_custom_url(self):
        cfg = EmbeddingConfig(
            enabled=True,
            base_url="https://api.deepseek.com",
            api_key="sk-test",
        )
        assert cfg.enabled is True
        assert cfg.base_url == "https://api.deepseek.com"


class TestContextWindowConfig:
    def test_defaults(self):
        cfg = ContextWindowConfig()
        assert cfg.strategy == "none"
        assert cfg.trigger_tokens == 100000
        assert cfg.keep_messages == 20

    def test_summarize(self):
        cfg = ContextWindowConfig(strategy="summarize", trigger_tokens=50000)
        assert cfg.strategy == "summarize"
        assert cfg.trigger_tokens == 50000


class TestMemoryConfig:
    def test_from_dict_defaults(self):
        cfg = MemoryConfig.from_dict({})
        assert cfg.embedding.enabled is False
        assert cfg.context_window.strategy == "none"

    def test_from_dict_full(self):
        cfg = MemoryConfig.from_dict({
            "embedding": {
                "enabled": True,
                "provider": "openai",
                "model": "text-embedding-3-large",
                "dims": 3072,
                "base_url": "https://api.custom.com",
                "api_key": "sk-test",
            },
            "context_window": {
                "strategy": "summarize",
                "trigger_tokens": 80000,
                "keep_messages": 10,
                "summary_model": "claude-haiku-4-5-20251001",
            },
        })
        assert cfg.embedding.enabled is True
        assert cfg.embedding.dims == 3072
        assert cfg.embedding.base_url == "https://api.custom.com"
        assert cfg.context_window.strategy == "summarize"
        assert cfg.context_window.keep_messages == 10
        assert cfg.context_window.summary_model == "claude-haiku-4-5-20251001"

    def test_from_dict_partial(self):
        cfg = MemoryConfig.from_dict({
            "embedding": {"enabled": True},
        })
        assert cfg.embedding.enabled is True
        assert cfg.embedding.model == "text-embedding-3-small"  # default
        assert cfg.context_window.strategy == "none"  # default


# ── Namespace ──


class TestNamespace:
    def test_profile_ns(self):
        ns = profile_ns("code_agent", "user_123")
        assert ns == ("code_agent", "user_123", "profile")

    def test_knowledge_ns(self):
        ns = knowledge_ns("code_agent", "user_123")
        assert ns == ("code_agent", "user_123", "knowledge")

    def test_preferences_ns(self):
        ns = preferences_ns("code_agent", "user_123")
        assert ns == ("code_agent", "user_123", "preferences")

    def test_agent_memory_ns(self):
        ns = agent_memory_ns("code_agent", "user_123", "code_writer")
        assert ns == ("code_agent", "user_123", "agent", "code_writer")

    def test_agent_isolation(self):
        ns_a = profile_ns("code_agent", "user_123")
        ns_b = profile_ns("research_agent", "user_123")
        assert ns_a != ns_b


# ── Context Window ──


class TestContextWindowManager:
    def test_none_strategy(self):
        mgr = ContextWindowManager(ContextWindowConfig(strategy="none"))
        # Should always return None
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            mgr.maybe_compress([], None)
        )
        assert result is None

    def test_trim_strategy_short_messages(self):
        mgr = ContextWindowManager(
            ContextWindowConfig(strategy="trim", trigger_tokens=0, keep_messages=3)
        )
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content=f"msg {i}") for i in range(5)]
        result = mgr._trim(messages)
        assert len(result) == 3
        assert result[0].content == "msg 2"

    def test_trim_strategy_within_limit(self):
        mgr = ContextWindowManager(
            ContextWindowConfig(strategy="trim", keep_messages=20)
        )
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content="msg")]
        result = mgr._trim(messages)
        assert len(result) == 1

    def test_estimate_tokens(self):
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content="a" * 400)]
        count = ContextWindowManager._estimate_tokens(messages)
        assert count == 100  # 400 / 4

    def test_no_compress_below_threshold(self):
        mgr = ContextWindowManager(
            ContextWindowConfig(strategy="trim", trigger_tokens=100000, keep_messages=3)
        )
        import asyncio

        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content="short")]
        result = asyncio.get_event_loop().run_until_complete(
            mgr.maybe_compress(messages, None)
        )
        assert result is None


# ── Extraction (unit-level, no LLM call) ──


class TestMemoryExtraction:
    def test_format_messages(self):
        from langchain_core.messages import AIMessage, HumanMessage

        from artipivot.memory.extraction import _format_messages

        messages = [
            HumanMessage(content="hello"),
            AIMessage(content="hi there"),
        ]
        result = _format_messages(messages)
        assert "Human: hello" in result
        assert "AI: hi there" in result

    def test_format_messages_limits_to_10(self):
        from langchain_core.messages import HumanMessage

        from artipivot.memory.extraction import _format_messages

        messages = [HumanMessage(content=f"msg {i}") for i in range(15)]
        result = _format_messages(messages)
        assert "msg 5" in result  # last 10: 5-14
        assert "msg 4" not in result


# ── Retrieval (unit-level) ──


class TestMemoryRetrieval:
    @pytest.mark.asyncio
    async def test_build_memory_context_empty_store(self):
        from langgraph.store.memory import InMemoryStore

        from artipivot.memory.retrieval import build_memory_context

        store = InMemoryStore()
        result = await build_memory_context(store, "code_agent", "user_123", "test query")
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_memory_context_with_profile(self):
        from langgraph.store.memory import InMemoryStore

        from artipivot.memory.namespace import profile_ns
        from artipivot.memory.retrieval import build_memory_context

        store = InMemoryStore()
        ns = profile_ns("code_agent", "user_123")
        await store.aput(ns, "main", {"name": "张三", "language": "Python"})

        result = await build_memory_context(store, "code_agent", "user_123", "test")
        assert "张三" in result
        assert "Python" in result
