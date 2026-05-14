"""
ArtiPivot P0 Demo — interactive end-to-end demonstration.

Usage:
    uv run python demo.py
    # or
    uv run python -m artipivot
"""

from __future__ import annotations

import asyncio
import sys


async def run_demo() -> None:
    from artipivot.agents.base import SubAgentDef
    from artipivot.agents.programmatic import build_programmatic_subagent
    from artipivot.config.center import ConfigCenter
    from artipivot.gateway.gateway import AgentGateway
    from artipivot.graph.factory import GraphFactory
    from artipivot.memory.checkpointer import create_checkpointer
    from artipivot.memory.store import create_store
    from artipivot.models.provider import ModelProvider
    from artipivot.observability.logging import configure_logging
    from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier
    from artipivot.tools.builtin.code_exec import code_exec
    from artipivot.tools.builtin.file_io import file_io
    from artipivot.tools.builtin.web_search import web_search
    from artipivot.tools.registry import ToolRegistry

    # 1. Logging
    configure_logging()
    print("=== ArtiPivot P0 Demo ===\n")

    # 2. Storage
    store = InMemoryDocumentStore()
    notifier = InProcessNotifier()

    # 3. Seed demo config directly into DocumentStore
    #    (production uses models.yaml → load_seed_if_empty, demo hardcodes for convenience)
    import os

    model_name = os.getenv("DEMO_MODEL", "claude-sonnet-4-6")
    model_provider_name = os.getenv("DEMO_PROVIDER", "anthropic")
    base_url = os.getenv("DEMO_BASE_URL", "")

    agent_model: dict = {"provider": model_provider_name, "name": model_name}
    if base_url:
        agent_model["base_url"] = base_url

    await store.put("model_configs", "global", {
        "scope": "global",
        "fallback_model": {"provider": "openai", "name": "gpt-4o"},
    })
    await store.put("model_configs", "agent:code_agent", {
        "scope": "agent",
        "agent_id": "code_agent",
        "model": agent_model,
    })

    await store.put("routing_configs", "code_agent", {
        "agent_id": "code_agent",
        "intent_map": {
            "code_write": "code_writer",
            "code_review": "code_writer",
            "debug": "code_writer",
        },
        "confidence_threshold": 0.6,
    })

    await store.put("prompt_configs", "classify", {
        "_id": "classify",
        "template": "Classify the user message into one of: {intents}. Reply in JSON: {{\"intent\": \"...\", \"confidence\": 0.0-1.0}}",
    })
    await store.put("prompt_configs", "respond", {
        "_id": "respond",
        "template": "Based on the sub-agent result, compose a helpful response to the user.",
    })
    await store.put("prompt_configs", "code_writer", {
        "_id": "code_writer",
        "template": "You are a professional coding assistant. Help the user with their coding tasks.",
    })

    print(f"Demo config seeded (provider={model_provider_name}, model={model_name})\n")

    # 4. ModelProvider + ConfigCenter
    model_provider = ModelProvider(store, notifier)
    await model_provider.start()

    config_center = ConfigCenter(store, notifier)
    await config_center.start()

    # 5. ToolRegistry
    tool_registry = ToolRegistry()
    tool_registry.register(web_search)
    tool_registry.register(code_exec)
    tool_registry.register(file_io)

    # 6. Sub-agent
    sub_def = SubAgentDef(
        name="code_writer",
        tools=["web_search", "code_exec", "file_io"],
        system_prompt="You are a professional coding assistant. Help the user with their coding tasks.",
        max_iterations=5,
    )
    tool_node = tool_registry.get_tool_node(sub_def.tools)
    sub_graph = build_programmatic_subagent(sub_def, tool_node)

    # 7. Main graph
    checkpointer = create_checkpointer()
    lg_store = create_store()

    graph_factory = GraphFactory(config_center)
    root_graph = graph_factory.build(
        agent_id="code_agent",
        sub_agent_nodes={"code_writer": sub_graph},
        checkpointer=checkpointer,
        store=lg_store,
    )

    # 8. Gateway
    gateway = AgentGateway(model_provider)
    gateway.register("code_agent", root_graph)

    print("Agent registered: code_agent")
    print("Tools: " + ", ".join(tool_registry.names))
    print("Type a message (or 'quit' to exit):\n")

    # 9. Interactive loop
    thread_id = "demo_session_1"
    while True:
        try:
            message = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if message.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        if not message:
            continue

        try:
            result = await gateway.invoke(
                agent_id="code_agent",
                message=message,
                thread_id=thread_id,
                user_id="demo_user",
            )

            # Extract last assistant message
            messages = result.get("messages", [])
            if messages:
                last = messages[-1]
                content = last.content if hasattr(last, "content") else str(last)
                print(f"\nAgent> {content}\n")
            else:
                print("\nAgent> (no response)\n")

        except Exception as e:
            print(f"\nError: {e}\n")


def main():
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
