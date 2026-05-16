"""Tests for Transform system -- registry, watcher, loader, nodes."""

from __future__ import annotations

import asyncio
import threading

import pytest

from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier
from artipivot.transforms.loader import load_transforms_seed
from artipivot.transforms.nodes import make_transform_node
from artipivot.transforms.registry import TransformRegistry


# ── Helpers ──


def _sync_upper(data: dict) -> dict:
    return {k: v.upper() if isinstance(v, str) else v for k, v in data.items()}


async def _async_enrich(data: dict) -> dict:
    return {**data, "enriched": True}


# ── Registry ──


class TestTransformRegistry:
    def test_register_and_get(self):
        reg = TransformRegistry()
        reg.register("upper", _sync_upper)
        fn = reg.get("upper")
        assert fn is _sync_upper

    def test_get_missing_raises(self):
        reg = TransformRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.get("nope")

    def test_has(self):
        reg = TransformRegistry()
        assert not reg.has("upper")
        reg.register("upper", _sync_upper)
        assert reg.has("upper")

    def test_unregister(self):
        reg = TransformRegistry()
        reg.register("upper", _sync_upper)
        reg.unregister("upper")
        assert not reg.has("upper")

    def test_unregister_missing_raises(self):
        reg = TransformRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nope")

    def test_register_overwrites(self):
        reg = TransformRegistry()
        reg.register("fn", _sync_upper, source="v1")
        reg.register("fn", _sync_upper, source="v2")
        meta = reg.list_transforms()
        assert len(meta) == 1
        assert meta[0]["source"] == "v2"

    def test_list_transforms(self):
        reg = TransformRegistry()
        reg.register("upper", _sync_upper)
        reg.register("enrich", _async_enrich)
        items = reg.list_transforms()
        assert len(items) == 2
        names = {i["name"] for i in items}
        assert names == {"upper", "enrich"}

    def test_metadata_sync(self):
        reg = TransformRegistry()
        reg.register("upper", _sync_upper)
        meta = reg.list_transforms()[0]
        assert meta["is_async"] is False
        assert meta["source"] == "manual"

    def test_metadata_async(self):
        reg = TransformRegistry()
        reg.register("enrich", _async_enrich)
        meta = reg.list_transforms()[0]
        assert meta["is_async"] is True

    def test_names(self):
        reg = TransformRegistry()
        reg.register("a", _sync_upper)
        reg.register("b", _sync_upper)
        assert set(reg.names) == {"a", "b"}

    def test_register_non_callable_raises(self):
        reg = TransformRegistry()
        with pytest.raises(TypeError, match="callable"):
            reg.register("bad", "not_a_function")


class TestTransformRegistryInvoke:
    @pytest.mark.asyncio
    async def test_invoke_sync(self):
        reg = TransformRegistry()
        reg.register("upper", _sync_upper)
        result = await reg.invoke("upper", {"name": "hello"})
        assert result == {"name": "HELLO"}

    @pytest.mark.asyncio
    async def test_invoke_async(self):
        reg = TransformRegistry()
        reg.register("enrich", _async_enrich)
        result = await reg.invoke("enrich", {"x": 1})
        assert result == {"x": 1, "enriched": True}

    @pytest.mark.asyncio
    async def test_invoke_missing_raises(self):
        reg = TransformRegistry()
        with pytest.raises(KeyError):
            await reg.invoke("nope", {})

    @pytest.mark.asyncio
    async def test_invoke_propagates_exception(self):
        reg = TransformRegistry()

        def _boom(data: dict) -> dict:
            raise ValueError("boom")

        reg.register("boom", _boom)
        with pytest.raises(ValueError, match="boom"):
            await reg.invoke("boom", {})


class TestTransformRegistryModule:
    def test_register_module(self):
        reg = TransformRegistry()
        # Register a function from a known stdlib module
        reg.register_module("json_loads", "json", "loads")
        assert reg.has("json_loads")
        fn = reg.get("json_loads")
        assert fn('{"a": 1}') == {"a": 1}

    def test_register_module_bad_module(self):
        reg = TransformRegistry()
        with pytest.raises(ImportError):
            reg.register_module("bad", "nonexistent_module_xyz", "nope")

    def test_register_module_bad_function(self):
        reg = TransformRegistry()
        with pytest.raises(AttributeError):
            reg.register_module("bad", "json", "no_such_function")

    def test_register_module_reload(self):
        reg = TransformRegistry()
        reg.register_module("json_loads", "json", "loads")
        # reload=True should succeed without error
        reg.register_module("json_loads", "json", "loads", reload=True)
        assert reg.has("json_loads")


class TestTransformRegistryThreadSafety:
    def test_concurrent_register_get(self):
        reg = TransformRegistry()
        errors = []

        def writer():
            try:
                for i in range(100):
                    reg.register(f"fn_{i}", _sync_upper)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    try:
                        reg.get(f"fn_{i}")
                    except KeyError:
                        pass
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert not errors


# ── Watcher ──


class TestTransformWatcher:
    @pytest.mark.asyncio
    async def test_watcher_registers_on_upsert(self):
        store = InMemoryDocumentStore()
        notifier = InProcessNotifier()
        registry = TransformRegistry()

        from artipivot.transforms.watcher import TransformWatcher

        watcher = TransformWatcher(notifier, registry)
        await watcher.start()

        await notifier.notify(
            "transform_configs",
            "upper",
            "upsert",
            {"name": "upper", "module": "json", "function": "loads"},
        )

        assert registry.has("upper")

    @pytest.mark.asyncio
    async def test_watcher_unregisters_on_delete(self):
        registry = TransformRegistry()
        registry.register("upper", _sync_upper)

        notifier = InProcessNotifier()
        from artipivot.transforms.watcher import TransformWatcher

        watcher = TransformWatcher(notifier, registry)
        await watcher.start()

        await notifier.notify(
            "transform_configs", "upper", "delete", {"name": "upper"}
        )
        assert not registry.has("upper")

    @pytest.mark.asyncio
    async def test_watcher_ignores_missing_fields(self):
        registry = TransformRegistry()
        notifier = InProcessNotifier()
        from artipivot.transforms.watcher import TransformWatcher

        watcher = TransformWatcher(notifier, registry)
        await watcher.start()

        # Should not raise, just log warning
        await notifier.notify(
            "transform_configs", "bad", "upsert", {"name": "bad"}
        )
        assert not registry.has("bad")

    @pytest.mark.asyncio
    async def test_watcher_handles_bad_module_gracefully(self):
        registry = TransformRegistry()
        notifier = InProcessNotifier()
        from artipivot.transforms.watcher import TransformWatcher

        watcher = TransformWatcher(notifier, registry)
        await watcher.start()

        # Should not raise — ImportError caught and logged
        await notifier.notify(
            "transform_configs",
            "bad",
            "upsert",
            {"name": "bad", "module": "nonexistent_xyz", "function": "nope"},
        )
        assert not registry.has("bad")


# ── Loader ──


class TestTransformLoader:
    def test_load_missing_file(self, tmp_path):
        reg = TransformRegistry()
        result = load_transforms_seed(reg, seed_dir=tmp_path)
        assert result == []

    def test_load_empty_yaml(self, tmp_path):
        (tmp_path / "transforms.yaml").write_text("")
        reg = TransformRegistry()
        result = load_transforms_seed(reg, seed_dir=tmp_path)
        assert result == []

    def test_load_valid_seed(self, tmp_path):
        (tmp_path / "transforms.yaml").write_text(
            "transforms:\n"
            "  json_loads:\n"
            "    module: json\n"
            "    function: loads\n"
        )
        reg = TransformRegistry()
        result = load_transforms_seed(reg, seed_dir=tmp_path)
        assert result == ["json_loads"]
        assert reg.has("json_loads")

    def test_load_skips_bad_transforms(self, tmp_path):
        (tmp_path / "transforms.yaml").write_text(
            "transforms:\n"
            "  good:\n"
            "    module: json\n"
            "    function: loads\n"
            "  bad:\n"
            "    module: nonexistent_xyz\n"
            "    function: nope\n"
        )
        reg = TransformRegistry()
        result = load_transforms_seed(reg, seed_dir=tmp_path)
        assert result == ["good"]
        assert reg.has("good")
        assert not reg.has("bad")


# ── Node ──


class TestTransformNode:
    @pytest.mark.asyncio
    async def test_make_transform_node(self):
        reg = TransformRegistry()
        reg.register("upper", _sync_upper)
        node = make_transform_node("upper", reg)

        state = {"metadata": {"name": "hello"}}
        result = await node(state, runtime=None)
        assert result == {"metadata": {"name": "HELLO"}}

    @pytest.mark.asyncio
    async def test_transform_node_custom_keys(self):
        reg = TransformRegistry()
        reg.register("upper", _sync_upper)
        node = make_transform_node(
            "upper", reg, input_key="input_data", output_key="output_data"
        )

        state = {"input_data": {"name": "hello"}}
        result = await node(state, runtime=None)
        assert result == {"output_data": {"name": "HELLO"}}

    @pytest.mark.asyncio
    async def test_transform_node_async_fn(self):
        reg = TransformRegistry()
        reg.register("enrich", _async_enrich)
        node = make_transform_node("enrich", reg)

        state = {"metadata": {"x": 1}}
        result = await node(state, runtime=None)
        assert result == {"metadata": {"x": 1, "enriched": True}}

    @pytest.mark.asyncio
    async def test_transform_node_hot_reload(self):
        """Verify that replacing a function in registry works without
        rebuilding the node."""
        reg = TransformRegistry()
        reg.register("fn", _sync_upper)
        node = make_transform_node("fn", reg)

        # First invocation
        state = {"metadata": {"name": "hello"}}
        result = await node(state, runtime=None)
        assert result == {"metadata": {"name": "HELLO"}}

        # Hot-reload: replace with a different function
        def _reverse_values(data: dict) -> dict:
            return {k: v[::-1] if isinstance(v, str) else v for k, v in data.items()}

        reg.register("fn", _reverse_values, source="hot_reload")

        # Same node, new behavior
        result = await node(state, runtime=None)
        assert result == {"metadata": {"name": "olleh"}}

    @pytest.mark.asyncio
    async def test_transform_node_missing_raises_value_error(self):
        reg = TransformRegistry()
        node = make_transform_node("missing", reg)

        with pytest.raises(ValueError, match="not registered"):
            await node({"metadata": {}}, runtime=None)

    @pytest.mark.asyncio
    async def test_transform_node_exception_raises_runtime_error(self):
        reg = TransformRegistry()

        def _boom(data: dict) -> dict:
            raise ValueError("boom")

        reg.register("boom", _boom)
        node = make_transform_node("boom", reg)

        with pytest.raises(RuntimeError, match="failed"):
            await node({"metadata": {}}, runtime=None)


# ── Integration: ConfigCenter with TransformWatcher ──


class TestConfigCenterTransforms:
    @pytest.mark.asyncio
    async def test_center_loads_transforms(self):
        store = InMemoryDocumentStore()
        await store.put(
            "transform_configs",
            "upper",
            {"name": "upper", "module": "json", "function": "loads"},
        )

        notifier = InProcessNotifier()
        from artipivot.config.center import ConfigCenter

        cc = ConfigCenter(store, notifier)
        await cc.start()

        assert cc.transforms.has("upper")
