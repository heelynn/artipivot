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


def _factory_deepseek(cfg: ModelConfig) -> BaseChatModel:
    kwargs: dict = {
        "model": cfg.name,
        "temperature": cfg.temperature,
        "timeout": cfg.timeout,
    }
    if cfg.max_tokens is not None:
        kwargs["max_tokens"] = cfg.max_tokens
    if cfg.api_key:
        kwargs["api_key"] = cfg.api_key
    if cfg.base_url:
        kwargs["api_base"] = cfg.base_url
    return _PatchedChatDeepSeek(**kwargs)


def _deepseek_get_request_payload(self, input_, *, stop=None, **kwargs):
    """Override that injects ``reasoning_content`` back into assistant messages.

    DeepSeek thinking models return ``reasoning_content`` in
    ``AIMessage.additional_kwargs``.  The upstream ``_convert_message_to_dict``
    drops it when building the next request, causing a 400 error.
    """
    from langchain_core.messages import AIMessage, BaseMessage
    from langchain_core.prompt_values import (
        ChatPromptValue,
        ChatPromptValueConcrete,
        StringPromptValue,
    )

    # ── recover original message objects ──
    raw_messages: list[BaseMessage] = []
    if isinstance(input_, list):
        for m in input_:
            if isinstance(m, BaseMessage):
                raw_messages.append(m)
            else:
                raw_messages.append(BaseMessage(content=str(m)))
    elif isinstance(input_, (ChatPromptValue, ChatPromptValueConcrete, StringPromptValue)):
        raw_messages = input_.to_messages()

    payload = self.__class__.__bases__[0]._get_request_payload(self, input_, stop=stop, **kwargs)
    payload_msgs = payload.get("messages", [])

    for i, pmsg in enumerate(payload_msgs):
        if pmsg.get("role") != "assistant":
            continue
        if i >= len(raw_messages):
            break
        rc = raw_messages[i].additional_kwargs.get("reasoning_content")
        if rc and "reasoning_content" not in pmsg:
            pmsg["reasoning_content"] = rc

    return payload


def _make_patched_deepseek_cls():
    from langchain_deepseek import ChatDeepSeek

    return type(
        "_PatchedChatDeepSeek",
        (ChatDeepSeek,),
        {"_get_request_payload": _deepseek_get_request_payload},
    )


_PatchedChatDeepSeek = _make_patched_deepseek_cls()


class _CircuitWrappedModel:
    """Proxy that wraps model.ainvoke through a circuit breaker.

    All other attribute access delegates to the underlying model.
    """

    def __init__(self, model: BaseChatModel, circuit) -> None:
        self._model = model
        self._circuit = circuit

    def __getattr__(self, name: str):
        if name in ("_model", "_circuit"):
            raise AttributeError(name)
        return getattr(self._model, name)

    async def ainvoke(self, *args, **kwargs):
        return await self._circuit.call(self._model.ainvoke, *args, **kwargs)


class ModelProvider:
    """Model resolution + fallback chain + dynamic hot-reload."""

    def __init__(
        self,
        store: DocumentStore,
        notifier: ChangeNotifier,
        *,
        circuit_registry=None,
    ) -> None:
        self._store = store
        self._notifier = notifier
        self._lock = threading.RLock()
        self._circuit_registry = circuit_registry

        self._agent_models: dict[str, ModelConfig] = {}
        self._sub_models: dict[str, ModelConfig] = {}  # "agent_id:sub_name"
        self._user_models: dict[str, ModelConfig] = {}  # "agent_id:user_id"
        self._global_fallback: ModelConfig | None = None
        self._circuit_configs: dict[str, object] = {}  # agent_id → CircuitConfig

        self._factories: dict[str, Callable[[ModelConfig], BaseChatModel]] = {
            "anthropic": _factory_anthropic,
            "openai": _factory_openai,
            "deepseek": _factory_deepseek,
        }

    def set_circuit_config(self, agent_id: str, circuit_config) -> None:
        """Set per-agent circuit breaker config (called by AgentRegistry)."""
        self._circuit_configs[agent_id] = circuit_config

    def load_from_manifest(self, manifest) -> None:
        """Populate model configs directly from an AgentManifest (no DocumentStore).

        Called at startup. After this, start() still subscribes to
        DocumentStore changes for runtime Admin API hot-reloads.
        """
        from artipivot.gateway.loader import AgentManifest

        with self._lock:
            if manifest.global_model:
                self._global_fallback = ModelConfig(**manifest.global_model)

            for agent_def in manifest.agents.values():
                if agent_def.model:
                    self._agent_models[agent_def.agent_id] = ModelConfig(
                        **agent_def.model
                    )

                    # Store circuit config per agent
                    self._circuit_configs[agent_def.agent_id] = agent_def.circuit

                    # Sub-agents inherit the main agent's model by default
                    for sub_name in agent_def.declarative_sub_agents:
                        key = f"{agent_def.agent_id}:{sub_name}"
                        if key not in self._sub_models:
                            self._sub_models[key] = ModelConfig(**agent_def.model)
                    for sub_name in agent_def.sub_agents:
                        key = f"{agent_def.agent_id}:{sub_name}"
                        if key not in self._sub_models:
                            self._sub_models[key] = ModelConfig(**agent_def.model)

    async def start(self) -> None:
        """Load any existing DocumentStore configs + subscribe to runtime changes.

        On first startup with the manifest-based approach, DocumentStore is
        empty so _load_all() is a no-op. On subsequent restarts with a
        persistent backend, runtime Admin API changes are reloaded.
        """
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
                model = factory(model_cfg)
                return self._wrap_circuit(agent_id, model_cfg.provider, model)
            except Exception:
                continue

        raise RuntimeError(
            f"All models unavailable: agent={agent_id}, sub={sub_name}"
        )

    def _wrap_circuit(
        self, agent_id: str, provider: str, model: BaseChatModel
    ) -> BaseChatModel:
        """Wrap a model with circuit breaker if enabled for the agent."""
        if self._circuit_registry is None:
            return model

        circuit_cfg = self._circuit_configs.get(agent_id)
        if circuit_cfg is None or not getattr(circuit_cfg, "enabled", True):
            return model

        cb = self._circuit_registry.get_or_create(
            provider,
            failure_threshold=getattr(circuit_cfg, "failure_threshold", 5),
            recovery_timeout=getattr(circuit_cfg, "recovery_timeout", 60.0),
        )
        return _CircuitWrappedModel(model, cb)

    def _build_chain(self, cfg: ModelConfig) -> list[ModelConfig]:
        chain = [cfg]
        current = cfg
        while current.fallback:
            chain.append(current.fallback)
            current = current.fallback
        if self._global_fallback and chain[-1] != self._global_fallback:
            chain.append(self._global_fallback)
        return chain
