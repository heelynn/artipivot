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

    return loaded


async def _load_models(store: DocumentStore, data: dict) -> None:
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
