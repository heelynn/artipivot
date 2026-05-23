"""Shared prompt builder — L3 memory injection + context window compression."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from artipivot.graph.context import AgentContext
from artipivot.graph.state import SubAgentState
from artipivot.observability import log


async def build_messages_with_memory(
    st: SubAgentState,
    ctx: AgentContext,
    store: object,
    base_prompt: str,
) -> list:
    """Build the message list for an LLM call, with L3 memory and compression.

    Args:
        st: Current sub-agent state.
        ctx: Agent runtime context (contains memory_config, agent_id, user_id, model).
        store: LangGraph store instance (from runtime.store).
        base_prompt: The resolved system prompt string.

    Returns:
        List of messages ready for the LLM.
    """
    from artipivot.memory.config import MemoryConfig
    from artipivot.memory.context_window import ContextWindowManager
    from artipivot.memory.retrieval import build_memory_context

    mem_cfg: MemoryConfig | None = ctx.memory_config
    system_prompt = base_prompt

    # Collect conversation messages
    messages: list = []
    if st.get("query"):
        messages.append(HumanMessage(content=st["query"]))
    messages.extend(st.get("messages", []))

    # 1. Context window compression (before memory injection)
    if mem_cfg and mem_cfg.context_window.enabled:
        mgr = ContextWindowManager(mem_cfg.context_window)
        compressed = await mgr.maybe_compress(messages, ctx.model)
        if compressed is not None:
            messages = compressed

    # 2. L3 memory injection
    if mem_cfg and store:
        try:
            query = _extract_user_query(st)
            memory_text = await build_memory_context(
                store, ctx.agent_id, ctx.user_id, query, mem_cfg.embedding
            )
            if memory_text:
                system_prompt += f"\n\n{memory_text}"
        except Exception:
            log.warning("L3 memory read failed, continuing without memory", exc_info=True)

    # Build final message list
    result: list = []
    if system_prompt:
        result.append(SystemMessage(content=system_prompt))
    result.extend(messages)
    return result


def _extract_user_query(st: SubAgentState) -> str:
    """Extract the user's query string from state."""
    if st.get("query"):
        return st["query"]
    # Fallback: last HumanMessage
    for m in reversed(st.get("messages", [])):
        if isinstance(m, HumanMessage):
            return m.content[:500]
    return ""
