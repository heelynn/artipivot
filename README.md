# ArtiPivot

**生产级多 Agent 编排框架** — 将"理解意图 → 选择专家 → 执行任务 → 组织回答"标准化为可配置的三层架构，所有组件支持热加载。

LangGraph v1.2 · FastAPI · structlog · 可插拔存储

---

## ArtiPivot 解决什么问题

构建 AI Agent 应用时，常见做法是把所有能力塞进一个 Agent。这很快会遇到瓶颈：

- **意图识别不准** — Agent 不知道该调哪个工具
- **扩展困难** — 加一个新能力就要改 Agent 核心
- **工具无法复用** — 工具绑死在某个 Agent 内部

ArtiPivot 将 Agent 拆分为三层，各司其职：

```
用户消息
  → classify（LLM 识别意图：写代码？审查？调试？）
  → route（查映射表，分派给对应子代理）
  → sub-agent（ReAct 循环，调工具，生成结果）
  → respond（格式化输出返回用户）
```

每一层都可以独立配置、热更新、多实例并行。

---

## 30 秒体验

### CLI 直接对话

```bash
# 安装
uv sync --dev

# 配置 .agents.yaml（项目根目录，首次自动创建模板）
# 配置 .env 填入 API Key

# 一行命令对话
uv run artipivot chat code_agent "使用 echo 工具打印 你好"
# → 你好

uv run artipivot chat code_agent "现在时间是多少"
# → 当前时间是：2026-05-17 21:54:00
```

### 启动 HTTP 服务

```bash
# 启动 API 服务（自动加载 .agents.yaml + .env）
uv run artipivot serve --port 8000

# 发送请求
curl -X POST http://localhost:8000/api/v1/chat/code_agent \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我写一个快速排序", "user_id": "alice"}'

# 多 Agent 路由 — 同一端点，按 agent_id 自动分发
curl -X POST http://localhost:8000/api/v1/chat/research_agent \
  -d '{"message": "调研 Transformer 最新进展", "user_id": "alice"}'
```

### .agents.yaml 配置示例

```yaml
# 项目根目录的 .agents.yaml — 启动时自动加载
global:
  fallback_model:
    provider: deepseek
    name: deepseek-v4-flash
    api_key: sk-xxx

tools:
  echo: builtin
  current_time: builtin
  file_io: builtin

agents:
  code_agent:
    model:
      provider: deepseek
      name: deepseek-v4-flash
      api_key: sk-xxx
    routing:
      confidence_threshold: 0.7
      intents:
        code_write:
          target: code_writer
          description: "用户要求编写代码、生成代码片段或创建新功能"
        code_review:
          target: code_writer
          description: "用户要求审查代码、检查质量或提供改进建议"
        debug:
          target: code_writer
          description: "用户遇到代码错误、需要调试或排查问题"
    sub_agents:
      code_writer:
        strategy: react
        tools: [echo, current_time, file_io]
        system_prompt: "你是一个智能助手，可以使用提供的工具来回答问题。"
        strategy_config:
          max_iterations: 5
    prompts:
      classify: ""    # 留空使用内置 default prompt
      respond: "Based on the sub-agent result, compose a helpful response."
```

`intents` 中的 `description` 会自动注入到意图识别的 system prompt 中，让 LLM 准确理解每个意图的边界。

---

## 三层架构

```
┌──────────────────────────────────────────────────────────┐
│                    AgentGateway                           │
│              按 agent_id 分发请求                          │
├──────────────────────────────────────────────────────────┤
│  第一层 · 多主路由 Agent（并行，可动态注册）               │
│  ┌──────────┐  ┌──────────┐  ┌──────┐                   │
│  │code_agent│  │research  │  │ ...  │  classify→route    │
│  └────┬─────┘  └────┬─────┘  └──┬───┘                   │
├───────┼──────────────┼──────────┼────────────────────────┤
│  第二层 · 子代理（可插拔，支持热加载）                     │
│                                                           │
│  ┌─ 图拓扑 ─────────────────────────────────────────┐    │
│  │  策略模板 ReAct/FC │ Graph DSL YAML 自定义图  │    │
│  │  ├ 循环保护 max_iterations                        │    │
│  │  ├ Human-in-the-loop interrupt                    │    │
│  │  ├ 节点级 retry RetryPolicy                       │    │
│  │  ├ 节点级多模型 model override                     │    │
│  │  └ LLM 节点 tools 绑定 — 多段 mini-agent 编排     │    │
│  └──────────────────────────────────────────────────┘    │
│                         │                                 │
├─────────────────────────┼─────────────────────────────────┤
│  第三层 · 工具（共享资源池）              │               │
│  ┌──────┐ ┌─────────┐ ┌──────┐ ┌────────┐              │
│  │ echo │ │current  │ │file  │ │MCP     │              │
│  │      │ │_time    │ │_io   │ │tools   │              │
│  └──────┘ └─────────┘ └──────┘ └────────┘              │
├──────────────────────────────────────────────────────────┤
│  横切 · 记忆（三层 State/Checkpointer/Store）             │
│  横切 · 日志（structlog + trace_id 全链路追踪）           │
│  横切 · 可视化（Mermaid 流程图 + Admin API）              │
└──────────────────────────────────────────────────────────┘
```

### 第一层 — 多主路由 Agent

多个主 Agent **并行运行**，各自拥有独立的图、意图体系和子代理集合，五维隔离互不干扰。

**意图识别与路由流程**：

```
用户消息
  │
  ▼
classify 节点（LLM 结构化输出）
  │ 读取 intents + description → 识别意图 + 置信度
  │ 输出: {"intent": "code_write", "confidence": 0.92}
  ▼
route_by_intent 条件边（查表分派）
  ├── confidence < threshold → clarify（请用户澄清）
  ├── intent 在映射表中 → 对应子代理
  └── 未匹配 → fallback（兜底）
  ▼
sub-agent 执行
  ▼
respond 格式化输出
```

关键特性：
- **intent description** — YAML 中配置的描述自动注入 classify prompt，LLM 不再只靠意图名猜测
- **热更新路由** — intent_map、threshold、classify prompt 修改即时生效，无需重建图
- **动态注册主 Agent** — 通过 Admin API 运行时注册新 Agent

### 第二层 — 子代理

子代理是**无状态的一级公民** — compiled graph 是纯拓扑，状态由 LangGraph runtime 在调用时注入。同一个 compiled graph 可以被多个主 Agent 共享。

子代理 = 图拓扑（策略模板或 Graph DSL），LLM 节点支持 `tools` 绑定，天然支持多段 mini-agent 编排

#### 三种策略模板

| 策略 | 图拓扑 | 适用场景 |
|------|-------|---------|
| **ReAct** | think → tools → think 循环 | 复杂多步推理，需要反复调用工具 |
| **Chain-of-Thought** | plan → execute → synthesize | 可分解的结构化任务 |
| **Function Calling** | llm → tools → END | 简单查询/转换，单次工具调用 |

```yaml
sub_agents:
  code_writer:
    strategy: react
    tools: [echo, current_time, file_io]
    system_prompt: "You are a coding assistant."
    strategy_config:
      max_iterations: 5
```

可通过 `register_strategy()` 注册自定义策略，实现 `Strategy` ABC 的 `build()` 方法。

#### Graph DSL 自定义拓扑

当固定策略无法满足时（并行执行、条件分支、多段接力），用 `graph:` 定义任意图拓扑。LLM 节点支持 `tools` 字段绑定工具，每个 LLM 节点可以是不同角色的 mini-agent：

```yaml
sub_agents:
  pipeline:
    graph:
      nodes:
        # Stage 1: 研究员 — LLM 绑定 echo + current_time
        researcher:
          type: llm
          system_prompt: "你是研究员，根据用户需求收集信息。"
          tools: [echo, current_time]
        collector:
          type: tools
          tools: [echo, current_time]

        # 桥梁：整合第一阶段
        summarizer:
          type: llm
          system_prompt: "总结前面收集到的原始信息。"

        # Stage 2: 精炼员 — 不同角色 + 不同工具集
        refiner:
          type: llm
          system_prompt: "基于总结进一步处理或格式化。"
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

4 种节点类型：`llm`（LLM 调用，可选 tools 绑定）、`tool`（单工具）、`tools`（多工具 ToolNode）、`sub_agent`（嵌套子代理）

**LLM 节点 tools 绑定**：LLM 产出 `tool_calls`，下游 `tools` 节点（LangGraph ToolNode）自动消费并执行，结果写回 `messages`——数据全程走 LangGraph 原生消息流，不需要中间适配层。

### ReAct vs DSL Pipeline

| | ReAct | DSL 多段编排 |
|---|---|---|
| **决策权** | LLM 自己决定调什么、几轮 | 每段独立角色 + 独立 prompt + 独立工具集 |
| **工具集** | 一个 LLM 绑一套工具 | 不同段可以绑不同工具 |
| **迭代** | 自动循环（max_iterations 保护） | 每段单次执行，可接任意多段 |
| **适合** | 开放式对话、不确定任务 | 已知工作流、需要分阶段处理的管线 |

ReAct 是“一个聪明大脑 + 一套工具反复调用”，DSL 是“多个专业角色按流程接力”。两者可以在同一个项目中混用——简单意图走 ReAct，复杂管线走 DSL。

#### 插件热加载

运行时通过 REST API 发布子代理，GraphRebuilder 自动重建图并原子替换：

```bash
curl -X POST http://localhost:8000/admin/plugins \
  -d '{
    "plugin_type": "sub_agent",
    "name": "dynamic_agent",
    "agent_id": "code_agent",
    "manifest": {
      "strategy": "react",
      "tools": ["web_search"],
      "system_prompt": "You are a dynamic agent."
    }
  }'
```

### 第三层 — 工具

工具是原子化、无状态的执行能力，注册在全局 `ToolRegistry` 中：

**内置工具**：

| 工具 | 说明 | 参数 |
|------|------|------|
| `echo` | 回显消息 | `message` |
| `current_time` | 获取当前时间 | 无 |
| `file_io` | 文件读写 | `path`, `content`, `action` |

**自定义工具**：

```python
from langchain_core.tools import tool

@tool
def database_query(sql: str, limit: int = 100) -> str:
    """查询数据库。Query a database and return results.

    Args:
        sql: SQL 查询语句。
        limit: 最大返回行数。
    """
    return execute_sql(sql, limit)
```

工具 description 支持中英双语，LLM 跨语言匹配更准确。注册到 ToolRegistry 后所有子代理按白名单共享，支持 MCP 适配器接入外部工具。

---

## 记忆系统

三层记忆，各司其职：

| 层级 | 实现 | 作用域 | 后端 |
|------|------|--------|------|
| **L1 · State** | `ArtiPivotState` / `SubAgentState` | 单次图执行 | 内存 |
| **L2 · Checkpointer** | `register_checkpointer_backend()` | per-thread 对话持久化 | Memory / PostgreSQL |
| **L3 · Store** | `register_store_backend()` | 跨 thread 长期记忆 | Memory / PostgreSQL |

Store 按 `(agent_id, user_id)` namespace 隔离，不同 Agent 的知识库互不可见。

---

## 模型配置

两种协议覆盖所有主流 LLM 供应商：

| provider 值 | 覆盖范围 |
|-------------|---------|
| `openai` | OpenAI、DeepSeek、Moonshot、通义千问、任何 OpenAI 兼容 API |
| `anthropic` | Anthropic 官方、任何 Anthropic 兼容 API |

多级优先级链（用户级 > Agent 级 > 全局 fallback）+ 递归 fallback 降级链。支持运行时热更新。

```yaml
model:
  provider: openai
  name: deepseek-chat
  base_url: https://api.deepseek.com
  api_key: sk-xxx
  fallback:
    provider: anthropic
    name: claude-sonnet-4-6
```

---

## 可观测性

structlog 结构化日志，基于 `contextvars` 自动传播 `trace_id`。所有日志可通过 `grep "trace_id.*xxx"` 获取完整请求链路。

**切面式日志** — `GraphLoggingCallback` 自动记录每个节点、LLM 调用、工具调用的完整生命周期，业务代码无需手动打日志。

双文件输出：`artipivot.log`（全量）+ `error.log`（仅 ERROR，用于告警）。可选 OpenTelemetry 指标导出：`OTEL_ENABLED=true`

---

## 项目结构

```
artipivot/
├── .agents.yaml                # Agent 配置（启动时自动加载）
├── .env                        # API Key 等环境变量
│
├── config/seed/                # 种子配置（YAML，首次启动自动加载）
│   ├── agents.yaml             #   多 Agent 声明
│   ├── models.yaml             #   模型配置 + fallback 链
│   ├── routing.yaml            #   意图 → 子代理映射
│   ├── prompts.yaml            #   系统提示词
│   └── memory.yaml             #   记忆策略
│
├── src/artipivot/
│   ├── api/                    # FastAPI（REST + Admin API）
│   ├── gateway/                # 多主 Agent 分发与注册
│   ├── graph/                  # LangGraph 图定义、路由、DSL、可视化
│   ├── agents/                 # 子代理 + 策略引擎（ReAct/FC）
│   ├── tools/                  # 工具注册表 + MCP 适配器
│   ├── memory/                 # 三层记忆 + 上下文压缩
│   ├── models/                 # 模型适配 + 三级 Fallback
│   ├── config/                 # 热更新配置中心
│   ├── storage/                # 可插拔存储（Memory/PostgreSQL）
│   ├── plugins/                # 插件系统（热重建图）
│   ├── resilience/             # 熔断/重试/限流
│   ├── observability/          # structlog 日志 + OTel
│   ├── bootstrap.py            # 一键初始化
│   └── cli/                    # CLI（Typer）
│
├── doc/                        # 文档
│   ├── usage.md                #   完整使用指南
│   └── modules/                #   模块详细文档（12 个）
└── tests/                      # 单元测试
```

---

## CLI 命令

```bash
# 与 Agent 对话（最简用法）
artipivot chat <agent_id> "你的消息"

# 列出已注册的 Agent
artipivot agents

# 启动 HTTP API 服务
artipivot serve --port 8000

# 创建插件模板
artipivot plugin init <name> --template react

# 发布插件到运行中的服务
artipivot plugin publish <name> --agent-id <agent_id>
```

---

## 快速开始

```bash
# 1. 安装依赖
uv sync --dev

# 2. 配置 .agents.yaml（参考上方示例）

# 3. 配置 .env（填入 API Key）

# 4. CLI 对话
uv run artipivot chat code_agent "使用 echo 打印 Hello World"

# 5. 或启动 HTTP 服务
uv run artipivot serve --port 8000

# 6. 运行测试
uv run pytest tests/ -v
```

---

## 模块文档

| 模块 | 文档 | 内容 |
|------|------|------|
| 完整使用指南 | [usage.md](doc/usage.md) | 从创建 Agent 到动态热更新的完整流程 |
| 存储层 | [storage.md](doc/modules/storage.md) | DocumentStore / ChangeNotifier / ArtifactStore 接口与后端 |
| 模型层 | [models.md](doc/modules/models.md) | ModelConfig、三级 Fallback、供应商工厂、动态切换 |
| 工具层 | [tools.md](doc/modules/tools.md) | ToolRegistry、@tool 装饰器、MCP 适配器 |
| 子代理 | [agents.md](doc/modules/agents.md) | 编程式/声明式定义、策略引擎（ReAct/FC） |
| 配置中心 | [config.md](doc/modules/config.md) | ConfigCenter、PromptStore、RoutingConfig、RateLimiter |
| 记忆系统 | [memory.md](doc/modules/memory.md) | 三层记忆模型、可插拔后端、Namespace 隔离 |
| 多主 Agent | [multi_agent.md](doc/modules/multi_agent.md) | AgentDef、AgentRegistry、YAML 声明、五维隔离 |
| 插件系统 | [plugins.md](doc/modules/plugins.md) | PluginManager、GraphRebuilder 热重建、PluginWatcher |
| Graph DSL | [graph_dsl.md](doc/modules/graph_dsl.md) | YAML 自定义图拓扑、4 种节点、LLM tools 绑定、条件路由、HITL、重试、多模型 |
| 可视化 | [visual.md](doc/modules/visual.md) | Mermaid 流程图生成、Admin API 图结构查询 |
| 容错 | [resilience.md](doc/modules/resilience.md) | CircuitBreaker、RetryPolicy、RateLimiter |
| 可观测 + API | [observability_api.md](doc/modules/observability_api.md) | structlog 日志、OpenTelemetry、REST/CLI 参考 |

---

## 热更新 vs 需重建

| 变更 | 需重建图？ | 机制 |
|------|:---------:|------|
| 注册新主 Agent | 是 | `register_def()` → 构建子图 + 主图 → Gateway 注册 |
| 发布/弃用子代理插件 | 是 | PluginWatcher → GraphRebuilder 重建 |
| 发布含 `graph:` 的 DSL 插件 | 是 | GraphRebuilder 重建 DSL 图 |
| 修改路由规则 | **否** | RoutingConfig 即时生效，下次 classify 读新值 |
| 切换模型 | **否** | ModelProvider 每次 invoke 动态解析 |
| 修改提示词 | **否** | PromptStore 即时生效，下次 LLM 调用读新值 |
| 修改限流规则 | **否** | RateLimiter 即时生效 |
| 注册新工具 | **否** | `registry.register()`，下次构建 ToolNode 自动包含 |

---

## 扩展点速查

| 扩展点 | 接口/基类 | 注册方式 | 热更新 |
|--------|-----------|----------|:------:|
| 模型供应商 | `_factories[provider]` | 添加工厂函数 | ✓ |
| 子代理策略 | `Strategy` ABC | `register_strategy()` | — |
| DSL 图 | `GraphDef` | YAML `graph:` 或插件 manifest | — |
| 图可视化 | `graph_to_mermaid()` | Admin API `/admin/graph/{id}/mermaid` | — |
| 自定义工具 | `@tool` 装饰器 | `registry.register(tool)` | — |
| 存储后端 | `DocumentStore` | 继承 + 工厂函数 | — |
| Checkpointer | `BaseCheckpointSaver` | `register_checkpointer_backend()` | — |
| Store | `BaseStore` | `register_store_backend()` | — |
| 多主 Agent | `AgentDef` | `AgentRegistry.register_def()` | — |
| 子代理插件 | `PluginDocument` | `pm.publish()` | ✓ |
| 图热重建 | `GraphRebuilder` | `rebuilder.rebuild_agent()` | ✓ |
| MCP 工具 | `MCPToolAdapter` | `MCPRegistry.register_server()` | — |
| OTel | `observability/otel.py` | `OTEL_ENABLED=true` | ✓ |

---

## 技术栈

Python 3.12 · LangGraph v1.2 · FastAPI + Uvicorn · structlog + orjson · Typer CLI · Anthropic Claude / OpenAI GPT / DeepSeek · Memory / PostgreSQL 可插拔存储
