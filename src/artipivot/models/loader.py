"""YAML seed loader — loads initial config into DocumentStore on first run."""

from __future__ import annotations

from pathlib import Path

import yaml

from artipivot.storage.base import DocumentStore


async def load_seed_if_empty(
    store: DocumentStore,
    seed_dir: str | Path = "config/seed",
) -> bool:
    """Load YAML seed files into DocumentStore if collections are empty.

    Returns True if any data was loaded.
    """
    seed_path = Path(seed_dir)
    if not seed_path.exists():
        return False

    loaded = False

    # models.yaml → model_configs
    models_file = seed_path / "models.yaml"
    if models_file.exists():
        docs = await store.query("model_configs", {})
        if not docs:
            data = yaml.safe_load(models_file.read_text())
            if data:
                await _load_models(store, data)
                loaded = True

    # routing.yaml → routing_configs
    routing_file = seed_path / "routing.yaml"
    if routing_file.exists():
        docs = await store.query("routing_configs", {})
        if not docs:
            data = yaml.safe_load(routing_file.read_text())
            if data:
                for agent_id, cfg in data.get("agents", {}).items():
                    cfg["agent_id"] = agent_id
                    await store.put("routing_configs", agent_id, cfg)
                loaded = True

    # prompts.yaml → prompt_configs
    prompts_file = seed_path / "prompts.yaml"
    if prompts_file.exists():
        docs = await store.query("prompt_configs", {})
        if not docs:
            data = yaml.safe_load(prompts_file.read_text())
            if data:
                for prompt_id, cfg in data.get("prompts", {}).items():
                    cfg["_id"] = prompt_id
                    await store.put("prompt_configs", prompt_id, cfg)
                loaded = True

    # agents.yaml → model_configs + routing_configs + prompt_configs + agent_configs
    agents_file = seed_path / "agents.yaml"
    if agents_file.exists():
        docs = await store.query("agent_configs", {})
        if not docs:
            data = yaml.safe_load(agents_file.read_text())
            if data:
                await _load_agents(store, data)
                loaded = True

    # sub_agents.yaml → sub_agent_configs
    sub_agents_file = seed_path / "sub_agents.yaml"
    if sub_agents_file.exists():
        docs = await store.query("sub_agent_configs", {})
        if not docs:
            data = yaml.safe_load(sub_agents_file.read_text())
            if data:
                for name, cfg in data.get("sub_agents", {}).items():
                    cfg["name"] = name
                    await store.put("sub_agent_configs", name, cfg)
                loaded = True

    return loaded


# ── Internal helpers ──


async def _load_models(store, data):
    global_cfg = data.get("global", {})
    if global_cfg.get("fallback_model"):
        await store.put(
            "model_configs",
            "global",
            {"scope": "global", "fallback_model": global_cfg["fallback_model"]},
        )

    for agent_id, agent_cfg in data.get("agents", {}).items():
        model = {
            k: v
            for k, v in agent_cfg.items()
            if k
            in (
                "provider",
                "name",
                "temperature",
                "timeout",
                "max_tokens",
                "base_url",
                "api_key",
            )
        }
        await store.put(
            "model_configs",
            f"agent:{agent_id}",
            {"scope": "agent", "agent_id": agent_id, "model": model},
        )

        for sub_name, sub_cfg in agent_cfg.get("sub_agents", {}).items():
            await store.put(
                "model_configs",
                f"sub_agent:{agent_id}:{sub_name}",
                {
                    "scope": "sub_agent",
                    "agent_id": agent_id,
                    "sub_agent": sub_name,
                    "model": sub_cfg,
                },
            )


async def _load_agents(store, data):
    """Load agents.yaml — comprehensive single-file agent definitions.

    Each agent entry contains model, routing, sub_agents, tools, and prompts.
    The data is distributed into the appropriate collections.
    """
    for agent_id, agent_cfg in data.get("agents", {}).items():
        # Model config
        model_fields = {
            k: v
            for k, v in agent_cfg.get("model", {}).items()
            if k
            in (
                "provider",
                "name",
                "temperature",
                "timeout",
                "max_tokens",
                "base_url",
                "api_key",
            )
        }
        if model_fields:
            await store.put(
                "model_configs",
                f"agent:{agent_id}",
                {"scope": "agent", "agent_id": agent_id, "model": model_fields},
            )

        # Routing config
        routing = agent_cfg.get("routing", {})
        if routing:
            await store.put(
                "routing_configs",
                agent_id,
                {
                    "agent_id": agent_id,
                    "confidence_threshold": routing.get("confidence_threshold", 0.7),
                    "intents": [
                        {"name": k, "sub_agent": v}
                        for k, v in routing.get("intents", {}).items()
                    ],
                },
            )

        # Prompt configs
        prompts = agent_cfg.get("prompts", {})
        if prompts:
            for node_name, template in prompts.items():
                prompt_id = f"{agent_id}:{node_name}"
                await store.put(
                    "prompt_configs",
                    prompt_id,
                    {"_id": prompt_id, "system": template},
                )

        # Agent config (retained for bootstrap to build agents from)
        await store.put("agent_configs", agent_id, {
            "agent_id": agent_id,
            "model": agent_cfg.get("model", {}),
            "tools": agent_cfg.get("tools", []),
            "sub_agent_refs": list(agent_cfg.get("sub_agents", {}).keys()),
            "confidence_threshold": routing.get("confidence_threshold", 0.7),
            "intent_map": routing.get("intents", {}),
            "prompts": agent_cfg.get("prompts", {}),
            "memory_config": agent_cfg.get("memory_config", {}),
        })

        # Sub-agent definitions → sub_agent_configs
        for sub_name, sub_cfg in agent_cfg.get("sub_agents", {}).items():
            await store.put(
                "model_configs",
                f"sub_agent:{agent_id}:{sub_name}",
                {
                    "scope": "sub_agent",
                    "agent_id": agent_id,
                    "sub_agent": sub_name,
                    "model": model_fields,
                },
            )
            await store.put("sub_agent_configs", f"{agent_id}:{sub_name}", {
                "name": sub_name,
                "agent_id": agent_id,
                "strategy": sub_cfg.get("strategy", "react"),
                "tools": sub_cfg.get("tools", []),
                "system_prompt": sub_cfg.get("system_prompt", ""),
                "strategy_config": sub_cfg.get("strategy_config", {}),
                "graph": sub_cfg.get("graph"),
            })
