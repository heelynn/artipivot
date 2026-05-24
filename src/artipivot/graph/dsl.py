"""Graph DSL — YAML-driven arbitrary graph topology for sub-agents.

Allows defining custom sub-agent graph topologies in YAML instead of
being limited to the two built-in strategies (ReAct/Function Calling).
Node types cover LLM calls, tool execution, and nested sub-agents.
Conditional routing supports field mapping and built-in functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from artipivot.graph.state import SubAgentState
from artipivot.observability import log

# ── Valid node types ──

VALID_NODE_TYPES = frozenset({"llm", "tool", "tools", "sub_agent"})
_VALID_INTERRUPTS = frozenset({"before", "after"})

# User-facing names in YAML → LangGraph internal constants
_RESOLVE = {"START": START, "END": END}

# ── Data model ──


@dataclass
class NodeDef:
    """Single node definition in a DSL graph."""

    name: str
    type: str  # "llm" | "tool" | "tools" | "sub_agent"
    # type="tool"
    tool: str | None = None
    # type="tools" or type="llm" (tool binding)
    tools: list[str] | None = None
    # type="llm"
    system_prompt: str = ""
    # type="sub_agent"
    ref: str | None = None
    # human-in-the-loop
    interrupt: str | None = None  # "before" | "after" | None
    # retry
    retry: dict | None = None  # {"max_attempts": 3, "delay_seconds": 1}
    # per-node model override (type="llm")
    model: dict | None = None  # {"provider": "anthropic", "name": "claude-haiku-4-5"}


@dataclass
class ConditionDef:
    """Conditional routing definition for an edge."""

    # 1. Field mapping — read state[field], map via mapping dict
    field: str | None = None
    mapping: dict[str, str] | None = None
    # 2. Built-in — predefined routing functions
    builtin: str | None = None

    def make_router(
        self,
        *,
        targets: list[str],
    ) -> Callable:
        """Build a router function for add_conditional_edges.

        Args:
            targets: Resolved target names (LangGraph constants or node names).
        """
        if self.field is not None and self.mapping is not None:
            return self._field_mapping_router(targets)
        if self.builtin is not None:
            return self._builtin_router(self.builtin, targets)
        raise ValueError(
            "ConditionDef must have one of: field+mapping, builtin"
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
    max_iterations: int | None = None

    def to_dict(self) -> dict:
        """Serialize to dict compatible with parse_graph_def()."""
        from dataclasses import asdict

        nodes_dict = {}
        for n, nd in self.nodes.items():
            d = {k: v for k, v in asdict(nd).items() if v is not None and k != "name"}
            nodes_dict[n] = d
        edges_list = []
        for e in self.edges:
            d = {"from": e.source}
            if e.target is not None:
                d["to"] = e.target
            if e.targets:
                d["targets"] = e.targets
            edges_list.append(d)
        result = {"nodes": nodes_dict, "edges": edges_list}
        if self.max_iterations is not None:
            result["max_iterations"] = self.max_iterations
        return result


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
        interrupt = node_cfg.get("interrupt")
        if interrupt is not None and interrupt not in _VALID_INTERRUPTS:
            raise ValueError(
                f"Graph '{name}', node '{node_name}': "
                f"invalid interrupt '{interrupt}', must be one of {sorted(_VALID_INTERRUPTS)}"
            )
        retry_cfg = node_cfg.get("retry")
        if retry_cfg is not None:
            if "max_attempts" not in retry_cfg:
                raise ValueError(
                    f"Graph '{name}', node '{node_name}': "
                    "retry requires 'max_attempts'"
                )

        nodes[node_name] = NodeDef(
            name=node_name,
            type=node_type,
            tool=node_cfg.get("tool"),
            tools=node_cfg.get("tools"),
            system_prompt=node_cfg.get("system_prompt", ""),
            ref=node_cfg.get("ref"),
            interrupt=interrupt,
            retry=retry_cfg,
            model=node_cfg.get("model"),
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

    max_iterations = graph_cfg.get("max_iterations")
    if max_iterations is not None:
        if not isinstance(max_iterations, int) or max_iterations < 1:
            raise ValueError(
                f"Graph '{name}': 'max_iterations' must be a positive integer"
            )

    return GraphDef(name=name, nodes=nodes, edges=edges, max_iterations=max_iterations)


def _parse_condition(cond_cfg: dict, graph_name: str, edge_idx: int) -> ConditionDef:
    """Parse a condition section of an edge."""
    has_field = "field" in cond_cfg
    has_mapping = "mapping" in cond_cfg
    has_builtin = "builtin" in cond_cfg

    if has_field or has_mapping:
        if not has_field or not has_mapping:
            raise ValueError(
                f"Graph '{graph_name}', edge[{edge_idx}]: "
                "field mapping requires both 'field' and 'mapping'"
            )
        return ConditionDef(field=cond_cfg["field"], mapping=cond_cfg["mapping"])

    if has_builtin:
        return ConditionDef(builtin=cond_cfg["builtin"])

    raise ValueError(
        f"Graph '{graph_name}', edge[{edge_idx}]: "
        "condition must have one of: field+mapping, builtin"
    )


# ── Validation ──


def validate_graph_def(
    graph_def: GraphDef,
    *,
    tool_registry=None,
    compiled_sub_agents: dict[str, CompiledStateGraph] | None = None,
) -> list[str]:
    """Runtime validation — check tools/sub-agents exist.

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

        if node_def.type == "sub_agent":
            if node_def.ref not in compiled_sub_agents:
                warnings.append(
                    f"Node '{node_name}': sub_agent '{node_def.ref}' not found"
                )

    return warnings


# ── Graph building ──


def build_dsl_graph(
    graph_def: GraphDef,
    *,
    tool_registry,
    compiled_sub_agents: dict[str, CompiledStateGraph] | None = None,
    checkpointer=None,
    model_provider=None,
) -> CompiledStateGraph:
    """Build a compiled StateGraph from a GraphDef.

    Creates node functions, wires edges, and compiles the graph.
    Supports human-in-the-loop via interrupt and checkpointer.
    """
    compiled_sub_agents = compiled_sub_agents or {}

    # Validate before building — warnings are logged, not raised
    warnings = validate_graph_def(
        graph_def,
        tool_registry=tool_registry,
        compiled_sub_agents=compiled_sub_agents,
    )
    for w in warnings:
        log.warning("dsl.validation_warning", graph=graph_def.name, detail=w)

    builder = StateGraph(SubAgentState)

    # Add nodes
    for node_name, node_def in graph_def.nodes.items():
        node_fn = _build_node(
            node_def, tool_registry,
            compiled_sub_agents, model_provider,
        )
        builder.add_node(node_name, node_fn)

    # Add edges
    for edge in graph_def.edges:
        if edge.condition:
            # Conditional edge
            router = edge.condition.make_router(targets=edge.targets)
            builder.add_conditional_edges(edge.source, router, edge.targets)
        elif edge.targets:
            # Fan-out: multiple fixed targets from same source
            for target in edge.targets:
                builder.add_edge(edge.source, target)
        else:
            # Fixed single edge
            builder.add_edge(edge.source, edge.target)

    # Collect interrupt nodes
    interrupt_before = [
        n.name for n in graph_def.nodes.values() if n.interrupt == "before"
    ]
    interrupt_after = [
        n.name for n in graph_def.nodes.values() if n.interrupt == "after"
    ]

    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    if interrupt_before:
        compile_kwargs["interrupt_before"] = interrupt_before
    if interrupt_after:
        compile_kwargs["interrupt_after"] = interrupt_after

    graph = builder.compile(**compile_kwargs)
    # Store max_iterations as attribute for callers to inject into config
    if graph_def.max_iterations is not None:
        graph.max_iterations = graph_def.max_iterations
    return graph


# ── Node factories ──


def _build_node(
    node_def: NodeDef,
    tool_registry,
    compiled_sub_agents: dict[str, CompiledStateGraph],
    model_provider=None,
) -> Any:
    """Create a LangGraph node function from a NodeDef."""
    if node_def.type == "llm":
        node_fn = _make_llm_node(node_def, tool_registry, model_provider)
    elif node_def.type == "tool":
        node_fn = _make_tool_node(node_def, tool_registry)
    elif node_def.type == "tools":
        node_fn = _make_tools_node(node_def, tool_registry)
    elif node_def.type == "sub_agent":
        # sub_agent returns a compiled graph, not a function — no retry wrapping
        return _make_sub_agent_node(node_def, compiled_sub_agents)
    else:
        raise ValueError(f"Unknown node type: {node_def.type}")

    # Wrap with retry if configured
    if node_def.retry:
        node_fn = _wrap_with_retry(node_fn, node_def.retry, node_def.name)
    return node_fn


def _make_llm_node(node_def: NodeDef, tool_registry=None, model_provider=None) -> Callable:
    """Create an LLM call node.

    If ``tools`` is configured, the model will have those tools bound,
    enabling it to produce ``tool_calls`` in its response.
    """
    system_prompt = node_def.system_prompt
    model_cfg = node_def.model
    tool_names = node_def.tools or []
    _model_provider = model_provider
    _tool_registry = tool_registry

    async def llm_node(state: SubAgentState, runtime) -> dict:
        from artipivot.graph.context import AgentContext

        # Resolve model: per-node config > runtime context
        if model_cfg and _model_provider is not None:
            from artipivot.models.config import ModelConfig

            cfg = ModelConfig(**model_cfg)
            factory = _model_provider._factories.get(cfg.provider)
            if factory is None:
                raise ValueError(f"Unknown provider: {cfg.provider}")
            model = factory(cfg)
        else:
            from langgraph.runtime import Runtime

            rt: Runtime[AgentContext] = runtime
            model = rt.context.model

        # Bind tools if configured
        if tool_names and _tool_registry is not None:
            resolved = [_tool_registry.get(name) for name in tool_names]
            missing = [tool_names[i] for i, t in enumerate(resolved) if t is None]
            if missing:
                log.warning("dsl.missing_llm_tools", node=node_def.name, tools=missing)
            resolved = [t for t in resolved if t is not None]
            if resolved:
                model = model.bind_tools(resolved)

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        if state.get("query"):
            messages.append(HumanMessage(content=state["query"]))
        messages.extend(state.get("messages", []))

        log.info("llm.call", node=node_def.name, messages_count=len(messages),
                 tools=len(tool_names))

        response = await model.ainvoke(messages)

        tool_calls = getattr(response, "tool_calls", [])
        log.info("llm.response", node=node_def.name, tool_calls=len(tool_calls))

        return {"messages": [response]}

    llm_node.__name__ = f"llm:{node_def.name}"
    return llm_node


def _wrap_with_retry(node_fn: Callable, retry_cfg: dict, node_name: str) -> Callable:
    """Wrap a node function with RetryPolicy."""
    from artipivot.resilience.retry import RetryPolicy

    policy = RetryPolicy(
        max_retries=retry_cfg.get("max_attempts", 3) - 1,
        base_delay=retry_cfg.get("delay_seconds", 1.0),
    )

    async def retried_node(state, runtime):
        async def _inner(s, r):
            return await node_fn(s, r)
        return await policy.execute(_inner, state, runtime)

    retried_node.__name__ = f"retry:{node_name}"
    return retried_node


def _make_tool_node(node_def: NodeDef, tool_registry) -> Callable:
    """Create a single-tool execution node.

    Uses get_or_stub() to auto-stub missing tools instead of crashing.
    """
    tool_name = node_def.tool
    tool = tool_registry.get_or_stub(tool_name)

    async def tool_node(state: SubAgentState, runtime) -> dict:
        msgs = state.get("messages", [])
        last_msg = msgs[-1] if msgs else None
        if not last_msg or not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
            return {}
        # Execute the first tool call
        tc = last_msg.tool_calls[0]

        log.info("tool.call", tool_name=tool_name, node=node_def.name)
        log.debug("tool.input", tool_name=tool_name, node=node_def.name, args=tc.get("args", {}))

        result = await tool.ainvoke(tc["args"])

        log.info("tool.result", tool_name=tool_name, node=node_def.name, status="ok")
        log.debug("tool.output", tool_name=tool_name, node=node_def.name, result=str(result)[:1000])

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
