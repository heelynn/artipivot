# ArtiPivot

生产级多层 Agent 框架，基于 LangGraph 构建。通过 **主路由 Agent → 子代理 → 工具** 三层解耦架构，实现意图识别、任务分发、工具执行的清晰分离。

## 项目简介

ArtiPivot 是一个面向生产环境的 AI Agent 编排框架。它将 Agent 系统拆分为三层：

- **第一层 — 主路由 Agent**：纯路由层，只做两件事——识别用户意图、选择合适的子代理。不涉及工具调用、记忆读写、响应生成。
- **第二层 — 子代理**：实际任务执行者，独立完成记忆读取、任务规划、工具编排、响应生成、记忆回写。支持**编程式**（Python）和**声明式**（YAML 零代码）两种开发模式。
- **第三层 — 工具**：原子化、无状态的执行能力（搜索、代码执行、文件读写等），可被任意子代理按需引用，支持 Pipeline 工具编排。

### 核心特性

| 特性 | 说明 |
|------|------|
| **多主 Agent 隔离** | 多个主 Agent 并存运行，State / 路由逻辑 / 子代理 / 工具 / 会话记忆完全隔离，通过 Agent Gateway 统一分发 |
| **可插拔架构** | 子代理和工具像 USB 设备一样动态加载/卸载，不影响其他功能；存储后端（Memory / MongoDB / PostgreSQL / Redis）可自由组合 |
| **动态配置** | 模型、提示词、限流规则等所有运行时参数存储在 DocumentStore，通过 API 动态管理，修改立即生效，无需重启服务 |
| **模型三级 Fallback** | 子代理模型 → 子代理兜底 → 全局兜底，保证可用性；模型变更在下次请求自动生效，无需重建图 |
| **生产级可观测性** | 自建文件日志系统（8 通道 structlog JSON 日志 + 自动轮转），不依赖外部 SaaS；含请求 trace / 会话 / LLM 调用 / 工具调用 / 记忆操作 / 审计等独立通道 |
| **全链路容错** | 节点级超时 + error_handler + 工具重试（指数退避）+ 模型 fallback + 熔断器，各层独立容错 |
| **开发体验优先** | 子代理只需实现 `_invoke` 一个方法；声明式子代理只需 YAML 配置；内置 CLI 脚手架 |

### 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 运行时 | LangGraph v1.2 | 图编排 + Checkpointer + Store + ToolNode，不依赖 LangChain 高层包 |
| 模型 | Anthropic Claude / OpenAI GPT | 通过 langchain-anthropic / langchain-openai 集成 |
| 日志 | structlog + orjson | 结构化 JSON 输出，按日轮转 |
| 存储 | 可插拔 | Memory（零依赖开发）/ MongoDB / PostgreSQL / Redis |
| 部署 | FastAPI + Uvicorn | REST API 入口（后续阶段） |

### 当前阶段：P0 骨架

P0 实现了最小可运行闭环：

- 1 个主 Agent（code_agent）+ 1 个编程式子代理（code_writer）+ 3 个 stub 工具
- InMemory 存储 + Checkpointer + Store（零外部依赖）
- ConfigCenter 动态配置 + YAML 种子加载
- 8 通道 structlog 日志
- 38 个单元测试全部通过

## 项目结构

```
artipivot/
├── pyproject.toml                          # 项目元数据、依赖声明、构建配置（hatch + uv）
├── uv.lock                                 # uv 锁文件，锁定所有依赖的精确版本
├── CLAUDE.md                               # Claude Code 项目指引
├── demo.py                                 # 端到端交互式演示脚本（初始化全链路 → 对话循环）
├── README.md                               # 本文件
│
├── doc/                                    # 设计文档
│   ├── DESIGN.md                           # 产品设计文档 — 三层架构、插件系统、集群方案
│   ├── ARCHITECTURE.md                     # 代码架构文档 — LangGraph 映射、模块设计、可观测性
│   ├── MEMORY.md                           # 记忆系统设计 — 三层记忆模型、隔离策略
│   └── DEVELOPMENT_PLAN.md                 # P0 开发计划 — 12 步骤拆解及进度追踪
│
├── config/seed/                            # 首次启动种子配置（YAML → DocumentStore 加载）
│   ├── models.yaml                         # 模型配置种子 — 全局兜底、主 Agent 模型、子代理模型及 fallback 链
│   ├── prompts.yaml                        # 提示词种子 — 各节点的系统提示词（classify/respond/子代理）
│   └── routing.yaml                        # 路由规则种子 — 意图列表、置信度阈值、意图→子代理映射表
│
├── src/artipivot/                          # 源码根目录
│   ├── __init__.py                         # 包入口，声明版本号
│   ├── __main__.py                         # CLI 入口，`python -m artipivot` 执行 demo
│   │
│   ├── gateway/                            # 多主 Agent 分发层
│   │   ├── __init__.py
│   │   └── gateway.py                      # AgentGateway — 按 agent_id 路由到对应主图，
│   │                                       #   动态解析模型、绑定 trace_id、管理 thread_id 隔离
│   │
│   ├── graph/                              # 核心图构建层
│   │   ├── __init__.py
│   │   ├── state.py                        # 状态定义 — ArtiPivotState（主图）、SubAgentState（子代理图），
│   │                                       #   含 messages reducer 和中间产物累积器
│   │   ├── context.py                      # AgentContext 数据类 — 运行时上下文，
│   │                                       #   通过 context_schema 注入（agent_id/user_id/thread_id/model/tools）
│   │   ├── router.py                       # 路由节点 — classify 节点（LLM 结构化输出识别意图）
│   │                                       #   + route_by_intent 条件边（阈值判断 → 子代理/澄清/兜底）
│   │   ├── root.py                         # build_root_graph() — 构建单个主图，
│   │                                       #   拓扑：START → classify → conditional → {子代理/clarify/fallback} → respond → END
│   │   └── factory.py                      # GraphFactory — 按 agent_id 构建独立主图，
│   │                                       #   挂载子代理子图、checkpointer、store
│   │
│   ├── agents/                             # 子代理层
│   │   ├── __init__.py
│   │   ├── base.py                         # SubAgentDef 数据类 — 子代理定义（名称/工具/提示词/最大迭代次数）
│   │   └── programmatic.py                 # build_programmatic_subagent() — 构建编程式子代理，
│   │                                       #   ReAct 循环拓扑：START → llm_call → conditional → {tools, END}，
│   │                                       #   tools → llm_call 循环
│   │
│   ├── tools/                              # 工具层
│   │   ├── __init__.py
│   │   ├── registry.py                     # ToolRegistry — 全局工具池 + 权限过滤矩阵，
│   │                                       #   按白名单生成 ToolNode
│   │   └── builtin/                        # 内置工具实现（P0 为 stub，返回固定结果）
│   │       ├── __init__.py
│   │       ├── web_search.py               # web_search — 互联网搜索工具 stub
│   │       ├── code_exec.py                # code_exec — 代码执行工具 stub
│   │       └── file_io.py                  # file_io — 文件读写工具 stub
│   │
│   ├── memory/                             # 记忆系统
│   │   ├── __init__.py
│   │   ├── checkpointer.py                 # create_checkpointer() 工厂 — P0 返回 InMemorySaver，
│   │                                       #   后续扩展 PostgresSaver
│   │   └── store.py                        # create_store() 工厂 — P0 返回 InMemoryStore，
│   │                                       #   后续扩展 PostgresStore + 语义搜索
│   │
│   ├── models/                             # 模型适配层
│   │   ├── __init__.py
│   │   ├── config.py                       # ModelConfig 数据类 — 单个模型配置（provider/name/temperature/timeout/fallback）
│   │   ├── provider.py                     # ModelProvider — 动态模型解析 + 三级 fallback 链，
│   │                                       #   从 DocumentStore 加载配置，ChangeNotifier 热更新，
│   │                                       #   支持 anthropic/openai 工厂，线程安全
│   │   └── loader.py                       # load_seed_if_empty() — 首次启动时从 YAML 种子文件
│   │                                       #   加载模型/路由/提示词配置到 DocumentStore
│   │
│   ├── config/                             # 动态配置中心
│   │   ├── __init__.py
│   │   ├── center.py                       # ConfigCenter — 统一配置入口，
│   │                                       #   管理 PromptStore + RoutingConfig + RateLimiter，
│   │                                       #   启动时全量加载 + 订阅 ChangeNotifier 热更新
│   │   ├── prompts.py                      # PromptStore — 提示词动态管理，
│   │                                       #   按 "agent_id:node" 或 "agent_id:sub:sub_name" 索引
│   │   ├── routing.py                      # RoutingConfig — 路由规则配置，
│   │                                       #   提供意图→子代理映射表和置信度阈值查询
│   │   └── ratelimit.py                    # RateLimiter — 限流骨架（P0 占位，不做实际限流）
│   │
│   ├── storage/                            # 可插拔存储抽象层
│   │   ├── __init__.py
│   │   ├── base.py                         # 三个抽象接口：
│   │                                       #   DocumentStore — 文档 CRUD + 查询（配置/插件元数据）
│   │                                       #   ChangeNotifier — 变更订阅/通知（集群同步）
│   │                                       #   ArtifactStore — 制品上传/下载（插件包）
│   │   └── memory.py                       # 内存实现（零依赖开发模式）：
│   │                                       #   InMemoryDocumentStore — defaultdict 实现
│   │                                       #   InProcessNotifier — 进程内回调
│   │                                       #   InMemoryArtifactStore — 本地文件系统
│   │
│   ├── observability/                      # 可观测性
│   │   ├── __init__.py
│   │   ├── logging.py                      # structlog 多通道配置 — 8 个独立日志通道（main/trace/session/
│   │                                       #   memory/llm/tool/error/audit），JSON 格式，按日轮转
│   │   └── trace.py                        # 请求级追踪 — 生成 trace_id，绑定/清除 contextvars，
│   │                                       #   自动携带 agent_id/user_id/thread_id
│   │
│   └── resilience/                         # 容错与弹性（P0 占位）
│       └── __init__.py                     # 后续实现：熔断器、重试策略、节点级 error_handler
│
└── tests/                                  # 测试套件（38 个测试）
    ├── conftest.py                         # 共享 fixtures — InMemoryDocumentStore + InProcessNotifier
    ├── test_storage.py                     # 存储层测试 — CRUD、查询过滤、订阅通知
    ├── test_models.py                      # 模型层测试 — ModelConfig、Provider 加载/fallback/异常
    ├── test_config.py                      # 配置层测试 — PromptStore、RoutingConfig、ConfigCenter 集成
    ├── test_tools.py                       # 工具层测试 — ToolRegistry 注册/过滤/ToolNode + 内置工具 stub
    ├── test_agents.py                      # 子代理测试 — SubAgentDef、编程式子图构建
    ├── test_graph.py                       # 图构建测试 — State 类型、主图/子图编译、主图+子图组合
    └── test_gateway.py                     # 网关测试 — 注册、未知 agent 异常、Memory 工厂
```

## 快速开始

```bash
# 安装依赖
uv sync --dev

# 运行测试（39 个）
uv run pytest tests/ -v

# 交互式 demo（需设置 API Key）
export ANTHROPIC_API_KEY=sk-...
# 可选：切换模型 / 兼容供应商
# export DEMO_PROVIDER=openai
# export DEMO_MODEL=gpt-4o
# export DEMO_BASE_URL=https://api.deepseek.com
uv run python demo.py
```

## 可插拔组件接入指南

框架的核心设计原则是**所有关键组件均可替换**。下面按组件类别逐一说明接口定义、接入方式和配置格式。

---

### 1. 存储后端（DocumentStore / ChangeNotifier / ArtifactStore）

存储层有三个独立的可插拔接口，各自可选用不同后端，互不耦合。

#### 1.1 DocumentStore — 文档存储

**接口定义**（`storage/base.py`）：

```python
class DocumentStore(ABC):
    async def get(self, collection: str, key: str) -> dict | None      # 按 key 获取文档
    async def put(self, collection: str, key: str, data: dict) -> None  # 写入（upsert 语义）
    async def delete(self, collection: str, key: str) -> None           # 删除
    async def query(self, collection: str, filter: dict) -> list[dict]  # 按条件查询，空 filter 返回全部
```

**已有实现**：

| 实现 | 文件 | 适用场景 |
|------|------|----------|
| `InMemoryDocumentStore` | `storage/memory.py` | 本地开发、单测（零依赖） |
| MongoDocumentStore | 后续 `storage/document/mongodb.py` | 生产（MongoDB 后端） |
| PostgresDocumentStore | 后续 `storage/document/postgres.py` | 生产（PostgreSQL 后端） |

**接入新后端**：继承 `DocumentStore`，实现四个抽象方法，然后在工厂函数中注册：

```python
# src/artipivot/storage/document/my_backend.py
from artipivot.storage.base import DocumentStore

class MyDocumentStore(DocumentStore):
    async def get(self, collection, key): ...
    async def put(self, collection, key, data): ...
    async def delete(self, collection, key): ...
    async def query(self, collection, filter): ...
```

#### 1.2 ChangeNotifier — 变更通知

**接口定义**：

```python
class ChangeNotifier(ABC):
    async def subscribe(self, collection: str, callback: Callable) -> None
        # callback 签名: async callback(collection, key, action, data)
    async def notify(self, collection: str, key: str, action: str, data: dict) -> None
    async def start(self) -> None
    async def stop(self) -> None
```

**已有实现**：

| 实现 | 适用场景 |
|------|----------|
| `InProcessNotifier` | 本地开发（进程内回调，零延迟） |
| MongoChangeStreamNotifier | 生产（MongoDB Change Stream） |
| RedisPubSubNotifier | 生产（Redis Pub/Sub） |
| PostgresListenNotifyNotifier | 生产（PostgreSQL LISTEN/NOTIFY） |

#### 1.3 ArtifactStore — 制品存储

**接口定义**：

```python
class ArtifactStore(ABC):
    async def upload(self, local_path: str, remote_key: str) -> str  # 上传文件，返回 URL
    async def download(self, remote_key: str, local_path: str) -> str # 下载文件，返回本地路径
```

**已有实现**：`InMemoryArtifactStore`（本地文件系统）、后续扩展 S3 / GCS。

#### 1.4 存储后端配置

在 `.env` 或环境变量中配置（后续通过 `artipivot.yaml` 统一管理）：

```bash
# DocumentStore 后端
STORAGE_DOCUMENT_BACKEND=memory    # memory | mongodb | postgres | redis

# ChangeNotifier 后端
STORAGE_NOTIFIER_BACKEND=memory    # memory | mongodb_stream | redis_pubsub | postgres_listen

# ArtifactStore 后端
STORAGE_ARTIFACT_BACKEND=memory    # memory | local | s3 | gcs

# 生产环境示例
# DATABASE_URI=postgresql://user:password@localhost:5432/artipivot
# REDIS_URI=redis://localhost:6379/0
```

**典型组合**：

| 场景 | DocumentStore | ChangeNotifier | ArtifactStore |
|------|---------------|----------------|---------------|
| 本地开发 | `memory` | `memory` | `memory` |
| 单机测试 | `memory` | `memory` | `local` |
| 生产（MongoDB） | `mongodb` | `mongodb_stream` | `s3` |
| 生产（PostgreSQL） | `postgres` | `redis_pubsub` | `s3` |

---

### 2. 模型配置（ModelProvider）

#### 2.1 ModelConfig 数据结构

```python
@dataclass
class ModelConfig:
    provider: str                # "anthropic" | "openai" | 自定义
    name: str                    # "claude-sonnet-4-6" | "gpt-4o" 等
    temperature: float = 0.0     # 采样温度
    timeout: int = 120           # 超时秒数
    max_tokens: int | None = None
    fallback: ModelConfig | None = None  # 兜底模型（递归）
```

#### 2.2 模型三级 Fallback 链

```
子代理自有模型 → 子代理 fallback → 全局 fallback
```

示例：`code_writer` 子代理调用 LLM 时的解析链：

1. `code_agent:code_writer` → `claude-sonnet-4-6`（子代理配置）
2. `code_agent:code_writer` fallback → `claude-haiku-4-5-20251001`
3. `global` fallback → `gpt-4o`

每一级实例化失败时自动降级到下一级，全部失败则抛出 `RuntimeError`。

#### 2.3 YAML 种子配置

首次启动时从 `config/seed/models.yaml` 加载到 DocumentStore，之后所有变更通过 API 管理：

```yaml
# config/seed/models.yaml
global:
  fallback_model:
    provider: openai
    name: gpt-4o
  defaults:
    temperature: 0.0
    timeout_seconds: 120

agents:
  code_agent:
    provider: anthropic
    name: claude-sonnet-4-6
    temperature: 0.0
    sub_agents:
      code_writer:
        provider: anthropic
        name: claude-sonnet-4-6
        temperature: 0.0
        fallback:
          provider: anthropic
          name: claude-haiku-4-5-20251001
```

#### 2.4 接入新模型供应商

在 `models/provider.py` 中添加工厂函数并注册：

```python
def _factory_my_provider(cfg: ModelConfig) -> BaseChatModel:
    from my_langchain_integration import ChatMyProvider
    return ChatMyProvider(
        model=cfg.name,
        temperature=cfg.temperature,
        timeout=cfg.timeout,
        max_tokens=cfg.max_tokens,
    )

# 在 ModelProvider.__init__ 中注册
self._factories["my_provider"] = _factory_my_provider
```

然后在 `models.yaml` 中使用：

```yaml
agents:
  my_agent:
    provider: my_provider
    name: my-model-v1
```

#### 2.5 运行时动态切换

模型变更**不需要重建图**，下一次 `invoke()` 自动使用新配置：

```python
# 通过 API 更新主 Agent 模型
await model_provider.update_agent_model("code_agent", {
    "provider": "anthropic",
    "name": "claude-opus-4-6",   # 从 sonnet 升级到 opus
})

# 更新子代理模型
await model_provider.update_sub_model("code_agent", "code_writer", {
    "provider": "openai",
    "name": "gpt-4o",
})
```

#### 2.6 API Key 配置

通过环境变量提供，在 `.env` 中设置：

```bash
ANTHROPIC_API_KEY=sk-ant-...     # Anthropic Claude 系列模型
OPENAI_API_KEY=sk-...            # OpenAI GPT 系列模型
```

---

### 3. 工具系统（ToolRegistry）

#### 3.1 注册自定义工具

使用 LangChain 的 `@tool` 装饰器定义，然后注册到 `ToolRegistry`：

```python
from langchain_core.tools import tool
from artipivot.tools.registry import ToolRegistry

@tool
def my_tool(query: str, max_results: int = 5) -> str:
    """工具描述（LLM 通过此描述理解工具用途）。"""
    # 实际实现
    return f"result for: {query}"

# 注册
registry = ToolRegistry()
registry.register(my_tool)
```

#### 3.2 权限过滤

通过白名单控制每个子代理可用的工具子集：

```python
# 子代理只能用 web_search 和 code_exec
tools = registry.get_for_agent(["web_search", "code_exec"])

# 生成 LangGraph ToolNode
tool_node = registry.get_tool_node(["web_search", "code_exec"])
```

权限矩阵示例：

| 子代理 | web_search | code_exec | file_io |
|--------|:----------:|:---------:|:-------:|
| code_writer | ✓ | ✓ | ✓ |
| researcher | ✓ | - | - |
| data_analyst | - | ✓ | - |

#### 3.3 内置工具（P0 stub）

P0 阶段内置 3 个 stub 工具，返回固定结果用于开发调试：

| 工具 | 文件 | 功能 |
|------|------|------|
| `web_search` | `tools/builtin/web_search.py` | 互联网搜索 |
| `code_exec` | `tools/builtin/code_exec.py` | 代码执行 |
| `file_io` | `tools/builtin/file_io.py` | 文件读写 |

---

### 4. 子代理系统（Agents）

#### 4.1 定义子代理

```python
from artipivot.agents.base import SubAgentDef

sub_def = SubAgentDef(
    name="code_writer",              # 子代理名称（对应路由目标）
    tools=["web_search", "code_exec", "file_io"],  # 可用工具白名单
    system_prompt="你是一个专业的编程助手...",      # 系统提示词
    max_iterations=10,               # ReAct 循环最大轮次
)
```

#### 4.2 构建编程式子代理

编程式子代理自动生成 ReAct 循环图（LLM → 工具调用 → 观察 → 循环）：

```python
from artipivot.agents.programmatic import build_programmatic_subagent

# 获取工具节点
tool_node = registry.get_tool_node(sub_def.tools)

# 构建子代理图
sub_graph = build_programmatic_subagent(sub_def, tool_node)
```

生成的图拓扑：

```
START → llm_call → should_continue?
                      ├─ 有 tool_calls → tools → llm_call（循环）
                      └─ 无 tool_calls → END
```

#### 4.3 挂载到主图

```python
from artipivot.graph.factory import GraphFactory

factory = GraphFactory(config_center)
root_graph = factory.build(
    agent_id="code_agent",
    sub_agent_nodes={
        "code_writer": sub_graph,     # 意图路由目标 = 子代理名称
        "code_reviewer": another_sub,  # 可挂载多个子代理
    },
    checkpointer=checkpointer,
    store=store,
)
```

#### 4.4 声明式子代理（后续阶段）

通过 YAML 配置零代码创建子代理：

```yaml
identity:
  name: customer_service
  description: 处理客户咨询

strategy:
  type: react
  max_iterations: 5

tools: ["order_query", "knowledge_base"]

prompt:
  system: "你是客服助手..."
```

---

### 5. 动态配置中心（ConfigCenter）

ConfigCenter 统一管理所有运行时配置，从 DocumentStore 加载，通过 ChangeNotifier 热更新。

#### 5.1 配置分类与生效方式

| 配置类型 | 变更是否重建图 | 管理方式 |
|----------|:------------:|----------|
| 模型配置 | 否 | `model_provider.update_*()` |
| 提示词 | 否 | 修改 DocumentStore `prompt_configs` 集合 |
| 限流参数 | 否 | 修改 DocumentStore `ratelimit_configs` 集合 |
| 路由规则 | **是** | 修改 DocumentStore `routing_configs` 集合 → 触发图重建 |

#### 5.2 路由配置（routing.yaml）

定义意图列表、置信度阈值、意图到子代理的映射关系：

```yaml
# config/seed/routing.yaml
agents:
  code_agent:
    confidence_threshold: 0.7       # 低于此值走 clarify 节点
    intents:
      - name: code_write            # 意图名称
        sub_agent: code_writer      # 路由目标子代理
        description: 代码编写相关    # 给 LLM 的意图描述
      - name: code_review
        sub_agent: code_reviewer
        description: 代码审查相关
      - name: debug
        sub_agent: code_writer
        description: 调试与修复
    fallback: fallback              # 无匹配意图时的兜底节点
    clarify: clarify                # 置信度不足时的追问节点
```

**路由逻辑**：

```
classify 节点输出 {intent, confidence}
  → confidence < threshold? → clarify（追问用户）
  → intent 在 intent_map 中? → 对应子代理
  → 否则 → fallback（兜底回复）
```

#### 5.3 提示词配置（prompts.yaml）

各节点和子代理的提示词，支持 system prompt + few-shot 示例：

```yaml
# config/seed/prompts.yaml
prompts:
  "code_agent:classify":            # agent_id:node 格式
    agent_id: code_agent
    node: classify
    system: |
      你是意图分类器。将用户消息分类为：
      code_write / code_review / debug / general
      返回 JSON: {"intent": "...", "confidence": 0.0-1.0}

  "code_agent:sub:code_writer":     # agent_id:sub:sub_name 格式
    agent_id: code_agent
    node: sub_agent
    sub_agent: code_writer
    system: |
      你是专业编程助手，使用可用工具帮助用户。
```

**在节点中读取**：

```python
prompt_cfg = config_center.prompts.get("code_agent", "classify")
system_prompt = prompt_cfg.get("system", DEFAULT_PROMPT)
```

---

### 6. 记忆系统（Memory）

#### 6.1 两层记忆

| 层级 | LangGraph 机制 | 内容 | 后端 |
|------|---------------|------|------|
| 会话记忆（L2） | `Checkpointer` (per-thread) | 对话消息历史、图执行快照 | InMemorySaver / PostgresSaver |
| 长期记忆（L3） | `Store` (跨 thread) | 用户画像、偏好、知识 | InMemoryStore / PostgresStore |

#### 6.2 工厂函数

```python
from artipivot.memory.checkpointer import create_checkpointer
from artipivot.memory.store import create_store

# P0: 内存后端（零外部依赖）
checkpointer = create_checkpointer("memory")
store = create_store("memory")

# 后续: PostgreSQL 后端
# checkpointer = create_checkpointer("postgres")
# store = create_store("postgres")
```

#### 6.3 会话隔离

同一 Checkpointer 通过 `thread_id` 前缀实现多 Agent 隔离：

```python
# Gateway 自动添加 agent_id 前缀
# Agent A 的会话
thread_id = "code_agent:session_123"

# Agent B 的会话（互不干扰）
thread_id = "research_agent:session_123"
```

#### 6.4 接入新后端

在工厂函数中扩展 `match` 分支：

```python
# memory/checkpointer.py
def create_checkpointer(backend: str = "memory"):
    match backend:
        case "memory":
            return InMemorySaver()
        case "postgres":
            from langgraph.checkpoint.postgres import AsyncPostgresSaver
            return AsyncPostgresSaver.from_conn_string(DB_URI)
        case _:
            raise ValueError(f"Unsupported: {backend}")
```

---

### 7. 日志系统（Observability）

#### 7.1 八通道日志

```python
from artipivot.observability.logging import configure_logging, get_logger

# 初始化（默认日志目录 logs/，级别 INFO）
configure_logging(log_dir="logs", level="INFO")

# 在代码中使用
logger = get_logger("trace")
logger.info("request.start", message_length=100)
```

| 通道 | 文件 | 内容 | 保留天数 |
|------|------|------|:--------:|
| `main` | `artipivot.log` | 所有组件 INFO+ 合并流 | 30 |
| `trace` | `trace.log` | 请求级完整生命周期 | 7 |
| `session` | `session.log` | 按 thread_id 串联多轮请求 + 记忆快照 | 30 |
| `memory` | `memory.log` | Store/Checkpointer 读写操作 | 30 |
| `llm` | `llm.log` | LLM 调用（prompt/response/token/耗时） | 30 |
| `tool` | `tool.log` | 工具调用（参数/结果/耗时） | 14 |
| `error` | `error.log` | 仅 ERROR+，含完整堆栈 | 90 |
| `audit` | `audit.log` | 管理操作（配置变更/插件发布） | 365 |

#### 7.2 请求追踪

```python
from artipivot.observability.trace import bind_trace_id, generate_trace_id, clear_trace

# 在请求入口绑定上下文
trace_id = generate_trace_id()
bind_trace_id(trace_id, agent_id="code_agent", user_id="u1", thread_id="t1")

# 后续所有日志自动携带 trace_id / agent_id / user_id / thread_id
logger.info("node.complete", node="classify", duration_ms=100)

# 请求结束时清除
clear_trace()
```

#### 7.3 配置

```bash
LOG_DIR=logs       # 日志输出目录
LOG_LEVEL=INFO     # 全局级别：DEBUG / INFO / WARNING / ERROR
```

---

### 8. 完整接入示例

以 demo.py 为参考，展示从零搭建一个 Agent 的完整流程：

```python
import asyncio

async def main():
    # ① 存储层（选择后端）
    from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier
    store = InMemoryDocumentStore()
    notifier = InProcessNotifier()

    # ② 加载种子配置（仅首次启动）
    from artipivot.models.loader import load_seed_if_empty
    await load_seed_if_empty(store, "config/seed")

    # ③ 模型 + 配置中心
    from artipivot.models.provider import ModelProvider
    from artipivot.config.center import ConfigCenter
    model_provider = ModelProvider(store, notifier)
    await model_provider.start()
    config_center = ConfigCenter(store, notifier)
    await config_center.start()

    # ④ 注册工具
    from artipivot.tools.registry import ToolRegistry
    from artipivot.tools.builtin.web_search import web_search
    registry = ToolRegistry()
    registry.register(web_search)

    # ⑤ 构建子代理
    from artipivot.agents.base import SubAgentDef
    from artipivot.agents.programmatic import build_programmatic_subagent
    sub_def = SubAgentDef(name="writer", tools=["web_search"], system_prompt="你是助手")
    sub_graph = build_programmatic_subagent(sub_def, registry.get_tool_node(sub_def.tools))

    # ⑥ 构建主图
    from artipivot.graph.factory import GraphFactory
    from artipivot.memory.checkpointer import create_checkpointer
    from artipivot.memory.store import create_store
    factory = GraphFactory(config_center)
    graph = factory.build(
        "my_agent",
        sub_agent_nodes={"writer": sub_graph},
        checkpointer=create_checkpointer(),
        store=create_store(),
    )

    # ⑦ 注册到 Gateway
    from artipivot.gateway.gateway import AgentGateway
    gateway = AgentGateway(model_provider)
    gateway.register("my_agent", graph)

    # ⑧ 调用
    result = await gateway.invoke("my_agent", "帮我写个函数", "session_1", user_id="user_1")
    print(result["messages"][-1].content)

asyncio.run(main())
```

### 扩展点速查表

| 扩展点 | 接口/基类 | 注册方式 | 热更新 |
|--------|-----------|----------|:------:|
| 文档存储 | `DocumentStore` | 继承 + 工厂函数 | — |
| 变更通知 | `ChangeNotifier` | 继承 + 工厂函数 | — |
| 制品存储 | `ArtifactStore` | 继承 + 工厂函数 | — |
| 模型供应商 | `_factories[provider]` | 添加工厂函数 | ✓ |
| 自定义工具 | `@tool` 装饰器 | `registry.register(tool)` | — |
| 子代理 | `SubAgentDef` + `build_programmatic_subagent()` | 挂载到 `sub_agent_nodes` | — |
| 会话记忆后端 | `create_checkpointer()` | 工厂函数 match 分支 | — |
| 长期记忆后端 | `create_store()` | 工厂函数 match 分支 | — |
| 提示词 | `prompt_configs` 集合 | DocumentStore.put() | ✓ |
| 路由规则 | `routing_configs` 集合 | DocumentStore.put() | ✓（需重建图） |
| 限流规则 | `ratelimit_configs` 集合 | DocumentStore.put() | ✓ |
