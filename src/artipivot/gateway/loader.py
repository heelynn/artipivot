"""Multi-agent YAML loader — load AgentDefs from agents.yaml."""

from __future__ import annotations

from pathlib import Path

from artipivot.gateway.agent_def import AgentDef


def load_agent_defs(seed_dir: str | Path = "config/seed") -> dict[str, AgentDef]:
    """Load agent definitions from agents.yaml.

    Returns:
        dict mapping agent_id → AgentDef
    """
    import yaml

    path = Path(seed_dir) / "agents.yaml"
    if not path.exists():
        return {}

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or "agents" not in data:
        return {}

    result = {}
    for agent_id, cfg in data["agents"].items():
        cfg["agent_id"] = agent_id
        result[agent_id] = AgentDef.from_dict(cfg)

    return result
