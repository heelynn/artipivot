"""Admin REST API — runtime configuration management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from artipivot.api.deps import get_config_center, get_plugin_manager, get_rate_limiter
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
