"""YAML seed loader for declarative sub-agent definitions."""

from __future__ import annotations

from pathlib import Path

import yaml

from artipivot.agents.declarative import DeclarativeSubAgentDef
from artipivot.graph.dsl import GraphDef, parse_graph_def


def load_sub_agent_defs(
    seed_dir: str | Path = "config/seed",
) -> dict[str, DeclarativeSubAgentDef | GraphDef]:
    """Load sub-agent definitions from sub_agents.yaml.

    Entries with a ``graph:`` key are parsed as GraphDef (DSL graph).
    Entries with a ``strategy:`` key are parsed as DeclarativeSubAgentDef.
    Backward compatible — existing configs work unchanged.

    Returns a dict mapping sub-agent name to its definition.
    """
    path = Path(seed_dir) / "sub_agents.yaml"
    if not path.exists():
        return {}

    data = yaml.safe_load(path.read_text())
    if not data or "sub_agents" not in data:
        return {}

    result: dict[str, DeclarativeSubAgentDef | GraphDef] = {}
    for name, cfg in data["sub_agents"].items():
        if "graph" in cfg:
            result[name] = parse_graph_def(name, cfg["graph"])
        else:
            result[name] = DeclarativeSubAgentDef(
                name=name,
                strategy=cfg["strategy"],
                tools=cfg.get("tools", []),
                system_prompt=cfg.get("system_prompt", ""),
                strategy_config=cfg.get("strategy_config", {}),
            )
    return result
