"""Graph visualization — generate Mermaid diagrams from GraphDef."""

from __future__ import annotations

from artipivot.graph.dsl import GraphDef

# LangGraph internal constants
_START = "__start__"
_END = "__end__"


def graph_to_mermaid(graph_def: GraphDef) -> str:
    """Generate a Mermaid flowchart from a GraphDef.

    Produces a ``flowchart TD`` diagram with nodes and edges.
    Conditional edges use dotted arrows with condition labels.
    Fan-out edges use separate solid arrows from the same source.
    """
    lines: list[str] = ["flowchart TD"]

    # Node declarations with shape hints
    for name, node_def in graph_def.nodes.items():
        label = _node_label(node_def.type, name)
        shape = _node_shape(node_def.type)
        lines.append(f"    {name}{shape[0]}\"{label}\"{shape[1]}")

    # Edges
    for edge in graph_def.edges:
        src = _display_name(edge.source)
        if edge.condition:
            # Conditional: dotted arrows to each target
            cond_label = _condition_label(edge.condition)
            if edge.targets:
                for target in edge.targets:
                    tgt = _display_name(target)
                    lines.append(f"    {src} -.->|\"{cond_label}\"| {tgt}")
        elif edge.targets:
            # Fan-out
            for target in edge.targets:
                tgt = _display_name(target)
                lines.append(f"    {src} --> {tgt}")
        else:
            tgt = _display_name(edge.target)
            lines.append(f"    {src} --> {tgt}")

    return "\n".join(lines)


def _display_name(name: str | None) -> str:
    """Convert LangGraph constants to readable names."""
    if name is None:
        return "?"
    if name == _START:
        return "START"
    if name == _END:
        return "END"
    return name


def _node_label(node_type: str, name: str) -> str:
    """Human-readable label for a node."""
    type_icons = {
        "llm": "LLM",
        "tool": "Tool",
        "tools": "Tools",
        "sub_agent": "SubAgent",
    }
    prefix = type_icons.get(node_type, "")
    return f"{prefix}: {name}"


def _node_shape(node_type: str) -> tuple[str, str]:
    """Mermaid shape delimiters for node types."""
    if node_type == "llm":
        return ("([", "])")  # stadium
    if node_type in ("tool", "tools"):
        return ("[[", "]]")  # subroutine
    return ("[", "]")  # rectangle


def _condition_label(cond) -> str:
    """Short label for a condition."""
    if cond.field:
        return f"field:{cond.field}"
    if cond.builtin:
        return f"fn:{cond.builtin}"
    return "cond"
