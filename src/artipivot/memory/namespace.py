"""Namespace construction — multi-agent isolation for Store operations."""

from __future__ import annotations


def profile_ns(agent_id: str, user_id: str) -> tuple[str, ...]:
    """Namespace for user profile."""
    return (agent_id, user_id, "profile")


def knowledge_ns(agent_id: str, user_id: str) -> tuple[str, ...]:
    """Namespace for user knowledge facts."""
    return (agent_id, user_id, "knowledge")


def preferences_ns(agent_id: str, user_id: str) -> tuple[str, ...]:
    """Namespace for user preferences."""
    return (agent_id, user_id, "preferences")


def agent_memory_ns(agent_id: str, user_id: str, sub_name: str) -> tuple[str, ...]:
    """Namespace for sub-agent specific memory."""
    return (agent_id, user_id, "agent", sub_name)
