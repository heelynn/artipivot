"""Tests for graph visualization — Mermaid generation."""

from __future__ import annotations

import pytest

from artipivot.graph.dsl import parse_graph_def
from artipivot.graph.visual import graph_to_mermaid


class TestGraphToMermaid:
    """Test Mermaid diagram generation from GraphDef."""

    def test_linear_graph(self):
        gd = parse_graph_def(
            "linear",
            {
                "nodes": {
                    "step1": {"type": "tool", "tool": "web_search"},
                    "step2": {"type": "tool", "tool": "code_exec"},
                },
                "edges": [
                    {"from": "START", "to": "step1"},
                    {"from": "step1", "to": "step2"},
                    {"from": "step2", "to": "END"},
                ],
            },
        )
        mermaid = graph_to_mermaid(gd)
        assert "flowchart TD" in mermaid
        assert "START --> step1" in mermaid
        assert "step1 --> step2" in mermaid
        assert "step2 --> END" in mermaid
        # Tool nodes use subroutine shape
        assert "[[" in mermaid
        assert "]]" in mermaid

    def test_parallel_graph(self):
        gd = parse_graph_def(
            "parallel",
            {
                "nodes": {
                    "search": {"type": "tool", "tool": "web_search"},
                    "execute": {"type": "tool", "tool": "code_exec"},
                    "merge": {"type": "llm", "system_prompt": "Merge results"},
                },
                "edges": [
                    {"from": "START", "targets": ["search", "execute"]},
                    {"from": "search", "to": "merge"},
                    {"from": "execute", "to": "merge"},
                    {"from": "merge", "to": "END"},
                ],
            },
        )
        mermaid = graph_to_mermaid(gd)
        assert "START --> search" in mermaid
        assert "START --> execute" in mermaid
        assert "search --> merge" in mermaid
        assert "execute --> merge" in mermaid

    def test_conditional_graph(self):
        gd = parse_graph_def(
            "conditional",
            {
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
                        "condition": {"builtin": "has_tool_calls"},
                    },
                    {"from": "search", "to": "END"},
                    {"from": "fallback", "to": "END"},
                ],
            },
        )
        mermaid = graph_to_mermaid(gd)
        assert "flowchart TD" in mermaid
        # Conditional edges use dotted arrows
        assert "-.->" in mermaid
        assert "has_tool_calls" in mermaid

    def test_llm_node_shape(self):
        gd = parse_graph_def(
            "llm_shape",
            {
                "nodes": {
                    "think": {"type": "llm", "system_prompt": "Think"},
                },
                "edges": [
                    {"from": "START", "to": "think"},
                    {"from": "think", "to": "END"},
                ],
            },
        )
        mermaid = graph_to_mermaid(gd)
        # LLM nodes use stadium shape
        assert "([" in mermaid
        assert "])" in mermaid

    def test_tool_node_shape(self):
        gd = parse_graph_def(
            "tool_shape",
            {
                "nodes": {
                    "search": {"type": "tool", "tool": "web_search"},
                },
                "edges": [
                    {"from": "START", "to": "search"},
                    {"from": "search", "to": "END"},
                ],
            },
        )
        mermaid = graph_to_mermaid(gd)
        # Tool nodes use subroutine shape
        assert "[[" in mermaid
        assert "]]" in mermaid

    def test_field_mapping_condition(self):
        gd = parse_graph_def(
            "field_cond",
            {
                "nodes": {
                    "router": {"type": "llm"},
                    "path_a": {"type": "tool", "tool": "web_search"},
                    "path_b": {"type": "tool", "tool": "code_exec"},
                },
                "edges": [
                    {"from": "START", "to": "router"},
                    {
                        "from": "router",
                        "to": ["path_a", "path_b"],
                        "condition": {
                            "field": "intent",
                            "mapping": {"a": "path_a", "_": "path_b"},
                        },
                    },
                    {"from": "path_a", "to": "END"},
                    {"from": "path_b", "to": "END"},
                ],
            },
        )
        mermaid = graph_to_mermaid(gd)
        assert "field:intent" in mermaid
