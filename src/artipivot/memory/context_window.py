"""Context window management — summarize or trim long conversations."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from artipivot.memory.config import ContextWindowConfig


class ContextWindowManager:
    """Compress conversation history when it exceeds token threshold."""

    def __init__(self, config: ContextWindowConfig | None = None):
        cfg = config or ContextWindowConfig()
        self.strategy = cfg.strategy
        self.trigger_tokens = cfg.trigger_tokens
        self.keep_messages = cfg.keep_messages
        self.summary_model_name = cfg.summary_model

    async def maybe_compress(self, messages: list, model) -> list | None:
        """Check if compression is needed. Returns new messages or None."""
        if self.strategy == "none":
            return None

        token_count = self._estimate_tokens(messages)
        if token_count < self.trigger_tokens:
            return None

        match self.strategy:
            case "summarize":
                return await self._summarize(messages, model)
            case "trim":
                return self._trim(messages)
            case _:
                return None

    async def _summarize(self, messages: list, model) -> list:
        """Summarize old messages, keep recent N."""
        if len(messages) <= self.keep_messages:
            return messages

        old_messages = messages[:-self.keep_messages]
        recent_messages = messages[-self.keep_messages :]

        conversation_text = "\n".join(
            f"{type(m).__name__}: {m.content[:200]}"
            for m in old_messages
            if hasattr(m, "content")
        )

        summary_prompt = (
            "请用简洁的中文总结以下对话的关键信息（包括用户需求、已完成的操作、"
            "重要的中间结论）。只保留对未来对话有用的内容。\n\n"
            f"{conversation_text}"
        )

        try:
            response = await model.ainvoke([HumanMessage(content=summary_prompt)])
            summary = SystemMessage(content=f"[对话摘要]\n{response.content}")
            return [summary, *recent_messages]
        except Exception:
            # Fallback to trim if summarization fails
            return self._trim(messages)

    def _trim(self, messages: list) -> list:
        """Keep only the most recent N messages."""
        if len(messages) <= self.keep_messages:
            return messages
        return messages[-self.keep_messages :]

    @staticmethod
    def _estimate_tokens(messages: list) -> int:
        """Rough token estimate (4 chars ≈ 1 token)."""
        total = 0
        for m in messages:
            content = m.content if hasattr(m, "content") else str(m)
            total += len(content)
        return total // 4
