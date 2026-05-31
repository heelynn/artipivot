"""Admin REST API — runtime configuration management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from artipivot.api.deps import (
    get_config_center, get_config_service, get_plugin_manager,
    get_rate_limiter, get_agent_registry, get_gateway,
    get_sub_agent_registry, get_tool_reloader, get_storage_provider,
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
    """Update agent rate limit override. Write + notify, subscriber applies."""
    sp = get_storage_provider()
    key = f"agent:{agent_id}"
    data = {"scope": "agent", "agent_id": agent_id, "overrides": dto.overrides}
    await sp.document_store.put("ratelimit_configs", key, data)
    await sp.change_notifier.notify("ratelimit_configs", key, "upsert", data)
    return {"status": "updated", "agent_id": agent_id}


@admin_router.put("/ratelimits/tool/{tool_name}")
async def update_tool_ratelimit(tool_name: str, dto: RateLimitDTO):
    """Update tool rate limit override. Write + notify, subscriber applies."""
    sp = get_storage_provider()
    key = f"tool:{tool_name}"
    data = {"scope": "tool", "tool_name": tool_name, "overrides": dto.overrides}
    await sp.document_store.put("ratelimit_configs", key, data)
    await sp.change_notifier.notify("ratelimit_configs", key, "upsert", data)
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


    # ── Agent management (ConfigService-backed) ──


class AgentRegisterDTO(BaseModel):
    agent_id: str
    model: dict = {}
    sub_agent_refs: list[str] = []
    routing: dict = {}
    tools: list[str] = []
    prompts: dict[str, str] = {}


@admin_router.post("/agents")
async def register_agent(request: Request):
    """Register a new agent. Writes to DocumentStore + notifies subscribers.

    All in-memory updates happen via subscriber callbacks, not direct mutation.
    """
    body = await _parse_yaml_or_json(request)
    dto = AgentRegisterDTO(**body)
    from artipivot.gateway.agent_def import AgentDef

    cs = get_config_service()
    existing = await cs.get_agent(dto.agent_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Agent '{dto.agent_id}' already registered")

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

    # 1. Write routing_configs first — ConfigCenter subscribes to this
    if intent_map:
        sp = get_storage_provider()
        routing_data = {
            "agent_id": dto.agent_id,
            "confidence_threshold": confidence_threshold,
            "intent_map": intent_map,
        }
        await sp.document_store.put("routing_configs", dto.agent_id, routing_data)
        await sp.change_notifier.notify("routing_configs", dto.agent_id, "upsert", routing_data)

    # 2. Write prompt_configs if present
    if dto.prompts:
        sp = get_storage_provider()
        for node_name, template in dto.prompts.items():
            key = f"{dto.agent_id}:{node_name}"
            prompt_data = {"_id": key, "agent_id": dto.agent_id, "node": node_name, "template": template}
            await sp.document_store.put("prompt_configs", key, prompt_data)
            await sp.change_notifier.notify("prompt_configs", key, "upsert", prompt_data)

    # 3. Persist agent + notify (cs.save_agent calls notify internally)
    agent_data = agent_def.to_dict()
    await cs.save_agent(dto.agent_id, agent_data)

    # 4. Register in-memory: subscriber _on_agent_change handles this.
    #    With InProcessNotifier, it already ran synchronously inside notify().
    #    With PollingChangeNotifier, trigger it explicitly so the agent is
    #    available immediately in this process.
    registry = get_agent_registry()
    agent_rec = await cs.get_agent(dto.agent_id)
    if agent_rec is not None:
        try:
            reloaded = AgentDef.from_dict(agent_rec)
            registry.register_def(reloaded)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"status": "registered", "agent_id": dto.agent_id}


@admin_router.get("/agents")
async def list_agents():
    """List all agents from ConfigService + in-memory registry."""
    cs = get_config_service()
    ids = set(await cs.list_agents())
    registry = get_agent_registry()
    for aid in registry.list_agents():
        ids.add(aid)
    return {"agents": sorted(ids)}


@admin_router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent — ConfigService first, fallback to in-memory."""
    cs = get_config_service()
    data = await cs.get_agent(agent_id)
    if data is not None:
        return data

    registry = get_agent_registry()
    agent_def = registry.get_def(agent_id)
    if agent_def is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent_def.to_dict()


class AgentUpdateDTO(BaseModel):
    model: dict | None = None
    confidence_threshold: float | None = None
    intent_map: dict | None = None  # str→str or str→{target,description}
    prompts: dict[str, str] | None = None
    tools: list[str] | None = None
    sub_agent_refs: list | None = None  # list of str | dict
    default_responses: dict | None = None  # {"clarify": "...", "fallback": "..."}
    circuit: dict | None = None
    memory: dict | None = None


@admin_router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, dto: AgentUpdateDTO):
    """Update agent config. Persists via ConfigService + hot-reloads memory."""
    registry = get_agent_registry()
    agent_def = registry.get_def(agent_id)

    updates = {}
    if dto.model is not None:
        updates["model"] = dto.model
    if dto.confidence_threshold is not None:
        updates["confidence_threshold"] = dto.confidence_threshold
    if dto.intent_map is not None:
        updates["intent_map"] = dto.intent_map
    if dto.prompts is not None:
        updates["prompts"] = dto.prompts
    if dto.tools is not None:
        updates["tools"] = dto.tools
    if dto.sub_agent_refs is not None:
        updates["sub_agent_refs"] = dto.sub_agent_refs
    if dto.circuit is not None:
        updates["circuit"] = dto.circuit
    if dto.memory is not None:
        updates["memory"] = dto.memory
    if dto.default_responses is not None:
        updates["default_responses"] = dto.default_responses

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Write routing_configs if intent_map changed (activates ConfigCenter subscription)
    if dto.intent_map is not None:
        sp = get_storage_provider()
        routing_data = {
            "agent_id": agent_id,
            "confidence_threshold": dto.confidence_threshold or 0.7,
            "intent_map": dto.intent_map,
        }
        await sp.document_store.put("routing_configs", agent_id, routing_data)
        await sp.change_notifier.notify("routing_configs", agent_id, "upsert", routing_data)

    # Write prompt_configs if prompts changed
    if dto.prompts is not None:
        sp = get_storage_provider()
        for node_name, template in dto.prompts.items():
            key = f"{agent_id}:{node_name}"
            prompt_data = {"_id": key, "agent_id": agent_id, "node": node_name, "template": template}
            await sp.document_store.put("prompt_configs", key, prompt_data)
            await sp.change_notifier.notify("prompt_configs", key, "upsert", prompt_data)

    # Persist + notify via ConfigService (subscriber _on_agent_change rebuilds)
    cs = get_config_service()
    try:
        updated = await cs.update_agent_fields(agent_id, updates)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"status": "updated", "agent_id": agent_id, "fields": list(updated)}


@admin_router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent. ConfigService notifies subscribers for cluster sync."""
    cs = get_config_service()
    try:
        await cs.delete_agent(agent_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Remove from in-memory immediately (subscriber _on_agent_change also does this)
    registry = get_agent_registry()
    registry.remove_def(agent_id)

    return {"status": "deleted", "agent_id": agent_id}


# ── Tools CRUD ──


@admin_router.get("/tools")
async def list_tools():
    """List all tools — DocumentStore records + in-memory registry."""
    from artipivot.api.deps import get_tool_registry
    cs = get_config_service()
    records = await cs.list_tools()
    tools = get_tool_registry()

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
            "config": record.get("config", {}),
            "status": record.get("status", "active"),
            "is_stub": not in_registry,
        })
    for name in tools.names:
        if name not in seen:
            result.append({
                "name": name,
                "type": "builtin",
                "module": None,
                "function": None,
                "config": {},
                "status": "active",
                "is_stub": False,
            })
    return result


@admin_router.post("/tools")
async def create_tool(request: Request):
    """Register or update a tool record. Accepts YAML or JSON."""
    body = await _parse_yaml_or_json(request)
    dto = ToolDTO(**body)
    cs = get_config_service()
    await cs.save_tool(dto.name, dto.model_dump())
    return {"status": "registered", "name": dto.name}


@admin_router.delete("/tools/{name}")
async def delete_tool(name: str):
    """Delete a tool record."""
    cs = get_config_service()
    try:
        await cs.delete_tool(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deleted", "name": name}


# ── Sub-Agents CRUD ──


@admin_router.get("/sub-agents")
async def list_sub_agents():
    """List all sub-agent records."""
    cs = get_config_service()
    return await cs.list_sub_agents()


@admin_router.post("/sub-agents")
async def create_sub_agent(request: Request):
    """Write a sub-agent record. Accepts YAML or JSON.

    YAML example:
        name: code_writer
        strategy: react
        tools:
          - web_search
          - code_exec
        system_prompt: You are a coding assistant.
    """
    body = await _parse_yaml_or_json(request)
    dto = SubAgentDTO(**body)
    cs = get_config_service()
    await cs.save_sub_agent(dto.name, dto.model_dump())
    return {"status": "registered", "name": dto.name}


@admin_router.delete("/sub-agents/{name}")
async def delete_sub_agent(name: str):
    """Delete a sub-agent record."""
    cs = get_config_service()
    try:
        await cs.delete_sub_agent(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deleted", "name": name}


# ── Circuit Breaker ──


@admin_router.get("/agents/{agent_id}/circuit")
async def get_circuit_status(agent_id: str):
    """Get circuit breaker status. Checks in-memory first, then ConfigService."""
    registry = get_agent_registry()
    agent_def = registry.get_def(agent_id)
    if agent_def is not None:
        return {
            "agent_id": agent_id,
            "circuit": {
                "enabled": agent_def.circuit.enabled,
                "failure_threshold": agent_def.circuit.failure_threshold,
                "recovery_timeout": agent_def.circuit.recovery_timeout,
            },
        }
    cs = get_config_service()
    data = await cs.get_agent_circuit(agent_id)
    if data is not None:
        return data
    raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


@admin_router.post("/agents/{agent_id}/circuit")
async def update_circuit_config(agent_id: str, request: Request):
    """Update circuit breaker config. Write + notify, subscriber rebuilds."""
    body = await _parse_yaml_or_json(request)
    cs = get_config_service()
    try:
        await cs.update_agent_fields(agent_id, {"circuit": body})
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "updated", "agent_id": agent_id, "circuit": body}


# ── Runtime observation (read-only) ──


@admin_router.get("/runtime/tools")
async def list_runtime_tools():
    """List tools currently loaded in the in-memory ToolRegistry."""
    from artipivot.api.deps import get_tool_registry
    tools = get_tool_registry()
    result = []
    for name in tools.names:
        tool = tools.get(name)
        result.append({
            "name": name,
            "type": "builtin",
            "description": tool.description if tool else "",
        })
    return result


@admin_router.get("/runtime/sub-agents")
async def list_runtime_sub_agents():
    """List sub-agents currently loaded in the in-memory SubAgentRegistry."""
    from artipivot.api.deps import get_sub_agent_registry
    sar = get_sub_agent_registry()
    result = []
    for name in sar.list_sub_agents():
        defn = sar.get_def(name)
        strategy = ""
        tools_list: list[str] = []
        system_prompt = ""
        strategy_config = {}
        if hasattr(defn, "strategy"):
            strategy = defn.strategy
        if hasattr(defn, "tools"):
            tools_list = defn.tools
        if hasattr(defn, "system_prompt"):
            system_prompt = defn.system_prompt
        if hasattr(defn, "strategy_config"):
            strategy_config = defn.strategy_config
        result.append({
            "name": name,
            "strategy": strategy or "dsl",
            "tools": tools_list,
            "system_prompt": system_prompt,
            "strategy_config": strategy_config,
        })
    return result


