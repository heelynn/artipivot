"""Bootstrap — one-call initialization for CLI server startup.

Loads .env, reads global model + memory config from YAML, loads all
agents/tools/sub-agents from DocumentStore (DB), and returns a ready app.

DocumentStore (SQLite) is the source of truth for agents, tools, sub-agents.

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

    # ── 7. ToolRegistry — always from DocumentStore ────────────
    tool_registry = ToolRegistry()
    await tool_registry.load_from_store(
        storage.document_store,
        include_builtins=register_builtin_tools,
    )
    _log.info("bootstrap.tools_from_store", count=len(tool_registry.names))

    # ── 8. SubAgentRegistry — always from DocumentStore ────────
    sub_agent_registry = SubAgentRegistry(
        tool_registry,
        model_provider=model_provider,
    )
    await sub_agent_registry.load_from_store(storage.document_store)
    _log.info("bootstrap.sub_agents_from_store")

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

    # ── 9a. Load agents from DocumentStore ────────────────────────
    agent_records = await storage.document_store.query("agents", {})
    agents_from_db: dict[str, AgentDef] = {}
    for data in agent_records:
        try:
            agent_def = AgentDef.from_dict(data)
            agents_from_db[agent_def.agent_id] = agent_def
        except Exception:
            _log.error(
                "bootstrap.agent_parse_failed",
                data=data,
                exc_info=True,
            )

    _log.info("bootstrap.agents_from_store", count=len(agents_from_db))

    # Register inline sub-agents from agent definitions
    sub_agent_registry.register_from_manifest(agents_from_db)
    _log.info("bootstrap.sub_agents_built", count=len(sub_agent_registry.list_sub_agents()))

    for agent_def in agents_from_db.values():
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

    # ── 9c. ConfigWatcher — hot-reload agents/tools/sub-agents on change ──
    async def _on_agent_change(
        collection: str, key: str, action: str, data: dict
    ) -> None:
        """Rebuild a single agent when its config changes.

        Reloads the agent from DocumentStore (includes inline sub-agent
        definitions that may have changed), re-registers with updated AgentDef,
        and triggers graph rebuild.
        """
        agent_id = data.get("agent_id") or key
        if not agent_id or action == "delete":
            return
        _log.info("config_watcher.agent_changed", agent_id=agent_id)

        # Reload agent from DB — this is the source of truth including
        # inline sub-agent definitions stored in sub_agent_refs
        agent_data = await storage.document_store.get("agents", agent_id)
        if agent_data is not None:
            try:
                agent_def = AgentDef.from_dict(agent_data)
                # Register the updated definitions (updates SubAgentRegistry)
                sub_agent_registry.register_from_manifest({agent_id: agent_def})
                # Re-register with updated AgentDef + rebuild graph
                agent_registry._defs[agent_id] = agent_def
                await agent_registry.rebuild_agent(agent_id, checkpointer=checkpointer, store=lg_store)
            except Exception:
                _log.error("config_watcher.rebuild_failed", agent_id=agent_id, exc_info=True)
        else:
            _log.warning("config_watcher.agent_not_in_db", agent_id=agent_id)

    async def _on_sub_agent_change(
        collection: str, key: str, action: str, data: dict
    ) -> None:
        """Reload sub-agents into registry, rebuild affected agents."""
        name = data.get("name") or key
        if not name:
            return
        _log.info("config_watcher.sub_agent_changed", name=name, action=action)
        await sub_agent_registry.load_from_store(storage.document_store)
        # Rebuild agents that reference the changed sub-agent
        for aid in agent_registry.list_agents():
            agent_def = agent_registry.get_def(aid)
            if agent_def and name in agent_def.sub_agent_refs:
                try:
                    await agent_registry.rebuild_agent(aid, checkpointer=checkpointer, store=lg_store)
                except Exception:
                    _log.error("config_watcher.rebuild_failed", agent_id=aid, exc_info=True)

    await storage.change_notifier.subscribe("agents", _on_agent_change)
    await storage.change_notifier.subscribe("sub_agents", _on_sub_agent_change)
    _log.info("bootstrap.config_watcher_started")

    # ── 10. ConfigService ───────────────────────────────────────
    from artipivot.config.service import ConfigService

    config_service = ConfigService(storage.document_store, storage.change_notifier)

    # ── 11. RateLimiter + PluginManager ─────────────────────────
    rate_limiter = RateLimiter()
    plugin_manager = PluginManager(
        store=storage.document_store,
        notifier=storage.change_notifier,
    )

    # ── 12. Wire up FastAPI dependencies ────────────────────────
    set_components(
        gateway=gateway,
        config_center=config_center,
        config_service=config_service,
        plugin_manager=plugin_manager,
        rate_limiter=rate_limiter,
        tool_registry=tool_registry,
        agent_registry=agent_registry,
        sub_agent_registry=sub_agent_registry,
        storage_provider=storage,
        tool_reloader=tool_reloader,
        memory_config=memory_config,
    )

    app = create_app()

    # ── 13. Restart PollingChangeNotifier in uvicorn event loop ──
    # Polling tasks were created in asyncio.run() loop which dies on return.
    # Restart in the FastAPI lifespan so tasks run in uvicorn's loop.
    if hasattr(storage.change_notifier, "start"):
        @app.on_event("startup")
        async def _restart_notifier():
            await storage.change_notifier.start()
            _log.info("bootstrap.notifier_restarted_in_uvicorn")

    return app


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
