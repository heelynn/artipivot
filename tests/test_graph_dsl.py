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


# ── Helpers ──


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
                "llm_node": {"type": "llm", "system_prompt": "You are helpful"},
            },
            "edges": [
                {"from": "START", "targets": ["search", "execute"]},
                {"from": "search", "to": "llm_node"},
                {"from": "execute", "to": "llm_node"},
                {"from": "llm_node", "to": "END"},
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
                "sa": {"type": "sub_agent", "ref": "other_agent"},
            },
            "edges": [{"from": "START", "to": "llm"}],
        }
        gd = parse_graph_def("all_types", cfg)
        assert gd.nodes["llm"].system_prompt == "You are helpful"
        assert gd.nodes["t"].tool == "web_search"
        assert gd.nodes["ts"].tools == ["web_search"]
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
    def test_linear_tool_pipeline(self):
        """START → tool → END"""
        gd = parse_graph_def(
            "linear",
            {
                "nodes": {"step1": {"type": "tool", "tool": "web_search"}},
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(
            gd,
            tool_registry=_make_tool_registry(),
        )
        assert graph is not None

    def test_missing_tool_auto_stubs(self):
        """Missing tool auto-stubs instead of crashing."""
        gd = parse_graph_def(
            "missing_tool",
            {
                "nodes": {"step1": {"type": "tool", "tool": "nonexistent"}},
                "edges": [{"from": "START", "to": "step1"}, {"from": "step1", "to": "END"}],
            },
        )
        # Build succeeds — missing tool gets a stub
        graph = build_dsl_graph(
            gd,
            tool_registry=ToolRegistry(),
        )
        assert graph is not None

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
            )


# ── Conditional build ──


class TestBuildConditionalGraph:
    def test_field_mapping_graph_builds(self):
        """Build a graph with field-mapping conditional routing."""
        gd = parse_graph_def(
            "field_route",
            {
                "nodes": {
                    "start": {"type": "tool", "tool": "web_search"},
                    "search": {"type": "tool", "tool": "web_search"},
                    "fallback": {"type": "tool", "tool": "code_exec"},
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
            tool_registry=_make_tool_registry(),
        )
        assert graph is not None

    def test_builtin_graph_builds(self):
        """Build a graph with has_tool_calls conditional routing."""
        gd = parse_graph_def(
            "builtin_route",
            {
                "nodes": {
                    "llm": {"type": "llm", "system_prompt": "You are helpful"},
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
            },
        )
        graph = build_dsl_graph(
            gd,
            tool_registry=_make_tool_registry(),
        )
        assert graph is not None


# ── Human-in-the-loop ──


class TestInterruptParsing:
    def test_parse_interrupt_before(self):
        gd = parse_graph_def(
            "hitl",
            {
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                    "review": {"type": "llm", "interrupt": "before"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "review"},
                    {"from": "review", "to": "END"},
                ],
            },
        )
        assert gd.nodes["review"].interrupt == "before"
        assert gd.nodes["step1"].interrupt is None

    def test_parse_interrupt_after(self):
        gd = parse_graph_def(
            "hitl",
            {
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                    "review": {"type": "llm", "interrupt": "after"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "review"},
                    {"from": "review", "to": "END"},
                ],
            },
        )
        assert gd.nodes["review"].interrupt == "after"

    def test_invalid_interrupt_raises(self):
        with pytest.raises(ValueError, match="invalid interrupt"):
            parse_graph_def(
                "bad",
                {
                    "nodes": {"step1": {"type": "llm", "interrupt": "invalid"}},
                    "edges": [{"from": "START", "to": "step1"}],
                },
            )


class TestInterruptBuild:
    def test_build_with_checkpointer_and_interrupt(self):
        """Build a graph with checkpointer + interrupt, verify compilation succeeds."""
        from langgraph.checkpoint.memory import MemorySaver

        gd = parse_graph_def(
            "hitl",
            {
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                    "review": {"type": "tool", "tool": "code_exec", "interrupt": "before"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "review"},
                    {"from": "review", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(
            gd,
            tool_registry=_make_tool_registry(),
            checkpointer=MemorySaver(),
        )
        assert graph is not None

    def test_build_without_checkpointer_no_interrupt(self):
        """Without checkpointer, build succeeds for non-interrupt nodes."""
        treg = _make_tool_registry()
        gd = parse_graph_def(
            "no_cp",
            {
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(
            gd,
            tool_registry=treg,
        )
        assert graph is not None


# ── P1: max_iterations ──


class TestMaxIterationsParsing:
    """Test max_iterations field parsing."""

    def test_parse_max_iterations(self):
        gd = parse_graph_def(
            "loop",
            {
                "max_iterations": 15,
                "nodes": {
                    "think": {"type": "llm"},
                    "act": {"type": "tool", "tool": "web_search"},
                },
                "edges": [
                    {"from": "START", "to": "think"},
                    {"from": "think", "to": "act"},
                    {"from": "act", "to": "END"},
                ],
            },
        )
        assert gd.max_iterations == 15

    def test_parse_no_max_iterations(self):
        gd = parse_graph_def(
            "no_limit",
            {
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "END"},
                ],
            },
        )
        assert gd.max_iterations is None

    def test_invalid_max_iterations_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            parse_graph_def(
                "bad",
                {
                    "max_iterations": 0,
                    "nodes": {"s": {"type": "llm"}},
                    "edges": [{"from": "START", "to": "s"}, {"from": "s", "to": "END"}],
                },
            )

    def test_negative_max_iterations_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            parse_graph_def(
                "neg",
                {
                    "max_iterations": -1,
                    "nodes": {"s": {"type": "llm"}},
                    "edges": [{"from": "START", "to": "s"}, {"from": "s", "to": "END"}],
                },
            )


class TestMaxIterationsBuild:
    """Test max_iterations is stored on compiled graph for config injection."""

    def test_max_iterations_attribute(self):
        gd = parse_graph_def(
            "limited",
            {
                "max_iterations": 5,
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(
            gd, tool_registry=_make_tool_registry(),
        )
        assert graph.max_iterations == 5

    def test_no_max_iterations_no_attribute(self):
        gd = parse_graph_def(
            "unlimited",
            {
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(
            gd, tool_registry=_make_tool_registry(),
        )
        # No max_iterations attribute when not set
        assert not hasattr(graph, "max_iterations")


# ── P3: Retry + Multi-model ──


class TestRetryParsing:
    """Test retry field parsing."""

    def test_parse_retry(self):
        gd = parse_graph_def(
            "retry",
            {
                "nodes": {
                    "call_api": {
                        "type": "tool",
                        "tool": "web_search",
                        "retry": {"max_attempts": 3, "delay_seconds": 1},
                    },
                },
                "edges": [
                    {"from": "START", "to": "call_api"},
                    {"from": "call_api", "to": "END"},
                ],
            },
        )
        assert gd.nodes["call_api"].retry == {"max_attempts": 3, "delay_seconds": 1}

    def test_parse_no_retry(self):
        gd = parse_graph_def(
            "no_retry",
            {
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "END"},
                ],
            },
        )
        assert gd.nodes["step1"].retry is None

    def test_retry_without_max_attempts_raises(self):
        with pytest.raises(ValueError, match="max_attempts"):
            parse_graph_def(
                "bad_retry",
                {
                    "nodes": {
                        "s": {
                            "type": "tool",
                            "tool": "web_search",
                            "retry": {"delay_seconds": 1},
                        },
                    },
                    "edges": [
                        {"from": "START", "to": "s"},
                        {"from": "s", "to": "END"},
                    ],
                },
            )


class TestRetryBuild:
    """Test retry graph builds correctly."""

    def test_retry_graph_builds(self):
        """Graph with retry configured builds successfully."""
        gd = parse_graph_def(
            "retry_test",
            {
                "nodes": {
                    "retry_node": {
                        "type": "tool",
                        "tool": "web_search",
                        "retry": {"max_attempts": 3, "delay_seconds": 0},
                    },
                },
                "edges": [
                    {"from": "START", "to": "retry_node"},
                    {"from": "retry_node", "to": "END"},
                ],
            },
        )
        graph = build_dsl_graph(gd, tool_registry=_make_tool_registry())
        assert graph is not None


class TestModelParsing:
    """Test per-node model override parsing."""

    def test_parse_model(self):
        gd = parse_graph_def(
            "multi_model",
            {
                "nodes": {
                    "classify": {
                        "type": "llm",
                        "model": {"provider": "anthropic", "name": "claude-haiku-4-5"},
                    },
                    "generate": {
                        "type": "llm",
                        "model": {"provider": "openai", "name": "gpt-4o"},
                    },
                },
                "edges": [
                    {"from": "START", "to": "classify"},
                    {"from": "classify", "to": "generate"},
                    {"from": "generate", "to": "END"},
                ],
            },
        )
        assert gd.nodes["classify"].model == {"provider": "anthropic", "name": "claude-haiku-4-5"}
        assert gd.nodes["generate"].model == {"provider": "openai", "name": "gpt-4o"}

    def test_no_model_default(self):
        gd = parse_graph_def(
            "no_model",
            {
                "nodes": {
                    "step1": {"type": "llm"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "END"},
                ],
            },
        )
        assert gd.nodes["step1"].model is None
