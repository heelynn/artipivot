"""Admin REST API — runtime configuration management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from artipivot.api.deps import get_config_center, get_plugin_manager, get_rate_limiter, get_transform_registry, get_agent_registry, get_gateway, get_sub_agent_registry
from artipivot.config.ratelimit import RateLimiter
from artipivot.plugins.manager import PluginDocument, PluginManager

admin_router = APIRouter()


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


class TransformRegisterDTO(BaseModel):
    name: str
    module: str
    function: str


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
async def publish_plugin(dto: PluginDTO):
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


# ── Transform management ──


@admin_router.get("/transforms")
async def list_transforms():
    tr = get_transform_registry()
    return tr.list_transforms()


@admin_router.post("/transforms/register")
async def register_transform(dto: TransformRegisterDTO):
    tr = get_transform_registry()
    try:
        tr.register_module(dto.name, dto.module, dto.function, source="api")
    except (ImportError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "registered", "name": dto.name}


@admin_router.delete("/transforms/{name}")
async def unregister_transform(name: str):
    tr = get_transform_registry()
    try:
        tr.unregister(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "unregistered", "name": name}


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
async def register_agent(dto: AgentRegisterDTO):
    """Dynamically register a new main agent at runtime."""
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
