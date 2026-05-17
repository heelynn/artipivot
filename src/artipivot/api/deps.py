"""Dependency injection — shared component lifecycle for FastAPI."""

from __future__ import annotations

from artipivot.config.center import ConfigCenter
from artipivot.config.ratelimit import RateLimiter
from artipivot.gateway.gateway import AgentGateway
from artipivot.gateway.registry import AgentRegistry
from artipivot.gateway.sub_agent_registry import SubAgentRegistry
from artipivot.graph.factory import GraphFactory
from artipivot.models.provider import ModelProvider
from artipivot.plugins.manager import PluginManager
from artipivot.tools.registry import ToolRegistry
from artipivot.transforms.registry import TransformRegistry

# Module-level singletons — set during init_app()
_gateway: AgentGateway | None = None
_config_center: ConfigCenter | None = None
_plugin_manager: PluginManager | None = None
_rate_limiter: RateLimiter | None = None
_tool_registry: ToolRegistry | None = None
_transform_registry: TransformRegistry | None = None
_agent_registry: AgentRegistry | None = None
_sub_agent_registry: SubAgentRegistry | None = None


def get_gateway() -> AgentGateway:
    if _gateway is None:
        raise RuntimeError("App not initialized — call init_app() first")
    return _gateway


def get_config_center() -> ConfigCenter:
    if _config_center is None:
        raise RuntimeError("App not initialized — call init_app() first")
    return _config_center


def get_plugin_manager() -> PluginManager:
    if _plugin_manager is None:
        raise RuntimeError("App not initialized — call init_app() first")
    return _plugin_manager


def get_rate_limiter() -> RateLimiter:
    if _rate_limiter is None:
        raise RuntimeError("App not initialized — call init_app() first")
    return _rate_limiter


def get_tool_registry() -> ToolRegistry:
    if _tool_registry is None:
        raise RuntimeError("App not initialized — call init_app() first")
    return _tool_registry


def get_transform_registry() -> TransformRegistry:
    if _transform_registry is None:
        raise RuntimeError("App not initialized — call init_app() first")
    return _transform_registry


def get_agent_registry() -> AgentRegistry:
    if _agent_registry is None:
        raise RuntimeError("App not initialized — call init_app() first")
    return _agent_registry


def get_sub_agent_registry() -> SubAgentRegistry:
    if _sub_agent_registry is None:
        raise RuntimeError("App not initialized — call init_app() first")
    return _sub_agent_registry


def set_components(
    *,
    gateway: AgentGateway,
    config_center: ConfigCenter,
    plugin_manager: PluginManager,
    rate_limiter: RateLimiter,
    tool_registry: ToolRegistry,
    transform_registry: TransformRegistry,
    agent_registry: AgentRegistry | None = None,
    sub_agent_registry: SubAgentRegistry | None = None,
) -> None:
    """Set shared components — called during app initialization."""
    global _gateway, _config_center, _plugin_manager, _rate_limiter, _tool_registry, _transform_registry, _agent_registry, _sub_agent_registry
    _gateway = gateway
    _config_center = config_center
    _plugin_manager = plugin_manager
    _rate_limiter = rate_limiter
    _tool_registry = tool_registry
    _transform_registry = transform_registry
    _agent_registry = agent_registry
    _sub_agent_registry = sub_agent_registry
