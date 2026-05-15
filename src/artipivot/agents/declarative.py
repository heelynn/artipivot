"""Declarative sub-agent builder — config-driven strategy selection."""

from __future__ import annotations

from dataclasses import dataclass, field

from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from artipivot.agents.base import SubAgentDef
from artipivot.agents.strategies import get_strategy


@dataclass
class DeclarativeSubAgentDef:
    """Declarative sub-agent definition — choose strategy via config."""

    name: str
    strategy: str  # "react" | "cot" | "function_calling"
    tools: list[str]
    system_prompt: str = ""
    strategy_config: dict = field(default_factory=dict)


def build_declarative_subagent(
    defn: DeclarativeSubAgentDef,
    tool_node: ToolNode,
) -> CompiledStateGraph:
    """Build sub-agent graph from declarative definition."""
    # Ensure strategy modules are imported so they self-register
    import artipivot.agents.strategies.react  # noqa: F401
    import artipivot.agents.strategies.cot  # noqa: F401
    import artipivot.agents.strategies.function_calling  # noqa: F401

    strategy = get_strategy(defn.strategy)
    sub_def = SubAgentDef(
        name=defn.name,
        tools=defn.tools,
        system_prompt=defn.system_prompt,
    )
    return strategy.build(sub_def, tool_node, config=defn.strategy_config or None)
