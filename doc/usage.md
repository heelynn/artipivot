# ArtiPivot 使用指南

本文档覆盖 ArtiPivot 的完整使用方式：从创建主 Agent、子代理、工具，到模型配置、意图路由、记忆系统、动态加载，以及各层之间的状态传递。

---

## 目录

- [核心理念](#核心理念)
- [三种创建方式](#三种创建方式)
  - [方式一：Web 管理页面](#方式一web-管理页面推荐)
  - [方式二：YAML 配置文件](#方式二yaml-配置文件)
  - [方式三：代码编程式](#方式三代码编程式)
- [主 Agent](#主-agent)
  - [定义结构](#主-agent-定义结构)
  - [意图识别与路由](#意图识别与路由)
  - [动态注册主 Agent](#动态注册主-agent)
- [子代理 Sub-Agent](#子代理-sub-agent)
  - [设计思路：子代理是无状态的](#设计思路子代理是无状态的)
  - [三种策略](#三种策略)
  - [SubAgentRegistry 独立注册](#subagentregistry-独立注册)
  - [同定义去重](#同定义去重)
  - [DSL 自定义拓扑](#dsl-自定义拓扑)
  - [Prompt 热加载](#prompt-热加载)
- [工具 Tool](#工具-tool)
  - [内置工具](#内置工具)
  - [自定义工具](#自定义工具)
  - [ToolRegistry 全局注册](#toolregistry-全局注册)
  - [MCP 适配器](#mcp-适配器)
- [模型配置](#模型配置)
  - [两种协议兼容层](#两种协议兼容层)
  - [多级优先级链](#多级优先级链)
  - [Fallback 降级链](#fallback-降级链)
  - [动态热更新](#模型动态热更新)
- [记忆与状态传递](#记忆与状态传递)
  - [两套 State，不是同一个对象](#两套-state不是同一个对象)
  - [State 字段结构与写入行为](#state-字段结构与写入行为)
  - [State 的完整流转](#state-的完整流转)
  - [上下文传递机制](#上下文传递机制)
  - [记忆记了什么](#记忆记了什么)
  - [短期记忆 vs 长期记忆](#短期记忆-vs-长期记忆)
  - [两种持久化](#两种持久化)
  - [对话记忆 (Checkpointer)](#对话记忆-checkpointer)
  - [长期记忆 (Store)](#长期记忆-store)
  - [Namespace 隔离](#namespace-隔离)
- [动态加载与热更新](#动态加载与热更新)
  - [Plugin 管理与路由管理](#plugin-管理与路由管理)
  - [三层配置架构](#三层配置架构)
  - [可热更新 vs 需重建](#可热更新-vs-需重建)
  - [Plugin 热重建机制](#plugin-热重建机制)
- [可观测性与日志](#可观测性与日志)
  - [设计理念](#设计理念)
  - [基本用法](#基本用法)
  - [模块 API 速查](#模块-api-速查)
  - [INFO vs DEBUG 粒度规范](#info-vs-debug-粒度规范)
  - [上下文自动注入](#上下文自动注入)
  - [全链路日志](#全链路日志)
  - [外部代码使用](#外部代码使用)
  - [配置与文件](#配置与文件)
- [完整案例](#完整案例)
  - [案例一：代码助手](#案例一代码助手)
  - [案例二：研究 + 写作双 Agent](#案例二研究--写作双-agent)
  - [案例三：自定义 DSL Pipeline](#案例三自定义-dsl-pipeline)
- [Admin API 速查](#admin-api-速查)
- [配置文件参考](#配置文件参考)

---

## 核心理念

ArtiPivot 的架构围绕几个核心设计决策：

| 概念 | 设计思路 |
|------|----------|
| **主 Agent** | 有状态的编排器，拥有模型配置、意图映射、对话线程。像一个项目经理。 |
| **子代理** | 无状态的执行器，compiled graph 是纯拓扑。像工具一样全局注册、按名引用。 |
| **工具** | 无状态的函数，全局注册在 ToolRegistry。 |
| **意图路由** | LLM 分类 → 查表路由。两级都是运行时从 ConfigCenter 读取，修改即时生效。 |
| **模型** | 多级优先级链 + fallback 降级链。用户级覆盖代理级覆盖全局。 |
| **记忆** | Checkpointer 管对话历史，Store 管长期记忆。线程级隔离。 |

**关键洞察**：子代理和工具一样是「无状态的一级公民」。多个主 Agent 可以共享同一个子代理的 compiled graph，因为图本身不持有任何运行时状态——状态由 LangGraph runtime 在调用时注入。

---

## 创建方式

### 方式一：Web 管理页面（推荐）

启动服务后，打开 `http://localhost:5173`，在 Agents 页面通过表单注册和配置 Agent。

```bash
uv run artipivot serve
```

在页面上完成：注册工具 → 注册子 Agent → 注册主 Agent → 配置路由、提示词、默认回复话术。修改即时生效，无需重启。

### 方式二：.agents.yaml 启动清单

适合生产环境部署。项目根目录的 `.agents.yaml` 在启动时自动加载：

```yaml
# .agents.yaml
agents:
  code_agent:
    model:
      provider: anthropic
      name: claude-sonnet-4-6
    routing:
      confidence_threshold: 0.7
      intents:
        code: code_writer
    sub_agent_refs:
      - name: code_writer
        public: false
        strategy: react
        tools: [web_search, code_exec]
        system_prompt: "You are a professional coding assistant."
```

启动后，后续配置全部通过 Web 页面或 Admin API 管理，无需重启。

### 方式三：代码编程式

```python
from artipivot.gateway.agent_def import AgentDef
from artipivot.gateway.registry import AgentRegistry

# ... 初始化 registry 等基础设施 ...

agent_def = AgentDef(
    agent_id="my_agent",
    model={"provider": "openai", "name": "gpt-4o"},
    confidence_threshold=0.7,
    intent_map={"code": "coder", "research": "researcher"},
    sub_agent_refs=["coder", "researcher"],
    tools=["web_search", "code_exec"],
)
registry.register_def(agent_def)
```

---

## 主 Agent

### 主 Agent 定义结构

`AgentDef` 是一个主 Agent 的完整定义：

| 字段 | 说明 |
|------|------|
| `agent_id` | 唯一标识 |
| `model` | 模型配置 dict |
| `confidence_threshold` | 意图分类置信度阈值 |
| `intent_map` | 意图名 → 子代理名映射 |
| `sub_agent_refs` | 引用的子代理名列表 |
| `sub_agents` | 旧式：内嵌 programmatic 子代理定义 |
| `declarative_sub_agents` | 旧式：内嵌 declarative 子代理定义 |
| `graph_sub_agents` | 旧式：内嵌 DSL 图定义 |
| `tools` | 工具白名单 |
| `prompts` | classify / respond 等 prompt 模板 |
| `memory_config` | 记忆配置 |

**新旧兼容**：`sub_agent_refs` 是新方式（按名引用 SubAgentRegistry 中的全局子代理）。旧方式（`sub_agents`、`declarative_sub_agents`、`graph_sub_agents` 字典内嵌）仍然支持——AgentRegistry 会自动检测并从旧字典构建。

### 意图识别与路由

路由是 **classify（识别意图）+ route_by_intent（查表分派）** 两个环节的组合。它是用户消息和子代理之间的调度层——识别用户想干嘛，决定让谁干。

#### 请求处理流程

```
用户消息："帮我写个快排"
  │
  ▼
┌─────────────┐
│  classify   │  LLM 结构化输出 → {"intent": "code_write", "confidence": 0.92}
└──────┬──────┘
       │ 写入 state: intent, confidence
       ▼
┌──────────────┐
│route_by_intent│  LangGraph 条件边（conditional edge）
└──────┬───────┘
       │
       ├── confidence < threshold → "clarify"   （请用户澄清意图）
       ├── intent 在 intent_map 中 → 对应子代理节点名
       └── 未匹配 → "fallback"                  （兜底处理）
       │
       ▼
┌─────────────┐
│  sub-agent  │  子代理执行（ReAct / FC）
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  respond    │  格式化最终响应返回用户
└─────────────┘
```

#### classify 节点：LLM 识别意图

classify 是主图中的 LLM 节点，做三件事：

1. **读配置**：从 `ConfigCenter.prompts.get(agent_id, "classify")` 获取 classify 专用的 system prompt（key: `{agent_id}:classify`），如果没配则使用内置默认 prompt
2. **调 LLM**：将 system prompt + 用户消息 history 发给 LLM，要求返回 JSON：`{"intent": "...", "confidence": 0.0-1.0}`
3. **写 state**：将解析出的 `intent` 和 `confidence` 写入 `ArtiPivotState`，同时记录 INFO 日志和 OTel 指标

```python
# classify 函数核心逻辑（router.py）
response = await model.ainvoke(messages)
result = json.loads(response.content)
intent = result["intent"]                           # e.g. "code_write"
confidence = float(result["confidence"])            # e.g. 0.92

return {"intent": intent, "confidence": confidence} # 写入 state
```

如果 LLM 返回的不是合法 JSON，fallback 为 `intent="general", confidence=0.0`。

#### route_by_intent：条件边查表分派

`route_by_intent` 不是图节点，是 LangGraph 的**条件边**——一个纯函数，返回下一个节点的名字符串。它不写 state，只做决策：

```python
# route_by_intent 核心逻辑（router.py）
threshold = config_center.routing.get_threshold(agent_id)   # 从 RoutingConfig 读阈值

if state["confidence"] < threshold:
    return "clarify"                                         # 置信度不够 → 让用户说清楚

intent_map = config_center.routing.get_intent_map(agent_id) # 从 RoutingConfig 读映射表
target = intent_map.get(state["intent"], "fallback")        # 查表，找不到走 fallback
return target                                                # 返回子代理节点名
```

三种分派结果：

| 条件 | 返回值 | 含义 |
|------|--------|------|
| `confidence < threshold` | `"clarify"` | LLM 不确定意图，让用户澄清 |
| intent 在 intent_map 中 | e.g. `"coder"` | 路由到对应子代理节点 |
| intent 不在 map 中 | `"fallback"` | 兜底处理 |

#### 路由配置数据模型

路由配置在 `ConfigCenter` 的 `RoutingConfig` 中以 agent_id 为 key 内存存储：

```python
# RoutingConfig 内部结构（_configs dict）
{
    "code_agent": {
        "agent_id": "code_agent",
        "confidence_threshold": 0.7,
        "intents": [
            {"name": "code_write", "sub_agent": "coder"},
            {"name": "code_review", "sub_agent": "coder"},
            {"name": "research", "sub_agent": "researcher"},
        ]
    }
}
```

`get_intent_map()` 将 `intents` 数组转换为 `{"code_write": "coder", ...}` 字典供 route_by_intent 查表。

#### 动态性

两个环节都是运行时动态的：
- **classify prompt** 从 `ConfigCenter.prompts` 读，修改即时生效
- **intent_map** 和 **threshold** 从 `ConfigCenter.routing` 读（`get_intent_map()` + `get_threshold()`），修改即时生效

都不需要重建图。`classify` 和 `route_by_intent` 每次执行时实时从 ConfigCenter 获取最新值。

### 动态注册主 Agent

运行时通过 Admin API 注册新的主 Agent：

```bash
# 注册新 Agent
curl -X POST http://localhost:8000/admin/agents \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "support_agent",
    "model": {"provider": "openai", "name": "gpt-4o"},
    "sub_agent_refs": ["assistant"],
    "routing": {
      "intents": {"question": "assistant"},
      "confidence_threshold": 0.6
    }
  }'

# 查询
curl http://localhost:8000/admin/agents
curl http://localhost:8000/admin/agents/support_agent
```

注册后立即可用，无需重启。前提是 `sub_agent_refs` 中的子代理已在 SubAgentRegistry 中注册。

---

## 子代理 Sub-Agent

### 设计思路：子代理是无状态的

这是 ArtiPivot 最核心的架构决策。

子代理的 compiled graph 是纯拓扑结构——节点和边的定义，不包含任何运行时数据。真正有状态的是 LangGraph runtime 在每次调用时创建的执行上下文。

**这意味着**：

- 同一个 compiled graph 可以被多个主 Agent 引用
- 同一个 compiled graph 可以服务不同用户的请求
- 不需要为每个主 Agent 重复构建相同的子代理

类比：子代理像函数定义，调用时的参数和局部变量才是状态。

### 三种策略

#### ReAct（Think → Act → Think 循环）

```
START → llm_call → 有 tool_calls?
                      ├── Yes → tools → llm_call (循环)
                      └── No  → END
```

适合需要多步推理、工具调用的复杂任务（代码编写、调试）。有 `max_iterations` 限制防止死循环。

```python
DeclarativeSubAgentDef(
    name="coder",
    strategy="react",
    tools=["web_search", "code_exec"],
    system_prompt="You are a coding assistant.",
    strategy_config={"max_iterations": 5},
)
```

#### Function Calling（单次调用）

```
START → llm_call → 有 tool_calls?
                      ├── Yes → tools → END
                      └── No  → END
```

适合简单查询、格式转换。没有循环，LLM 最多调一次工具就返回。

```python
DeclarativeSubAgentDef(
    name="quick_query",
    strategy="function_calling",
    tools=["web_search"],
)
```

### SubAgentRegistry 独立注册

子代理通过 `SubAgentRegistry` 全局注册，独立于主 Agent：

```python
from artipivot.gateway.sub_agent_registry import SubAgentRegistry

sub_reg = SubAgentRegistry(tool_registry)

# 声明式
sub_reg.build_and_register("coder", DeclarativeSubAgentDef(
    name="coder", strategy="react", tools=["web_search", "code_exec"],
))

# 编程式
from artipivot.agents.base import SubAgentDef
sub_reg.build_and_register("writer", SubAgentDef(
    name="writer", tools=["web_search"], system_prompt="Write well.",
))

# 预编译 graph 直接注册
from langgraph.graph import StateGraph, END, START
from artipivot.graph.state import SubAgentState
builder = StateGraph(SubAgentState)
builder.add_node("a", lambda s: s)
builder.add_edge(START, "a")
builder.add_edge("a", END)
sub_reg.register("my_sub", builder.compile())
```

主 Agent 通过 `sub_agent_refs` 按名引用：

```python
AgentDef(
    agent_id="agent_a",
    sub_agent_refs=["coder"],   # 引用全局注册的 coder
)
```

### 同定义去重

**巧思**：两个不同名字的子代理，如果策略和工具列表完全相同，共享同一个 compiled graph：

```python
sub_reg.build_and_register("writer_a", DeclarativeSubAgentDef(
    name="writer_a", strategy="react", tools=["web_search"],
))
sub_reg.build_and_register("writer_b", DeclarativeSubAgentDef(
    name="writer_b", strategy="react", tools=["web_search"],
))

# 两者是同一个 compiled graph 对象
assert sub_reg.get("writer_a") is sub_reg.get("writer_b")
```

去重 key = hash(type, strategy, sorted(tools))。`system_prompt` 不参与去重——因为它是运行时从 ConfigCenter 热加载的，构建时的值只是默认值。

### DSL 自定义拓扑

当三种内置策略不够用时，可以通过 DSL 定义任意图拓扑：

```yaml
# 在 agents.yaml 的 sub_agents 中
pipeline:
  graph:
    nodes:
      # Stage 1：研究员（LLM 绑定 echo + current_time）
      researcher:
        type: llm
        system_prompt: "你是研究员，根据用户需求收集信息。"
        tools: [echo, current_time]
      collector:
        type: tools
        tools: [echo, current_time]

      # 中间桥梁：总结第一阶段成果
      summarizer:
        type: llm
        system_prompt: "总结前面收集的原始信息，提取关键要点。"

      # Stage 2：精炼员（不同角色 + 不同工具集）
      refiner:
        type: llm
        system_prompt: "基于总结，决定是否需要进一步格式化。"
        tools: [echo]
      formatter:
        type: tools
        tools: [echo]

      # 最终输出
      finalizer:
        type: llm
        system_prompt: "将所有信息整合成一段清晰的中文回复。"

    edges:
      - { from: START, to: researcher }
      - { from: researcher, to: collector }
      - { from: collector, to: summarizer }
      - { from: summarizer, to: refiner }
      - { from: refiner, to: formatter }
      - { from: formatter, to: finalizer }
      - { from: finalizer, to: END }
```

支持的节点类型：

| 类型 | 说明 | 关键字段 |
|------|------|----------|
| `llm` | LLM 调用，可选 `tools` 绑定 | `system_prompt`, `tools`, `model`(可选覆盖), `interrupt`(HITL) |
| `tool` | 单工具调用 | `tool` |
| `tools` | 多工具 ToolNode | `tools` |
| `sub_agent` | 嵌套子代理 | `ref`（SubAgentRegistry 中的名） |

**LLM 节点 tools 绑定**：配置 `tools: [echo, current_time]` 后，LLM 会 `model.bind_tools()` 产出 `tool_calls`，下游 `tools` 节点（LangGraph ToolNode）自动消费这些 `tool_calls` 并执行，结果以 `ToolMessage` 追加到 `messages`。数据流完全走 LangGraph 原生机制，不需要中间适配层。

高级特性：
- **条件边**：field mapping / builtin 路由
- **HITL**：`interrupt: before` / `after` 暂停等待人工确认
- **重试**：`retry: {max_attempts: 3, delay_seconds: 1}`
- **max_iterations**：循环上界
- **per-node model**：节点级模型覆盖

### Prompt 热加载

子代理的 system_prompt 支持运行时热更新，无需重建图。

**实现原理**：策略的 `build()` 方法在闭包中捕获 `sub_def.name` 和 `sub_def.system_prompt`（作为默认值）。每次 LLM 调用时：

```python
# 在策略的 llm_call 闭包中（运行时执行）
system_prompt = default_prompt          # 构建时的默认值
if ctx.config_center:                   # 运行时有 ConfigCenter
    prompt_cfg = ctx.config_center.prompts.get(
        ctx.agent_id, "system", sub_name=sub_name  # 闭包捕获的子代理名
    )
    system_prompt = prompt_cfg.get("system", default_prompt)
```

**PromptStore key 格式**：`{agent_id}:{sub_name}:system`

如果 ConfigCenter 中有这个 key，使用运行时的值；否则用构建时的默认值。

---

## 工具 Tool

### 内置工具

ArtiPivot 内置三个工具（当前为 stub 实现，可替换为真实实现）：

| 工具名 | 说明 | 参数 |
|--------|------|------|
| `web_search` | 网络搜索 | `query`, `max_results` |
| `code_exec` | 代码执行 | `code`, `language` |
| `file_io` | 文件读写 | `path`, `content`, `action` |

### 自定义工具

使用 LangChain 的 `@tool` 装饰器：

```python
from langchain_core.tools import tool

@tool
def database_query(sql: str, limit: int = 100) -> str:
    """Execute a SQL query and return results.

    Args:
        sql: The SQL query to execute.
        limit: Maximum number of rows to return.
    """
    # 实际实现
    return f"query results: {sql[:50]}..."
```

> **注意**：`@tool` 要求函数有 docstring（用作工具描述），否则报错。

注册到 ToolRegistry：

```python
from artipivot.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register(database_query)
```

### ToolRegistry 全局注册

ToolRegistry 是全局工具池，所有主 Agent 和子代理共享：

```python
# 注册
registry.register(my_tool)

# 获取单个工具
tool = registry.get("database_query")

# 为子代理构建 ToolNode（LangGraph 的工具执行节点）
tool_node = registry.get_tool_node(["web_search", "code_exec"])

# 列出所有注册名
names = registry.names()  # ["web_search", "code_exec", "database_query"]
```

子代理的 `tools` 字段只是名字列表。运行时从 ToolRegistry 查找对应工具构建 ToolNode。

### MCP 适配器

支持通过 Model Context Protocol 接入外部工具：

```python
from artipivot.tools.mcp_adapter import MCPToolAdapter

adapter = MCPToolAdapter("my_mcp_server", {"command": "npx", "args": ["-y", "some-mcp-server"]})
tools = adapter.adapt_tools()  # → [BaseTool, ...]

for t in tools:
    registry.register(t)
```

---

## 模型配置

### 两种协议兼容层

ArtiPivot 本质上只区分两种 API 协议：

| provider 值 | 底层实现 | 覆盖范围 |
|-------------|---------|---------|
| `openai` | `langchain_openai.ChatOpenAI` | OpenAI、Azure OpenAI、DeepSeek、Moonshot、通义千问、任何 OpenAI 兼容 API |
| `anthropic` | `langchain_anthropic.ChatAnthropic` | Anthropic 官方、任何 Anthropic 兼容 API |

每个配置都是 `base_url` + `api_key` + `name` 的组合：

```python
# DeepSeek（OpenAI 兼容）
{"provider": "openai", "name": "deepseek-chat", "base_url": "https://api.deepseek.com", "api_key": "sk-xxx"}

# Azure OpenAI
{"provider": "openai", "name": "gpt-4o", "base_url": "https://xxx.openai.azure.com", "api_key": "xxx"}

# 本地模型（Ollama 等）
{"provider": "openai", "name": "llama3", "base_url": "http://localhost:11434/v1", "api_key": "dummy"}

# Anthropic 直连
{"provider": "anthropic", "name": "claude-sonnet-4-6", "api_key": "sk-ant-xxx"}

# Anthropic 兼容方
{"provider": "anthropic", "name": "claude-sonnet-4-6", "base_url": "https://proxy.example.com", "api_key": "xxx"}
```

`api_key` 如果不填，LangChain 会自动从环境变量读取（`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`）。

### 多级优先级链

模型解析时按优先级从高到低查找：

```
user_id + agent_id 级  ("agent_id:user_id" 在 _user_models 中)
        ↓ 没配
user_id 全局级         ("__global__:user_id" 在 _user_models 中)
        ↓ 没配
agent_id 级             (_agent_models["agent_id"])
        ↓ 没配
global_fallback         (_global_fallback)
        ↓ 没有
raise ValueError
```

典型场景：全局配 `gpt-4o`，特定 Agent 用 `claude-sonnet-4-6`，VIP 用户 `alice` 用 `claude-opus-4-6`。

### Fallback 降级链

每个 `ModelConfig` 支持递归的 `fallback` 字段：

```yaml
agents:
  my_agent:
    provider: anthropic
    name: claude-sonnet-4-6
    fallback:
      provider: openai
      name: gpt-4o
      fallback:
        provider: openai
        name: gpt-4o-mini
```

运行时按顺序尝试，某个 provider 不可用时自动降级到下一个。

### 模型动态热更新

```bash
# 设置全局 fallback
curl -X PUT http://localhost:8000/admin/models/global \
  -d '{"provider": "anthropic", "name": "claude-haiku-4-5"}'

# 为用户设置专属模型（覆盖 agent 级）
curl -X PUT http://localhost:8000/admin/models/user/alice/agent/my_agent \
  -d '{"provider": "anthropic", "name": "claude-opus-4-6"}'

# 查询用户模型配置
curl http://localhost:8000/admin/models/user/alice

# 删除用户级覆盖
curl -X DELETE http://localhost:8000/admin/models/user/alice/agent/my_agent
```

修改即时生效，无需重启。

---

## 记忆与状态传递

ArtiPivot 有两层独立的状态体系——**持久化记忆**（跨对话保留）和**运行时状态**（单次请求内流转）。两者职责不同，互不干扰。

### 两套 State，不是同一个对象

主 Agent 和子代理各自有独立的 state 类型，它们**不是同一个 dict 在传递**：

```
主 Agent 图:  ArtiPivotState
  ├── messages      对话消息列表
  ├── intent        classify 识别出的意图
  ├── confidence    置信度
  ├── active_agent  当前激活的子代理名
  └── metadata      附加数据

子代理图:  SubAgentState
  ├── messages      子代理内部消息
  ├── query         用户原始问题
  ├── artifacts     子代理产出物（列表，支持追加）
  └── metadata      附加数据
```

层与层之间通过 LangGraph 的子图机制做映射——主图的 `messages` 作为子图输入，子图执行完后 `messages` 写回主图。Tool 没有 state，输入是 LLM 生成的参数，输出是一段文本追加到 `messages`。

```
ArtiPivotState["messages"]  ──→  SubAgentState["messages"]   （主图 → 子图）
ArtiPivotState["messages"]  ←──  SubAgentState["messages"]   （子图 → 主图）

Tool: 无 state
  SubAgentState.messages 最后一条 AIMessage.tool_calls
    → ToolNode 调用 tool(query="...")
    → ToolMessage(content="结果") 追加到 messages
```

### State 字段结构与写入行为

State 的结构由 TypedDict 定义，每个字段的**写入方式**不同——这是理解数据流的关键：

**ArtiPivotState（主 Agent）**

| 字段 | 类型 | 写入方式 | 说明 |
|------|------|---------|------|
| `messages` | `list[AnyMessage]` | `add_messages`（智能合并） | 新消息追加，同 id 的覆盖 |
| `intent` | `str \| None` | 直接赋值（覆盖） | classify 节点写入 |
| `confidence` | `float` | 直接赋值（覆盖） | classify 节点写入 |
| `active_agent` | `str \| None` | 直接赋值（覆盖） | 当前子代理名 |
| `metadata` | `dict` | 直接赋值（覆盖） | 自由 kv，**整个 dict 替换** |

**SubAgentState（子代理）**

| 字段 | 类型 | 写入方式 | 说明 |
|------|------|---------|------|
| `messages` | `list[AnyMessage]` | `add_messages`（智能合并） | LLM/Tool 追加消息 |
| `query` | `str` | 直接赋值（覆盖） | 用户原始问题 |
| `artifacts` | `list[str]` | `operator.add`（列表拼接） | 产出物追加，不覆盖旧的 |
| `metadata` | `dict` | 直接赋值（覆盖） | 自由 kv |

写入行为决定了节点返回值的语义：

```python
# 覆盖型字段 — 返回新值直接替换
return {"intent": "code_write", "confidence": 0.9}
# → intent = "code_write", confidence = 0.9, 其他字段不变

# 追加型字段（messages）— add_messages 智能合并
return {"messages": [AIMessage(content="response")]}
# → 新消息追加到列表，不覆盖已有消息

# 追加型字段（artifacts）— 列表拼接
return {"artifacts": [json.dumps(steps)]}
# → 新元素追加到列表，不覆盖已有元素

# 覆盖型字段（metadata）— 整个 dict 替换
return {"metadata": {"c": 3}}
# → metadata = {"c": 3}  ← 原来的 key 全没了！
```

### State 的完整流转

一个请求从入口到响应，数据在各层之间的完整流转：

```
用户消息
  │
  ▼
ArtiPivotState.messages ──→ classify 读 messages，写入 intent / confidence
  │
  ▼
route_by_intent 读 intent，查 intent_map，决定走哪个子代理
  │
  ▼
SubAgentState.messages ←── 主图 messages 映射过来
  │
  ├── llm_call 读 messages，调 LLM，结果 AIMessage 追加到 messages
  │
  ├── ToolNode 读最后一条消息的 tool_calls
  │     → 调用 tool，结果 ToolMessage 追加到 messages
  │
  ▼
SubAgentState.messages ──→ 写回 ArtiPivotState.messages
  │
  ▼
respond 读 messages，格式化最终输出返回用户
```

**各层读写 State 的方式**：

| 层 | 操作的 State | 读什么 | 写什么 |
|---|-------------|--------|--------|
| classify | ArtiPivotState | messages | intent, confidence |
| route_by_intent | ArtiPivotState | intent, confidence | （返回节点名，不写 state） |
| LLM 节点 | SubAgentState | messages | messages（追加 AIMessage，可选 tool_calls） |
| ToolNode | SubAgentState | messages（取 tool_calls） | messages（追加 ToolMessage） |
| respond | ArtiPivotState | messages | （格式化输出，不修改 state） |

### 两种持久化

ArtiPivot 使用 LangGraph 的两种持久化机制：

| 机制 | 用途 | 后端 |
|------|------|------|
| **Checkpointer** | 对话历史、断点续传 | memory / postgres |
| **Store** | 长期记忆（用户画像、知识库） | memory / postgres |

后端通过工厂模式注册，可扩展：

```python
from artipivot.memory.checkpointer import create_checkpointer
from artipivot.memory.store import create_store

cp = create_checkpointer(backend="memory")   # 或 "postgres"
st = create_store(backend="memory")           # 或 "postgres"
```

Postgres 后端需要 `DATABASE_URI` 环境变量或传入 `uri` 参数。

### 对话记忆 (Checkpointer)

Checkpointer 按 thread_id 存储对话历史。ArtiPivot 的 thread_id 格式为 `{agent_id}:{thread_id}`，天然隔离不同 Agent 的对话。

```python
# AgentGateway.invoke() 内部
full_thread_id = f"{agent_id}:{thread_id}"
config = {"configurable": {"thread_id": full_thread_id}}
result = await graph.ainvoke(input, config, context=...)
```

LangGraph 自动管理：
- 每轮对话后保存 state snapshot
- 下次同 thread_id 调用时恢复上下文
- 支持 HITL 断点恢复

### 长期记忆 (Store)

Store 是 key-value 存储，用于跨对话的长期信息：

```python
# Namespace 结构
(agent_id, user_id, "profile")           # 用户画像
(agent_id, user_id, "knowledge")         # 知识事实
(agent_id, user_id, "preferences")       # 用户偏好
(agent_id, user_id, "agent", sub_name)   # 子代理专属记忆
```

### Namespace 隔离

所有记忆操作都通过 Namespace 确保 Agent 间隔离：

```
agent_a:user_1:profile  ← Agent A 看到的 user_1 画像
agent_b:user_1:profile  ← Agent B 看到的 user_1 画像（独立）
```

同一个用户在不同 Agent 下有独立的记忆空间。

### 上下文传递机制

除了 State 数据流，还有一个平行的**运行时上下文**通过 LangGraph 的 `context_schema` 注入：

```
HTTP POST /api/v1/chat/{agent_id}
  body: {message, thread_id, user_id}
  │
  ▼
ChatRouter
  │ 读取 agent_id, message, thread_id, user_id
  │ 调用 rate_limiter.check(agent_id, user_id)
  ▼
AgentGateway.invoke(agent_id, message, thread_id, user_id=user_id)
  │ 解析模型: get_model(agent_id, user_id=user_id)
  │ 生成 full_thread_id = f"{agent_id}:{thread_id}"
  │ 生成 trace_id
  ▼
构建 AgentContext（运行时上下文，不是 State）
  agent_id      ← 来自 URL
  user_id       ← 来自请求体
  thread_id     ← "{agent_id}:{thread_id}"
  model         ← ModelProvider 解析结果
  config_center ← Gateway 持有
  │
  ▼
graph.ainvoke(input, config, context=AgentContext(...))
  │
  ├─→ classify 节点
  │     从 AgentContext 取 model, agent_id
  │     从 ConfigCenter 取 classify prompt
  │     写入 ArtiPivotState: intent, confidence
  │
  ├─→ route_by_intent 条件边
  │     从 ConfigCenter 取 intent_map, threshold
  │     返回子代理节点名（不写 state）
  │
  ├─→ sub-agent 节点
  │     AgentContext 自动传递给子图
  │     从 context 取 model（调 LLM）
  │     从 context 取 config_center（热加载 prompt）
  │     闭包中的 sub_name 用于 prompt 查找
  │     读写 SubAgentState
  │
  └─→ respond 节点
        格式化最终输出
  │
  ▼
返回 ChatResponse {response, thread_id}
```

**关键区分**：State 是节点之间传递的数据载体，AgentContext 是注入给每个节点的运行时环境信息。State 会被 Checkpointer 持久化，AgentContext 每次请求重新构建。

### 记忆记了什么

Checkpointer 挂在主图上，持久化的是 `ArtiPivotState`。子代理的 `SubAgentState` 是每次调用临时创建的，调用完就没了。

```
主图 compile(checkpointer=cp)
  │
  ├── classify 节点执行
  │     cp 保存 ArtiPivotState {messages, intent, confidence, metadata}
  │
  ├── sub-agent 节点执行
  │     内部创建临时 SubAgentState {messages, query, artifacts, metadata}
  │       ├── llm_call 读写 SubAgentState.messages
  │       ├── ToolNode 读写 SubAgentState.messages
  │       └── 执行完毕
  │     只有 messages 映射回 ArtiPivotState
  │     SubAgentState 销毁
  │
  └── cp 保存 ArtiPivotState {messages, intent, confidence, metadata}
```

Checkpointer 实际保存的内容：

```python
{
    "messages": [
        HumanMessage("帮我写个快排"),           # 用户输入
        AIMessage(tool_calls=[{...}]),          # sub-agent 思考过程
        ToolMessage("搜索结果..."),             # tool 调用结果
        AIMessage("这是 Python 快排实现..."),    # 最终结果
    ],
    "intent": "code_write",       # 调了哪个 sub-agent
    "confidence": 0.92,
}
```

| 内容 | 是否持久化 | 原因 |
|------|-----------|------|
| 对话消息 (messages) | 是 | 映射回 ArtiPivotState，被 Checkpointer 保存 |
| 意图/置信度 (intent/confidence) | 是 | 在 ArtiPivotState 里，被 Checkpointer 保存 |

### 短期记忆 vs 长期记忆

| 持久化方式 | 记什么 | 生命周期 | 例子 |
|-----------|--------|---------|------|
| Checkpointer | 对话上下文（用户输入 + 调了谁 + 结果） | 同一 thread 内 | "我们刚才聊了快排" |
| Store | 用户画像 / 知识 / 偏好 | 跨对话永久 | "这个用户偏好 Python"、"他的代码风格是 X" |


---

## 动态加载与热更新

### Plugin 管理与路由管理

这两套机制分别管「子代理本身」和「子代理怎么被选中」，配合使用实现完整的运行时动态调度。

#### Plugin 管理：子代理的热插拔

Plugin 是子代理的「动态注册表」——把子代理定义打包成 Document，存进 DocumentStore，通过 API 管理生命周期。和 `SubAgentRegistry.build_and_register()` 做的事情一样，区别是 Plugin 走 API、持久化存储、可随时增删。

**PluginDocument 数据结构**（存于 DocumentStore 的 `"plugins"` collection）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `plugin_type` | `str` | 类型：`"sub_agent"` / `"tool"` / `"pipeline"` |
| `name` | `str` | 插件名，对应子代理名 |
| `version` | `str` | 语义化版本号 |
| `agent_id` | `str` | 所属主 Agent |
| `manifest` | `dict` | 子代理完整定义：strategy、tools、system_prompt、routing 等 |
| `status` | `str` | `"active"` / `"inactive"` / `"deprecated"` |
| `created_at` | `str` | ISO 8601 时间戳，publish 时自动生成 |
| `updated_at` | `str` | ISO 8601 时间戳，publish/deprecate 时自动更新 |

**DocumentStore 存储方式**：key = `"{plugin_type}:{agent_id}:{name}"`，例如 `"sub_agent:my_agent:translator"`。

**API 操作**：

```bash
# 上线一个新子代理
curl -X POST http://localhost:8000/admin/plugins \
  -d '{
    "plugin_type": "sub_agent",
    "name": "translator",
    "version": "1.0",
    "agent_id": "my_agent",
    "manifest": {
      "strategy": "react",
      "tools": ["web_search"],
      "system_prompt": "You translate text.",
      "routing": {"intents": {"translate": "translator"}}
    }
  }'

# 下线（软删除，标记为 deprecated，不物理删除）
curl -X DELETE http://localhost:8000/admin/plugins/sub_agent/my_agent/translator
```

> **注意**：DELETE 是软删除（`deprecate`，将 status 改为 `"deprecated"`），不是物理删除。目的是保留历史记录，同时让下次 `list_plugins(status="active")` 排除它。

**发布一个 Plugin 触发的完整链路**：

```
POST /admin/plugins
  │
  ▼
PluginManager.publish(plugin)
  │ 1. 设置 created_at / updated_at = now (UTC ISO)
  │ 2. status = "active"
  │ 3. store.put("plugins", key, data)       ← 持久化到 DocumentStore
  └── 4. notifier.notify("plugins", key, "upsert", data)  ← 广播变更
        │
        ▼
      PluginWatcher._on_plugin_change()
        │ 从 data 中提取 agent_id
        │ 调用 rebuilder.rebuild_agent(agent_id)
        │
        ▼
      GraphRebuilder.rebuild_agent("my_agent")
        │ 1. plugin_manager.list_plugins(agent_id, status="active")
        │    → 查所有活跃 Plugin
        │ 2. _build_sub_agents(plugins)
        │    ├── manifest 含 "graph"  → parse_graph_def() → build_dsl_graph()
        │    ├── manifest 含 strategy → DeclarativeSubAgentDef → build_declarative_subagent()
        │    └── 否则                 → SubAgentDef → build_programmatic_subagent()
        │ 3. 从 sub_agent plugin 的 manifest.routing.intents 收集 intent_map
        │ 4. GraphFactory.build(agent_id, sub_agent_nodes) 编译新主图
        └── 5. gateway.register(agent_id, graph)  ← 原子替换旧图（字典赋值）
```

**失败安全保障**：`gateway.register()` 只是一个字典赋值，只有在前 4 步全部成功后才会执行。如果 manifest 格式错误、路由配置不对、或模型缺失导致 `build()` 抛异常，旧图保持不变，线上服务不受影响。

**Plugin 与 SubAgentRegistry 的关系**：

| | SubAgentRegistry | Plugin 系统 |
|---|---|---|
| 注册方式 | 代码中调用 `build_and_register()` | REST API 调用 |
| 存储 | 内存 dict | DocumentStore（持久化） |
| 生命周期 | 进程重启后消失，需重新构建 | 持久化保留，重启后仍在 |
| 触发重建 | 不触发（需手动重建主图） | 自动触发 GraphRebuilder |
| 适用场景 | 开发调试、固定拓扑 | 生产动态调度、多租户定制 |

**离线 CLI**（生成 manifest 模板）：

```bash
# 生成插件目录和 manifest 模板
artipivot plugin init translator --template react

# 查看将发布的 manifest 内容（实际发布需服务器运行中调 API）
artipivot plugin publish translator --agent-id my_agent --version 1.0
```

#### 路由管理：意图分派规则表

路由管理控制 classify 识别出意图后怎么分派到子代理。两个配置项存在 `RoutingConfig` 中：

- **intent_map**：意图名 → 子代理名的映射表
- **confidence_threshold**：置信度低于此值走 clarify（让用户澄清）

```bash
# 查询当前路由配置
curl http://localhost:8000/admin/routing/code_agent
```

返回：
```json
{
  "agent_id": "code_agent",
  "confidence_threshold": 0.7,
  "intents": [
    {"name": "code_write", "sub_agent": "code_writer"},
    {"name": "code_review", "sub_agent": "code_writer"},
    {"name": "debug", "sub_agent": "code_writer"}
  ]
}
```

**路由配置修改即时生效**——不需要重建图。`classify` 和 `route_by_intent` 函数每次执行时调用 `config_center.routing.get_threshold()` 和 `get_intent_map()`，实时从内存中的 `RoutingConfig._configs` 读取最新值。

**路由修改触发图重建的情况**：当路由配置的变更通过 `ChangeNotifier` 通知 `RoutingConfig.apply()` 时，`RoutingConfig` 内存数据会直接更新。但如果修改涉及新增子代理（新 intent 对应的 sub_agent 不在图中），则需要 Plugin 系统触发 GraphRebuilder 重建主图。

**与 Plugin 路由的关系**：Plugin 发布时 `manifest.routing.intents` 会被 GraphRebuilder 收集进 routing config。但路由配置也可以独立修改——比如只想调低 confidence_threshold 让分类更宽容，不需要动子代理本身。

#### 两者的关系

| | Plugin 管理 | 路由管理 |
|--|------------|---------|
| **管什么** | 子代理本身（创建/销毁 compiled graph） | 子代理怎么被选中（映射表 + 阈值） |
| **生效方式** | 触发图重建，原子替换 | 即时生效，下次请求读新值 |
| **类比** | 给系统装/卸一个模块 | 改路由转发的规则表 |

Plugin 发布时 `manifest.routing.intents` 会被 GraphRebuilder 收集，合并进 intent_map。但路由配置也可以独立于 Plugin 修改（直接通过 DocumentStore 或未来的 Admin API 端点改 `routing_configs`）。

### 三层配置架构

```
┌──────────────────────────────────────────┐
│  REST API (Admin)                         │  ← 运行时修改
│  PUT /admin/models/user/...              │
│  POST /admin/agents                      │
├──────────────────────────────────────────┤
│  DocumentStore + ChangeNotifier           │  ← 运行时存储
│  model_configs, routing_configs,          │
│  prompt_configs                           │
├──────────────────────────────────────────┤
│  Admin API + Web UI                        │  ← 运行时管理
│  agents.yaml, models.yaml, ...            │
└──────────────────────────────────────────┘
```

### 可热更新 vs 需重建

| 配置项 | 热更新？ | 说明 |
|--------|---------|------|
| 模型配置 | 即时 | ModelProvider 内存中直接替换 |
| Prompt | 即时 | PromptStore 内存中直接替换，下次 LLM 调用生效 |
| Routing (intent_map) | 即时 | RoutingConfig 内存中替换，下次 classify 生效 |
| Rate limit | 即时 | RateLimiter 内存中替换 |
| 子代理注册 | 需重建主图 | 新子代理注册后，主 Agent 的图需 rebuild |
| 主 Agent 注册 | 即时 | Admin API 自动构建图并注册到 Gateway |

### Plugin 热重建机制

Plugin 系统的核心能力是**发布/下线即触发图重建**——不需要重启服务，新请求立即使用新图。

**四个组件协作流程**：

```
PluginManager              PluginWatcher              GraphRebuilder            AgentGateway
     │                          │                          │                        │
     │ publish(plugin)          │                          │                        │
     │   store.put("plugins")   │                          │                        │
     │   notifier.notify()  ──→ │                          │                        │
     │                          │ _on_plugin_change()      │                        │
     │                          │   extract agent_id       │                        │
     │                          │   rebuild_agent()  ────→ │                        │
     │                          │                          │ list_plugins(active)    │
     │                          │                          │ _build_sub_agents()    │
     │                          │                          │ factory.build()        │
     │                          │                          │ gateway.register() ──→ │ _graphs[id]=graph
     │                          │                          │                        │
     │ deprecate()              │                          │                        │
     │   store.put("plugins")   │                          │                        │
     │   notifier.notify()  ──→ │  (同上流程)               │                        │
```

**GraphRebuilder 支持的三种 manifest 格式**（`_build_sub_agents()` 方法）：

```python
for p in plugins:
    if "graph" in p.manifest:
        # 方式 1：DSL 图定义（最灵活）
        graph_def = parse_graph_def(p.name, p.manifest["graph"])
        result[p.name] = build_dsl_graph(graph_def, ...)
    elif p.manifest.get("strategy"):
        # 方式 2：声明式策略（react / function_calling）
        defn = DeclarativeSubAgentDef(name=p.name, strategy=..., tools=..., ...)
        result[p.name] = build_declarative_subagent(defn, tool_node)
    else:
        # 方式 3：编程式（无策略关键字，直接给 system_prompt + tools）
        sub_def = SubAgentDef(name=p.name, tools=..., ...)
        result[p.name] = build_programmatic_subagent(sub_def, tool_node)
```

**三种失败场景与保障**：

| 失败场景 | 表现 | 保障 |
|---------|------|------|
| manifest 格式错误 | `build()` 抛异常 | 旧图继续服务，异常被记录到 error.log |
| 路由意图指向不存在的子代理 | `GraphFactory.build()` 校验失败 | 同上 |
| 模型配置缺失 | `build()` 抛异常 | 同上 |

关键保证：`gateway.register()`（一个简单的 `_graphs[agent_id] = graph` 字典赋值）只在 `factory.build()` 成功返回后执行。这意味着旧的 compiled graph 一直在服务，直到新图完全就绪。

**隔离性**：`GraphRebuilder.rebuild_agent()` 只重建指定的 agent。修改 `agent_a` 的 plugin 不影响 `agent_b` 的图。

## 可观测性与日志

### 设计理念

ArtiPivot 采用 **structlog** 作为日志框架，所有输出为结构化 JSON 行，设计目标：

- **结构化**：每条日志是独立 JSON 对象，可直接被 ELK/Loki/Datadog 采集，无需 Grok 解析
- **上下文自动传播**：基于 `contextvars`，trace_id、agent_id、user_id 等在整个请求链中自动注入，不需要每处显式传参
- **敏感数据遮盖**：日志输出前自动遮盖 api_key、token、authorization、password、secret 等敏感字段
- **双文件输出**：主日志 `artipivot.log` 记录所有事件，`error.log` 独立记录 ERROR，便于告警
- **可选 OTel**：通过环境变量 `OTEL_ENABLED=true` 开启 OpenTelemetry 指标导出

### 基本用法

`from artipivot.observability import log, bind` 是日志的唯一切入点——页面上不再需要 `logging.getLogger`：

```python
from artipivot.observability import log, bind

# 绑定上下文（一次绑定，后续日志自动携带）
bind(sub_name="writer", strategy="react")

# 记录事件
log.info("sub_agent.start")
log.info("llm.call", messages_count=5)
log.debug("llm.input", messages=[...])
log.error("gateway.error", error="timeout")
```

输出样例：

```json
{
  "trace_id": "a1b2c3d4e5f6",
  "agent_id": "code_agent",
  "user_id": "alice",
  "sub_name": "writer",
  "strategy": "react",
  "event": "llm.call",
  "messages_count": 5,
  "level": "info",
  "timestamp": "2026-05-17T09:30:00.123456+00:00"
}
```

### 模块 API 速查

| API | 说明 |
|-----|------|
| `log` | structlog 日志器（`structlog.get_logger("artipivot")`） |
| `bind(**kwargs)` | 绑定 key=value 到当前请求的上下文变量 |
| `configure_logging(log_dir, level)` | 初始化日志系统（文件轮转、级别、控制台） |
| `bind_trace_id(trace_id, ...)` | 请求入口绑定 trace_id + agent_id + user_id + thread_id |
| `generate_trace_id()` | 生成 12 字符十六进制 trace_id |
| `clear_trace()` | 清除上下文变量（请求结束时调用） |
| `serialize(obj)` | 安全序列化 LangChain 消息对象用于 debug 日志 |

### INFO vs DEBUG 粒度规范

日志级别有两个维度：**事件本身**和**负载内容**。

| 级别 | 记录什么 | 样例 |
|------|---------|------|
| `INFO` | 控制流事件 + 关键计数 | `gateway.request`、`llm.call`（含 `messages_count`）、`tool.result`（含状态） |
| `DEBUG` | 完整负载（消息内容、tool 参数等） | `llm.input`（含完整 messages 列表）、`tool.call`（含参数） |
| `ERROR` | 异常、不可恢复故障 | `gateway.error`、`circuit.open` |

典型日志对（同一操作的 INFO + DEBUG）：

```python
log.info("llm.call", messages_count=len(messages))       # INFO：只记录消息数量
log.debug("llm.input", messages=[serialize(m) for m in messages])  # DEBUG：记录完整内容

log.info("llm.response", tool_calls=len(response.tool_calls))  # INFO：工具调用数量
log.debug("llm.output", response=serialize(response))          # DEBUG：完整响应
```

原则：**INFO 知道发生了什么，DEBUG 才能看到发生了什么。** 这样线上开 INFO 不刷屏，排查时开到 DEBUG 获得完整信息。

### 上下文自动注入

上下文通过 Python `contextvars` 机制传播——不需要在函数间显式传递 logger，调用链中任何位置的 `log.info(...)` 都会自动携带绑定过的上下文键。

**请求级上下文**（Gateway.invoke 入口绑定，整个请求链自动携带）：

```python
# gateway.py 内部
trace_id = generate_trace_id()                 # "a1b2c3d4e5f6"
bind_trace_id(trace_id, agent_id="code_agent", user_id="alice", thread_id="code_agent:t1")
# 此后所有 log.info(...) 自动携带 trace_id、agent_id、user_id、thread_id
```

**子代理级上下文**（策略内绑定，该子代理执行期间自动携带）：

```python
# react.py / function_calling.py / programmatic.py 内部
bind(sub_name="coder", strategy="react")   # 自动携带 sub_name + strategy
bind(iteration=2)                           # 循环场景追加迭代号
```

**上下文传播链示意**：

```
请求入口 bind_trace_id(trace_id, agent_id, user_id, thread_id)
  │
  ├── classify 节点: log.info("classify.result")  ← 携带 [trace_id, agent_id, ...]
  │
  ├── sub-agent 节点: bind(sub_name="coder", strategy="react")
  │     │
  │     ├── llm_call: log.info("llm.call")  ← 携带 [trace_id, ..., sub_name, strategy]
  │     ├── bind(iteration=1)
  │     ├── tools:    log.info("tool.result")  ← 携带 [+ iteration]
  │     └── ...
  │
  ├── 下一个 sub-agent: bind(sub_name="researcher", strategy="react")
  │     └── ...  ← 携带新的 sub_name + strategy（trace_id 不变）
  │
  └── clear_trace()  ← 请求结束，清除所有上下文
```

`bind()` 是对 `structlog.contextvars.bind_contextvars` 的短别名——每次 bind 追加新的 k=v，不清除已有的。trace_id 由 `bind_trace_id` 绑定时会先 `clear_contextvars()` 再写入，确保请求间不串。

### 全链路日志

一个完整请求的日志事件序列：

```
1. log.info("gateway.request", mode="invoke")        ← 请求入口
2. log.debug("classify.llm_input", messages_count=3)  ← classify 输入
3. log.debug("classify.llm_output", raw_response=...)  ← classify 输出
4. log.info("classify.result", intent="code_write", confidence=0.92, threshold=0.7)
5. log.info("route.decision", intent="code_write", target="coder")  ← 路由决策
6. bind(sub_name="coder", strategy="react")          ← 上下文切换
7. log.info("sub_agent.start")                        ← 子代理开始
8. log.info("llm.call", messages_count=2)             ← ReAct 第1轮 LLM
9. log.info("llm.response", tool_calls=1)             ← LLM 决定调工具
10. log.info("tool.call", tool_name="web_search", ...) ← 工具调用
11. log.info("tool.result", tool_name="web_search", status="ok")
12. bind(iteration=1)                                  ← 第2轮迭代
13. log.info("llm.call", messages_count=4)             ← ReAct 第2轮 LLM
14. log.info("llm.response", tool_calls=0)             ← LLM 不再调工具
15. log.info("sub_agent.end", duration_ms=1234)        ← 子代理结束
16. log.info("gateway.complete", duration_ms=1500, messages_count=6)
```

每个事件都携带 trace_id，所有日志 `grep "trace_id.*a1b2c3d4e5f6"` 即可获取该请求的完整链路。

### 外部代码使用

系统内的外部模块（如 ConfigCenter、RateLimiter）也可独立使用 structlog：

```python
import structlog
logger = structlog.get_logger("artipivot.config")
logger.info("ratelimit.config_updated", scope="agent", key="code_agent")
```

使用 `artipivot` 前缀的 logger 名称，`configure_logging()` 中的 `foreign_pre_chain` 处理器会自动格式化这些外部日志，使其与内部日志一致的 JSON 结构。

### 配置与文件

**初始化**（在应用启动时调用一次）：

```python
from artipivot.observability.logging import configure_logging

# 默认：logs/ 目录，级别 INFO（或 ARTIPIVOT_LOG_LEVEL 环境变量）
configure_logging()

# 自定义目录和级别
configure_logging(log_dir="/var/log/artipivot", level="DEBUG")
```

**日志级别解析优先级**：显式 `level` 参数 > 环境变量 `ARTIPIVOT_LOG_LEVEL` > 默认 `"INFO"`

**输出文件**：

| 文件 | 处理 | 保留天数 | 内容 |
|------|------|---------|------|
| `logs/artipivot.log` | `TimedRotatingFileHandler`，每天午夜轮转 | 30 天 | 所有 `>= level` 的事件 |
| `logs/error.log` | `TimedRotatingFileHandler`，每天午夜轮转 | 90 天 | 仅 ERROR 级别（用于告警） |
| `stderr`（仅 DEBUG 模式） | `StreamHandler` | — | 当 `level=DEBUG` 时额外输出到控制台 |


**可选 OTel 集成**：

```bash
# 开启 OpenTelemetry 指标导出
OTEL_ENABLED=true python main.py
```

开启后自动记录以下指标：

| 指标 | 类型 | 说明 |
|------|------|------|
| `artipivot.request.duration` | Histogram | 请求耗时 |
| `artipivot.classify.duration` | Histogram | 意图分类耗时 |
| `artipivot.tool.duration` | Histogram | 工具调用耗时 |
| `artipivot.tool.errors` | Counter | 工具调用错误次数 |
| `artipivot.intent.classified` | Counter | 意图分类分布 |
| `artipivot.circuit.opens` | Counter | 熔断器打开次数 |

---

## 完整案例

### 案例一：代码助手

```bash
curl -X POST http://localhost:8000/api/v1/chat/code_assistant \
  -d '{"message": "帮我写一个快速排序的 Python 实现", "thread_id": "t1", "user_id": "alice"}'
```

### 案例二：研究 + 写作双 Agent

```yaml
agents:
  research_agent:
    model:
      provider: openai
      name: gpt-4o
    routing:
      confidence_threshold: 0.6
      intents:
        search: researcher
        summarize: researcher
        write: writer
    sub_agents:
      researcher:
        strategy: react
        tools: [web_search]
        system_prompt: "You are a research assistant. Plan, search, and synthesize."
        strategy_config:
          max_iterations: 5
      writer:
        strategy: react
        tools: [web_search, file_io]
        system_prompt: "You are a professional writer."
    prompts:
      classify: "Classify: search, summarize, or write."
      respond: "Present the result clearly."
```

### 案例三：自定义 DSL Pipeline

多段 mini-agent 管线，每段不同角色 + 不同工具集：

```yaml
# agents.yaml 中
doc_processor:
  model:
    provider: openai
    name: gpt-4o
  routing:
    confidence_threshold: 0.5
    intents:
      process: pipeline
  sub_agents:
    pipeline:
      graph:
        nodes:
          # Stage 1: 研究员 — 收集信息
          researcher:
            type: llm
            system_prompt: "你是研究员，根据用户需求收集信息。"
            tools: [echo, current_time]
          collector:
            type: tools
            tools: [echo, current_time]

          # 桥梁：总结第一阶段
          summarizer:
            type: llm
            system_prompt: "总结前面收集到的信息，提取关键要点。"

          # Stage 2: 精炼员 — 不同角色 + 不同工具
          refiner:
            type: llm
            system_prompt: "基于总结，进一步处理或格式化输出。"
            tools: [echo]
          formatter:
            type: tools
            tools: [echo]

          # HITL 人工审批
          review:
            type: llm
            system_prompt: "审核最终结果，确保质量。"
            interrupt: after   # ← HITL：暂停等人工确认

        edges:
          - { from: START, to: researcher }
          - { from: researcher, to: collector }
          - { from: collector, to: summarizer }
          - { from: summarizer, to: refiner }
          - { from: refiner, to: formatter }
          - { from: formatter, to: review }
          - { from: review, to: END }
```

---

## Admin API 速查

### Chat

```
POST /api/v1/chat/{agent_id}
  body: {message, thread_id?, user_id?}
  → {response, thread_id}
```

### Agent 管理

```
POST   /admin/agents                      # 动态注册主 Agent
GET    /admin/agents                      # 列出所有主 Agent
GET    /admin/agents/{agent_id}           # 查询主 Agent 定义
```

### 模型管理

```
GET    /admin/models/{agent_id}           # 查询 agent 模型配置
PUT    /admin/models/user/{user_id}       # 设置用户全局模型
PUT    /admin/models/user/{user_id}/agent/{agent_id}  # 设置用户 agent 级模型
GET    /admin/models/user/{user_id}       # 查询用户模型配置
DELETE /admin/models/user/{user_id}/agent/{agent_id}  # 删除用户级覆盖
```

### Plugin 管理

```
GET    /admin/plugins                     # 列出插件
POST   /admin/plugins                     # 发布插件
DELETE /admin/plugins/{type}/{agent_id}/{name}  # 下线插件
```

### 路由管理

```
GET    /admin/routing/{agent_id}          # 查询路由配置
```

### Rate Limit

```
GET    /admin/ratelimits                  # 查询限流配置
PUT    /admin/ratelimits/agent/{agent_id} # 设置 agent 限流
PUT    /admin/ratelimits/tool/{tool_name} # 设置工具限流
```

### 图可视化

```
GET    /admin/graph/{agent_id}/mermaid    # Mermaid 流程图
GET    /admin/graph/{agent_id}/structure  # JSON 结构
```

### 健康检查

```
GET    /health                            # 服务健康
GET    /admin/health                      # Admin 健康检查
```

---

## 配置文件参考


| 配置项 | 管理方式 | 存储 |
|------|---------|------|
| 主 Agent 定义（模型、路由、子代理、prompt） | Web 页面 / Admin API | DocumentStore `agents` |
| 模型配置（global fallback、agent 级） | Web 页面 / Admin API | DocumentStore `model_configs` |
| 路由配置（意图映射、阈值） | Web 页面 / Admin API | DocumentStore `routing_configs` |
| 提示词（classify 等节点） | Web 页面 / Admin API | DocumentStore `prompt_configs` |
| 默认回复话术（clarify/fallback） | Web 页面 / Admin API | DocumentStore `agents` |
| 子代理定义 | Web 页面 / Admin API | DocumentStore `sub_agent_configs` |
| 记忆配置 | Web 页面 / Admin API | DocumentStore `agents` |
