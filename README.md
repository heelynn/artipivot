# ArtiPivot

> 生产级多 Agent 编排框架 — 意图路由、可插拔子 Agent、共享工具池、全组件热加载。

Python 3.12 · LangGraph v1.2 · FastAPI · structlog · 可插拔存储

---

## ArtiPivot 是什么

ArtiPivot 是一个**生产级多 Agent 编排框架**，用清晰的三层架构将"理解意图 → 选择专家 → 执行任务 → 组织回答"标准化为可配置的图拓扑。

每一层独立配置、热加载、多实例并行。YAML 定义，CLI 一行启动。

```
用户消息
  └─ 主 Agent（识别意图 → 路由到子 Agent → 格式化输出）
       └─ 子 Agent（通过 ReAct 循环 / Function Calling / 自定义 DSL 图执行任务）
            └─ 工具（原子能力 — echo、file_io、web_search、MCP 工具……）
```

## 设计亮点

| 亮点 | 说明 |
|------|------|
| **无状态子 Agent** | compiled graph 是纯拓扑，状态由 LangGraph runtime 注入。同一图可被多个主 Agent 共享，相同策略+工具自动去重为同一对象 |
| **意图路由是一等公民** | 分类（LLM 结构化输出）与路由（表查分派）解耦，两者均可运行时热更新，无需重建图 |
| **Graph DSL** | YAML 定义任意图拓扑：多段 LLM 接力、HITL 人工审批、条件分支、节点级重试——零 Python 代码 |
| **原子热替换** | PluginWatcher → GraphRebuilder 构建新图 → `gateway.register()` 原子替换。旧图服务到新图就绪，构建失败不影响线上 |
| **双状态架构** | `ArtiPivotState`（编排）与 `SubAgentState`（执行）分离，通过 LangGraph subgraph 边界映射，非引用传递 |
| **五维隔离** | 多主 Agent 间图、意图、子 Agent、记忆、模型配置完全隔离，互不干扰 |

## 为什么需要 ArtiPivot

把所有能力塞进一个 Agent 的做法很快会遇到瓶颈：

| 问题 | ArtiPivot 的解决方式 |
|------|---------------------|
| 意图识别不准 | LLM 分类 + 每个意图的 description 自动注入 prompt，LLM 精准理解边界 |
| 加能力改坏老逻辑 | 子 Agent 是独立 compiled graph，主 Agent 间共享互不干扰 |
| 工具绑死在一个 Agent 里 | 全局 `ToolRegistry`，注册一次，按白名单分配给子 Agent |
| 改配置要重启 | 模型、提示词、路由规则、限流——全部运行时热更新，无需重建图 |
| 没有生产级可观测性 | structlog + trace_id 全链路追踪、OpenTelemetry、熔断器、限流 |

---

## 30 秒上手

两步启动：**安装 → 启动服务 → 用 Admin API 或 Web 页面初始化**。

**第一步：安装并启动服务**

```bash
uv sync --dev
uv run artipivot serve
```

服务启动后，打开 `http://localhost:5173` 进入 Web 控制台，通过页面管理工具、子 Agent、Agent 配置。

也可以通过 Admin API 初始化，以下是完整的 curl 示例：

**第二步：用 Admin API 初始化配置**

```bash
# ── 1. 注册工具 ──
curl -s -X POST http://localhost:8000/api/v1/admin/tools \
  -H "Content-Type: application/x-yaml" --data "
name: echo
type: builtin
"

curl -s -X POST http://localhost:8000/api/v1/admin/tools \
  -H "Content-Type: application/x-yaml" --data "
name: current_time
type: builtin
"

curl -s -X POST http://localhost:8000/api/v1/admin/tools \
  -H "Content-Type: application/x-yaml" --data "
name: file_io
type: builtin
"

# ── 2. 注册全局 Sub-Agent（公用池，可被任意 Agent 引用） ──
curl -s -X POST http://localhost:8000/api/v1/admin/sub-agents \
  -H "Content-Type: application/x-yaml" --data "
name: time_helper
strategy: react
tools:
  - echo
  - current_time
system_prompt: 你是一个时间助手。使用 current_time 工具获取时间信息并回复用户。
"

# ── 3. 注册主 Agent（chat_agent） ──
curl -s -X POST http://localhost:8000/api/v1/admin/agents \
  -H "Content-Type: application/json" --data '
{
  "agent_id": "chat_agent",
  "model": {
    "provider": "deepseek",
    "name": "deepseek-v4-flash",
    "api_key": "sk-*****************************",
    "temperature": 0.0,
    "timeout": 120
  },
  "routing": {
    "confidence_threshold": 0.7,
    "intents": {
      "chat": {
        "target": "chat",
        "description": "用户进行日常对话"
      },
      "time": {
        "target": "time_helper",
        "description": "用户询问时间相关问题"
      }
    }
  },
  "sub_agent_refs": [
    {
      "name": "time_helper",
      "public": true
    },
    {
      "name": "chat",
      "public": false,
      "strategy": "react",
      "tools": ["echo"],
      "system_prompt": "你是一个聊天助手。友好地回复用户的问题。",
      "strategy_config": {
        "max_iterations": 3
      }
    }
  ],
  "prompts": {
    "classify": "",
    "respond": ""
  }
}
'

# ── 4. 注册主 Agent（code_agent，含 DSL 图拓扑） ──
curl -s -X POST http://localhost:8000/api/v1/admin/agents \
  -H "Content-Type: application/json" --data '
{
  "agent_id": "code_agent",
  "model": {
    "provider": "deepseek",
    "name": "deepseek-v4-flash",
    "api_key": "sk-*****************************",
    "temperature": 0.0,
    "timeout": 120
  },
  "routing": {
    "confidence_threshold": 0.7,
    "intents": {
      "code": {
        "target": "code",
        "description": "用户要求代码相关，编写代码、生成代码片段或创建新功能"
      },
      "time": {
        "target": "time",
        "description": "用户想要进行时间方面的处理或逻辑"
      },
      "analyzer": {
        "target": "analyzer",
        "description": "用户需要进行分析，或者流水线操作"
      }
    }
  },
  "sub_agent_refs": [
    {
      "name": "code",
      "public": false,
      "strategy": "react",
      "tools": ["echo", "current_time", "file_io"],
      "system_prompt": "你是一个代码助手。严格按照工具返回结果回复用户。",
      "strategy_config": {
        "max_iterations": 5
      }
    },
    {
      "name": "time",
      "public": false,
      "strategy": "react",
      "tools": ["echo", "current_time", "file_io"],
      "system_prompt": "你是一个使用时间的工具。严格按照工具返回结果回复用户。",
      "strategy_config": {
        "max_iterations": 5
      }
    }
  ],
  "prompts": {
    "classify": "",
    "respond": "Based on the sub-agent result, compose a helpful response."
  }
}
'
```

**第三步：开始对话**

通过 Web 控制台 `http://localhost:5173` 或 CLI 开聊：

```bash
uv run artipivot chat chat_agent "你好"
uv run artipivot chat code_agent "使用 echo 工具打印 你好"
# → 你好

uv run artipivot chat chat_agent "现在几点了"
# → 当前时间是：2026-05-31 14:30:00
```

### Admin API 快速参考

| 操作 | 方法 | 路径 |
|------|------|------|
| 注册工具 | `POST` | `/api/v1/admin/tools` |
| 列出工具 | `GET` | `/api/v1/admin/tools` |
| 删除工具 | `DELETE` | `/api/v1/admin/tools/{name}` |
| 注册子 Agent | `POST` | `/api/v1/admin/sub-agents` |
| 列出子 Agent | `GET` | `/api/v1/admin/sub-agents` |
| 删除子 Agent | `DELETE` | `/api/v1/admin/sub-agents/{name}` |
| 注册主 Agent | `POST` | `/api/v1/admin/agents` |
| 列出主 Agent | `GET` | `/api/v1/admin/agents` |
| 更新主 Agent | `PUT` | `/api/v1/admin/agents/{agent_id}` |
| 删除主 Agent | `DELETE` | `/api/v1/admin/agents/{agent_id}` |
| 查看路由 | `GET` | `/api/v1/admin/routing/{agent_id}` |
| 熔断器状态 | `GET` | `/api/v1/admin/agents/{agent_id}/circuit` |
| 更新熔断器 | `POST` | `/api/v1/admin/agents/{agent_id}/circuit` |
| 图结构 | `GET` | `/api/v1/admin/graph/{agent_id}/structure` |
| Mermaid 图 | `GET` | `/api/v1/admin/graph/{agent_id}/mermaid` |

所有 Admin API 端点支持 YAML 和 JSON 两种请求体格式（通过 `Content-Type` 区分）。

### 存储配置（.env）

存储模式是技术决策，通过环境变量配置：

```bash
# .env
# 默认 memory → SQLite 本地持久化（.artipivot/data.db），零配置
ARTIPIVOT_STORAGE_MODE=memory

# 生产环境 → MongoDB / PostgreSQL 等外部数据库
# ARTIPIVOT_STORAGE_MODE=persistent
# DATABASE_URI=postgresql://user:password@localhost:5432/artipivot

# 外部数据库需要代码注册：
# from artipivot.storage.registry import register_persistent
# register_persistent(YourPersistentFactory())
```

## Web 控制台

启动服务后访问 `http://localhost:5173`，5 个页面覆盖日常操作：

### Chat — 对话

左侧选择 Agent，右侧输入消息开始对话。流式输出，支持 Markdown 渲染。

![Chat 对话历史](doc/screenshots/chat-with-history.png)

### Agents — Agent 管理

![Agents 列表](doc/screenshots/agents-list.png)

查看所有 Agent，一键进入详情或编辑。

![Agent 详情](doc/screenshots/agent-detail.png)

查看 Agent 模型配置、路由规则、子 Agent 绑定等完整信息。

![Agent 编辑](doc/screenshots/agent-edit.png)

修改 Agent 配置，保存后自动热更新，无需重启。

### Config — 配置管理

![Config 页面](doc/screenshots/config.png)

管理工具、子 Agent、路由等运行时配置。

### Observe — 可观测性

![Observe 页面](doc/screenshots/observe.png)

实时查看请求日志、trace 链路、节点状态。

### Runtime — 运行时状态

![Runtime 页面](doc/screenshots/runtime.png)

查看当前内存中加载的工具、子 Agent、Agent 实例——即实际生效的运行时配置。

---

## 三层架构

```mermaid
graph TB
    REQ["用户请求"] --> GW

    subgraph GW["AgentGateway — 按 agent_id 分发"]
        direction TB
        subgraph MA1["code_agent"]
            direction LR
            C1["classify"] --> R1["route"] --> S1["sub-agent"] --> P1["respond"]
        end
        subgraph MA2["research_agent"]
            direction LR
            C2["classify"] --> R2["route"] --> S2["sub-agent"] --> P2["respond"]
        end
    end

    S1 --> DISPATCH
    S2 --> DISPATCH

    subgraph DISPATCH["策略分发"]
        direction LR
        A["ReAct"] ~~~ B["FC"] ~~~ D["DSL"]
    end

    DISPATCH --> TOOL_LAYER

    subgraph TOOL_LAYER["工具池"]
        direction LR
        T1["echo"] ~~~ T2["time"] ~~~ T3["file_io"] ~~~ T4["MCP..."]
    end

    P1 --> RES["JSON 响应"]
    P2 --> RES

    style GW fill:#dceefb,stroke:#1976d2,color:#000
    style DISPATCH fill:#fff4d0,stroke:#f57f17,color:#000
    style TOOL_LAYER fill:#d5f5d5,stroke:#2e7d32,color:#000
```

### 请求全链路

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant GW as Gateway
    participant MA as 主 Agent
    participant SA as 子 Agent
    participant Tool as 工具

    User ->> GW: POST /api/v1/chat/agent_id
    activate GW
    GW ->> GW: rate limit 检查
    GW ->> MA: invoke(agent_id, message)
    activate MA

    MA ->> MA: classify - LLM 输出 intent + confidence

    alt confidence 小于 threshold
        MA -->> User: 请澄清您的意图
    else intent 匹配
        MA ->> SA: 分派到对应子 Agent
        activate SA
        loop ReAct 循环 max_iterations
            SA ->> SA: think - LLM 推理
            SA ->> Tool: 调用工具
            Tool -->> SA: 返回结果
        end
        SA -->> MA: 执行结果
        deactivate SA
    else 未匹配
        MA ->> SA: fallback 兜底
    end

    MA ->> MA: respond 格式化
    MA -->> GW: ChatResponse
    deactivate MA
    GW -->> User: JSON 响应
    deactivate GW
```

---

## 第一层 — 主 Agent（路由）

每个主 Agent 拥有独立的图：`classify → route → sub-agent → respond`。

**意图分类**：LLM 读取 YAML 中的 intent `description`，输出 `{intent, confidence}`。description 自动注入 classify prompt——LLM 理解意图边界，而不是靠名字猜。

**路由逻辑**：`confidence < threshold → clarify`；匹配到意图 → 对应子 Agent；未匹配 → fallback。

**热更新**：intent_map、threshold、classify prompt 修改即时生效，无需重建图。

**多主 Agent 隔离**：多个主 Agent 并行运行，各自拥有独立的图、意图体系、子 Agent 集合、记忆和模型配置——五维隔离互不干扰。

---

## 第二层 — 子 Agent（执行）

子 Agent 是**无状态的 compiled graph**——纯拓扑，状态由 LangGraph runtime 在调用时注入。同一个 compiled graph 可以被多个主 Agent 共享。

> **设计决策**：子 Agent 是无状态的一等公民。图是纯拓扑，不带运行时数据。这带来三个关键收益：
> 1. **共享复用** — 相同策略 + 工具 = 同一个 compiled graph 对象（去重）
> 2. **安全隔离** — 一次请求的状态不会泄漏到下一次
> 3. **热替换** — 替换 compiled graph 不影响正在执行的请求

### 三种执行策略

```mermaid
graph TB
    subgraph REACT["ReAct"]
        R_THINK["think"] --> R_TOOLS["tools"]
        R_TOOLS --> R_CHECK{继续?}
        R_CHECK -->|是| R_THINK
        R_CHECK -->|否| R_END["END"]
    end

    subgraph FC["Function Calling"]
        FC_LLM["llm"] --> FC_TOOLS["tools"] --> FC_END["END"]
    end

    subgraph DSL_GRAPH["Graph DSL"]
        DSL_A["llm #1"] --> DSL_B["llm #2"]
        DSL_B --> DSL_C["tools"]
        DSL_C --> DSL_D["llm #3"] --> DSL_E["END"]
    end

    style REACT fill:#dceefb,stroke:#1565c0,color:#000
    style FC fill:#e8d5f5,stroke:#6a1b9a,color:#000
    style DSL_GRAPH fill:#fff4d0,stroke:#ef6c00,color:#000
```

| 策略 | 图拓扑 | 适用场景 |
|------|--------|---------|
| **ReAct** | think → tools → think 循环（`max_iterations` 保护） | 复杂多步推理，需要反复调用工具 |
| **Function Calling** | llm → tools → END | 简单查询，单次工具调用 |
| **Graph DSL** | YAML 自定义任意图拓扑 | 已知工作流，多阶段管线 |

#### ReAct vs DSL——怎么选？

- **ReAct**：一个 LLM 自己决定调什么工具、循环几轮。适合开放式、不确定的任务。
- **DSL**：多个 LLM 节点按固定管线接力，每段有独立角色、prompt 和工具集。适合结构化、分阶段的流程。

两者可以在同一个项目中混用——简单意图走 ReAct，复杂管线走 DSL。

#### Graph DSL — YAML 定义任意图拓扑

当固定策略无法满足时（并行执行、条件分支、多段接力、人工审批），用 `graph:` 定义拓扑。

```mermaid
graph LR
    START(( )) --> R["researcher<br/>LLM + tools"]
    R --> S["summarizer<br/>LLM"]
    S --> RF["refiner<br/>LLM + tools"]
    RF --> F["finalizer<br/>LLM"]
    F --> END(( ))

    style R fill:#dceefb,stroke:#1565c0,color:#000
    style S fill:#e8d5f5,stroke:#6a1b9a,color:#000
    style RF fill:#fff4d0,stroke:#ef6c00,color:#000
    style F fill:#d5f5d5,stroke:#2e7d32,color:#000
    style START fill:#e0e0e0,stroke:#757575,color:#000
    style END fill:#e0e0e0,stroke:#757575,color:#000
```

对应 YAML：

```yaml
sub_agents:
  pipeline:
    graph:
      nodes:
        researcher:
          type: llm
          system_prompt: "你是研究员，收集信息。"
          tools: [echo, current_time]
        summarizer:
          type: llm
          system_prompt: "总结原始信息。"
        refiner:
          type: llm
          system_prompt: "精炼和格式化。"
          tools: [echo]
        finalizer:
          type: llm
          system_prompt: "整合成清晰的中文回复。"
      edges:
        - { from: START, to: researcher }
        - { from: researcher, to: summarizer }
        - { from: summarizer, to: refiner }
        - { from: refiner, to: finalizer }
        - { from: finalizer, to: END }
```

**DSL 高级能力**：

| 能力 | YAML 写法 | 说明 |
|------|----------|------|
| HITL 人工审批 | `interrupt: before` / `after` | 暂停图执行，等待人工确认后恢复 |
| 条件路由 | `condition` + 字段映射 | 按输出字段值走不同分支 |
| 节点级重试 | `retry` + 指数退避 | 单节点失败自动重试，不影响整图 |
| 节点级多模型 | `model` override | 同一图中不同节点用不同 LLM |
| 循环保护 | `max_iterations` | 防止无限循环 |

4 种节点类型：`llm`（LLM 调用，可选 tools 绑定）、`tool`（单工具）、`tools`（多工具 ToolNode）、`sub_agent`（嵌套子 Agent）。

LLM 节点 `tools` 绑定后，LLM 产出 `tool_calls`，下游 `tools` 节点（LangGraph ToolNode）自动消费并执行，结果写回 `messages`——数据全程走 LangGraph 原生消息流，不需要中间适配层。

---

## 第三层 — 工具（能力）

原子化、无状态的执行能力，注册在全局 `ToolRegistry` 中。子 Agent 按名引用，`ToolNode` 在图构建时装配。

**内置工具**：`echo`、`current_time`、`file_io`

**自定义工具**——用 `@tool` 装饰器 + 一行注册：

```python
from langchain_core.tools import tool

@tool
def database_query(sql: str, limit: int = 100) -> str:
    """查询数据库。Query a database.

    Args:
        sql: SQL 查询语句。
        limit: 最大返回行数。
    """
    return execute_sql(sql, limit)
```

**MCP 工具**：通过 `MCPToolAdapter` 接入外部 MCP 工具服务器，注册后与内置工具无异。

**自定义工具**——外部 git 仓库中的 Python 包，`pip install` 后用 YAML 声明：

```yaml
tools:
  my_search:
    type: module
    module: my_company.tools.search
    function: baidu_search
```

或通过 Admin API 动态注册（支持 YAML 请求体）：

```bash
curl -X POST /admin/tools --data "
name: baidu_search
type: module
module: my_company.tools.search
function: baidu_search
"
# → ChangeNotifier → ToolWatcher → ToolReloader → 受影响 agent 自动重建 graph
```

**Tool 热加载**：运行时注册 tool 后，自动找到引用该 tool 的 sub-agent 和主 agent，重建 graph 并原子替换——零停机。

---

## 核心特性

### 三级记忆

```mermaid
graph LR
    L1["L1 工作记忆<br/>Graph State / 内存"]
    -->|请求结束| L2["L2 会话记忆<br/>Checkpointer"]
    -->|语义检索| L3["L3 长期记忆<br/>Store"]

    style L1 fill:#dceefb,stroke:#1565c0,color:#000
    style L2 fill:#fff4d0,stroke:#ef6c00,color:#000
    style L3 fill:#d5f5d5,stroke:#2e7d32,color:#000
```

| 层 | 存什么 | 隔离方式 | 生命周期 |
|---|--------|---------|---------|
| L1 | 当前对话消息列表 | 无（单次请求） | 请求结束即消失 |
| L2 | 图 state 快照 | `agent_id:thread_id` | 跨 turn，同一会话 |
| L3 | 提取后的画像 / 知识 | `(agent_id, user_id, type)` | 永久，跨会话 |

存储后端由 `.env` 的 `ARTIPIVOT_STORAGE_MODE` 控制，`StorageProvider` 统一管理所有后端：

| 模式 | 后端 | 持久化 | 适用场景 |
|------|------|:--:|------|
| `memory`（默认） | SQLite → `.artipivot/data.db` | 是 | 本地开发、单机部署 |
| `persistent` | MongoDB / PostgreSQL / MySQL 等 | 是 | 生产集群 |

**可插拔存储后端**：通过 `BackendFactory` ABC 注册新后端，`register_persistent()` 一行接入。Embedding 默认关闭——开启需要后端支持 `asearch`（如 PostgresStore + pgvector）。

### 模型配置与 Fallback

两种 provider 覆盖所有主流 LLM：

| Provider 值 | 覆盖范围 |
|-------------|---------|
| `openai` | OpenAI、DeepSeek、Moonshot、通义千问、任何 OpenAI 兼容 API |
| `anthropic` | Anthropic 官方、任何 Anthropic 兼容 API |

```mermaid
graph TD
    START(( )) --> L1{"用户+Agent级?"}
    L1 -->|有| USE["使用该模型"]
    L1 -->|无| L2{"用户全局?"}
    L2 -->|有| USE
    L2 -->|无| L3{"Agent级?"}
    L3 -->|有| USE
    L3 -->|无| L4["全局 fallback"]
    L4 --> USE

    USE --> CALL{"调用结果?"}
    CALL -->|成功| RES["返回结果"]
    CALL -->|失败| FB["递归 fallback"]
    FB --> USE

    style RES fill:#d5f5d5,stroke:#2e7d32,color:#000
    style FB fill:#fdd,stroke:#c62828,color:#000
```

多级优先级链 + 递归 fallback 降级：

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

### 热更新与插件系统

```mermaid
sequenceDiagram
    autonumber
    participant OP as Admin API
    participant PM as PluginManager
    participant DS as DocumentStore
    participant CN as ChangeNotifier
    participant PW as PluginWatcher
    participant GR as GraphRebuilder
    participant GW as Gateway

    OP ->> PM: publish(manifest)
    PM ->> DS: put 持久化
    PM ->> CN: notify
    CN ->> PW: onChange
    PW ->> GR: rebuild_agent
    Note right of GR: 构建新图 旧图继续服务
    GR ->> GW: register 原子替换
    Note right of GW: 新请求走新图 旧请求走旧图
```

**热更新 vs 需重建**：

| 变更内容 | 需重建图？ | 机制 |
|---------|:---------:|------|
| 注册新主 Agent | 是 | `register_def()` → 构建子图 + 主图 → Gateway 注册 |
| 发布/弃用子 Agent 插件 | 是 | PluginWatcher → GraphRebuilder 重建 |
| DSL 图插件 | 是 | GraphRebuilder 重建 |
| 路由规则（intent_map、threshold） | **否** | RoutingConfig 每次 classify 读新值 |
| 切换模型 | **否** | ModelProvider 每次 invoke 动态解析 |
| 修改提示词 | **否** | PromptStore 每次 LLM 调用读新值 |
| 修改限流规则 | **否** | RateLimiter 即时生效 |
| 注册新工具 | **是**（精准） | ToolWatcher → ToolReloader → 重建引用链上所有 agent |
| 删除工具 | **是**（精准） | 同上，stub 替换 + 重建 |
| 熔断器配置 | **否** | circuit config 每次 LLM 调用即时读取 |

### 双状态架构

主 Agent 与子 Agent 使用不同的 State 类型，通过 LangGraph subgraph 边界映射，非引用传递：

```mermaid
graph LR
    subgraph MA["主 Agent State"]
        direction TB
        AS_MSG["messages  add_messages"]
        AS_INT["intent confidence  覆写"]
        AS_META["metadata  字典替换"]
    end

    AS_MSG -->|边界映射| SS_MSG
    SS_MSG -->|结果回写| AS_MSG

    subgraph SA["子 Agent State"]
        direction TB
        SS_MSG["messages  add_messages"]
        SS_ART["artifacts  列表追加"]
        SS_META["metadata  字典替换"]
    end

    style MA fill:#dceefb,stroke:#1565c0,color:#000
    style SA fill:#fff4d0,stroke:#ef6c00,color:#000
```

### 可观测性

`structlog` + `contextvars` 自动传播 `trace_id`。所有日志 JSON lines 格式，`grep "trace_id.*xxx"` 获取完整请求链路。`GraphLoggingCallback` 自动记录每个节点、LLM 调用、工具调用的完整生命周期——业务代码无需手动打日志。

双文件输出：`artipivot.log`（全量）+ `error.log`（仅 ERROR，用于告警）。可选 OpenTelemetry：`OTEL_ENABLED=true`。

### 容错

```mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open : 连续失败达阈值
    Open --> HalfOpen : 冷却期结束
    HalfOpen --> Closed : 探测成功
    HalfOpen --> Open : 探测失败

    state Closed {
        [*] --> 执行请求
        执行请求 --> 重试 : 失败
        重试 --> 执行请求 : 未达上限
        重试 --> Fallback : 达到上限
        执行请求 --> [*] : 成功
    }

    state Open {
        [*] --> Fallback1["Fallback 降级"]
    }
```

内置熔断器（closed → open → half_open）、重试策略（指数退避 + 抖动）、多维限流。

**熔断器配置**（per-agent，YAML 业务配置）：

```yaml
agents:
  code_agent:
    circuit:
      enabled: true               # 开关，默认 true
      failure_threshold: 5        # 连续失败 N 次 → 熔断，默认 5
      recovery_timeout: 60.0      # 冷却时间（秒），默认 60
```

熔断按 LLM provider（`deepseek`/`anthropic`/`openai`）独立工作，一个挂了不影响另一个。通过 Admin API 热修改即时生效，无需重建图。LLM 调用失败达阈值 → 电路 open → 不再徒劳发请求 → 冷却期满 → half_open 探测 → 成功闭合。

详见 [resilience.md](doc/modules/resilience.md)。

---

## 项目结构

```
artipivot/
├── .agents.yaml               # Agent 清单（启动时自动加载）
├── .env                       # API Key 等环境变量
├── src/artipivot/
│   ├── api/                   # FastAPI（REST + Admin API）
│   ├── gateway/               # 多主 Agent 分发与注册
│   ├── graph/                 # LangGraph 图定义、路由、DSL、可视化
│   ├── agents/                # 子 Agent + 策略引擎（ReAct / FC）
│   ├── tools/                 # 工具注册表 + MCP 适配器
│   ├── memory/                # 三层记忆 + 上下文压缩
│   ├── models/                # 模型适配 + 三级 Fallback
│   ├── config/                # 热更新配置中心
│   ├── storage/               # 可插拔存储（StorageProvider + BackendFactory 注册）
│   ├── plugins/               # 插件系统（热重建图）
│   ├── resilience/            # 熔断 / 重试 / 限流
│   ├── observability/         # structlog + OTel
│   ├── bootstrap.py           # 一键初始化
│   └── cli/                   # CLI（Typer）
├── doc/                       # 文档
│   ├── usage.md               #   完整使用指南
│   └── modules/               #   模块详细文档（14 个）
└── tests/                     # 测试（177+）
```

---

## 常用命令

```bash
uv sync --dev                              # 安装依赖
uv run pytest tests/ -v                    # 运行全部测试
uv run pytest tests/test_strategies.py -v  # 运行单个测试文件
uv run artipivot serve --port 8000         # 启动 HTTP API 服务
uv run artipivot chat code_agent "hello"   # CLI 对话
uv run artipivot agents                    # 列出已注册 Agent
uv run artipivot plugin init <name>        # 创建插件模板
uv run artipivot plugin publish <name>     # 发布插件
python main.py                             # 通过 main 入口运行
```

---

## 扩展点

| 扩展点 | 接口/基类 | 注册方式 |
|--------|-----------|---------|
| 模型供应商 | `_factories[provider]` | 添加工厂函数 |
| 子 Agent 策略 | `Strategy` ABC | `register_strategy()` |
| 自定义图拓扑 | `GraphDef` | YAML `graph:` 或插件 manifest |
| 自定义工具 | `@tool` 装饰器 | `registry.register()` |
| 存储后端 | `BackendFactory` ABC | `register_persistent()` |
| 主 Agent | `AgentDef` | `AgentRegistry.register_def()` |
| 子 Agent 插件 | `PluginDocument` | `pm.publish()` |
| MCP 工具服务器 | `MCPToolAdapter` | `MCPRegistry.register_server()` |
| 上下文压缩策略 | 自定义 handler | `register_compression_strategy()` |

---

## 模块文档

| 模块 | 文档 | 内容 |
|------|------|------|
| 完整使用指南 | [usage.md](doc/usage.md) | 从创建 Agent 到动态热更新的完整流程 |
| 存储层 | [storage.md](doc/modules/storage.md) | DocumentStore / ChangeNotifier / 后端 |
| 模型层 | [models.md](doc/modules/models.md) | ModelConfig、三级 Fallback、供应商工厂 |
| 工具层 | [tools.md](doc/modules/tools.md) | ToolRegistry、@tool 装饰器、MCP 适配器 |
| 子 Agent | [agents.md](doc/modules/agents.md) | 编程式/声明式定义、策略引擎 |
| 配置中心 | [config.md](doc/modules/config.md) | ConfigCenter、PromptStore、RoutingConfig |
| 记忆系统 | [memory.md](doc/modules/memory.md) | 三层记忆模型、可插拔后端、Namespace 隔离 |
| 多主 Agent | [multi_agent.md](doc/modules/multi_agent.md) | AgentDef、AgentRegistry、五维隔离 |
| 插件系统 | [plugins.md](doc/modules/plugins.md) | PluginManager、GraphRebuilder、PluginWatcher |
| Graph DSL | [graph_dsl.md](doc/modules/graph_dsl.md) | YAML 自定义图拓扑、4 种节点、条件路由 |
| 可视化 | [visual.md](doc/modules/visual.md) | Mermaid 流程图生成、Admin API 图查询 |
| 容错 | [resilience.md](doc/modules/resilience.md) | CircuitBreaker、RetryPolicy、RateLimiter |
| 可观测 + API | [observability_api.md](doc/modules/observability_api.md) | structlog、OpenTelemetry、REST/CLI 参考 |
---

## 技术栈

Python 3.12 · LangGraph v1.2 · FastAPI + Uvicorn · structlog + orjson · Typer CLI · Anthropic Claude / OpenAI GPT / DeepSeek · StorageProvider 可插拔存储（Memory / PostgreSQL / 自定义后端）
