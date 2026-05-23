"""Tests for P4 plugin system + hot rebuild."""

from __future__ import annotations

import pytest

from artipivot.plugins.manager import PluginDocument, PluginManager
from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier


# ── Step 31: StorageBundle ──


class TestStorageBundle:
    def test_default_config_creates_all(self):
        from artipivot.storage.bundle import StorageBundle, StorageConfig

        bundle = StorageBundle(StorageConfig())
        assert bundle.document_store is not None
        assert bundle.change_notifier is not None

    def test_custom_options(self):
        from artipivot.storage.bundle import StorageBundle, StorageConfig

        bundle = StorageBundle(StorageConfig(mode="memory"))
        assert bundle.document_store is not None

    def test_persistent_mode_without_registration(self):
        from artipivot.storage.bundle import StorageBundle, StorageConfig

        bundle = StorageBundle(StorageConfig(mode="persistent"))
        # Without registering a persistent factory, backends gracefully return None
        assert bundle.document_store is None

    def test_from_config(self):
        from artipivot.storage.bundle import StorageBundle, StorageConfig

        bundle = StorageBundle.from_config(StorageConfig())
        assert isinstance(bundle, StorageBundle)


# ── Step 32: PluginManager ──


class TestPluginDocument:
    def test_to_dict_roundtrip(self):
        p = PluginDocument(
            plugin_type="sub_agent",
            name="writer",
            version="1.0",
            agent_id="code_agent",
            manifest={"strategy": "react", "tools": ["web_search"]},
        )
        d = p.to_dict()
        p2 = PluginDocument.from_dict(d)
        assert p2.plugin_type == "sub_agent"
        assert p2.name == "writer"
        assert p2.manifest["strategy"] == "react"

    def test_key_format(self):
        p = PluginDocument(
            plugin_type="sub_agent", name="writer",
            version="1.0", agent_id="code_agent", manifest={},
        )
        assert p.key == "sub_agent:code_agent:writer"


class TestPluginManager:
    @pytest.fixture
    def pm(self):
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        return PluginManager(store, notifier)

    @pytest.mark.asyncio
    async def test_publish_and_get(self, pm):
        plugin = PluginDocument(
            plugin_type="sub_agent", name="writer",
            version="1.0", agent_id="code_agent",
            manifest={"strategy": "react", "tools": ["web_search"]},
        )
        await pm.publish(plugin)

        result = await pm.get_plugin("sub_agent", "writer", "code_agent")
        assert result is not None
        assert result.name == "writer"
        assert result.version == "1.0"
        assert result.status == "active"
        assert result.created_at != ""

    @pytest.mark.asyncio
    async def test_list_plugins_filter(self, pm):
        p1 = PluginDocument(
            plugin_type="sub_agent", name="writer",
            version="1.0", agent_id="code_agent", manifest={},
        )
        p2 = PluginDocument(
            plugin_type="sub_agent", name="searcher",
            version="1.0", agent_id="research_agent", manifest={},
        )
        await pm.publish(p1)
        await pm.publish(p2)

        # Filter by agent_id
        result = await pm.list_plugins(agent_id="code_agent")
        assert len(result) == 1
        assert result[0].name == "writer"

        # Filter by plugin_type
        result = await pm.list_plugins(plugin_type="sub_agent")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_deprecate(self, pm):
        plugin = PluginDocument(
            plugin_type="sub_agent", name="writer",
            version="1.0", agent_id="code_agent", manifest={},
        )
        await pm.publish(plugin)
        await pm.deprecate("sub_agent", "writer", "code_agent")

        # Deprecated plugins not in default list
        result = await pm.list_plugins(agent_id="code_agent", status="active")
        assert len(result) == 0

        # But visible with status=deprecated
        result = await pm.list_plugins(agent_id="code_agent", status="deprecated")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_deprecate_unknown_raises(self, pm):
        with pytest.raises(ValueError, match="Plugin not found"):
            await pm.deprecate("sub_agent", "unknown", "code_agent")

    @pytest.mark.asyncio
    async def test_publish_notifies(self, pm):
        """Publishing a plugin triggers ChangeNotifier."""
        received = []

        async def on_change(collection, key, action, data):
            received.append((collection, action, data.get("name")))

        notifier = pm._notifier
        await notifier.subscribe("plugins", on_change)

        plugin = PluginDocument(
            plugin_type="sub_agent", name="writer",
            version="1.0", agent_id="code_agent", manifest={},
        )
        await pm.publish(plugin)

        assert len(received) == 1
        assert received[0] == ("plugins", "upsert", "writer")

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, pm):
        result = await pm.get_plugin("sub_agent", "unknown", "code_agent")
        assert result is None


# ── Step 34: PluginWatcher ──


class TestPluginWatcher:
    @pytest.mark.asyncio
    async def test_watcher_triggers_rebuild(self):
        from artipivot.plugins.watcher import PluginWatcher
        from artipivot.plugins.rebuilder import GraphRebuilder

        notifier = InProcessNotifier()

        # Mock rebuilder to track calls
        rebuild_calls = []

        class MockRebuilder:
            async def rebuild_agent(self, agent_id, **kwargs):
                rebuild_calls.append(agent_id)

        watcher = PluginWatcher(notifier, MockRebuilder())
        await watcher.start()

        # Simulate a plugin change notification
        await notifier.notify("plugins", "sub_agent:code_agent:writer", "upsert", {
            "agent_id": "code_agent",
            "name": "writer",
        })

        assert rebuild_calls == ["code_agent"]

    @pytest.mark.asyncio
    async def test_watcher_ignores_no_agent_id(self):
        from artipivot.plugins.watcher import PluginWatcher

        notifier = InProcessNotifier()
        rebuild_calls = []

        class MockRebuilder:
            async def rebuild_agent(self, agent_id, **kwargs):
                rebuild_calls.append(agent_id)

        watcher = PluginWatcher(notifier, MockRebuilder())
        await watcher.start()

        # Notification without agent_id — should be ignored
        await notifier.notify("plugins", "some_key", "upsert", {"name": "x"})

        assert rebuild_calls == []


# ── Step 35: ConfigCenter dynamic routing callback ──


class TestConfigCenterDynamic:
    @pytest.mark.asyncio
    async def test_routing_change_callback(self):
        from artipivot.config.center import ConfigCenter

        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()

        callbacks = []

        async def on_routing(collection, key, action, data):
            callbacks.append(data.get("agent_id"))

        cc = ConfigCenter(store, notifier, on_routing_change=on_routing)
        await cc.start()

        # Simulate routing change
        await notifier.notify("routing_configs", "code_agent", "update", {
            "agent_id": "code_agent",
            "confidence_threshold": 0.8,
            "intents": [],
        })

        assert callbacks == ["code_agent"]
        # ConfigCenter should also have updated its internal state
        assert cc.routing.get_threshold("code_agent") == 0.8

    @pytest.mark.asyncio
    async def test_prompt_change_no_rebuild(self):
        """Prompt changes should NOT trigger routing callback."""
        from artipivot.config.center import ConfigCenter

        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()

        callbacks = []

        async def on_routing(collection, key, action, data):
            callbacks.append("called")

        cc = ConfigCenter(store, notifier, on_routing_change=on_routing)
        await cc.start()

        # Simulate prompt change — should NOT call on_routing_change
        await notifier.notify("prompt_configs", "code_agent:classify", "update", {
            "agent_id": "code_agent",
            "system": "new prompt",
        })

        assert callbacks == []


# ── Step 36: Hot rebuild integration ──


class TestHotRebuild:
    def _setup(self):
        from artipivot.config.center import ConfigCenter
        from artipivot.gateway.gateway import AgentGateway
        from artipivot.graph.factory import GraphFactory
        from artipivot.models.provider import ModelProvider
        from artipivot.plugins.manager import PluginManager
        from artipivot.plugins.rebuilder import GraphRebuilder
        from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier
        from artipivot.tools.registry import ToolRegistry
        from artipivot.tools.builtin.web_search import web_search

        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        provider = ModelProvider(store, notifier)
        config_center = ConfigCenter(store, notifier)
        gateway = AgentGateway(model_provider=provider, config_center=config_center)
        factory = GraphFactory(config_center)
        tools = ToolRegistry()
        tools.register(web_search)
        pm = PluginManager(store, notifier)
        rebuilder = GraphRebuilder(gateway, factory, tools, pm)

        return gateway, rebuilder, pm, notifier

    @pytest.mark.asyncio
    async def test_rebuild_replaces_graph(self):
        gw, rebuilder, pm, notifier = self._setup()

        # Initially no agents
        assert "code_agent" not in gw._graphs

        # Publish a plugin and rebuild
        plugin = PluginDocument(
            plugin_type="sub_agent", name="writer",
            version="1.0", agent_id="code_agent",
            manifest={"strategy": "react", "tools": ["web_search"]},
        )
        await pm.publish(plugin)
        await rebuilder.rebuild_agent("code_agent")

        # Now agent should be registered
        assert "code_agent" in gw._graphs

    @pytest.mark.asyncio
    async def test_rebuild_isolation(self):
        """Rebuilding one agent doesn't affect another."""
        gw, rebuilder, pm, notifier = self._setup()

        # Register two agents
        for agent_id, sub_name in [("agent_a", "sa"), ("agent_b", "sb")]:
            plugin = PluginDocument(
                plugin_type="sub_agent", name=sub_name,
                version="1.0", agent_id=agent_id,
                manifest={"tools": ["web_search"]},
            )
            await pm.publish(plugin)
            await rebuilder.rebuild_agent(agent_id)

        graph_a = gw._graphs["agent_a"]
        graph_b = gw._graphs["agent_b"]

        # Rebuild agent_a
        await rebuilder.rebuild_agent("agent_a")

        # agent_a's graph should be replaced
        assert gw._graphs["agent_a"] is not graph_a
        # agent_b's graph should be unchanged
        assert gw._graphs["agent_b"] is graph_b

    @pytest.mark.asyncio
    async def test_watcher_end_to_end(self):
        """Publish plugin → watcher → rebuild → agent available."""
        from artipivot.plugins.watcher import PluginWatcher

        gw, rebuilder, pm, notifier = self._setup()

        watcher = PluginWatcher(notifier, rebuilder)
        await watcher.start()
        await notifier.start()

        # Publish triggers notify → watcher → rebuild
        plugin = PluginDocument(
            plugin_type="sub_agent", name="writer",
            version="1.0", agent_id="code_agent",
            manifest={"strategy": "react", "tools": ["web_search"]},
        )
        await pm.publish(plugin)

        # Agent should now be registered via watcher
        assert "code_agent" in gw._graphs
