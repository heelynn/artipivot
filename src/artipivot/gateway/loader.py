"""Agent manifest loader — read agents.yaml directly into structured objects.

No DocumentStore involved. This is the primary startup path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from artipivot.gateway.agent_def import AgentDef


@dataclass
class ToolDef:
    """Tool definition parsed from YAML."""
    name: str
    type: str = "builtin"       # "builtin" | "module"
    module: str | None = None   # for type=module
    function: str | None = None  # for type=module
    config: dict = field(default_factory=dict)


@dataclass
class AgentManifest:
    """Complete startup manifest — everything needed to build all agents.

    Parsed directly from agents.yaml on every startup.
    """
    global_model: dict | None = None
    tools: list[ToolDef] = field(default_factory=list)
    agents: dict[str, AgentDef] = field(default_factory=dict)


def load_agent_manifest(path: str | Path = ".agents.yaml") -> AgentManifest:
    """Load an agent manifest YAML file directly into an AgentManifest.

    The path can be:
      - A file path (e.g. ``.agents.yaml``, ``/etc/artipivot/agents.yaml``)
      - A directory (backward compat — looks for ``agents.yaml`` inside)

    No DocumentStore round-trip — YAML is parsed straight into
    ToolDef + AgentDef objects, ready to build and register.

    The default path is ``.agents.yaml`` in the current working directory.
    Override via ``ARTIPIVOT_AGENTS_MANIFEST`` env var or ``--manifest`` CLI flag.

    Returns:
        AgentManifest with tools, global model, and agent definitions.
    """
    import yaml

    p = Path(path)
    if p.is_dir():
        p = p / "agents.yaml"
    if not p.exists():
        return AgentManifest()

    data = yaml.safe_load(p.read_text())
    if not data:
        return AgentManifest()

    manifest = AgentManifest()

    # ── global ──────────────────────────────────────────────────
    global_cfg = data.get("global", {})
    if global_cfg.get("fallback_model"):
        manifest.global_model = dict(global_cfg["fallback_model"])

    # ── tools ───────────────────────────────────────────────────
    tools_cfg = data.get("tools", {})
    for tool_name, tool_cfg in tools_cfg.items():
        if isinstance(tool_cfg, str):
            # Shorthand: "web_search: builtin"
            tool_cfg = {"type": tool_cfg}
        manifest.tools.append(ToolDef(
            name=tool_name,
            type=tool_cfg.get("type", "builtin"),
            module=tool_cfg.get("module"),
            function=tool_cfg.get("function"),
            config=tool_cfg.get("config", {}),
        ))

    # ── agents ──────────────────────────────────────────────────
    for agent_id, cfg in data.get("agents", {}).items():
        cfg["agent_id"] = agent_id
        manifest.agents[agent_id] = AgentDef.from_dict(cfg)

    return manifest


def load_agent_defs(path: str | Path = ".agents.yaml") -> dict[str, AgentDef]:
    """Load agent definitions from a YAML file (backward-compatible wrapper).

    Returns:
        dict mapping agent_id → AgentDef
    """
    return load_agent_manifest(path).agents
