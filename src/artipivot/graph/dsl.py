"""Graph DSL — YAML-driven arbitrary graph topology for sub-agents.

Allows defining custom sub-agent graph topologies in YAML instead of
being limited to the three built-in strategies (ReAct/CoT/Function Calling).
Node types cover LLM calls, tool execution, data transforms, and nested
sub-agents.  Conditional routing supports field mapping, built-in functions,
and Transform-based routers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from artipivot.graph.state import SubAgentState
from artipivot.transforms.nodes import make_transform_node

logger = structlog.get_logger(__name__)

# ── Valid node types ──

VALID_NODE_TYPES = frozenset({"llm", "tool", "tools", "transform", "sub_agent"})

# User-facing names in YAML → LangGraph internal constants
_RESOLVE = {"START": START, "END": END}

# ── Data model ──


@dataclass
class NodeDef:
    """Single node definition in a DSL graph."""

    name: str
    type: str  # "llm" | "tool" | "tools" | "transform" | "sub_agent"
    # type="tool"
    tool: str | None = None
    # type="tools"
    tools: list[str] | None = None
    # type="transform"
    handler: str | None = None
    input_key: str = "metadata"
    output_key: str = "metadata"
    # type="llm"
    system_prompt: str = ""
    # type="sub_agent"
    ref: str | None = None


@dataclass
class ConditionDef:
    """Conditional routing definition for an edge."""

    # 1. Field mapping — read state[field], map via mapping dict
    field: str | None = None
    mapping: dict[str, str] | None = None
    # 2. Built-in — predefined routing functions
    builtin: str | None = None
    # 3. Transform — call transform function with state, return node name
    transform: str | None = None

    def make_router(
        self,
        *,
        targets: list[str],
        transform_registry=None,
    ) -> Callable:
        """Build a router function for add_conditional_edges.

        Args:
            targets: Resolved target names (LangGraph constants or node names).
            transform_registry: Required for transform-based routing.
        """
        if self.field is not None and self.mapping is not None:
            return self._field_mapping_router(targets)
        if self.builtin is not None:
            return self._builtin_router(self.builtin, targets)
        if self.transform is not None:
            return self._transform_router(self.transform, targets, transform_registry)
        raise ValueError(
            "ConditionDef must have one of: field+mapping, builtin, transform"
        )

    def _field_mapping_router(self, targets: list[str]) -> Callable:
        mapping = self.mapping
        field_name = self.field
        # Build resolved mapping: user-facing names → resolved targets
        # targets order matches the mapping values
        resolved = {}
        for key, user_target in mapping.items():
            resolved[key] = _RESOLVE.get(user_target, user_target)

        # Ensure _ fallback resolves to a valid target (last target by convention)
        default = resolved.get("_", targets[-1])

        def router(state: dict) -> str:
            value = state.get(field_name, "")
            return resolved.get(str(value), default)

        router.__name__ = f"route:{field_name}"
        return router

    def _builtin_router(self, name: str, targets: list[str]) -> Callable:
        if name == "has_tool_calls":
            # Convention: targets[0] = tool node, targets[1] = END or similar
            tool_target = targets[0]
            no_tool_target = targets[1] if len(targets) > 1 else END

            def has_tool_calls(state: dict) -> str:
                msgs = state.get("messages", [])
                if msgs:
                    last = msgs[-1]
                    if hasattr(last, "tool_calls") and last.tool_calls:
                        return tool_target
                return no_tool_target

            has_tool_calls.__name__ = "route:has_tool_calls"
            return has_tool_calls

        if name == "no_tool_calls":
            tool_target = targets[0]
            no_tool_target = targets[1] if len(targets) > 1 else END

            def no_tool_calls(state: dict) -> str:
                msgs = state.get("messages", [])
                if msgs:
                    last = msgs[-1]
                    if hasattr(last, "tool_calls") and last.tool_calls:
                        return no_tool_target
                return tool_target

            no_tool_calls.__name__ = "route:no_tool_calls"
            return no_tool_calls

        raise ValueError(f"Unknown builtin router: {name}")

    def _transform_router(
        self,
        transform_name: str,
        targets: list[str],
        transform_registry,
    ) -> Callable:
        if transform_registry is None:
            raise ValueError(
                f"Transform router '{transform_name}' requires a transform_registry"
            )

        def transform_router(state: dict) -> str:
            fn = transform_registry.get(transform_name)
            result = fn(state)
            if asyncio.iscoroutine(result):
                raise RuntimeError(
                    f"Transform router '{transform_name}' returned a coroutine — "
                    "routing transforms must be synchronous"
                )
            resolved = _RESOLVE.get(result, result)
            return resolved

        transform_router.__name__ = f"route:transform:{transform_name}"
        return transform_router


@dataclass
class EdgeDef:
    """Edge definition — fixed or conditional."""

    source: str
    target: str | None = None  # Fixed edge: single target
    targets: list[str] | None = None  # Conditional edge: possible targets
    condition: ConditionDef | None = None


@dataclass
class GraphDef:
    """Complete graph definition parsed from YAML."""

    name: str
    nodes: dict[str, NodeDef]
    edges: list[EdgeDef]


# ── Parsing ──


def parse_graph_def(name: str, graph_cfg: dict) -> GraphDef:
    """Parse a graph: section from YAML into GraphDef.

    Validates node types, edge references, and condition targets.
    """
    nodes_cfg = graph_cfg.get("nodes")
    if not nodes_cfg:
        raise ValueError(f"Graph '{name}': 'nodes' section is required")

    # Parse nodes
    nodes: dict[str, NodeDef] = {}
    for node_name, node_cfg in nodes_cfg.items():
        node_type = node_cfg.get("type")
        if node_type not in VALID_NODE_TYPES:
            raise ValueError(
                f"Graph '{name}', node '{node_name}': "
                f"invalid type '{node_type}', must be one of {sorted(VALID_NODE_TYPES)}"
            )
        nodes[node_name] = NodeDef(
            name=node_name,
            type=node_type,
            tool=node_cfg.get("tool"),
            tools=node_cfg.get("tools"),
            handler=node_cfg.get("handler"),
            input_key=node_cfg.get("input_key", "metadata"),
            output_key=node_cfg.get("output_key", "metadata"),
            system_prompt=node_cfg.get("system_prompt", ""),
            ref=node_cfg.get("ref"),
        )

    # Parse edges
    edges_cfg = graph_cfg.get("edges", [])
    edges: list[EdgeDef] = []
    # User-facing names valid as targets: node names + START/END strings
    valid_user_targets = set(nodes) | {"START", "END"}

    for i, edge_cfg in enumerate(edges_cfg):
        source_raw = edge_cfg.get("from")
        if not source_raw:
            raise ValueError(f"Graph '{name}', edge[{i}]: 'from' is required")
        source = _RESOLVE.get(source_raw, source_raw)

        cond_cfg = edge_cfg.get("condition")
        condition = None

        # Single target (fixed edge)
        target_raw = edge_cfg.get("to")
        # Multiple targets (conditional edge or fan-out)
        targets_raw = edge_cfg.get("targets")
        # "to" can also be a list in YAML
        if isinstance(target_raw, list):
            targets_raw = target_raw
            target_raw = None

        # Resolve raw values to LangGraph constants
        target = _RESOLVE.get(target_raw, target_raw) if isinstance(target_raw, str) else target_raw
        if targets_raw:
            targets = [_RESOLVE.get(t, t) for t in targets_raw]
        else:
            targets = None

        if cond_cfg:
            condition = _parse_condition(cond_cfg, name, i)
            # Conditional edges need targets list
            if not targets:
                raise ValueError(
                    f"Graph '{name}', edge[{i}]: conditional edges require "
                    "'targets' or list-valued 'to'"
                )
        elif targets is None and target is None:
            raise ValueError(
                f"Graph '{name}', edge[{i}]: 'to' is required for fixed edges"
            )

        # Validate targets exist (check against user-facing names)
        if target_raw and target_raw not in valid_user_targets:
            raise ValueError(
                f"Graph '{name}', edge[{i}]: target '{target_raw}' "
                f"is not a defined node (valid: {sorted(valid_user_targets)})"
            )
        if targets_raw:
            for t in targets_raw:
                if t not in valid_user_targets:
                    raise ValueError(
                        f"Graph '{name}', edge[{i}]: target '{t}' "
                        f"is not a defined node (valid: {sorted(valid_user_targets)})"
                    )

        edges.append(
            EdgeDef(
                source=source,
                target=target,
                targets=targets,
                condition=condition,
            )
        )

    return GraphDef(name=name, nodes=nodes, edges=edges)


def _parse_condition(cond_cfg: dict, graph_name: str, edge_idx: int) -> ConditionDef:
    """Parse a condition section of an edge."""
    has_field = "field" in cond_cfg
    has_mapping = "mapping" in cond_cfg
    has_builtin = "builtin" in cond_cfg
    has_transform = "transform" in cond_cfg

    if has_field or has_mapping:
        if not has_field or not has_mapping:
            raise ValueError(
                f"Graph '{graph_name}', edge[{edge_idx}]: "
                "field mapping requires both 'field' and 'mapping'"
            )
        return ConditionDef(field=cond_cfg["field"], mapping=cond_cfg["mapping"])

    if has_builtin:
        return ConditionDef(builtin=cond_cfg["builtin"])

    if has_transform:
        return ConditionDef(transform=cond_cfg["transform"])

    raise ValueError(
        f"Graph '{graph_name}', edge[{edge_idx}]: "
        "condition must have one of: field+mapping, builtin, transform"
    )


# ── Validation ──


def validate_graph_def(
    graph_def: GraphDef,
    *,
    tool_registry=None,
    transform_registry=None,
    compiled_sub_agents: dict[str, CompiledStateGraph] | None = None,
) -> list[str]:
    """Runtime validation — check tools/transforms/sub-agents exist.

    Returns a list of warning strings.  Empty list means all OK.
    Does not raise — warnings are informational.
    """
    warnings: list[str] = []
    compiled_sub_agents = compiled_sub_agents or {}

    for node_name, node_def in graph_def.nodes.items():
        if node_def.type == "tool" and tool_registry:
            if not tool_registry.get(node_def.tool):
                warnings.append(
                    f"Node '{node_name}': tool '{node_def.tool}' not found in registry"
                )

        if node_def.type == "tools" and tool_registry:
            for t in node_def.tools or []:
                if not tool_registry.get(t):
                    warnings.append(
                        f"Node '{node_name}': tool '{t}' not found in registry"
                    )

        if node_def.type == "transform" and transform_registry:
            if not transform_registry.has(node_def.handler):
                warnings.append(
                    f"Node '{node_name}': transform '{node_def.handler}' not registered"
                )

        if node_def.type == "sub_agent":
            if node_def.ref not in compiled_sub_agents:
                warnings.append(
                    f"Node '{node_name}': sub_agent '{node_def.ref}' not found"
                )

        # Check condition transform references
        for edge in graph_def.edges:
            if edge.condition and edge.condition.transform and transform_registry:
                if not transform_registry.has(edge.condition.transform):
                    warnings.append(
                        f"Edge from '{edge.source}': "
                        f"transform router '{edge.condition.transform}' not registered"
                    )

    return warnings


# ── Graph building ──


def build_dsl_graph(
    graph_def: GraphDef,
    *,
    tool_registry,
    transform_registry,
    compiled_sub_agents: dict[str, CompiledStateGraph] | None = None,
) -> CompiledStateGraph:
    """Build a compiled StateGraph from a GraphDef.

    Creates node functions, wires edges, and compiles the graph.
    """
    compiled_sub_agents = compiled_sub_agents or {}
    builder = StateGraph(SubAgentState)

    # Add nodes
    for node_name, node_def in graph_def.nodes.items():
        node_fn = _build_node(node_def, tool_registry, transform_registry, compiled_sub_agents)
        builder.add_node(node_name, node_fn)

    # Add edges
    for edge in graph_def.edges:
        if edge.condition:
            # Conditional edge
            router = edge.condition.make_router(
                targets=edge.targets, transform_registry=transform_registry
            )
            builder.add_conditional_edges(edge.source, router, edge.targets)
        elif edge.targets:
            # Fan-out: multiple fixed targets from same source
            for target in edge.targets:
                builder.add_edge(edge.source, target)
        else:
            # Fixed single edge
            builder.add_edge(edge.source, edge.target)

    return builder.compile()


# ── Node factories ──


def _build_node(
    node_def: NodeDef,
    tool_registry,
    transform_registry,
    compiled_sub_agents: dict[str, CompiledStateGraph],
) -> Any:
    """Create a LangGraph node function from a NodeDef."""
    if node_def.type == "llm":
        return _make_llm_node(node_def)
    if node_def.type == "tool":
        return _make_tool_node(node_def, tool_registry)
    if node_def.type == "tools":
        return _make_tools_node(node_def, tool_registry)
    if node_def.type == "transform":
        return make_transform_node(
            node_def.handler,
            transform_registry,
            input_key=node_def.input_key,
            output_key=node_def.output_key,
        )
    if node_def.type == "sub_agent":
        return _make_sub_agent_node(node_def, compiled_sub_agents)
    raise ValueError(f"Unknown node type: {node_def.type}")


def _make_llm_node(node_def: NodeDef) -> Callable:
    """Create an LLM call node."""
    system_prompt = node_def.system_prompt

    async def llm_node(state: SubAgentState, runtime) -> dict:
        from langgraph.runtime import Runtime

        from artipivot.graph.context import AgentContext

        rt: Runtime[AgentContext] = runtime
        model = rt.context.model

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        if state.get("query"):
            messages.append(HumanMessage(content=state["query"]))
        messages.extend(state.get("messages", []))

        response = await model.ainvoke(messages)
        return {"messages": [response]}

    llm_node.__name__ = f"llm:{node_def.name}"
    return llm_node


def _make_tool_node(node_def: NodeDef, tool_registry) -> Callable:
    """Create a single-tool execution node."""
    tool_name = node_def.tool
    tool = tool_registry.get(tool_name)
    if tool is None:
        raise ValueError(
            f"Tool '{tool_name}' not found in registry for node '{node_def.name}'"
        )

    async def tool_node(state: SubAgentState, runtime) -> dict:
        msgs = state.get("messages", [])
        last_msg = msgs[-1] if msgs else None
        if not last_msg or not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
            return {}
        # Execute the first tool call
        tc = last_msg.tool_calls[0]
        result = await tool.ainvoke(tc["args"])
        return {"messages": [AIMessage(content=str(result))]}

    tool_node.__name__ = f"tool:{node_def.name}"
    return tool_node


def _make_tools_node(node_def: NodeDef, tool_registry) -> ToolNode:
    """Create a ToolNode (multi-tool) from the registry."""
    tool_names = node_def.tools or []
    return tool_registry.get_tool_node(tool_names)


def _make_sub_agent_node(
    node_def: NodeDef, compiled_sub_agents: dict[str, CompiledStateGraph]
) -> CompiledStateGraph:
    """Return a compiled sub-agent graph to be used as a node."""
    ref = node_def.ref
    if ref not in compiled_sub_agents:
        raise ValueError(
            f"Sub-agent '{ref}' not found for node '{node_def.name}'. "
            f"Available: {list(compiled_sub_agents)}"
        )
    return compiled_sub_agents[ref]
