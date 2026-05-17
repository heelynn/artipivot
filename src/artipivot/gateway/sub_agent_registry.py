"""SubAgentRegistry — independent sub-agent lifecycle management.

Sub-agents are stateless compiled graphs, registered globally.
Main agents reference them by name. Same definition = shared instance.
"""

from __future__ import annotations

import hashlib
import json

import structlog
from langgraph.graph.state import CompiledStateGraph

from artipivot.agents.base import SubAgentDef
from artipivot.agents.declarative import DeclarativeSubAgentDef, build_declarative_subagent
from artipivot.agents.programmatic import build_programmatic_subagent
from artipivot.graph.dsl import GraphDef, build_dsl_graph

logger = structlog.get_logger(__name__)


class SubAgentRegistry:
    """Global sub-agent registry — build once, share across main agents."""

    def __init__(
        self,
        tool_registry,
        *,
        transform_registry=None,
        model_provider=None,
    ) -> None:
        self._tools = tool_registry
        self._transforms = transform_registry
        self._model_provider = model_provider
        self._compiled: dict[str, CompiledStateGraph] = {}
        self._defs: dict[str, object] = {}
        # Deduplication: cache_key → registered name
        self._cache: dict[str, str] = {}

    def register(
        self,
        name: str,
        graph: CompiledStateGraph,
        defn: object | None = None,
    ) -> None:
        """Register an already-compiled sub-agent graph."""
        self._compiled[name] = graph
        if defn is not None:
            self._defs[name] = defn
        logger.info("sub_agent.registered", name=name)

    def get(self, name: str) -> CompiledStateGraph | None:
        """Get compiled sub-agent by name."""
        return self._compiled.get(name)

    def get_def(self, name: str) -> object | None:
        """Get sub-agent definition by name."""
        return self._defs.get(name)

    def list_sub_agents(self) -> list[str]:
        """List all registered sub-agent names."""
        return list(self._compiled)

    def register_from_manifest(self, agents: dict) -> None:
        """Discover and build all sub-agents declared in the manifest.

        Args:
            agents: dict of agent_id → AgentDef (from manifest).
        """
        for agent_def in agents.values():
            for name, decl_def in agent_def.declarative_sub_agents.items():
                self.build_and_register(name, decl_def)
            for name, sub_def in agent_def.sub_agents.items():
                self.build_and_register(name, sub_def)
            for name, graph_def in agent_def.graph_sub_agents.items():
                self.build_and_register(name, graph_def)

    def build_and_register(
        self,
        name: str,
        defn: SubAgentDef | DeclarativeSubAgentDef | GraphDef,
        *,
        checkpointer=None,
    ) -> CompiledStateGraph:
        """Build a compiled graph from a definition and register it.

        Deduplicates: if an equivalent definition was already built,
        reuses the same compiled graph.
        """
        cache_key = self._make_cache_key(defn)
        if cache_key in self._cache:
            existing_name = self._cache[cache_key]
            graph = self._compiled[existing_name]
            self._compiled[name] = graph
            self._defs[name] = defn
            logger.info(
                "sub_agent.deduplicated",
                name=name,
                reused_from=existing_name,
            )
            return graph

        graph = self._build(defn, checkpointer=checkpointer)
        self._compiled[name] = graph
        self._defs[name] = defn
        if cache_key:
            self._cache[cache_key] = name
        logger.info("sub_agent.built_and_registered", name=name)
        return graph

    def _build(
        self,
        defn: SubAgentDef | DeclarativeSubAgentDef | GraphDef,
        *,
        checkpointer=None,
    ) -> CompiledStateGraph:
        """Build compiled graph from definition."""
        if isinstance(defn, GraphDef):
            return build_dsl_graph(
                defn,
                tool_registry=self._tools,
                transform_registry=self._transforms,
                checkpointer=checkpointer,
                model_provider=self._model_provider,
            )

        if isinstance(defn, DeclarativeSubAgentDef):
            tool_node = self._tools.get_tool_node(defn.tools)
            return build_declarative_subagent(defn, tool_node)

        if isinstance(defn, SubAgentDef):
            tool_node = self._tools.get_tool_node(defn.tools)
            return build_programmatic_subagent(defn, tool_node)

        raise TypeError(f"Unknown sub-agent definition type: {type(defn)}")

    def _make_cache_key(
        self, defn: SubAgentDef | DeclarativeSubAgentDef | GraphDef
    ) -> str:
        """Produce a deterministic cache key for deduplication."""
        if isinstance(defn, GraphDef):
            # DSL graphs: hash the full definition
            raw = json.dumps(
                {
                    "type": "dsl",
                    "nodes": {
                        n: {"type": d.type, "tool": d.tool, "tools": d.tools}
                        for n, d in defn.nodes.items()
                    },
                    "edges": [
                        {"from": e.source, "to": e.target, "targets": e.targets}
                        for e in defn.edges
                    ],
                },
                sort_keys=True,
            )
            return hashlib.md5(raw.encode()).hexdigest()

        if isinstance(defn, DeclarativeSubAgentDef):
            raw = json.dumps(
                {
                    "type": "declarative",
                    "strategy": defn.strategy,
                    "tools": sorted(defn.tools),
                    "strategy_config": defn.strategy_config,
                },
                sort_keys=True,
            )
            return hashlib.md5(raw.encode()).hexdigest()

        if isinstance(defn, SubAgentDef):
            raw = json.dumps(
                {
                    "type": "programmatic",
                    "tools": sorted(defn.tools),
                },
                sort_keys=True,
            )
            return hashlib.md5(raw.encode()).hexdigest()

        return ""
