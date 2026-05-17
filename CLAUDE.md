# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**artipivot** — Production-grade multi-agent orchestration framework built on LangGraph v1.2 + FastAPI. Python 3.12, managed with `uv`.

## Commands

```bash
uv sync --dev                  # Install dependencies
uv run pytest tests/ -v        # Run all tests
uv run pytest tests/test_strategies.py -v   # Run single test file
uv run pytest tests/test_strategies.py::TestReActStrategy -v  # Run single test class
uv run artipivot serve          # Start HTTP API server
uv run artipivot chat <agent_id> "message"  # CLI chat
uv run artipivot agents         # List registered agents
python main.py                  # Run via main entry point
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions work without decorators.

## Architecture

Three-layer agent architecture: **Main Agent (router)** → **Sub-Agent (executor)** → **Tool (atomic capability)**.

### Request Flow

```
POST /api/v1/chat/{agent_id}
  → ChatRouter (rate limit)
  → AgentGateway.invoke()
    → classify node (LLM intent classification → {intent, confidence})
    → route_by_intent conditional edge (confidence < threshold → clarify, else → sub-agent)
    → sub-agent node (ReAct/FC strategy executes with tools)
    → respond node (format output)
  → ChatResponse
```

### Key Layers

**Main Agent** (`graph/root.py`, `graph/router.py`): Has state. Owns the compiled graph with classify → route → sub-agent → respond flow. State is `ArtiPivotState` (messages, intent, confidence, metadata).

**Sub-Agent** (`agents/strategies/`): Stateless compiled graphs — pure topology, state injected by LangGraph runtime. Multiple main agents share the same sub-agent graph. State is `SubAgentState` (messages, query, artifacts, metadata).

**Tool** (`tools/`): Stateless functions in global `ToolRegistry`. Sub-agents reference tools by name; `ToolNode` built at graph construction time.

### Core Registries (all singletons in `api/deps.py`)

| Registry | What it holds | Key method |
|----------|--------------|------------|
| `ToolRegistry` | `@tool` functions | `register()`, `get_tool_node(names)` |
| `SubAgentRegistry` | Compiled sub-agent graphs | `build_and_register()`, `get(name)` |
| `AgentRegistry` | Main agent defs + graphs | `register_def(agent_def)` |
| `AgentGateway` | agent_id → compiled graph map | `register()`, `invoke()` |

### Two Sub-Agent Strategies

- **ReAct** (`agents/strategies/react.py`): `think → tools → think` loop with `max_iterations`. For complex multi-step tasks.
- **Function Calling** (`agents/strategies/function_calling.py`): `llm → tools → END` single shot. For simple queries.

**Graph DSL** (`graph/dsl.py`): Custom YAML-defined topologies with `llm`, `tool`, `tools`, `sub_agent` node types. Used when fixed strategies aren't enough.

### Context & State Passing

- **AgentContext** (`graph/context.py`): Runtime context (agent_id, user_id, model, config_center) injected via LangGraph's `context_schema`. Not persisted.
- **ArtiPivotState** (`graph/state.py`): Main graph state. `messages` uses `add_messages` reducer; `intent`/`confidence` are direct overwrite; `metadata` is whole-dict overwrite.
- **SubAgentState**: Sub-graph state. `artifacts` uses `operator.add` (list append). Mapped to/from `ArtiPivotState.messages` at sub-graph boundary.

### Configuration & Hot-Reload

YAML is source of truth on every startup (`bootstrap.py` loads `.agents.yaml` or `ARTIPIVOT_AGENTS_MANIFEST`). At runtime:

- **Hot-reloadable** (no graph rebuild): model config, prompts, routing rules (intent_map, threshold), rate limits
- **Requires graph rebuild**: sub-agent registration, main agent registration (auto-rebuilt via PluginWatcher → GraphRebuilder)

`ConfigCenter` holds `ModelProvider`, `PromptStore`, `RoutingConfig` — all read from memory on every request.

### Model Resolution

Two providers: `openai` (covers OpenAI, DeepSeek, any OpenAI-compatible API) and `anthropic`. Resolution chain: user+agent level → user global → agent level → global fallback. Each `ModelConfig` supports recursive `fallback` field.

### Observability

`from artipivot.observability import log, bind` is the only logging API. Uses structlog with `contextvars`-based context propagation. `bind_trace_id()` at gateway entry, `bind()` for sub-agent-level context. All logs are JSON lines.

### File Layout Conventions

- `src/artipivot/` — all source code under `src/`
- `config/seed/` — YAML seed configs (loaded on first start only)
- `doc/` — usage guide + per-module docs
- `plan/` — design docs and development plan
- `.agents.yaml` — runtime agent manifest (project root)

### Extension Points

To add a new strategy: subclass `Strategy` ABC, implement `build()`, call `register_strategy()`. See `agents/strategies/base.py`.
To add a new tool: use `@tool` decorator, call `ToolRegistry.register()`.
To add a storage backend: subclass `DocumentStore`, register with factory function.
