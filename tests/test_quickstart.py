"""Tests for quickstart API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from artipivot.quickstart import quickstart


class TestQuickstart:
    """Test quickstart() creates a working FastAPI app."""

    def test_returns_fastapi(self):
        app = quickstart(tools=[])
        assert isinstance(app, FastAPI)

    def test_health_endpoint(self):
        app = quickstart(tools=[])
        # Find the health route
        routes = [r.path for r in app.routes]
        assert "/health" in routes

    def test_chat_route_registered(self):
        app = quickstart(tools=[])
        routes = [r.path for r in app.routes]
        # Should have the chat endpoint for the default agent
        assert any("/api/v1/chat" in r for r in routes)

    def test_admin_route_registered(self):
        app = quickstart(tools=[])
        routes = [r.path for r in app.routes]
        assert any("/admin" in r for r in routes)

    def test_with_tools(self):
        app = quickstart(tools=["web_search"])
        assert isinstance(app, FastAPI)

    def test_with_custom_model(self):
        app = quickstart(
            model={"provider": "anthropic", "name": "claude-sonnet-4-6"},
            tools=[],
        )
        assert isinstance(app, FastAPI)

    def test_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="Unknown built-in tool"):
            quickstart(tools=["nonexistent_tool"])

    def test_custom_agent_id(self):
        app = quickstart(agent_id="my_agent", tools=[])
        assert isinstance(app, FastAPI)

    def test_custom_strategy(self):
        app = quickstart(strategy="react", tools=[])
        assert isinstance(app, FastAPI)

    def test_with_system_prompt(self):
        app = quickstart(
            system_prompt="You are a helpful assistant.",
            tools=[],
        )
        assert isinstance(app, FastAPI)
