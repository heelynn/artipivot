"""Agent manifest loader — read agents.yaml directly into structured objects.

No DocumentStore involved. This is the primary startup path.

Supports two modes:
  - Single file: .agents.yaml (backward compatible)
  - Directory: manifests/ with agents/*.yaml + sub_agents.yaml + tools.yaml
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
class SubAgentDefRecord:
    """Sub-agent definition — stored in DocumentStore "sub_agents" collection."""
    name: str
    strategy: str = "react"            # "react" | "function_calling" | "dsl"
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    strategy_config: dict = field(default_factory=dict)
    graph: dict | None = None           # DSL graph definition
    status: str = "active"


@dataclass
class AgentManifest:
    """Complete startup manifest — everything needed to build all agents.

    Parsed directly from YAML on every startup.
    """
    global_model: dict | None = None
    tools: list[ToolDef] = field(default_factory=list)
    sub_agents: list[SubAgentDefRecord] = field(default_factory=list)
    agents: dict[str, AgentDef] = field(default_factory=dict)
    memory: dict = field(default_factory=dict)


def load_agent_manifest(path: str | Path = ".agents.yaml") -> AgentManifest:
    """Load an agent manifest from a file or directory.

    The path can be:
      - A single file (.agents.yaml) — backward compatible
      - A directory (manifests/) — scans agents/*.yaml, tools.yaml, sub_agents.yaml

    Override via ``ARTIPIVOT_AGENTS_MANIFEST`` env var or ``--manifest`` CLI flag.
    """
    import yaml

    p = Path(path)

    # ── Directory mode ──
    if p.is_dir():
        # New manifest directory: agents/*.yaml + tools.yaml + sub_agents.yaml
        if (p / "agents").is_dir():
            return _load_from_dir(p)
        # Old style: agents.yaml inside a directory (backward compat)
        legacy = p / "agents.yaml"
        if legacy.exists():
            data = yaml.safe_load(legacy.read_text())
            if data:
                return _parse_manifest(data)
        return AgentManifest()

    # ── Single file mode (backward compatible) ──
    if not p.exists():
        return AgentManifest()

    data = yaml.safe_load(p.read_text())
    if not data:
        return AgentManifest()
    return _parse_manifest(data)


def load_agent_defs(path: str | Path = ".agents.yaml") -> dict[str, AgentDef]:
    """Load agent definitions from a YAML file (backward-compatible wrapper)."""
    return load_agent_manifest(path).agents


# ── Internal: directory mode ──


def _load_from_dir(manifest_dir: Path) -> AgentManifest:
    """Scan a manifest directory and merge all files into an AgentManifest."""
    import yaml

    manifest = AgentManifest()

    # ── settings.yaml (optional: memory, storage, global) ──
    settings_path = manifest_dir / "settings.yaml"
    settings_data = {}
    if settings_path.exists():
        settings_data = yaml.safe_load(settings_path.read_text()) or {}

    # ── agents/*.yaml ──
    agents_dir = manifest_dir / "agents"
    if agents_dir.is_dir():
        for agent_file in sorted(agents_dir.glob("*.yaml")):
            _cfg = yaml.safe_load(agent_file.read_text())
            if _cfg:
                agent_id = _cfg.get("agent_id") or agent_file.stem
                _cfg["agent_id"] = agent_id
                manifest.agents[agent_id] = AgentDef.from_dict(_cfg)

    # ── tools.yaml ──
    tools_path = manifest_dir / "tools.yaml"
    if tools_path.exists():
        tools_data = yaml.safe_load(tools_path.read_text())
        if tools_data:
            manifest.tools = _parse_tools(tools_data.get("tools", {}))

    # ── sub_agents.yaml ──
    sub_path = manifest_dir / "sub_agents.yaml"
    if sub_path.exists():
        sub_data = yaml.safe_load(sub_path.read_text())
        if sub_data:
            manifest.sub_agents = _parse_sub_agents(sub_data.get("sub_agents", {}))

    # ── Global settings ──
    global_cfg = settings_data.get("global", {})
    if global_cfg.get("fallback_model"):
        manifest.global_model = dict(global_cfg["fallback_model"])
    manifest.memory = settings_data.get("memory", {})

    return manifest


# ── Internal: single file mode (backward compatible) ──


def _parse_manifest(data: dict) -> AgentManifest:
    """Parse a single agents.yaml dict into AgentManifest."""
    manifest = AgentManifest()

    # ── global ──
    global_cfg = data.get("global", {})
    if global_cfg.get("fallback_model"):
        manifest.global_model = dict(global_cfg["fallback_model"])

    # ── tools ──
    tools_cfg = data.get("tools", {})
    manifest.tools = _parse_tools(tools_cfg)

    # ── sub_agents ──
    sub_cfg = data.get("sub_agents", {})
    manifest.sub_agents = _parse_sub_agents(sub_cfg)

    # ── memory ──
    manifest.memory = data.get("memory", {})

    # ── agents ──
    for agent_id, cfg in data.get("agents", {}).items():
        cfg["agent_id"] = agent_id
        manifest.agents[agent_id] = AgentDef.from_dict(cfg)

    return manifest


# ── Internal: parse helpers ──


def _parse_tools(tools_cfg: dict) -> list[ToolDef]:
    """Parse a tools section dict into ToolDef list."""
    result: list[ToolDef] = []
    for tool_name, tool_cfg in tools_cfg.items():
        if isinstance(tool_cfg, str):
            # Shorthand: "web_search: builtin"
            tool_cfg = {"type": tool_cfg}
        result.append(ToolDef(
            name=tool_name,
            type=tool_cfg.get("type", "builtin"),
            module=tool_cfg.get("module"),
            function=tool_cfg.get("function"),
            config=tool_cfg.get("config", {}),
        ))
    return result


def _parse_sub_agents(sub_cfg: dict) -> list[SubAgentDefRecord]:
    """Parse a sub_agents section dict into SubAgentDefRecord list."""
    result: list[SubAgentDefRecord] = []
    for name, cfg in sub_cfg.items():
        result.append(SubAgentDefRecord(
            name=name,
            strategy=cfg.get("strategy", "react"),
            tools=cfg.get("tools", []),
            system_prompt=cfg.get("system_prompt", ""),
            strategy_config=cfg.get("strategy_config", {}),
            graph=cfg.get("graph"),
        ))
    return result
