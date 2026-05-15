"""AgentDef — unified agent definition data structure."""

from __future__ import annotations

from dataclasses import dataclass, field

from artipivot.agents.base import SubAgentDef
from artipivot.agents.declarative import DeclarativeSubAgentDef
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

    # Sub-agents (programmatic)
    sub_agents: dict[str, SubAgentDef] = field(default_factory=dict)
    # {"code_writer": SubAgentDef(...)}

    # Sub-agents (declarative)
    declarative_sub_agents: dict[str, DeclarativeSubAgentDef] = field(default_factory=dict)
    # {"code_writer": DeclarativeSubAgentDef(...)}

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
        for name, sd in data.get("sub_agents", {}).items():
            sub_agents[name] = SubAgentDef(
                name=name,
                tools=sd.get("tools", []),
                system_prompt=sd.get("system_prompt", ""),
                max_iterations=sd.get("strategy_config", {}).get("max_iterations", 10),
            )

        decl_sub_agents = {}
        for name, sd in data.get("sub_agents", {}).items():
            strategy = sd.get("strategy")
            if strategy:
                decl_sub_agents[name] = DeclarativeSubAgentDef(
                    name=name,
                    strategy=strategy,
                    tools=sd.get("tools", []),
                    system_prompt=sd.get("system_prompt", ""),
                    strategy_config=sd.get("strategy_config", {}),
                )

        routing = data.get("routing", {})
        mem_data = data.get("memory", {})

        return cls(
            agent_id=data["agent_id"],
            model=data.get("model", {}),
            confidence_threshold=routing.get("confidence_threshold", 0.7),
            intent_map=routing.get("intents", {}),
            sub_agents=sub_agents,
            declarative_sub_agents=decl_sub_agents,
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
            "tools": self.tools,
            "prompts": self.prompts,
        }
