"""Bootstrap — one-call initialization for CLI server startup.

Loads .env, reads agents.yaml directly into AgentManifest, initializes all
components, builds agents, and returns a ready-to-serve FastAPI app.

No DocumentStore round-trip — YAML is the source of truth on every startup.

Usage:
    from artipivot.bootstrap import bootstrap

    app = await bootstrap()
    # uvicorn artipivot.bootstrap:bootstrap_sync --factory
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import structlog

from artipivot.api.deps import set_components
from artipivot.api.server import create_app
from artipivot.config.center import ConfigCenter
from artipivot.config.ratelimit import RateLimiter
from artipivot.gateway.agent_def import AgentDef
from artipivot.gateway.gateway import AgentGateway
from artipivot.gateway.loader import AgentManifest, load_agent_manifest
from artipivot.gateway.registry import AgentRegistry
from artipivot.gateway.sub_agent_registry import SubAgentRegistry
from artipivot.graph.factory import GraphFactory
from artipivot.memory.config import MemoryConfig
from artipivot.models.provider import ModelProvider
from artipivot.observability.logging import configure_logging
from artipivot.plugins.manager import PluginManager
from artipivot.storage.provider import StorageConfig, StorageProvider
from artipivot.tools.registry import ToolRegistry


_log = structlog.get_logger("artipivot")


async def bootstrap(
    *,
    manifest_path: str | None = None,
    env_file: str | None = ".env",
    log_dir: str | None = None,
    log_level: str | None = None,
    log_format: str | None = None,
    register_builtin_tools: bool = True,
) -> "FastAPI":
    """Full initialization — load .env, parse YAML, create components, build agents.

    Returns a fully configured FastAPI application ready to serve.

    Args:
        manifest_path: Path to agents YAML file. Default: ``ARTIPIVOT_AGENTS_MANIFEST``
            env var, or ``.agents.yaml`` in the current directory.
            Can be a file path or a directory (looks for ``agents.yaml`` inside).
        env_file: Path to .env file (None to skip).
        log_dir: Directory for log files. Default: ARTIPIVOT_LOG_DIR env or "logs".
        log_level: Log level override. Default: ARTIPIVOT_LOG_LEVEL env or "INFO".
        log_format: Log format — "json" or "text". Default: ARTIPIVOT_LOG_FORMAT env or "json".
        register_builtin_tools: Whether to pre-register built-in tool stubs.

    Returns:
        FastAPI application.
    """
    from fastapi import FastAPI

    # ── 1. Load .env ────────────────────────────────────────────
    if env_file is not None:
        _load_dotenv(env_file)

    # Resolve manifest path: explicit arg > env var > default
    if manifest_path is None:
        manifest_path = os.environ.get(
            "ARTIPIVOT_AGENTS_MANIFEST", ".agents.yaml"
        )

    # ── 2. Logging ──────────────────────────────────────────────
    configure_logging(log_dir=log_dir, level=log_level, log_format=log_format)

    # ── 3. Load manifest from YAML directly ─────────────────────
    manifest = load_agent_manifest(manifest_path)
    if manifest.agents:
        _log.info(
            "bootstrap.manifest_loaded",
            manifest_path=manifest_path,
            agents=list(manifest.agents.keys()),
            tools=[t.name for t in manifest.tools],
            sub_agents=[s.name for s in manifest.sub_agents],
        )

    # ── 4. StorageProvider — 技术决策，从 .env 读取 ───────────
    storage_mode = os.environ.get("ARTIPIVOT_STORAGE_MODE", "memory")
    storage_config = StorageConfig(mode=storage_mode)
    storage = StorageProvider(storage_config)
    await storage.setup()

    _log.info("bootstrap.storage_ready", mode=storage_config.mode)

    # ── 4b. MemoryConfig from manifest ──
    memory_config = MemoryConfig.from_dict(manifest.memory) if manifest.memory else None
    if memory_config and (
        memory_config.extraction.enabled
        or memory_config.embedding.enabled
        or memory_config.context_window.enabled
    ):
        _log.info("bootstrap.memory_enabled", extraction=memory_config.extraction.enabled)
    else:
        memory_config = None  # All disabled → None (zero overhead)

    # ── 5. ModelProvider — populate from manifest ───────────────
    from artipivot.resilience.circuit_breaker import CircuitRegistry

    circuit_registry = CircuitRegistry()
    model_provider = ModelProvider(
        storage.document_store,
        storage.change_notifier,
        circuit_registry=circuit_registry,
    )
    model_provider.load_from_manifest(manifest)
    await model_provider.start()

    # ── 6. ConfigCenter — populate from manifest ────────────────
    config_center = ConfigCenter(
        storage.document_store,
        storage.change_notifier,
    )
    config_center.load_from_manifest(manifest)
    await config_center.start()

    # ── 7. ToolRegistry — from YAML (CLI) or DocumentStore ─────
    tool_registry = ToolRegistry()
    if manifest.tools:
        # CLI / YAML mode: load tools directly from manifest
        tool_registry.register_from_manifest(
            manifest.tools, include_builtins=register_builtin_tools,
        )
        _log.info("bootstrap.tools_from_yaml", count=len(tool_registry.names))
    else:
        # Server mode: load from DocumentStore (may be empty)
        await tool_registry.load_from_store(
            storage.document_store,
            include_builtins=register_builtin_tools,
        )
        _log.info("bootstrap.tools_from_store", count=len(tool_registry.names))

    # ── 8. SubAgentRegistry — from YAML (CLI) or DocumentStore ──
    sub_agent_registry = SubAgentRegistry(
        tool_registry,
        model_provider=model_provider,
    )
    if manifest.sub_agents:
        # CLI / YAML mode: build sub-agents directly from manifest
        for sd in manifest.sub_agents:
            from artipivot.agents.declarative import (
                DeclarativeSubAgentDef,
                build_declarative_subagent,
            )
            if sd.graph:
                from artipivot.graph.dsl import parse_graph_def, build_dsl_graph
                gd = parse_graph_def(sd.name, sd.graph)
                graph = build_dsl_graph(
                    gd,
                    tool_registry=tool_registry,
                    model_provider=model_provider,
                )
                sub_agent_registry.register(sd.name, graph)
            else:
                defn = DeclarativeSubAgentDef(
                    name=sd.name,
                    strategy=sd.strategy,
                    tools=sd.tools,
                    system_prompt=sd.system_prompt,
                    strategy_config=sd.strategy_config,
                )
                tool_node = tool_registry.get_tool_node(sd.tools)
                graph = build_declarative_subagent(defn, tool_node)
                sub_agent_registry.register(sd.name, graph, defn=defn)
        _log.info("bootstrap.sub_agents_from_yaml", count=len(manifest.sub_agents))
    else:
        # Server mode: load from DocumentStore (may be empty)
        await sub_agent_registry.load_from_store(storage.document_store)
        _log.info("bootstrap.sub_agents_from_store")

    # Also register any inline sub-agents from agent definitions
    sub_agent_registry.register_from_manifest(manifest.agents)

    _log.info("bootstrap.sub_agents_built", count=len(sub_agent_registry.list_sub_agents()))

    # ── 9. Gateway + GraphFactory + AgentRegistry ───────────────
    # L2/L3 controlled by memory_config
    checkpointer = storage.checkpointer if memory_config and memory_config.l2 else None
    lg_store = storage.store if memory_config and memory_config.l3 else None

    gateway = AgentGateway(
        model_provider,
        config_center=config_center,
        storage_provider=storage,
    )
    graph_factory = GraphFactory(config_center)

    agent_registry = AgentRegistry(
        gateway=gateway,
        graph_factory=graph_factory,
        tool_registry=tool_registry,
        model_provider=model_provider,
        sub_agent_registry=sub_agent_registry,
    )

    for agent_def in manifest.agents.values():
        try:
            agent_registry.register_def(
                agent_def,
                checkpointer=checkpointer,
                store=lg_store,
            )
        except Exception:
            _log.error(
                "bootstrap.agent_register_failed",
                agent_id=agent_def.agent_id,
                exc_info=True,
            )

    _log.info("bootstrap.agents_registered", agents=agent_registry.list_agents())

    # ── 9b. ToolReloader + ToolWatcher ──────────────────────────
    from artipivot.tools.reloader import ToolReloader
    from artipivot.tools.watcher import ToolWatcher

    tool_reloader = ToolReloader(
        gateway=gateway,
        tool_registry=tool_registry,
        agent_registry=agent_registry,
        store=lg_store,
        checkpointer=checkpointer,
    )
    tool_watcher = ToolWatcher(storage.change_notifier, tool_reloader)
    await tool_watcher.start()
    _log.info("bootstrap.tool_watcher_started")

    # ── 10. RateLimiter + PluginManager ─────────────────────────
    rate_limiter = RateLimiter()
    plugin_manager = PluginManager(
        store=storage.document_store,
        notifier=storage.change_notifier,
    )

    # ── 11. Wire up FastAPI dependencies ────────────────────────
    set_components(
        gateway=gateway,
        config_center=config_center,
        plugin_manager=plugin_manager,
        rate_limiter=rate_limiter,
        tool_registry=tool_registry,
        agent_registry=agent_registry,
        sub_agent_registry=sub_agent_registry,
        storage_provider=storage,
        tool_reloader=tool_reloader,
        memory_config=memory_config,
    )

    return create_app()


# ── Helpers ──


def _load_dotenv(env_file: str) -> None:
    """Load .env file if it exists."""
    env_path = Path(env_file)
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("\"'")
            if key not in os.environ:
                os.environ[key] = val


# ── Sync wrapper for uvicorn factory ──


def bootstrap_sync(
    *,
    manifest_path: str | None = None,
    env_file: str | None = ".env",
    log_dir: str | None = None,
    log_level: str | None = None,
    log_format: str | None = None,
    register_builtin_tools: bool = True,
):
    """Synchronous wrapper for bootstrap — usable as uvicorn factory.

        uvicorn artipivot.bootstrap:bootstrap_sync --factory
    """
    return asyncio.run(bootstrap(
        manifest_path=manifest_path,
        env_file=env_file,
        log_dir=log_dir,
        log_level=log_level,
        log_format=log_format,
        register_builtin_tools=register_builtin_tools,
    ))
