"""Quickstart API — one-line agent service creation.

Skips the three-layer configuration for simple use cases:

    from artipivot.quickstart import quickstart

    app = quickstart(
        strategy="react",
        tools=["web_search", "code_exec"],
        system_prompt="You are a coding assistant.",
    )
    # uvicorn artipivot.quickstart:app  (or use app.run)
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from artipivot.api.deps import set_components
from artipivot.api.server import create_app
from artipivot.config.center import ConfigCenter
from artipivot.config.ratelimit import RateLimiter
from artipivot.gateway.agent_def import AgentDef
from artipivot.gateway.gateway import AgentGateway
from artipivot.gateway.registry import AgentRegistry
from artipivot.gateway.sub_agent_registry import SubAgentRegistry
from artipivot.graph.factory import GraphFactory
from artipivot.memory.checkpointer import create_checkpointer
from artipivot.memory.store import create_store
from artipivot.models.provider import ModelProvider
from artipivot.plugins.manager import PluginManager
from artipivot.storage.memory import InProcessNotifier
from artipivot.storage.sqlite import SQLiteDocumentStore
from artipivot.tools.builtin.code_exec import code_exec
from artipivot.tools.builtin.file_io import file_io
from artipivot.tools.builtin.web_search import web_search
from artipivot.tools.registry import ToolRegistry

# Built-in tool name → tool instance
_BUILTIN_TOOLS = {
    "web_search": web_search,
    "code_exec": code_exec,
    "file_io": file_io,
}


def quickstart(
    *,
    strategy: str = "react",
    tools: list[str] | None = None,
    system_prompt: str = "",
    agent_id: str = "default",
    model: dict[str, str] | None = None,
    intents: dict[str, str] | None = None,
    checkpointer_backend: str = "memory",
    store_backend: str = "memory",
) -> FastAPI:
    """Create a single-agent FastAPI service with minimal config.

    Args:
        strategy: Sub-agent strategy — "react" or "function_calling".
        tools: List of built-in tool names to register (e.g. ["web_search", "code_exec"]).
        system_prompt: System prompt for the sub-agent.
        agent_id: Agent identifier (default "default").
        model: Model config dict, e.g. {"provider": "anthropic", "name": "claude-sonnet-4-6"}.
            Defaults to {"provider": "openai", "name": "gpt-4o"}.
        intents: Intent-to-sub-agent mapping for routing. If not provided, all messages
            go to the single sub-agent named "assistant".
        checkpointer_backend: Checkpointer backend name (default "memory").
        store_backend: Store backend name (default "memory").

    Returns:
        Configured FastAPI application ready to run.
    """
    import asyncio

    tool_names = tools or []

    # 1. ToolRegistry — register requested built-in tools
    tool_registry = ToolRegistry()
    for name in tool_names:
        t = _BUILTIN_TOOLS.get(name)
        if t is None:
            raise ValueError(
                f"Unknown built-in tool '{name}'. "
                f"Available: {sorted(_BUILTIN_TOOLS)}"
            )
        tool_registry.register(t)

    # 2. Storage
    doc_store = SQLiteDocumentStore()
    notifier = InProcessNotifier()

    # 3. Seed model config
    model_cfg = model or {"provider": "openai", "name": "gpt-4o"}
    _run_async(_seed_config(doc_store, agent_id, model_cfg))

    # 4. Core components
    model_provider = ModelProvider(doc_store, notifier)
    _run_async(model_provider.start())

    config_center = ConfigCenter(doc_store, notifier)
    _run_async(config_center.start())

    # 5. Build AgentDef
    sub_agent_name = "assistant"
    intent_map = intents or {"_default": sub_agent_name}

    agent_def = AgentDef(
        agent_id=agent_id,
        model=model_cfg,
        confidence_threshold=0.5,
        intent_map=intent_map,
        sub_agent_refs=[sub_agent_name],
        tools=tool_names,
        prompts={
            "classify": "Classify the user message into one of: {intents}. Reply in JSON: {\"intent\": \"...\", \"confidence\": 0.0-1.0}",
            "respond": "Based on the sub-agent result, compose a helpful response.",
        },
    )

    # 6. SubAgentRegistry + AgentRegistry
    sub_agent_reg = SubAgentRegistry(tool_registry)
    sub_def = _make_decl_def(sub_agent_name, strategy, tool_names, system_prompt)
    sub_agent_reg.build_and_register(sub_agent_name, sub_def)

    gateway = AgentGateway(model_provider, config_center=config_center)
    graph_factory = GraphFactory(config_center)

    registry = AgentRegistry(
        gateway=gateway,
        graph_factory=graph_factory,
        tool_registry=tool_registry,
        sub_agent_registry=sub_agent_reg,
    )

    checkpointer = create_checkpointer(backend=checkpointer_backend)
    lg_store = create_store(backend=store_backend)
    registry.register_def(agent_def, checkpointer=checkpointer, store=lg_store)

    # 7. Wire up FastAPI deps
    rate_limiter = RateLimiter()
    plugin_manager = PluginManager(store=doc_store, notifier=notifier)

    set_components(
        gateway=gateway,
        config_center=config_center,
        plugin_manager=plugin_manager,
        rate_limiter=rate_limiter,
        tool_registry=tool_registry,
        agent_registry=registry,
        sub_agent_registry=sub_agent_reg,
    )

    return create_app()


# ── Helpers ──


def _make_decl_def(name, strategy, tools, system_prompt):
    from artipivot.agents.declarative import DeclarativeSubAgentDef

    return DeclarativeSubAgentDef(
        name=name,
        strategy=strategy,
        tools=tools,
        system_prompt=system_prompt,
    )


async def _seed_config(store, agent_id, model_cfg):
    await store.put("model_configs", "global", {
        "scope": "global",
        "fallback_model": {"provider": "openai", "name": "gpt-4o"},
    })
    await store.put("model_configs", f"agent:{agent_id}", {
        "scope": "agent",
        "agent_id": agent_id,
        "model": model_cfg,
    })
    await store.put("routing_configs", agent_id, {
        "agent_id": agent_id,
        "intent_map": {"_default": "assistant"},
        "confidence_threshold": 0.5,
    })
    await store.put("prompt_configs", "classify", {
        "_id": "classify",
        "template": "Classify the user message into one of: {intents}. Reply in JSON: {\"intent\": \"...\", \"confidence\": 0.0-1.0}",
    })
    await store.put("prompt_configs", "respond", {
        "_id": "respond",
        "template": "Based on the sub-agent result, compose a helpful response.",
    })


def _run_async(coro):
    """Run an async coroutine in a fresh event loop (thread-safe)."""
    import asyncio
    import concurrent.futures

    result = None
    exc = None

    def _target():
        nonlocal result, exc
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(coro)
        except Exception as e:
            exc = e
        finally:
            loop.close()

    t = concurrent.futures.ThreadPoolExecutor(max_workers=1).submit(_target)
    t.result()  # propagate exceptions
    if exc:
        raise exc
    return result
