"""Tests for Graph DSL — parsing, validation, building, conditional routing."""

from __future__ import annotations

import pytest

from artipivot.graph.dsl import (
    ConditionDef,
    EdgeDef,
    GraphDef,
    NodeDef,
    build_dsl_graph,
    parse_graph_def,
    validate_graph_def,
)
from artipivot.tools.registry import ToolRegistry
from artipivot.transforms.registry import TransformRegistry


# ── Helpers ──


def _sync_upper(data: dict) -> dict:
    return {k: v.upper() if isinstance(v, str) else v for k, v in data.items()}


def _make_tool_registry():
    """Create a ToolRegistry with stub tools."""
    from langchain_core.tools import tool

    @tool
    def web_search(query: str) -> str:
        """Search the web."""
        return f"results for: {query}"

    @tool
    def code_exec(code: str) -> str:
        """Execute code."""
        return f"executed: {code}"

    reg = ToolRegistry()
    reg.register(web_search)
    reg.register(code_exec)
    return reg


def _make_transform_registry():
    """Create a TransformRegistry with test transforms."""
    reg = TransformRegistry()
    reg.register("upper", _sync_upper)
    return reg


# ── Parsing ──


class TestParseGraphDef:
    def test_minimal_linear(self):
        cfg = {
            "nodes": {
                "step1": {"type": "tool", "tool": "web_search"},
                "step2": {"type": "tool", "tool": "code_exec"},
            },
            "edges": [
                {"from": "START", "to": "step1"},
                {"from": "step1", "to": "step2"},
                {"from": "step2", "to": "END"},
            ],
        }
        gd = parse_graph_def("test", cfg)
        assert gd.name == "test"
        assert len(gd.nodes) == 2
        assert gd.nodes["step1"].type == "tool"
        assert gd.nodes["step1"].tool == "web_search"
        assert len(gd.edges) == 3

    def test_parallel_fan_out(self):
        cfg = {
            "nodes": {
                "search": {"type": "tool", "tool": "web_search"},
                "execute": {"type": "tool", "tool": "code_exec"},
                "merge": {"type": "transform", "handler": "upper"},
            },
            "edges": [
                {"from": "START", "targets": ["search", "execute"]},
                {"from": "search", "to": "merge"},
                {"from": "execute", "to": "merge"},
                {"from": "merge", "to": "END"},
            ],
        }
        gd = parse_graph_def("fan_out", cfg)
        assert len(gd.edges) == 4
        # First edge has targets list
        assert gd.edges[0].targets == ["search", "execute"]

    def test_no_nodes_raises(self):
        with pytest.raises(ValueError, match="nodes"):
            parse_graph_def("bad", {"edges": []})

    def test_empty_nodes_raises(self):
        with pytest.raises(ValueError, match="nodes"):
            parse_graph_def("bad", {"nodes": {}})

    def test_invalid_node_type_raises(self):
        cfg = {
            "nodes": {"step1": {"type": "unknown"}},
            "edges": [{"from": "START", "to": "step1"}],
        }
        with pytest.raises(ValueError, match="invalid type"):
            parse_graph_def("bad", cfg)

    def test_invalid_target_raises(self):
        cfg = {
            "nodes": {"step1": {"type": "tool", "tool": "x"}},
            "edges": [{"from": "START", "to": "nonexistent"}],
        }
        with pytest.raises(ValueError, match="not a defined node"):
            parse_graph_def("bad", cfg)

    def test_missing_to_raises(self):
        cfg = {
            "nodes": {"step1": {"type": "tool", "tool": "x"}},
            "edges": [{"from": "START"}],
        }
        with pytest.raises(ValueError, match="'to' is required"):
            parse_graph_def("bad", cfg)

    def test_node_types(self):
        cfg = {
            "nodes": {
                "llm": {"type": "llm", "system_prompt": "You are helpful"},
                "t": {"type": "tool", "tool": "web_search"},
                "ts": {"type": "tools", "tools": ["web_search"]},
                "tr": {
                    "type": "transform",
                    "handler": "upper",
                    "input_key": "data",
                    "output_key": "result",
                },
                "sa": {"type": "sub_agent", "ref": "other_agent"},
            },
            "edges": [{"from": "START", "to": "llm"}],
        }
        gd = parse_graph_def("all_types", cfg)
        assert gd.nodes["llm"].system_prompt == "You are helpful"
        assert gd.nodes["t"].tool == "web_search"
        assert gd.nodes["ts"].tools == ["web_search"]
        assert gd.nodes["tr"].handler == "upper"
        assert gd.nodes["tr"].input_key == "data"
        assert gd.nodes["tr"].output_key == "result"
        assert gd.nodes["sa"].ref == "other_agent"


# ── Conditional routing parsing ──


class TestParseCondition:
    def test_field_mapping(self):
        cfg = {
            "nodes": {
                "classify": {"type": "llm", "system_prompt": "classify"},
                "search": {"type": "tool", "tool": "web_search"},
                "fallback": {"type": "llm", "system_prompt": "fallback"},
            },
            "edges": [
                {"from": "START", "to": "classify"},
                {
                    "from": "classify",
                    "to": ["search", "fallback"],
                    "condition": {
                        "field": "intent",
                        "mapping": {"search": "search", "_": "fallback"},
                    },
                },
            ],
        }
        gd = parse_graph_def("cond", cfg)
        edge = gd.edges[1]
        assert edge.condition is not None
        assert edge.condition.field == "intent"
        assert edge.condition.mapping == {"search": "search", "_": "fallback"}
        assert edge.targets == ["search", "fallback"]

    def test_builtin_condition(self):
        cfg = {
            "nodes": {
                "llm": {"type": "llm"},
                "tools": {"type": "tools", "tools": ["web_search"]},
            },
            "edges": [
                {"from": "START", "to": "llm"},
                {
                    "from": "llm",
                    "to": ["tools", "END"],
                    "condition": {"builtin": "has_tool_calls"},
                },
            ],
        }
        gd = parse_graph_def("builtin", cfg)
        assert gd.edges[1].condition.builtin == "has_tool_calls"

    def test_transform_condition(self):
        cfg = {
            "nodes": {
                "classify": {"type": "llm"},
                "search": {"type": "tool", "tool": "web_search"},
                "fallback": {"type": "llm"},
            },
            "edges": [
                {"from": "START", "to": "classify"},
                {
                    "from": "classify",
                    "to": ["search", "fallback"],
                    "condition": {"transform": "classify_intent"},
                },
            ],
        }
        gd = parse_graph_def("transform_cond", cfg)
        assert gd.edges[1].condition.transform == "classify_intent"

    def test_invalid_condition_raises(self):
        cfg = {
            "nodes": {"a": {"type": "llm"}, "b": {"type": "llm"}},
            "edges": [
                {"from": "START", "to": "a"},
                {
                    "from": "a",
                    "to": ["b", "END"],
                    "condition": {"unknown_key": "x"},
                },
            ],
        }
        with pytest.raises(ValueError, match="condition must have one of"):
            parse_graph_def("bad", cfg)

    def test_conditional_without_targets_raises(self):
        cfg = {
            "nodes": {"a": {"type": "llm"}, "b": {"type": "llm"}},
            "edges": [
                {"from": "START", "to": "a"},
                {
                    "from": "a",
                    "to": "b",
                    "condition": {"builtin": "has_tool_calls"},
                },
            ],
        }
        with pytest.raises(ValueError, match="conditional edges require"):
            parse_graph_def("bad", cfg)

    def test_field_without_mapping_raises(self):
        cfg = {
            "nodes": {"a": {"type": "llm"}, "b": {"type": "llm"}},
            "edges": [
                {"from": "START", "to": "a"},
                {
                    "from": "a",
                    "to": ["b", "END"],
                    "condition": {"field": "intent"},
                },
            ],
        }
        with pytest.raises(ValueError, match="field mapping requires both"):
            parse_graph_def("bad", cfg)


# ── ConditionDef.make_router ──


class TestConditionRouter:
    def test_field_mapping_router(self):
        from langgraph.graph import END

        cond = ConditionDef(
            field="intent",
            mapping={"search": "search_node", "_": "fallback"},
        )
        router = cond.make_router(targets=["search_node", "fallback"])
        assert router({"intent": "search"}) == "search_node"
        assert router({"intent": "unknown"}) == "fallback"
        assert router({}) == "fallback"

    def test_builtin_has_tool_calls(self):
        from langchain_core.messages import AIMessage
        from langgraph.graph import END

        cond = ConditionDef(builtin="has_tool_calls")
        router = cond.make_router(targets=["tools", END])

        # With tool calls
        msg_with_tc = AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}])
        assert router({"messages": [msg_with_tc]}) == "tools"

        # Without tool calls
        msg_without = AIMessage(content="no tools")
        assert router({"messages": [msg_without]}) == END

    def test_builtin_no_tool_calls(self):
        from langchain_core.messages import AIMessage
        from langgraph.graph import END

        cond = ConditionDef(builtin="no_tool_calls")
        router = cond.make_router(targets=["tools", END])

        msg_with_tc = AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}])
        assert router({"messages": [msg_with_tc]}) == END

        msg_without = AIMessage(content="no tools")
        assert router({"messages": [msg_without]}) == "tools"

    def test_builtin_unknown_raises(self):
        cond = ConditionDef(builtin="nonexistent")
        with pytest.raises(ValueError, match="Unknown builtin"):
            cond.make_router(targets=["a", "b"])

    def test_transform_router(self):
        def classify_fn(state: dict) -> str:
            return "search" if "search" in state.get("query", "") else "fallback"

        treg = TransformRegistry()
        treg.register("classify", classify_fn)

        cond = ConditionDef(transform="classify")
        router = cond.make_router(targets=["search", "fallback"], transform_registry=treg)
        assert router({"query": "search for X"}) == "search"
        assert router({"query": "help me"}) == "fallback"

    def test_transform_router_without_registry_raises(self):
        cond = ConditionDef(transform="classify")
        with pytest.raises(ValueError, match="transform_registry"):
            cond.make_router(targets=["a", "b"])

    def test_no_condition_type_raises(self):
        cond = ConditionDef()
        with pytest.raises(ValueError, match="must have one of"):
            cond.make_router(targets=["a", "b"])


# ── Validation ──


class TestValidateGraphDef:
    def test_all_valid(self):
        gd = GraphDef(
            name="test",
            nodes={"step1": NodeDef(name="step1", type="tool", tool="web_search")},
            edges=[],
        )
        warnings = validate_graph_def(gd, tool_registry=_make_tool_registry())
        assert warnings == []

    def test_missing_tool_warning(self):
        gd = GraphDef(
            name="test",
            nodes={"step1": NodeDef(name="step1", type="tool", tool="nonexistent")},
            edges=[],
        )
        warnings = validate_graph_def(gd, tool_registry=_make_tool_registry())
        assert any("nonexistent" in w for w in warnings)

    def test_missing_transform_warning(self):
        gd = GraphDef(
            name="test",
            nodes={"step1": NodeDef(name="step1", type="transform", handler="missing")},
            edges=[],
        )
        warnings = validate_graph_def(gd, transform_registry=_make_transform_registry())
        assert any("missing" in w for w in warnings)

    def test_missing_sub_agent_warning(self):
        gd = GraphDef(
            name="test",
            nodes={"step1": NodeDef(name="step1", type="sub_agent", ref="ghost")},
            edges=[],
        )
        warnings = validate_graph_def(gd, compiled_sub_agents={})
        assert any("ghost" in w for w in warnings)

    def test_no_registry_no_warnings(self):
        gd = GraphDef(
            name="test",
            nodes={"step1": NodeDef(name="step1", type="tool", tool="x")},
            edges=[],
        )
        # Without registries, validation is a no-op
        assert validate_graph_def(gd) == []


# ── Build ──


class TestBuildDslGraph:
    def test_linear_transform_pipeline(self):
        """START → transform → END"""
        gd = parse_graph_def(
            "linear",
            {
                "nodes": {"step1": {"type": "transform", "handler": "upper"}},
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(
            gd,
            tool_registry=ToolRegistry(),
            transform_registry=_make_transform_registry(),
        )
        assert graph is not None

    @pytest.mark.asyncio
    async def test_transform_execution(self):
        """Build and invoke a transform-only graph."""
        gd = parse_graph_def(
            "tr",
            {
                "nodes": {"upper": {"type": "transform", "handler": "upper"}},
                "edges": [
                    {"from": "START", "to": "upper"},
                    {"from": "upper", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(
            gd,
            tool_registry=ToolRegistry(),
            transform_registry=_make_transform_registry(),
        )
        result = await graph.ainvoke(
            {"messages": [], "query": "", "artifacts": [], "metadata": {"name": "hello"}}
        )
        assert result["metadata"] == {"name": "HELLO"}

    def test_missing_tool_raises(self):
        gd = parse_graph_def(
            "bad_tool",
            {
                "nodes": {"step1": {"type": "tool", "tool": "nonexistent"}},
                "edges": [{"from": "START", "to": "step1"}, {"from": "step1", "to": "END"}],
            },
        )
        with pytest.raises(ValueError, match="not found"):
            build_dsl_graph(
                gd,
                tool_registry=ToolRegistry(),
                transform_registry=TransformRegistry(),
            )

    def test_missing_sub_agent_raises(self):
        gd = parse_graph_def(
            "bad_sub",
            {
                "nodes": {"step1": {"type": "sub_agent", "ref": "ghost"}},
                "edges": [{"from": "START", "to": "step1"}, {"from": "step1", "to": "END"}],
            },
        )
        with pytest.raises(ValueError, match="not found"):
            build_dsl_graph(
                gd,
                tool_registry=ToolRegistry(),
                transform_registry=TransformRegistry(),
            )

    def test_missing_transform_handler_raises(self):
        """build_dsl_graph doesn't validate transforms at build time —
        the node factory delegates to make_transform_node which also
        doesn't raise until execution.  This test confirms that."""
        gd = parse_graph_def(
            "missing_handler",
            {
                "nodes": {"step1": {"type": "transform", "handler": "missing"}},
                "edges": [{"from": "START", "to": "step1"}, {"from": "step1", "to": "END"}],
            },
        )
        # Build succeeds — transform is resolved at execution time
        graph = build_dsl_graph(
            gd,
            tool_registry=ToolRegistry(),
            transform_registry=TransformRegistry(),
        )
        assert graph is not None


# ── Conditional build ──


class TestBuildConditionalGraph:
    @pytest.mark.asyncio
    async def test_field_mapping_routing(self):
        """Build a graph with field-mapping conditional routing."""
        gd = parse_graph_def(
            "field_route",
            {
                "nodes": {
                    "start": {"type": "transform", "handler": "upper"},
                    "search": {"type": "transform", "handler": "upper"},
                    "fallback": {"type": "transform", "handler": "upper"},
                },
                "edges": [
                    {"from": "START", "to": "start"},
                    {
                        "from": "start",
                        "to": ["search", "fallback"],
                        "condition": {
                            "field": "intent",
                            "mapping": {"search": "search", "_": "fallback"},
                        },
                    },
                    {"from": "search", "to": "END"},
                    {"from": "fallback", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(
            gd,
            tool_registry=ToolRegistry(),
            transform_registry=_make_transform_registry(),
        )
        # Route to "search" when intent=search
        result = await graph.ainvoke(
            {
                "messages": [],
                "query": "",
                "artifacts": [],
                "metadata": {"name": "hello"},
                "intent": "search",
            }
        )
        assert result["metadata"] == {"name": "HELLO"}

    @pytest.mark.asyncio
    async def test_builtin_routing(self):
        """Build a graph with has_tool_calls conditional routing."""
        from langchain_core.messages import AIMessage

        treg = _make_transform_registry()

        # Add an identity transform for pass-through
        def identity(data: dict) -> dict:
            return data

        treg.register("identity", identity)

        gd = parse_graph_def(
            "builtin_route",
            {
                "nodes": {
                    "llm": {"type": "transform", "handler": "identity"},
                    "tools": {"type": "transform", "handler": "upper"},
                },
                "edges": [
                    {"from": "START", "to": "llm"},
                    {
                        "from": "llm",
                        "to": ["tools", "END"],
                        "condition": {"builtin": "has_tool_calls"},
                    },
                ],
            },
        )
        graph = build_dsl_graph(
            gd,
            tool_registry=ToolRegistry(),
            transform_registry=treg,
        )

        # Invoke with a message that has tool_calls
        msg_with_tc = AIMessage(
            content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}]
        )
        result = await graph.ainvoke(
            {
                "messages": [msg_with_tc],
                "query": "",
                "artifacts": [],
                "metadata": {"name": "hello"},
            }
        )
        # Should have gone through "tools" node (upper transform)
        assert result["metadata"] == {"name": "HELLO"}

    @pytest.mark.asyncio
    async def test_transform_routing(self):
        """Build a graph with transform-based conditional routing."""
        treg = _make_transform_registry()

        def route_by_query(state: dict) -> str:
            query = state.get("query", "")
            return "search" if "search" in query else "fallback"

        treg.register("route_by_query", route_by_query)

        def identity(data: dict) -> dict:
            return data

        treg.register("identity", identity)

        gd = parse_graph_def(
            "transform_route",
            {
                "nodes": {
                    "start": {"type": "transform", "handler": "identity"},
                    "search": {"type": "transform", "handler": "upper"},
                    "fallback": {"type": "transform", "handler": "identity"},
                },
                "edges": [
                    {"from": "START", "to": "start"},
                    {
                        "from": "start",
                        "to": ["search", "fallback"],
                        "condition": {"transform": "route_by_query"},
                    },
                    {"from": "search", "to": "END"},
                    {"from": "fallback", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(
            gd,
            tool_registry=ToolRegistry(),
            transform_registry=treg,
        )

        # Route to "search" when query contains "search"
        result = await graph.ainvoke(
            {
                "messages": [],
                "query": "search for X",
                "artifacts": [],
                "metadata": {"name": "hello"},
            }
        )
        assert result["metadata"] == {"name": "HELLO"}

        # Route to "fallback"
        result2 = await graph.ainvoke(
            {
                "messages": [],
                "query": "help me",
                "artifacts": [],
                "metadata": {"name": "hello"},
            }
        )
        assert result2["metadata"] == {"name": "hello"}
