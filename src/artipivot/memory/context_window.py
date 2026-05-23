"""Context window management — summarize, trim, or custom compress long conversations."""

from __future__ import annotations

import importlib
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from artipivot.memory.config import ContextWindowConfig

log = logging.getLogger(__name__)

# Built-in summarize prompt
_SUMMARIZE_PROMPT = (
    "请用简洁的中文总结以下对话的关键信息（包括用户需求、已完成的操作、"
    "重要的中间结论）。只保留对未来对话有用的内容。"
)

# Registry for custom compression strategies
_custom_strategies: dict[str, object] = {}


def register_compression_strategy(name: str, handler: object) -> None:
    """Register a custom context window compression function.

    Args:
        name: Strategy name (used as strategy="custom" + custom_handler="name").
        handler: Async callable (messages, config) -> compressed_messages.
    """
    _custom_strategies[name] = handler


class ContextWindowManager:
    """Compress conversation history when it exceeds token threshold."""

    def __init__(self, config: ContextWindowConfig | None = None):
        cfg = config or ContextWindowConfig()
        self.config = cfg
        self.strategy = cfg.strategy
        self.trigger_tokens = cfg.trigger_tokens
        self.keep_messages = cfg.keep_messages

    async def maybe_compress(self, messages: list, model) -> list | None:
        """Check if compression is needed. Returns new messages or None."""
        if self.strategy == "none" or not self.config.enabled:
            return None

        token_count = self._estimate_tokens(messages)
        if token_count < self.trigger_tokens:
            return None

        match self.strategy:
            case "summarize":
                return await self._summarize(messages, model)
            case "trim":
                return self._trim(messages)
            case "custom":
                return await self._custom(messages)
            case _:
                return None

    async def _summarize(self, messages: list, model) -> list:
        """Summarize old messages, keep recent N."""
        if len(messages) <= self.keep_messages:
            return messages

        old_messages = messages[: -self.keep_messages]
        recent_messages = messages[-self.keep_messages :]

        # Pick model: dedicated summary model > agent model
        summarize_model = model
        if self.config.summarize.model:
            # Model resolution is handled upstream — here we just note the preference
            pass

        conversation_text = "\n".join(
            f"{type(m).__name__}: {m.content[:200]}"
            for m in old_messages
            if hasattr(m, "content")
        )

        summary_prompt = self.config.summarize.prompt or _SUMMARIZE_PROMPT
        max_chars = self.config.summarize.max_summary_chars
        summary_prompt = f"{summary_prompt}\n\n{conversation_text}"

        try:
            response = await summarize_model.ainvoke(
                [HumanMessage(content=summary_prompt)]
            )
            content = response.content[:max_chars] if max_chars else response.content
            summary = SystemMessage(content=f"[对话摘要]\n{content}")
            return [summary, *recent_messages]
        except Exception:
            log.warning("Summarization failed, falling back to trim", exc_info=True)
            return self._trim(messages)

    def _trim(self, messages: list) -> list:
        """Trim messages, respecting TrimConfig settings."""
        if len(messages) <= self.keep_messages:
            return messages

        trim_cfg = self.config.trim

        # Start with system messages if configured
        head: list = []
        if trim_cfg.keep_system:
            head = [m for m in messages if isinstance(m, SystemMessage)]

        # Keep leading non-system messages if configured
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]
        if trim_cfg.keep_first_n > 0:
            leading = non_system[: trim_cfg.keep_first_n]
            # Keep tail from the remaining messages (after leading)
            remaining = non_system[trim_cfg.keep_first_n :]
            tail = remaining[-(self.keep_messages - len(leading)) :] if len(remaining) > max(0, self.keep_messages - len(leading)) else remaining
        else:
            leading = []
            tail = non_system[-self.keep_messages :]

        return head + leading + tail

    async def _custom(self, messages: list) -> list:
        """Delegate to a registered custom compression handler."""
        handler_name = self.config.custom_handler
        if not handler_name:
            log.warning("Custom strategy selected but no custom_handler configured")
            return messages

        # Check in-memory registry first
        handler = _custom_strategies.get(handler_name)

        # Try loading as "module:function" entry point
        if handler is None and ":" in handler_name:
            try:
                module_path, func_name = handler_name.rsplit(":", 1)
                mod = importlib.import_module(module_path)
                handler = getattr(mod, func_name)
            except (ImportError, AttributeError) as e:
                log.error("Failed to load custom handler '%s': %s", handler_name, e)
                return messages

        if handler is None:
            log.error("Custom handler '%s' not found", handler_name)
            return messages

        try:
            return await handler(messages, self.config)
        except Exception:
            log.error("Custom handler '%s' failed", handler_name, exc_info=True)
            return self._trim(messages)

    @staticmethod
    def _estimate_tokens(messages: list) -> int:
        """Rough token estimate (4 chars ≈ 1 token)."""
        total = 0
        for m in messages:
            content = m.content if hasattr(m, "content") else str(m)
            total += len(content)
        return total // 4
