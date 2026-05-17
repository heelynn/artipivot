"""AgentDef — unified agent definition data structure."""

from __future__ import annotations

from dataclasses import dataclass, field

from artipivot.agents.base import SubAgentDef
from artipivot.agents.declarative import DeclarativeSubAgentDef
from artipivot.graph.dsl import GraphDef
from artipivot.memory.config import MemoryConfig


@dataclass
class AgentDef:
    """Complete agent definition — everything needed to build a main graph."""

    agent_id: str

    # Model
    model: dict = field(default_factory=dict)
    # {"provider": "anthropic", "name": "claude-sonnet-4-6"}

    # Routing
    confidence_threshold: float = 0.7
    intent_map: dict[str, str] = field(default_factory=dict)
    # {"code_write": "code_writer", "debug": "code_writer"}
    intent_descriptions: dict[str, str] = field(default_factory=dict)
    # {"code_write": "用户要求写代码...", "debug": "用户遇到错误..."}

    # Sub-agents (programmatic)
    sub_agents: dict[str, SubAgentDef] = field(default_factory=dict)
    # {"code_writer": SubAgentDef(...)}

    # Sub-agents (declarative)
    declarative_sub_agents: dict[str, DeclarativeSubAgentDef] = field(default_factory=dict)
    # {"code_writer": DeclarativeSubAgentDef(...)}

    # Sub-agents (DSL graph)
    graph_sub_agents: dict[str, GraphDef] = field(default_factory=dict)
    # {"research_and_code": GraphDef(...)}

    # Sub-agent references (new style — just names)
    sub_agent_refs: list[str] = field(default_factory=list)
    # ["code_writer", "research_and_code"]

    # Tools — global whitelist for this agent
    tools: list[str] = field(default_factory=list)

    # Prompts
    prompts: dict[str, str] = field(default_factory=dict)
    # {"classify": "...", "respond": "...", "code_writer": "..."}

    # Memory
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)

    @classmethod
    def from_dict(cls, data: dict) -> AgentDef:
        """Build AgentDef from a dict (e.g. parsed from YAML)."""
        sub_agents = {}
        decl_sub_agents = {}
        graph_sub_agents = {}
        for name, sd in data.get("sub_agents", {}).items():
            if "graph" in sd:
                from artipivot.graph.dsl import parse_graph_def

                graph_sub_agents[name] = parse_graph_def(name, sd["graph"])
            elif sd.get("strategy"):
                decl_sub_agents[name] = DeclarativeSubAgentDef(
                    name=name,
                    strategy=sd["strategy"],
                    tools=sd.get("tools", []),
                    system_prompt=sd.get("system_prompt", ""),
                    strategy_config=sd.get("strategy_config", {}),
                )
            else:
                sub_agents[name] = SubAgentDef(
                    name=name,
                    tools=sd.get("tools", []),
                    system_prompt=sd.get("system_prompt", ""),
                    max_iterations=sd.get("strategy_config", {}).get("max_iterations", 10),
                )

        routing = data.get("routing", {})
        mem_data = data.get("memory", {})

        # Normalize intents: support both simple (str) and rich (dict with target+description)
        raw_intents = routing.get("intents", {})
        intent_map = {}
        intent_descriptions = {}
        for intent, value in raw_intents.items():
            if isinstance(value, str):
                intent_map[intent] = value
            elif isinstance(value, dict):
                intent_map[intent] = value.get("target", "")
                if value.get("description"):
                    intent_descriptions[intent] = value["description"]

        # Backward compat: populate sub_agent_refs from old-style dict keys
        all_sub_names = (
            set(sub_agents) | set(decl_sub_agents) | set(graph_sub_agents)
        )
        sub_agent_refs = list(all_sub_names)

        return cls(
            agent_id=data["agent_id"],
            model=data.get("model", {}),
            confidence_threshold=routing.get("confidence_threshold", 0.7),
            intent_map=intent_map,
            intent_descriptions=intent_descriptions,
            sub_agents=sub_agents,
            declarative_sub_agents=decl_sub_agents,
            graph_sub_agents=graph_sub_agents,
            sub_agent_refs=sub_agent_refs,
            tools=data.get("tools", []),
            prompts=data.get("prompts", {}),
            memory_config=MemoryConfig.from_dict(mem_data) if mem_data else MemoryConfig(),
        )

    def to_dict(self) -> dict:
        """Serialize AgentDef to dict."""
        return {
            "agent_id": self.agent_id,
            "model": self.model,
            "confidence_threshold": self.confidence_threshold,
            "intent_map": self.intent_map,
            "sub_agents": {
                n: {"tools": s.tools, "system_prompt": s.system_prompt, "max_iterations": s.max_iterations}
                for n, s in self.sub_agents.items()
            },
            "declarative_sub_agents": {
                n: {"strategy": d.strategy, "tools": d.tools, "system_prompt": d.system_prompt, "strategy_config": d.strategy_config}
                for n, d in self.declarative_sub_agents.items()
            },
            "graph_sub_agents": {
                n: {"name": g.name, "nodes": len(g.nodes), "edges": len(g.edges)}
                for n, g in self.graph_sub_agents.items()
            },
            "sub_agent_refs": self.sub_agent_refs,
            "tools": self.tools,
            "prompts": self.prompts,
        }
