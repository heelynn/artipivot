"""Sub-agent data structure."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubAgentDef:
    """Definition of a sub-agent."""

    name: str
    tools: list[str]  # tool names
    system_prompt: str = ""
    max_iterations: int = 10
