"""YAML seed loader for declarative sub-agent definitions."""

from __future__ import annotations

from pathlib import Path

import yaml

from artipivot.agents.declarative import DeclarativeSubAgentDef


def load_sub_agent_defs(
    seed_dir: str | Path = "config/seed",
) -> dict[str, DeclarativeSubAgentDef]:
    """Load sub-agent definitions from sub_agents.yaml.

    Returns a dict mapping sub-agent name to DeclarativeSubAgentDef.
    """
    path = Path(seed_dir) / "sub_agents.yaml"
    if not path.exists():
        return {}

    data = yaml.safe_load(path.read_text())
    if not data or "sub_agents" not in data:
        return {}

    result: dict[str, DeclarativeSubAgentDef] = {}
    for name, cfg in data["sub_agents"].items():
        result[name] = DeclarativeSubAgentDef(
            name=name,
            strategy=cfg["strategy"],
            tools=cfg.get("tools", []),
            system_prompt=cfg.get("system_prompt", ""),
            strategy_config=cfg.get("strategy_config", {}),
        )
    return result
