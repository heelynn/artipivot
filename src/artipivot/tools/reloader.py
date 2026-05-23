"""ToolReloader — hot-reload tools and rebuild affected agent graphs.

Orchestrates: ToolRegistry ← tool change → affected sub-agents → affected agents.
"""

from __future__ import annotations

import structlog

from artipivot.gateway.gateway import AgentGateway
from artipivot.gateway.registry import AgentRegistry
from artipivot.tools.registry import ToolRegistry

log = structlog.get_logger(__name__)


class ToolReloader:
    """Hot-reload tools from DocumentStore changes and rebuild affected agents."""

    def __init__(
        self,
        gateway: AgentGateway,
        tool_registry: ToolRegistry,
        agent_registry: AgentRegistry,
        *,
        store=None,
        checkpointer=None,
    ) -> None:
        self._gateway = gateway
        self._tools = tool_registry
        self._agents = agent_registry
        self._store = store
        self._checkpointer = checkpointer

    async def reload_one_tool(
        self, name: str, tool_data: dict, *, invalidate: bool = False
    ) -> dict:
        """Register or update a single tool, then rebuild affected agents.

        Returns a summary: {"tool": name, "action": "added"|"updated",
                            "rebuilt_agents": [...]}
        """
        action = "updated" if self._tools.get(name) else "added"
        tool_type = tool_data.get("type", "builtin")

        if invalidate and tool_type == "module":
            self._tools.reload_module(
                name,
                tool_data.get("module", ""),
                tool_data.get("function", ""),
            )
        elif tool_type == "module":
            self._tools.register_module(
                name,
                tool_data.get("module", ""),
                tool_data.get("function", ""),
            )
        else:
            # builtin: discover and match by name
            from artipivot.tools.builtin import discover
            pool = discover()
            tool = pool.get(name)
            if tool is not None:
                self._tools.register(tool)

        log.info("tool_reloader.tool_registered", tool=name, action=action)

        # Find and rebuild affected agents
        affected = self._find_affected_agents({name})
        for agent_id in affected:
            await self._rebuild_agent(agent_id)

        return {
            "tool": name,
            "action": action,
            "rebuilt_agents": affected,
        }

    async def reload_tools(
        self, tool_data_list: list[dict], *, invalidate: bool = False
    ) -> dict:
        """Batch reload multiple tools, rebuild affected agents once."""
        changed_names: set[str] = set()
        actions: list[dict] = []

        for tool_data in tool_data_list:
            name = tool_data.get("name", "")
            if not name:
                continue
            result = await self.reload_one_tool(
                name, tool_data, invalidate=invalidate
            )
            actions.append(result)
            changed_names.add(name)

        return {"actions": actions, "changed_tools": list(changed_names)}

    async def remove_tool(self, name: str) -> dict:
        """Unregister a tool and rebuild affected agents."""
        self._tools.unregister(name)
        affected = self._find_affected_agents({name})
        for agent_id in affected:
            await self._rebuild_agent(agent_id)
        log.info("tool_reloader.tool_removed", tool=name)
        return {"tool": name, "action": "removed", "rebuilt_agents": affected}

    def _find_affected_agents(self, changed_tool_names: set[str]) -> list[str]:
        """Find agent IDs that reference any of the changed tools.

        Checks the agent's own tools list and each sub-agent's tools list.
        """
        affected: set[str] = set()
        for agent_id in self._agents.list_agents():
            agent_def = self._agents.get_def(agent_id)
            if agent_def is None:
                continue

            # Check agent-level tool whitelist
            if changed_tool_names & set(agent_def.tools or []):
                affected.add(agent_id)
                continue

            # Check sub-agent tool lists
            for sub_def in (
                list(agent_def.sub_agents.values())
                + list(agent_def.declarative_sub_agents.values())
                + list(agent_def.graph_sub_agents.values())
            ):
                sub_tools = getattr(sub_def, "tools", []) or []
                if changed_tool_names & set(sub_tools):
                    affected.add(agent_id)
                    break

        return list(affected)

    async def _rebuild_agent(self, agent_id: str) -> None:
        """Rebuild a single agent with lock protection."""
        try:
            await self._agents.rebuild_agent(
                agent_id,
                checkpointer=self._checkpointer,
                store=self._store,
            )
        except Exception:
            log.error(
                "tool_reloader.rebuild_failed",
                agent_id=agent_id,
                exc_info=True,
            )
