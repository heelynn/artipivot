"""Tests for P5 FastAPI server + admin API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from artipivot.api.deps import set_components
from artipivot.api.server import create_app
from artipivot.config.center import ConfigCenter
from artipivot.config.ratelimit import RateLimiter
from artipivot.gateway.gateway import AgentGateway
from artipivot.models.provider import ModelProvider
from artipivot.plugins.manager import PluginManager
from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier
from artipivot.tools.registry import ToolRegistry
from artipivot.transforms.registry import TransformRegistry


@pytest.fixture
def client():
    store = InMemoryDocumentStore()
    notifier = InProcessNotifier()
    provider = ModelProvider(store, notifier)
    config_center = ConfigCenter(store, notifier)
    gateway = AgentGateway(model_provider=provider, config_center=config_center)
    pm = PluginManager(store, notifier)
    rl = RateLimiter(store, notifier)
    tools = ToolRegistry()
    transforms = TransformRegistry()

    set_components(
        gateway=gateway,
        config_center=config_center,
        plugin_manager=pm,
        rate_limiter=rl,
        tool_registry=tools,
        transform_registry=transforms,
    )

    app = create_app()
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_admin_health(self, client):
        resp = client.get("/admin/health")
        assert resp.status_code == 200


class TestChatEndpoint:
    def test_chat_unknown_agent(self, client):
        resp = client.post(
            "/api/v1/chat/unknown_agent",
            json={"message": "hello", "thread_id": "t1", "user_id": "u1"},
        )
        assert resp.status_code == 404

    def test_chat_missing_body(self, client):
        resp = client.post("/api/v1/chat/code_agent")
        assert resp.status_code == 422


class TestAdminPlugins:
    @pytest.mark.asyncio
    async def test_list_plugins(self, client):
        resp = client.get("/admin/plugins")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_publish_and_list(self, client):
        resp = client.post(
            "/admin/plugins",
            json={
                "plugin_type": "sub_agent",
                "name": "writer",
                "version": "1.0",
                "agent_id": "code_agent",
                "manifest": {"strategy": "react", "tools": ["web_search"]},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "published"

        resp = client.get("/admin/plugins")
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_deprecate_nonexistent(self, client):
        resp = client.delete("/admin/plugins/sub_agent/code_agent/nope")
        assert resp.status_code == 404


class TestAdminRouting:
    def test_get_routing(self, client):
        resp = client.get("/admin/routing/code_agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "code_agent"


class TestAdminRateLimits:
    def test_get_ratelimits(self, client):
        resp = client.get("/admin/ratelimits")
        assert resp.status_code == 200
        data = resp.json()
        assert "defaults" in data

    def test_update_agent_ratelimit(self, client):
        resp = client.put(
            "/admin/ratelimits/agent/code_agent",
            json={"scope": "agent", "overrides": {"user_rpm": 30}},
        )
        assert resp.status_code == 200

        resp = client.get("/admin/ratelimits")
        assert resp.json()["agent_overrides"]["code_agent"]["user_rpm"] == 30

    def test_update_tool_ratelimit(self, client):
        resp = client.put(
            "/admin/ratelimits/tool/code_exec",
            json={"scope": "tool", "overrides": {"tool_rpm": 10}},
        )
        assert resp.status_code == 200


class TestAdminTransforms:
    def test_list_transforms_empty(self, client):
        resp = client.get("/admin/transforms")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_register_and_list(self, client):
        resp = client.post(
            "/admin/transforms/register",
            json={"name": "json_loads", "module": "json", "function": "loads"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "registered"
        assert data["name"] == "json_loads"

        resp = client.get("/admin/transforms")
        items = resp.json()
        assert len(items) == 1
        assert items[0]["name"] == "json_loads"
        assert items[0]["source"] == "api"

    def test_register_bad_module_returns_500(self, client):
        resp = client.post(
            "/admin/transforms/register",
            json={
                "name": "bad",
                "module": "nonexistent_module_xyz",
                "function": "nope",
            },
        )
        assert resp.status_code == 500

    def test_unregister(self, client):
        client.post(
            "/admin/transforms/register",
            json={"name": "json_loads", "module": "json", "function": "loads"},
        )
        resp = client.delete("/admin/transforms/json_loads")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unregistered"

    def test_unregister_missing_returns_404(self, client):
        resp = client.delete("/admin/transforms/nope")
        assert resp.status_code == 404
