# ArtiPivot

**生产级多 Agent 编排框架** — 三层解耦，子代理热加载，177 个测试全部通过。

LangGraph v1.2 · FastAPI · structlog · 可插拔存储

---

## 30 秒体验

```python
from artipivot.api.server import create_app, init_app
import uvicorn

# 启动服务器（首次自动从 config/seed/ 加载种子配置）
init_app()
app = create_app()
uvicorn.run(app, port=8000)
```

```bash
# 发送请求
curl -X POST http://localhost:8000/api/v1/chat/code_agent \
  -H "Content-Type: application/json" \
  -d '{"message": "用 Python 写一个快速排序", "user_id": "alice"}'
```

同一个 API 端点，按 `agent_id` 自动路由到不同的 Agent 和子代理：

```bash
curl -X POST http://localhost:8000/api/v1/chat/research_agent \
  -d '{"message": "调研 Transformer 架构的最新进展", "user_id": "alice"}'
```

---

## 为什么需要 ArtiPivot

当前主流 Agent 框架（AutoGen、CrewAI 等）大多采用扁平架构，所有能力塞进一个 Agent，带来三个核心问题：

| 问题 | 表现 | ArtiPivot 解法 |
|------|------|---------------|
| 职责混乱 | 一个 Agent 同时负责理解意图、规划任务、调用工具、组织回答 | **三层解耦**：路由 → 子代理 → 工具，各司其职 |
| 工具无法复用 | 工具绑死在某个 Agent 内部 | **共享 ToolRegistry**：所有子代理按白名单共享工具池 |
| 扩展侵入性强 | 添加新能力需要修改框架核心 | **插件热加载**：运行时 publish，自动重建图，无需重启 |

---

## 三层架构

```
┌─────────────────────────────────────────────────────┐
│                  AgentGateway                        │
│            按 agent_id 分发请求                       │
├─────────────────────────────────────────────────────┤
│  第一层 · 多主路由 Agent（并行，可动态注册）           │
│  ┌──────────┐  ┌──────────┐  ┌──────┐              │
│  │code_agent│  │research  │  │ ...  │   classify    │
│  │classify  │  │_agent    │  │      │   → route     │
│  │→ route   │  │classify  │  │      │               │
│  │          │  │→ route   │  │      │               │
│  └────┬─────┘  └────┬─────┘  └──┬───┘              │
├───────┼──────────────┼──────────┼───────────────────┤
│  第二层 · 子代理（可插拔，支持热加载）                 │
│  ┌────┐ ┌────┐  ┌──────────┐  ┌──────┐             │
│  │writer│reviewer│researcher│  │ ...  │  独立 State  │
│  │ReAct││ReAct │  │   CoT    │  │      │  独立模型    │
│  └──┬─┘ └──┬──┘  └────┬─────┘  └──┬───┘  独立策略    │
├──────┼──────┼──────────┼──────────┼───────────────────┤
│  第三层 · 工具（共享资源池）                           │
│  ┌──────┐ ┌────────┐ ┌───────┐ ┌────────┐          │
│  │web   │ │code    │ │file   │ │MCP     │          │
│  │search│ │exec    │ │io     │ │tools   │          │
│  └──────┘ └────────┘ └───────┘ └────────┘          │
├─────────────────────────────────────────────────────┤
│  横切 · 记忆（三层 State/Checkpointer/Store）         │
│  横切 · 日志（8 通道 structlog + trace_id 全链路）    │
└─────────────────────────────────────────────────────┘
```

### 第一层 — 多主路由 Agent

多个主 Agent **并行运行**，各自拥有独立的图、意图体系和子代理集合，五维隔离互不干扰。

- 图拓扑：`START → classify → route → (子代理/clarify/fallback) → respond → END`
- 通过 `AgentRegistry.register_def()` 动态注册，自动构建子图 + 主图 + 注册到 Gateway
- 路由规则存储在 ConfigCenter，**热更新，下次请求自动生效，无需重建图**

### 第二层 — 子代理

子代理是自治执行单元，独立完成"规划 → 调工具 → 生成响应"全流程。

**三种创建方式：**

| 方式 | 适用场景 | 示例 |
|------|---------|------|
| **声明式** — YAML 配置 | 零代码快速创建 | `strategy: react` + `tools: [web_search]` |
| **编程式** — Python API | 完全控制图结构 | `build_programmatic_subagent(def, tool_node)` |
| **插件热加载** — REST/CLI | 运行时动态添加 | `pm.publish(PluginDocument(...))` → 自动重建图 |

**三种内置策略（可通过 `register_strategy()` 扩展）：**

| 策略 | 图拓扑 | 适用 |
|------|-------|------|
| **ReAct** | think → tools → think 循环 | 复杂多步推理 |
| **Chain-of-Thought** | plan → execute → synthesize | 可分解的结构化任务 |
| **Function Calling** | llm → tools → END | 简单查询/转换 |

### 第三层 — 工具

工具是原子化、无状态的执行能力，注册在全局 `ToolRegistry` 中：

- `@tool` 装饰器自定义工具 + MCP 适配器接入外部工具
- 子代理通过 ToolNode 白名单引用，实现 **权限隔离**
- 运行时注册新工具：`registry.register(tool)`，下次构建 ToolNode 自动包含

---

## 记忆系统

三层记忆，各司其职：

| 层级 | 实现 | 作用域 | 后端 |
|------|------|--------|------|
| **L1 · State** | `ArtiPivotState` / `SubAgentState` | 单次图执行 | 内存 |
| **L2 · Checkpointer** | `register_checkpointer_backend()` | per-thread 持久化 | Memory / PostgreSQL |
| **L3 · Store** | `register_store_backend()` | 跨 thread 长期记忆 | Memory / PostgreSQL |

Store 按 `(agent_id, user_id)` namespace 隔离，不同 Agent 的知识库互不可见。

---

## 可观测性

8 通道 structlog，基于 `contextvars` 自动传播 `trace_id`：

| 通道 | 覆盖 |
|------|------|
| **trace** | 请求全生命周期 |
| **session** | 会话创建/恢复 |
| **llm** | prompt、response、token 统计 |
| **tool** | 工具名、入参、结果、耗时 |
| **memory** | Checkpointer 保存/读取、Store 读写 |
| **error** | 异常（含堆栈） |
| **audit** | 配置变更、插件发布 |
| **main** | INFO+ 聚合通道 |

可选开启 OpenTelemetry 导出：`OTEL_ENABLED=true`

---

## 项目结构

```
artipivot/
├── config/seed/                # 种子配置（YAML，首次启动自动加载）
│   ├── agents.yaml             #   多 Agent 声明
│   ├── models.yaml             #   模型配置 + fallback 链
│   ├── routing.yaml            #   意图 → 子代理映射
│   ├── prompts.yaml            #   系统提示词
│   ├── sub_agents.yaml         #   声明式子代理定义
│   └── memory.yaml             #   记忆策略
│
├── src/artipivot/
│   ├── api/                    # FastAPI（REST + Admin API）
│   ├── gateway/                # 多主 Agent 分发与注册
│   ├── graph/                  # LangGraph 图定义与路由
│   ├── agents/                 # 子代理 + 策略引擎（ReAct/CoT/FC）
│   ├── tools/                  # 工具注册表 + MCP 适配器
│   ├── memory/                 # 三层记忆 + 上下文压缩
│   ├── models/                 # 模型适配 + 三级 Fallback
│   ├── config/                 # 热更新配置中心
│   ├── storage/                # 可插拔存储（Memory/PostgreSQL）
│   ├── plugins/                # 插件系统（热重建图）
│   ├── resilience/             # 熔断/重试/限流
│   ├── observability/          # 8 通道日志 + OTel
│   └── cli/                    # CLI（Typer）
│
├── doc/modules/                # 模块详细文档（10 个）
└── tests/                      # 177 个单元测试
```

---

## 快速开始

```bash
# 安装
uv sync --dev

# 测试
uv run pytest tests/ -v          # 177 个测试

# 交互式 demo（需 API Key）
export ANTHROPIC_API_KEY=sk-...
uv run python demo.py

# 启动服务
uv run artipivot serve --port 8000

# CLI 创建插件
uv run artipivot plugin init my_plugin --template react
```

---

## 模块文档

| 模块 | 文档 | 内容 |
|------|------|------|
| 存储层 | [storage.md](doc/modules/storage.md) | DocumentStore / ChangeNotifier / ArtifactStore 接口与后端 |
| 模型层 | [models.md](doc/modules/models.md) | ModelConfig、三级 Fallback、供应商工厂、动态切换 |
| 工具层 | [tools.md](doc/modules/tools.md) | ToolRegistry、@tool 装饰器、MCP 适配器 |
| 子代理 | [agents.md](doc/modules/agents.md) | 编程式/声明式定义、策略引擎（ReAct/CoT/FC） |
| 配置中心 | [config.md](doc/modules/config.md) | ConfigCenter、PromptStore、RoutingConfig、RateLimiter |
| 记忆系统 | [memory.md](doc/modules/memory.md) | 三层记忆模型、可插拔后端、Namespace 隔离 |
| 多主 Agent | [multi_agent.md](doc/modules/multi_agent.md) | AgentDef、AgentRegistry、YAML 声明、五维隔离 |
| 插件系统 | [plugins.md](doc/modules/plugins.md) | PluginManager、GraphRebuilder 热重建、PluginWatcher |
| 容错 | [resilience.md](doc/modules/resilience.md) | CircuitBreaker、RetryPolicy、RateLimiter |
| 可观测 + API | [observability_api.md](doc/modules/observability_api.md) | 8 通道日志、OpenTelemetry、REST/CLI 参考 |

---

## 热更新 vs 需重建

| 变更 | 需重建图？ | 机制 |
|------|:---------:|------|
| 注册新主 Agent | 是 | `register_def()` → 构建子图 + 主图 → Gateway 注册 |
| 发布/弃用子代理插件 | 是 | PluginWatcher → GraphRebuilder 重建 |
| 修改路由规则 | 是 | ConfigCenter 回调 → GraphRebuilder 重建 |
| 切换模型 | **否** | ModelProvider 每次 invoke 动态解析，下次请求生效 |
| 修改提示词 | **否** | ConfigCenter 从 DocumentStore 热读取 |
| 修改限流规则 | **否** | RateLimiter 从 DocumentStore 热更新 |
| 注册新工具 | **否** | `registry.register()` 写入，下次构建 ToolNode 自动包含 |

---

## 扩展点速查

| 扩展点 | 接口/基类 | 注册方式 | 热更新 |
|--------|-----------|----------|:------:|
| 模型供应商 | `_factories[provider]` | 添加工厂函数 | ✓ |
| 子代理策略 | `Strategy` ABC | `register_strategy()` | — |
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

Python 3.12 · LangGraph v1.2 · FastAPI + Uvicorn · structlog + orjson · Typer CLI · Anthropic Claude / OpenAI GPT · Memory / PostgreSQL 可插拔存储
