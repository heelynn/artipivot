"""Admin REST API — runtime configuration management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from artipivot.api.deps import (
    get_config_center, get_plugin_manager, get_rate_limiter,
    get_agent_registry, get_gateway, get_sub_agent_registry,
    get_tool_reloader, get_storage_provider,
)
from artipivot.config.ratelimit import RateLimiter
from artipivot.plugins.manager import PluginDocument, PluginManager

admin_router = APIRouter()


# ── Helpers ──


async def _parse_yaml_or_json(request: Request) -> dict:
    """Parse request body as YAML or JSON (auto-detect).

    Supports Content-Type: application/json, application/x-yaml, text/yaml.
    Falls back to YAML if content type is not JSON.
    """
    import yaml

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")

    content_type = request.headers.get("content-type", "")

    if "json" in content_type:
        import json
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    # Default: parse as YAML
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

    if data is None:
        raise HTTPException(status_code=400, detail="Empty request body")
    return data


# ── DTOs ──


class PluginDTO(BaseModel):
    plugin_type: str
    name: str
    version: str
    agent_id: str
    manifest: dict = {}


class RateLimitDTO(BaseModel):
    scope: str = "agent"
    agent_id: str | None = None
    tool_name: str | None = None
    overrides: dict = {}


class ToolDTO(BaseModel):
    name: str
    type: str = "builtin"
    module: str | None = None
    function: str | None = None
    config: dict = {}
    status: str = "active"


class SubAgentDTO(BaseModel):
    name: str
    strategy: str = "react"
    tools: list[str] = []
    system_prompt: str = ""
    strategy_config: dict = {}
    graph: dict | None = None
    status: str = "active"


class UserModelDTO(BaseModel):
    provider: str
    name: str
    temperature: float = 0.0
    timeout: int = 120
    max_tokens: int | None = None
    base_url: str | None = None
    api_key: str | None = None


# ── Health ──


@admin_router.get("/health")
async def admin_health():
    return {"status": "ok"}


# ── Plugin management ──


@admin_router.get("/plugins")
async def list_plugins(
    agent_id: str | None = None,
    plugin_type: str | None = None,
    status: str | None = "active",
):
    pm = get_plugin_manager()
    plugins = await pm.list_plugins(
        agent_id=agent_id, plugin_type=plugin_type, status=status
    )
    return [p.to_dict() for p in plugins]


@admin_router.post("/plugins")
async def publish_plugin(request: Request):
    body = await _parse_yaml_or_json(request)
    dto = PluginDTO(**body)
    pm = get_plugin_manager()
    plugin = PluginDocument(
        plugin_type=dto.plugin_type,
        name=dto.name,
        version=dto.version,
        agent_id=dto.agent_id,
        manifest=dto.manifest,
    )
    await pm.publish(plugin)
    return {"status": "published", "key": plugin.key}


@admin_router.delete("/plugins/{plugin_type}/{agent_id}/{name}")
async def deprecate_plugin(plugin_type: str, agent_id: str, name: str):
    pm = get_plugin_manager()
    try:
        await pm.deprecate(plugin_type, name, agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deprecated"}


# ── Model management ──


@admin_router.get("/models/{agent_id}")
async def get_model_config(agent_id: str):
    cc = get_config_center()
    # Model config is stored in DocumentStore, read via ConfigCenter
    return {"agent_id": agent_id, "note": "model config managed by ModelProvider"}


# ── User-level model management ──


@admin_router.put("/models/user/{user_id}/agent/{agent_id}")
async def set_user_model(user_id: str, agent_id: str, dto: UserModelDTO):
    """Set user-level model config for a specific agent."""
    gw = get_gateway()
    await gw._model_provider.update_user_model(
        user_id=user_id,
        model=dto.model_dump(exclude_none=True),
        agent_id=agent_id,
    )
    return {"status": "updated", "user_id": user_id, "agent_id": agent_id}


@admin_router.put("/models/user/{user_id}")
async def set_user_global_model(user_id: str, dto: UserModelDTO):
    """Set user-level model config (applies to all agents without specific config)."""
    gw = get_gateway()
    await gw._model_provider.update_user_model(
        user_id=user_id,
        model=dto.model_dump(exclude_none=True),
    )
    return {"status": "updated", "user_id": user_id, "scope": "global"}


@admin_router.get("/models/user/{user_id}")
async def get_user_models(user_id: str):
    """List all model configs for a user."""
    gw = get_gateway()
    mp = gw._model_provider
    result = {}
    with mp._lock:
        for key, cfg in mp._user_models.items():
            parts = key.split(":", 1)
            agent_id = parts[0] if parts[0] != "__global__" else None
            if parts[1] == user_id:
                result[agent_id or "__global__"] = {
                    "provider": cfg.provider,
                    "name": cfg.name,
                }
    return {"user_id": user_id, "models": result}


@admin_router.delete("/models/user/{user_id}/agent/{agent_id}")
async def delete_user_model(user_id: str, agent_id: str):
    """Remove user-level model config for a specific agent."""
    gw = get_gateway()
    await gw._model_provider.delete_user_model(user_id=user_id, agent_id=agent_id)
    return {"status": "deleted", "user_id": user_id, "agent_id": agent_id}


# ── Routing management ──


@admin_router.get("/routing/{agent_id}")
async def get_routing(agent_id: str):
    cc = get_config_center()
    intent_map = cc.routing.get_intent_map(agent_id)
    threshold = cc.routing.get_threshold(agent_id)
    return {
        "agent_id": agent_id,
        "confidence_threshold": threshold,
        "intents": intent_map,
    }


# ── Rate limit management ──


@admin_router.get("/ratelimits")
async def get_ratelimits():
    rl = get_rate_limiter()
    return {
        "defaults": rl.config.defaults,
        "agent_overrides": rl.config.agent_overrides,
        "tool_overrides": rl.config.tool_overrides,
    }


@admin_router.put("/ratelimits/agent/{agent_id}")
async def update_agent_ratelimit(agent_id: str, dto: RateLimitDTO):
    rl = get_rate_limiter()
    rl.config.agent_overrides[agent_id] = dto.overrides
    return {"status": "updated", "agent_id": agent_id}


@admin_router.put("/ratelimits/tool/{tool_name}")
async def update_tool_ratelimit(tool_name: str, dto: RateLimitDTO):
    rl = get_rate_limiter()
    rl.config.tool_overrides[tool_name] = dto.overrides
    return {"status": "updated", "tool_name": tool_name}


# ── Graph visualization ──


@admin_router.get("/graph/{agent_id}/mermaid")
async def get_graph_mermaid(agent_id: str):
    """Get Mermaid flowchart for the agent's DSL graph."""
    from artipivot.graph.visual import graph_to_mermaid

    registry = get_agent_registry()
    agent_def = registry.get_def(agent_id)
    if agent_def is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    if not agent_def.graph_sub_agents:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' has no DSL graph sub-agents",
        )

    # Return all graph sub-agents as Mermaid
    diagrams = {}
    for name, gd in agent_def.graph_sub_agents.items():
        diagrams[name] = graph_to_mermaid(gd)

    return {"agent_id": agent_id, "graphs": diagrams}


@admin_router.get("/graph/{agent_id}/structure")
async def get_graph_structure(agent_id: str):
    """Get GraphDef structure (JSON) for the agent's DSL graph."""
    registry = get_agent_registry()
    agent_def = registry.get_def(agent_id)
    if agent_def is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    if not agent_def.graph_sub_agents:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' has no DSL graph sub-agents",
        )

    return {"agent_id": agent_id, "graphs": agent_def.to_dict().get("graph_sub_agents", {})}


# ── Dynamic agent registration ──


class AgentRegisterDTO(BaseModel):
    agent_id: str
    model: dict = {}
    sub_agent_refs: list[str] = []
    routing: dict = {}  # {"intents": {...}, "confidence_threshold": 0.7}
    tools: list[str] = []
    prompts: dict[str, str] = {}


@admin_router.post("/agents")
async def register_agent(request: Request):
    """Dynamically register a new main agent at runtime. Accepts YAML or JSON."""
    body = await _parse_yaml_or_json(request)
    dto = AgentRegisterDTO(**body)
    from artipivot.gateway.agent_def import AgentDef

    registry = get_agent_registry()
    if registry.get_def(dto.agent_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{dto.agent_id}' already registered",
        )

    routing = dto.routing
    intent_map = routing.get("intents", {})
    confidence_threshold = routing.get("confidence_threshold", 0.7)

    agent_def = AgentDef(
        agent_id=dto.agent_id,
        model=dto.model,
        confidence_threshold=confidence_threshold,
        intent_map=intent_map,
        sub_agent_refs=dto.sub_agent_refs,
        tools=dto.tools,
        prompts=dto.prompts,
    )

    try:
        registry.register_def(agent_def)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "registered", "agent_id": dto.agent_id}


@admin_router.get("/agents")
async def list_agents():
    """List all registered main agents."""
    registry = get_agent_registry()
    agent_ids = registry.list_agents()
    return {"agents": agent_ids}


@admin_router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent definition."""
    registry = get_agent_registry()
    agent_def = registry.get_def(agent_id)
    if agent_def is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent_def.to_dict()


# ── Tools CRUD ──


@admin_router.get("/tools")
async def list_tools():
    """List all registered tools (name, type, module, status)."""
    from artipivot.api.deps import get_tool_registry
    tools = get_tool_registry()
    sp = get_storage_provider()
    store = sp.document_store
    records = await store.query("tools", {})
    # Merge with in-memory registry to show stub status
    result = []
    seen = set()
    for record in records:
        name = record.get("name", "")
        seen.add(name)
        in_registry = tools.get(name) is not None
        result.append({
            "name": name,
            "type": record.get("type", "builtin"),
            "module": record.get("module"),
            "function": record.get("function"),
            "status": record.get("status", "active"),
            "is_stub": not in_registry,
        })
    # Include tools in registry but not in store (builtins)
    for name in tools.names:
        if name not in seen:
            result.append({
                "name": name,
                "type": "builtin",
                "module": None,
                "function": None,
                "status": "active",
                "is_stub": False,
            })
    return result


@admin_router.post("/tools")
async def create_tool(request: Request):
    """Register or update a single tool record. Accepts YAML or JSON body.

    YAML example:
        name: baidu_search
        type: module
        module: my_pkg.tools.search
        function: baidu_search

    Writing triggers ChangeNotifier → ToolWatcher → ToolReloader → graph rebuild.
    """
    body = await _parse_yaml_or_json(request)
    dto = ToolDTO(**body)

    sp = get_storage_provider()
    store = sp.document_store
    notifier = sp.change_notifier

    data = dto.model_dump()
    await store.put("tools", dto.name, data)
    await notifier.notify("tools", dto.name, "upsert", data)

    return {"status": "registered", "name": dto.name}


@admin_router.delete("/tools/{name}")
async def delete_tool(name: str):
    """Delete a tool record from DocumentStore."""
    sp = get_storage_provider()
    store = sp.document_store
    notifier = sp.change_notifier

    existing = await store.get("tools", name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")

    await store.delete("tools", name)
    await notifier.notify("tools", name, "delete", {"name": name})

    return {"status": "deleted", "name": name}


# ── Sub-Agents CRUD ──


@admin_router.get("/sub-agents")
async def list_sub_agents():
    """List all sub-agent records from DocumentStore."""
    sp = get_storage_provider()
    store = sp.document_store
    records = await store.query("sub_agents", {})
    return [
        {
            "name": r.get("name"),
            "strategy": r.get("strategy", "react"),
            "tools": r.get("tools", []),
            "system_prompt": r.get("system_prompt", ""),
            "status": r.get("status", "active"),
        }
        for r in records
    ]


@admin_router.post("/sub-agents")
async def create_sub_agent(request: Request):
    """Write a sub-agent record. Accepts YAML or JSON body.

    YAML example:
        name: code_writer
        strategy: react
        tools:
          - web_search
          - code_exec
        system_prompt: You are a coding assistant.

    Writing triggers ChangeNotifier — PluginWatcher rebuilds affected agents.
    """
    body = await _parse_yaml_or_json(request)
    dto = SubAgentDTO(**body)

    sp = get_storage_provider()
    store = sp.document_store
    notifier = sp.change_notifier

    data = dto.model_dump()
    await store.put("sub_agents", dto.name, data)
    await notifier.notify("sub_agents", dto.name, "upsert", data)

    return {"status": "registered", "name": dto.name}


@admin_router.delete("/sub-agents/{name}")
async def delete_sub_agent(name: str):
    """Delete a sub-agent record from DocumentStore."""
    sp = get_storage_provider()
    store = sp.document_store
    notifier = sp.change_notifier

    existing = await store.get("sub_agents", name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Sub-agent '{name}' not found")

    await store.delete("sub_agents", name)
    await notifier.notify("sub_agents", name, "delete", {"name": name})

    return {"status": "deleted", "name": name}


# ── Circuit Breaker ──


@admin_router.get("/agents/{agent_id}/circuit")
async def get_circuit_status(agent_id: str):
    """Get circuit breaker status for an agent's LLM providers."""
    registry = get_agent_registry()
    agent_def = registry.get_def(agent_id)
    if agent_def is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    from artipivot.models.provider import ModelProvider
    # Read circuit state from the ModelProvider's circuit registry
    # For now return the config — runtime state requires CircuitRegistry access
    return {
        "agent_id": agent_id,
        "circuit": {
            "enabled": agent_def.circuit.enabled,
            "failure_threshold": agent_def.circuit.failure_threshold,
            "recovery_timeout": agent_def.circuit.recovery_timeout,
        },
    }


@admin_router.post("/agents/{agent_id}/circuit")
async def update_circuit_config(agent_id: str, request: Request):
    """Update circuit breaker config for an agent (hot-reload, no graph rebuild)."""
    registry = get_agent_registry()
    agent_def = registry.get_def(agent_id)
    if agent_def is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    body = await _parse_yaml_or_json(request)
    if "enabled" in body:
        agent_def.circuit.enabled = body["enabled"]
    if "failure_threshold" in body:
        agent_def.circuit.failure_threshold = body["failure_threshold"]
    if "recovery_timeout" in body:
        agent_def.circuit.recovery_timeout = body["recovery_timeout"]

    # Push updated config to ModelProvider
    from artipivot.api.deps import get_gateway
    gw = get_gateway()
    if gw and hasattr(gw._model_provider, "set_circuit_config"):
        gw._model_provider.set_circuit_config(agent_id, agent_def.circuit)

    return {"status": "updated", "agent_id": agent_id, "circuit": {
        "enabled": agent_def.circuit.enabled,
        "failure_threshold": agent_def.circuit.failure_threshold,
        "recovery_timeout": agent_def.circuit.recovery_timeout,
    }}
