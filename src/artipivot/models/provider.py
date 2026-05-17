"""ModelProvider — dynamic model resolution with fallback chain."""

from __future__ import annotations

import threading
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel

from artipivot.models.config import ModelConfig
from artipivot.storage.base import ChangeNotifier, DocumentStore


def _factory_anthropic(cfg: ModelConfig) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    kwargs: dict = {
        "model": cfg.name,
        "temperature": cfg.temperature,
        "timeout": cfg.timeout,
    }
    if cfg.max_tokens is not None:
        kwargs["max_tokens"] = cfg.max_tokens
    if cfg.base_url:
        kwargs["anthropic_api_url"] = cfg.base_url
    if cfg.api_key:
        kwargs["anthropic_api_key"] = cfg.api_key
    return ChatAnthropic(**kwargs)


def _factory_openai(cfg: ModelConfig) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    kwargs: dict = {
        "model": cfg.name,
        "temperature": cfg.temperature,
        "timeout": cfg.timeout,
    }
    if cfg.max_tokens is not None:
        kwargs["max_tokens"] = cfg.max_tokens
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    if cfg.api_key:
        kwargs["api_key"] = cfg.api_key
    return ChatOpenAI(**kwargs)


class ModelProvider:
    """Model resolution + fallback chain + dynamic hot-reload."""

    def __init__(self, store: DocumentStore, notifier: ChangeNotifier) -> None:
        self._store = store
        self._notifier = notifier
        self._lock = threading.RLock()

        self._agent_models: dict[str, ModelConfig] = {}
        self._sub_models: dict[str, ModelConfig] = {}  # "agent_id:sub_name"
        self._user_models: dict[str, ModelConfig] = {}  # "agent_id:user_id"
        self._global_fallback: ModelConfig | None = None

        self._factories: dict[str, Callable[[ModelConfig], BaseChatModel]] = {
            "anthropic": _factory_anthropic,
            "openai": _factory_openai,
        }

    async def start(self) -> None:
        """Load all configs from DocumentStore + subscribe to changes."""
        await self._load_all()
        await self._notifier.subscribe("model_configs", self._on_change)

    async def _load_all(self) -> None:
        docs = await self._store.query("model_configs", {})
        with self._lock:
            for doc in docs:
                self._apply_doc(doc)

    async def _on_change(
        self, collection: str, key: str, action: str, data: dict
    ) -> None:
        with self._lock:
            self._apply_doc(data)

    def _apply_doc(self, doc: dict) -> None:
        match doc.get("scope"):
            case "global":
                fb = doc.get("fallback_model")
                if fb:
                    self._global_fallback = ModelConfig(**fb)
            case "agent":
                model = doc.get("model")
                if model:
                    agent_id = doc["agent_id"]
                    self._agent_models[agent_id] = ModelConfig(**model)
            case "sub_agent":
                model = doc.get("model")
                if model:
                    key = f"{doc['agent_id']}:{doc['sub_agent']}"
                    self._sub_models[key] = ModelConfig(**model)
            case "user":
                model = doc.get("model")
                if model:
                    key = f"{doc['agent_id']}:{doc['user_id']}"
                    self._user_models[key] = ModelConfig(**model)

    # ── Management API ──

    async def update_agent_model(self, agent_id: str, model: dict) -> None:
        doc = {"scope": "agent", "agent_id": agent_id, "model": model}
        await self._store.put("model_configs", f"agent:{agent_id}", doc)
        with self._lock:
            self._apply_doc(doc)

    async def update_sub_model(
        self, agent_id: str, sub_name: str, model: dict
    ) -> None:
        doc = {
            "scope": "sub_agent",
            "agent_id": agent_id,
            "sub_agent": sub_name,
            "model": model,
        }
        await self._store.put(
            "model_configs", f"sub_agent:{agent_id}:{sub_name}", doc
        )
        with self._lock:
            self._apply_doc(doc)

    async def update_user_model(
        self, user_id: str, model: dict, agent_id: str | None = None
    ) -> None:
        """Set user-level model config. agent_id=None means user global."""
        effective_agent = agent_id or "__global__"
        doc = {
            "scope": "user",
            "agent_id": effective_agent,
            "user_id": user_id,
            "model": model,
        }
        await self._store.put(
            "model_configs", f"user:{effective_agent}:{user_id}", doc
        )
        with self._lock:
            self._apply_doc(doc)

    async def delete_user_model(
        self, user_id: str, agent_id: str | None = None
    ) -> None:
        """Remove user-level model config."""
        effective_agent = agent_id or "__global__"
        key = f"user:{effective_agent}:{user_id}"
        with self._lock:
            self._user_models.pop(f"{effective_agent}:{user_id}", None)
        await self._store.delete("model_configs", key)

    def get_user_model_config(
        self, user_id: str, agent_id: str | None = None
    ) -> ModelConfig | None:
        """Read current user-level model config (for API queries)."""
        effective_agent = agent_id or "__global__"
        return self._user_models.get(f"{effective_agent}:{user_id}")

    # ── Runtime resolution ──

    def get_model(
        self, agent_id: str, sub_name: str | None = None, user_id: str | None = None
    ) -> BaseChatModel:
        """Resolve model instance with fallback chain.

        Resolution order: user:agent → user:global → agent → global_fallback.
        """
        with self._lock:
            if (
                user_id
                and f"{agent_id}:{user_id}" in self._user_models
            ):
                cfg = self._user_models[f"{agent_id}:{user_id}"]
            elif (
                user_id
                and f"__global__:{user_id}" in self._user_models
            ):
                cfg = self._user_models[f"__global__:{user_id}"]
            elif (
                sub_name
                and f"{agent_id}:{sub_name}" in self._sub_models
            ):
                cfg = self._sub_models[f"{agent_id}:{sub_name}"]
            elif agent_id in self._agent_models:
                cfg = self._agent_models[agent_id]
            elif self._global_fallback is not None:
                cfg = self._global_fallback
            else:
                raise ValueError(f"No model config for agent={agent_id}")

            chain = self._build_chain(cfg)

        for model_cfg in chain:
            try:
                factory = self._factories[model_cfg.provider]
                return factory(model_cfg)
            except Exception:
                continue

        raise RuntimeError(
            f"All models unavailable: agent={agent_id}, sub={sub_name}"
        )

    def _build_chain(self, cfg: ModelConfig) -> list[ModelConfig]:
        chain = [cfg]
        current = cfg
        while current.fallback:
            chain.append(current.fallback)
            current = current.fallback
        if self._global_fallback and chain[-1] != self._global_fallback:
            chain.append(self._global_fallback)
        return chain
