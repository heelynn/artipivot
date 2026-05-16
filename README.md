# ArtiPivot

**生产级多 Agent 编排框架** — 三层解耦，子代理热加载，Transform 数据编排，251 个测试全部通过。

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
| 数据编排受限 | 多个工具/子代理的返回值难以灵活组合 | **Transform 系统**：DSL 管控制流，Python 函数管数据变换，热加载生效 |

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
│  │  策略模板 ReAct/CoT/FC │ Graph DSL YAML 自定义图  │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌─ 数据编排 ───────────────────────────────────────┐    │
│  │  Transform 注册表 — 按名引用，替换 ≠ 重建图       │    │
│  │  来源：pip 包 / YAML / REST API                   │    │
│  └──────────────────────┬───────────────────────────┘    │
│                         │                                 │
├─────────────────────────┼─────────────────────────────────┤
│  第三层 · 工具（共享资源池）              │               │
│  ┌──────┐ ┌────────┐ ┌───────┐ ┌────────┐              │
│  │web   │ │code    │ │file   │ │MCP     │              │
│  │search│ │exec    │ │io     │ │tools   │              │
│  └──────┘ └────────┘ └───────┘ └────────┘              │
├──────────────────────────────────────────────────────────┤
│  横切 · 记忆（三层 State/Checkpointer/Store）             │
│  横切 · 日志（8 通道 structlog + trace_id 全链路）        │
└──────────────────────────────────────────────────────────┘
```

子代理由两部分组成：

- **图拓扑**决定执行流程 — 策略模板（ReAct/CoT/FC）或 Graph DSL（YAML 自定义），DSL 让不写代码也能定义任意流程
- **数据编排**决定数据怎么流动 — Transform 注册表按名引用变换函数，替换函数不触发图重建，来源不限（pip 包/YAML/REST API）

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
| **DSL 图** — YAML 自定义拓扑 | 自定义流程编排 | `graph:` + `nodes/edges` 定义 |
| **编程式** — Python API | 完全控制图结构 | `build_programmatic_subagent(def, tool_node)` |
| **插件热加载** — REST/CLI | 运行时动态添加 | `pm.publish(PluginDocument(...))` → 自动重建图 |

**三种内置策略（可通过 `register_strategy()` 扩展）：**

| 策略 | 图拓扑 | 适用 |
|------|-------|------|
| **ReAct** | think → tools → think 循环 | 复杂多步推理 |
| **Chain-of-Thought** | plan → execute → synthesize | 可分解的结构化任务 |
| **Function Calling** | llm → tools → END | 简单查询/转换 |

### Graph DSL

当三种固定策略无法满足需求时，用 Graph DSL 在 YAML 中定义任意图拓扑：

```yaml
sub_agents:
  research_and_code:
    graph:
      nodes:
        search:   { type: tool, tool: web_search }
        execute:  { type: tool, tool: code_exec }
        merge:    { type: transform, handler: merge_results }
        respond:  { type: llm, system_prompt: "Compose a response." }
      edges:
        - { from: START, to: search }
        - { from: START, to: execute }
        - { from: search, to: merge }
        - { from: execute, to: merge }
        - { from: merge, to: respond }
        - { from: respond, to: END }
```

5 种节点类型：`llm` / `tool` / `tools` / `transform` / `sub_agent`。条件路由支持字段映射、内置函数、Transform 路由三种机制。详见 [graph_dsl.md](doc/modules/graph_dsl.md)。

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

## Transform 系统

Transform 是轻量数据编排机制 — **Python 函数管数据变换，注册表管生命周期，热加载即时生效**。当多个工具或子代理的返回值需要合并、过滤、格式化时，用 Transform 节点处理，无需编写完整的 Agent 类。

### 核心设计

Transform 变更**不触发图重建**。图节点在执行时从注册表获取函数引用，替换函数后下次执行自动生效。

函数可以来自任意位置 — 本地文件、pip 包、git 仓库 — 框架只关心能不能 import 到。

### 三种注册来源

| 来源 | 时机 | 是否需要重启 | 使用场景 |
|------|------|:----------:|---------|
| **Entry Points** | 启动自动发现 | 是 | pip 包发布，团队共享 |
| **YAML 配置** | 启动加载 + 热加载 | 否 | 运行时动态调整 |
| **REST API** | 运行时即时注册 | 否 | 临时调试，快速验证 |

### 使用示例

**1. 编写 Transform 函数（任意 Python 文件）**

```python
# my_transforms/merge.py
async def merge_results(data: dict) -> dict:
    """合并多个工具/子代理的返回值"""
    results = data.get("results", [])
    return {
        **data,
        "summary": " | ".join(r.get("content", "") for r in results),
        "count": len(results),
    }
```

**2. 注册 Transform（三种方式任选其一）**

```yaml
# 方式 A: config/seed/transforms.yaml — 配置即用
transforms:
  merge_results:
    module: my_transforms.merge
    function: merge_results
```

```bash
# 方式 B: REST API — 不重启即时生效
curl -X POST http://localhost:8000/admin/transforms/register \
  -H "Content-Type: application/json" \
  -d '{"name": "merge_results", "module": "my_transforms.merge", "function": "merge_results"}'
```

```toml
# 方式 C: pip 包 Entry Points — pip install 自动发现
[project.entry-points."artipivot.transforms"]
merge_results = "my_transforms.merge:merge_results"
```

**3. 在图中使用 Transform 节点**

```python
from artipivot.transforms.nodes import make_transform_node

# 创建 LangGraph 节点 — 运行时动态查找函数
node = make_transform_node("merge_results", registry, input_key="metadata")
builder.add_node("merge", node)
```

### Transform 热加载流程

```
改 transforms.yaml 或调 REST API
    ↓
DocumentStore.put() → ChangeNotifier.notify()
    ↓
TransformWatcher.apply() → registry.register_module()
    ↓
函数引用替换（不重建图，不中断请求）
    ↓
下次图执行 → registry.get() → 拿到新函数
```

### Admin API

```
GET    /admin/transforms              # 列出所有已注册 Transform
POST   /admin/transforms/register     # 运行时注册（即时生效）
DELETE /admin/transforms/{name}        # 注销
```

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
│   ├── transforms.yaml         #   Transform 函数注册
│   └── memory.yaml             #   记忆策略
│
├── src/artipivot/
│   ├── api/                    # FastAPI（REST + Admin API）
│   ├── gateway/                # 多主 Agent 分发与注册
│   ├── graph/                  # LangGraph 图定义、路由、DSL
│   ├── agents/                 # 子代理 + 策略引擎（ReAct/CoT/FC）
│   ├── tools/                  # 工具注册表 + MCP 适配器
│   ├── memory/                 # 三层记忆 + 上下文压缩
│   ├── models/                 # 模型适配 + 三级 Fallback
│   ├── config/                 # 热更新配置中心
│   ├── storage/                # 可插拔存储（Memory/PostgreSQL）
│   ├── plugins/                # 插件系统（热重建图）
│   ├── resilience/             # 熔断/重试/限流
│   ├── transforms/             # Transform 注册表 + 热加载 + 图节点
│   ├── observability/          # 8 通道日志 + OTel
│   └── cli/                    # CLI（Typer）
│
├── doc/modules/                # 模块详细文档（11 个）
└── tests/                      # 251 个单元测试
```

---

## 快速开始

```bash
# 安装
uv sync --dev

# 测试
uv run pytest tests/ -v          # 251 个测试

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
| Transform | [transforms.md](doc/modules/transforms.md) | TransformRegistry、热加载、Entry Points、图节点集成 |
| Graph DSL | [graph_dsl.md](doc/modules/graph_dsl.md) | YAML 自定义图拓扑、5 种节点、条件路由、热加载 |
| 容错 | [resilience.md](doc/modules/resilience.md) | CircuitBreaker、RetryPolicy、RateLimiter |
| 可观测 + API | [observability_api.md](doc/modules/observability_api.md) | 8 通道日志、OpenTelemetry、REST/CLI 参考 |

---

## 热更新 vs 需重建

| 变更 | 需重建图？ | 机制 |
|------|:---------:|------|
| 注册新主 Agent | 是 | `register_def()` → 构建子图 + 主图 → Gateway 注册 |
| 发布/弃用子代理插件 | 是 | PluginWatcher → GraphRebuilder 重建 |
| 发布含 `graph:` 的 DSL 插件 | 是 | GraphRebuilder 重建 DSL 图 |
| 修改路由规则 | 是 | ConfigCenter 回调 → GraphRebuilder 重建 |
| 切换模型 | **否** | ModelProvider 每次 invoke 动态解析，下次请求生效 |
| 修改提示词 | **否** | ConfigCenter 从 DocumentStore 热读取 |
| 修改限流规则 | **否** | RateLimiter 从 DocumentStore 热更新 |
| 注册新工具 | **否** | `registry.register()` 写入，下次构建 ToolNode 自动包含 |
| 注册/更新 Transform | **否** | TransformWatcher 替换函数引用，下次执行生效 |
| DSL 图中 Transform 节点更新 | **否** | 复用 TransformRegistry 热加载，下次执行生效 |

---

## 扩展点速查

| 扩展点 | 接口/基类 | 注册方式 | 热更新 |
|--------|-----------|----------|:------:|
| 模型供应商 | `_factories[provider]` | 添加工厂函数 | ✓ |
| 子代理策略 | `Strategy` ABC | `register_strategy()` | — |
| DSL 图 | `GraphDef` | YAML `graph:` 或插件 manifest | — |
| 自定义工具 | `@tool` 装饰器 | `registry.register(tool)` | — |
| 存储后端 | `DocumentStore` | 继承 + 工厂函数 | — |
| Checkpointer | `BaseCheckpointSaver` | `register_checkpointer_backend()` | — |
| Store | `BaseStore` | `register_store_backend()` | — |
| 多主 Agent | `AgentDef` | `AgentRegistry.register_def()` | — |
| 子代理插件 | `PluginDocument` | `pm.publish()` | ✓ |
| 图热重建 | `GraphRebuilder` | `rebuilder.rebuild_agent()` | ✓ |
| MCP 工具 | `MCPToolAdapter` | `MCPRegistry.register_server()` | — |
| Transform | `TransformRegistry` | `registry.register()` / Entry Points / YAML / API | ✓ |
| OTel | `observability/otel.py` | `OTEL_ENABLED=true` | ✓ |

---

## 技术栈

Python 3.12 · LangGraph v1.2 · FastAPI + Uvicorn · structlog + orjson · Typer CLI · Anthropic Claude / OpenAI GPT · Memory / PostgreSQL 可插拔存储
