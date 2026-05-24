"""AgentDef — unified agent definition data structure."""

from __future__ import annotations

from dataclasses import dataclass, field

from artipivot.agents.base import SubAgentDef
from artipivot.agents.declarative import DeclarativeSubAgentDef
from artipivot.graph.dsl import GraphDef
from artipivot.memory.config import MemoryConfig


@dataclass
class CircuitConfig:
    """Per-agent circuit breaker configuration."""

    enabled: bool = True
    failure_threshold: int = 5           # 连续失败 N 次 → 熔断
    recovery_timeout: float = 60.0       # 冷却时间（秒）


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

    # Sub-agent references
    # Can be bare strings ("code_writer") or dicts with public/private flag:
    #   {name: "code_writer", public: true}          — public pool reference
    #   {name: "my_analyzer", public: false, strategy: "react", ...} — private inline
    sub_agent_refs: list = field(default_factory=list)

    # Tools — global whitelist for this agent
    tools: list[str] = field(default_factory=list)

    # Prompts
    prompts: dict[str, str] = field(default_factory=dict)
    # {"classify": "...", "respond": "...", "code_writer": "..."}

    # Circuit breaker
    circuit: CircuitConfig = field(default_factory=CircuitConfig)

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

        # Parse sub_agent_refs — supports strings and dicts
        agent_id = data["agent_id"]
        raw_refs = data.get("sub_agent_refs", [])
        sub_agent_refs = []
        for ref in raw_refs:
            if isinstance(ref, str):
                # Bare string — backward compat (checks private then public)
                sub_agent_refs.append(ref)
            elif isinstance(ref, dict):
                name = ref.get("name", "")
                if not name:
                    continue
                if ref.get("public", True):
                    # Public pool reference — just the name
                    sub_agent_refs.append(name)
                else:
                    # Private sub-agent — namespace with agent_id, store inline def
                    ns_name = f"{agent_id}__{name}"
                    sub_agent_refs.append(ns_name)
                    if ref.get("graph"):
                        from artipivot.graph.dsl import parse_graph_def
                        graph_sub_agents[ns_name] = parse_graph_def(ns_name, ref["graph"])
                    elif ref.get("strategy"):
                        decl_sub_agents[ns_name] = DeclarativeSubAgentDef(
                            name=ns_name,
                            strategy=ref["strategy"],
                            tools=ref.get("tools", []),
                            system_prompt=ref.get("system_prompt", ""),
                            strategy_config=ref.get("strategy_config", {}),
                        )
                    else:
                        sub_agents[ns_name] = SubAgentDef(
                            name=ns_name,
                            tools=ref.get("tools", []),
                            system_prompt=ref.get("system_prompt", ""),
                            max_iterations=ref.get("strategy_config", {}).get("max_iterations", 10),
                        )
            else:
                sub_agent_refs.append(str(ref))

        # Backward compat: also include old-style inline def names
        old_style_names = (
            set(sub_agents) | set(decl_sub_agents) | set(graph_sub_agents)
        )
        for n in old_style_names:
            if n not in sub_agent_refs:
                sub_agent_refs.append(n)

        # Resolve intent_map targets: private (public:false) sub-agents get
        # namespaced names. Build mapping: clean_name → resolved_name.
        # Old-format inline defs stay as-is (bare names, backward compat).
        _name_map: dict[str, str] = {}
        for ref in raw_refs:
            if isinstance(ref, dict):
                nm = ref.get("name", "")
                if not nm:
                    continue
                if ref.get("public", True):
                    _name_map[nm] = nm
                else:
                    _name_map[nm] = f"{agent_id}__{nm}"

        # Update intent_map targets that match private sub-agent names
        for intent, target in list(intent_map.items()):
            if target in _name_map:
                intent_map[intent] = _name_map[target]

        # Circuit breaker config
        circuit_data = data.get("circuit", {})
        circuit = CircuitConfig(
            enabled=circuit_data.get("enabled", True),
            failure_threshold=circuit_data.get("failure_threshold", 5),
            recovery_timeout=circuit_data.get("recovery_timeout", 60.0),
        )

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
            circuit=circuit,
            memory_config=MemoryConfig.from_dict(mem_data) if mem_data else MemoryConfig(),
        )

    def to_dict(self) -> dict:
        """Serialize AgentDef to a dict compatible with from_dict().

        Returns a format that can be stored in DocumentStore and reconstructed
        via from_dict() without data loss. Also includes flat fields for
        frontend compatibility (confidence_threshold, intent_map).
        """
        # Build rich intents with descriptions
        intents = {}
        for intent, target in self.intent_map.items():
            entry: dict = {"target": target}
            desc = self.intent_descriptions.get(intent)
            if desc:
                entry["description"] = desc
            intents[intent] = entry

        # Build sub_agents dict — from_dict reads all types from one dict
        sub_agents = {}
        for n, s in self.sub_agents.items():
            sub_agents[n] = {
                "tools": s.tools,
                "system_prompt": s.system_prompt,
                "max_iterations": s.max_iterations,
            }
        for n, d in self.declarative_sub_agents.items():
            sub_agents[n] = {
                "strategy": d.strategy,
                "tools": d.tools,
                "system_prompt": d.system_prompt,
                "strategy_config": d.strategy_config,
            }
        for n, g in self.graph_sub_agents.items():
            sub_agents[n] = {"graph": g.to_dict()}

        mc = self.memory_config
        return {
            "agent_id": self.agent_id,
            "model": self.model,
            "routing": {
                "intents": intents,
                "confidence_threshold": self.confidence_threshold,
            },
            "sub_agents": sub_agents,
            "sub_agent_refs": self.sub_agent_refs,
            "tools": self.tools,
            "prompts": self.prompts,
            "circuit": {
                "enabled": self.circuit.enabled,
                "failure_threshold": self.circuit.failure_threshold,
                "recovery_timeout": self.circuit.recovery_timeout,
            },
            "memory": {
                "l2": mc.l2,
                "l3": mc.l3,
                "embedding": {"enabled": mc.embedding.enabled},
                "context_window": {
                    "enabled": mc.context_window.enabled,
                    "strategy": mc.context_window.strategy,
                    "trigger_tokens": mc.context_window.trigger_tokens,
                    "keep_messages": mc.context_window.keep_messages,
                },
                "extraction": {
                    "enabled": mc.extraction.enabled,
                    "max_messages": mc.extraction.max_messages,
                    "write_on": mc.extraction.write_on,
                },
                "retention": {
                    "knowledge_ttl_days": mc.retention.knowledge_ttl_days,
                    "max_items_per_namespace": mc.retention.max_items_per_namespace,
                },
            },
            # Flat fields for frontend backward compat
            "confidence_threshold": self.confidence_threshold,
            "intent_map": self.intent_map,
        }
