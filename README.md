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
| 部署 | FastAPI + Uvicorn | REST API 入口 + 管理 API + CLI |
| CLI | Typer | `artipivot` 命令行工具（plugin init/dev/publish/serve） |

### 当前阶段：P5 生产级保障

P5 在 P4 插件系统基础上新增完整的容错、限流、REST API、CLI、可观测性和工具生态：

- CircuitBreaker 熔断器：per-provider 三态机（closed/open/half_open），连续失败自动熔断，恢复后自动放行
- RetryPolicy 重试策略：指数退避 + 可选抖动，可配置可重试异常类型
- error_handler 节点容错：classify/子代理/工具节点级容错，LangGraph 原生 error_handler 集成
- RateLimiter 限流器：多维度限流（per-user/agent/tool），内存滑动窗口，DocumentStore 动态配置
- FastAPI REST API：chat 端点 + 管理 API（模型/路由/插件/限流 CRUD）+ 中间件（trace/限流/CORS）
- CLI 工具：`artipivot plugin init/dev/publish` 脚手架 + `artipivot serve` 启动服务器
- OpenTelemetry：可选 metrics/traces 导出，环境变量控制，未启用零影响
- MCP 适配器：MCP Server → BaseTool 适配，外部工具生态无缝接入 ToolRegistry
- 177 个单元测试全部通过（P0: 38 + P1: 23 + P2: 25 + P3: 21 + P4: 19 + P5: 51）

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
│   └── DEVELOPMENT_PLAN.md                 # 开发计划 — P0（12）+ P1（7）+ P2（7）+ P3（5）+ P4（6）+ P5（9）拆解及进度追踪
│
├── config/seed/                            # 首次启动种子配置（YAML → DocumentStore 加载）
│   ├── models.yaml                         # 模型配置种子 — 全局兜底、主 Agent 模型、子代理模型及 fallback 链
│   ├── prompts.yaml                        # 提示词种子 — 各节点的系统提示词（classify/respond/子代理）
│   ├── routing.yaml                        # 路由规则种子 — 意图列表、置信度阈值、意图→子代理映射表
│   ├── sub_agents.yaml                     # 声明式子代理种子 — 策略/工具/提示词配置模板
│   ├── memory.yaml                         # 记忆配置种子 — embedding 开关、上下文窗口管理
│   └── agents.yaml                         # 多 Agent 声明配置 — 各 Agent 模型/路由/子代理/提示词
│
├── src/artipivot/                          # 源码根目录
│   ├── __init__.py                         # 包入口，声明版本号
│   ├── __main__.py                         # CLI 入口，`python -m artipivot` 执行 demo
│   │
│   ├── gateway/                            # 多主 Agent 分发层
│   │   ├── __init__.py
│   │   ├── gateway.py                      # AgentGateway — 按 agent_id 路由到对应主图，
│   │   │                                   #   动态解析模型、绑定 trace_id、管理 thread_id 隔离
│   │   ├── agent_def.py                    # AgentDef — 统一 Agent 定义数据结构，
│   │   │                                   #   包含模型/路由/子代理/工具/提示词/记忆配置
│   │   ├── registry.py                     # AgentRegistry — 多 Agent 注册表，
│   │   │                                   #   根据 AgentDef 自动构建子代理+主图+注册到 Gateway
│   │   └── loader.py                       # load_agent_defs() — 从 agents.yaml 加载多 Agent 定义
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
│   │                                       #   挂载子代理子图、checkpointer、store，
│   │                                       #   构建时验证 routing 配置与子代理一致性
│   │
│   ├── agents/                             # 子代理层
│   │   ├── __init__.py
│   │   ├── base.py                         # SubAgentDef 数据类 — 子代理定义（名称/工具/提示词/最大迭代次数）
│   │   ├── programmatic.py                 # build_programmatic_subagent() — 构建编程式子代理，
│   │                                       #   ReAct 循环拓扑：START → llm_call → conditional → {tools, END}，
│   │                                       #   tools → llm_call 循环
│   │   ├── declarative.py                  # DeclarativeSubAgentDef + build_declarative_subagent() —
│   │                                       #   声明式子代理引擎，根据 strategy 字段选择策略并构建子图
│   │   ├── loader.py                       # load_sub_agent_defs() — 从 YAML 加载声明式子代理定义
│   │   └── strategies/                     # 子代理策略实现
│   │       ├── __init__.py                 # 策略注册表 — register_strategy() / get_strategy()
│   │       ├── base.py                     # Strategy ABC — 统一策略接口（build 方法）
│   │       ├── react.py                    # ReAct 策略 — think → tools → think 循环，支持 max_iterations
│   │       ├── cot.py                      # CoT 策略 — plan → execute → synthesize 线性流水线
│   │       └── function_calling.py         # Function Calling 策略 — 单次 LLM → tools，无循环
│   │
│   ├── tools/                              # 工具层
│   │   ├── __init__.py
│   │   ├── registry.py                     # ToolRegistry — 全局工具池 + 权限过滤矩阵，
│   │                                       #   按白名单生成 ToolNode
│   │   ├── mcp_adapter.py                  # MCPToolAdapter + MCPRegistry — MCP Server → BaseTool 适配，
│   │                                       #   外部工具生态无缝接入 ToolRegistry
│   │   └── builtin/                        # 内置工具实现（P0 为 stub，返回固定结果）
│   │       ├── __init__.py
│   │       ├── web_search.py               # web_search — 互联网搜索工具 stub
│   │       ├── code_exec.py                # code_exec — 代码执行工具 stub
│   │       └── file_io.py                  # file_io — 文件读写工具 stub
│   │
│   ├── memory/                             # 记忆系统
│   │   ├── __init__.py
│   │   ├── checkpointer.py                 # Checkpointer 工厂 — 可插拔后端注册表，
│   │                                       #   register_checkpointer_backend() 注册，内置 memory / postgres
│   │   ├── store.py                        # Store 工厂 — 可插拔后端注册表，
│   │                                       #   register_store_backend() 注册，内置 memory / postgres
│   │   ├── config.py                       # 记忆配置 — EmbeddingConfig（默认关闭）+ ContextWindowConfig + MemoryConfig
│   │   ├── namespace.py                    # Namespace 构建 — profile/knowledge/preferences/agent 多 Agent 隔离
│   │   ├── context_window.py               # 上下文窗口管理 — summarize/trim 长对话压缩策略
│   │   ├── extraction.py                   # 记忆提取 — extract_profile/extract_knowledge + write_memory
│   │   └── retrieval.py                    # 记忆读取 — build_memory_context，embedding 开关控制语义/明文查询
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
│   │   └── ratelimit.py                    # RateLimiter — 多维度限流器（per-user/agent/tool），
│   │                                       #   内存滑动窗口，DocumentStore 动态配置
│   │
│   ├── storage/                            # 可插拔存储抽象层
│   │   ├── __init__.py
│   │   ├── base.py                         # 三个抽象接口：
│   │                                       #   DocumentStore — 文档 CRUD + 查询（配置/插件元数据）
│   │                                       #   ChangeNotifier — 变更订阅/通知（集群同步）
│   │                                       #   ArtifactStore — 制品上传/下载（插件包）
│   │   ├── bundle.py                       # StorageBundle + StorageConfig — 统一存储组件工厂，
│   │                                       #   从配置创建 DocumentStore + ChangeNotifier + ArtifactStore
│   │   └── memory.py                       # 内存实现（零依赖开发模式）：
│   │                                       #   InMemoryDocumentStore — defaultdict 实现
│   │                                       #   InProcessNotifier — 进程内回调
│   │                                       #   InMemoryArtifactStore — 本地文件系统
│   │
│   ├── observability/                      # 可观测性
│   │   ├── __init__.py
│   │   ├── logging.py                      # structlog 多通道配置 — 8 个独立日志通道（main/trace/session/
│   │                                       #   memory/llm/tool/error/audit），JSON 格式，按日轮转
│   │   ├── trace.py                        # 请求级追踪 — 生成 trace_id，绑定/清除 contextvars，
│   │                                       #   自动携带 agent_id/user_id/thread_id
│   │   └── otel.py                         # OpenTelemetry 可选导出 — metrics/traces，
│   │                                       #   OTEL_ENABLED=true 启用，未启用零影响
│   │
│   ├── plugins/                            # 插件系统
│   │   ├── __init__.py
│   │   ├── manager.py                      # PluginDocument + PluginManager — 插件元数据 CRUD，
│   │                                       #   通过 DocumentStore 持久化，自动触发 ChangeNotifier
│   │   ├── rebuilder.py                    # GraphRebuilder — 图热重建，
│   │                                       #   从插件元数据重建子代理 + 主图，Gateway 原子替换
│   │   └── watcher.py                      # PluginWatcher — 订阅 plugins 集合变更，
│   │                                       #   自动触发对应 Agent 的图重建
│   │
│   ├── api/                                # REST API 层
│   │   ├── __init__.py
│   │   ├── server.py                       # FastAPI 应用 — create_app() 入口 + 中间件（trace/限流/CORS）
│   │   ├── chat.py                         # Chat 端点 — POST /api/v1/chat/{agent_id}
│   │   ├── admin.py                        # 管理 API — 模型/路由/插件/限流 CRUD
│   │   └── deps.py                         # 依赖注入 — 共享组件生命周期
│   │
│   ├── cli/                                # CLI 工具
│   │   ├── __init__.py
│   │   └── main.py                         # artipivot CLI — plugin init/dev/publish + serve
│   │
│   └── resilience/                         # 容错与弹性
│       ├── __init__.py
│       ├── circuit_breaker.py              # CircuitBreaker — per-provider 三态机 + CircuitRegistry
│       ├── retry.py                        # RetryPolicy — 指数退避重试 + 可选抖动
│       └── error_handlers.py               # 节点级 error_handler — classify/子代理/工具容错
│
└── tests/                                  # 测试套件（177 个测试）
    ├── conftest.py                         # 共享 fixtures — InMemoryDocumentStore + InProcessNotifier
    ├── test_storage.py                     # 存储层测试 — CRUD、查询过滤、订阅通知
    ├── test_models.py                      # 模型层测试 — ModelConfig、Provider 加载/fallback/异常
    ├── test_config.py                      # 配置层测试 — PromptStore、RoutingConfig、ConfigCenter 集成
    ├── test_tools.py                       # 工具层测试 — ToolRegistry 注册/过滤/ToolNode + 内置工具 stub
    ├── test_agents.py                      # 子代理测试 — SubAgentDef、编程式子图构建
    ├── test_strategies.py                  # 策略测试 — 注册表、ReAct/CoT/FC 图构建与拓扑验证
    ├── test_declarative.py                 # 声明式测试 — DeclarativeSubAgentDef、策略引擎、YAML 加载
    ├── test_memory.py                      # 记忆测试 — 配置、Namespace、上下文窗口、提取、读取、自定义后端注册
    ├── test_graph.py                       # 图构建测试 — State 类型、主图/子图编译、主图+子图组合
    ├── test_gateway.py                     # 网关测试 — 注册、未知 agent 异常、Memory 工厂 + 自定义后端
    ├── test_multi_agent.py                 # 多 Agent 测试 — AgentDef、AgentRegistry、YAML 加载、五维隔离验证
    ├── test_plugins.py                     # 插件系统测试 — StorageBundle、PluginManager、Watcher、热重建、端到端
    ├── test_resilience.py                  # 容错测试 — 熔断器状态转换、重试策略、error_handler
    ├── test_ratelimit.py                   # 限流测试 — 多维度限流、配置合并、动态更新
    ├── test_api.py                         # API 测试 — chat/admin 端点、中间件、CRUD
    ├── test_otel.py                        # OTel 测试 — 禁用/启用状态、no-op 行为
    └── test_mcp.py                         # MCP 测试 — 工具适配、注册表、自定义调用
```

## 快速开始

```bash
# 安装依赖
uv sync --dev

# 运行测试（177 个）
uv run pytest tests/ -v

# 交互式 demo（需设置 API Key）
export ANTHROPIC_API_KEY=sk-...
# 可选：切换模型 / 兼容供应商
# export DEMO_PROVIDER=openai
# export DEMO_MODEL=gpt-4o
# export DEMO_BASE_URL=https://api.deepseek.com
uv run python demo.py

# 启动 API 服务器
uv run artipivot serve --port 8000

# CLI 插件脚手架
uv run artipivot plugin init my_plugin --template react
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

#### 4.4 声明式子代理

通过 `DeclarativeSubAgentDef` 选择策略，零代码创建子代理：

```python
from artipivot.agents.declarative import DeclarativeSubAgentDef, build_declarative_subagent

defn = DeclarativeSubAgentDef(
    name="code_writer",
    strategy="react",                  # react | cot | function_calling
    tools=["web_search", "code_exec"],
    system_prompt="You are a coding assistant.",
    strategy_config={"max_iterations": 5},
)

sub_graph = build_declarative_subagent(defn, tool_node)
```

**三种策略对比**：

| 策略 | 拓扑 | 适用场景 | strategy_config 参数 |
|------|------|----------|---------------------|
| `react` | think → tools → think（循环） | 复杂多步推理任务 | `max_iterations`（默认 10） |
| `cot` | plan → execute → synthesize（线性） | 可分解的结构化任务 | `max_plan_steps`（默认 5） |
| `function_calling` | llm → tools → END（单次） | 简单查询/转换 | 无 |

#### 4.5 YAML 声明式配置

在 `config/seed/sub_agents.yaml` 中定义子代理，启动时加载：

```yaml
sub_agents:
  code_writer:
    strategy: react
    tools: [web_search, code_exec, file_io]
    system_prompt: "You are a professional coding assistant."
    strategy_config:
      max_iterations: 5

  code_reviewer:
    strategy: cot
    tools: [web_search, file_io]
    system_prompt: "You are a code reviewer."
    strategy_config:
      max_plan_steps: 3
```

加载方式：

```python
from artipivot.agents.loader import load_sub_agent_defs

defs = load_sub_agent_defs("config/seed")
for name, defn in defs.items():
    graph = build_declarative_subagent(defn, tool_node)
```

---

### 5. 动态配置中心（ConfigCenter）

ConfigCenter 统一管理所有运行时配置，从 DocumentStore 加载，通过 ChangeNotifier 热更新。

#### 5.1 配置分类与生效方式

| 配置类型 | 变更是否重建图 | 管理方式 |
|----------|:------------:|----------|
| 模型配置 | 否 | `model_provider.update_*()` |
| 提示词 | 否 | 修改 DocumentStore `prompt_configs` 集合 |
| 限流参数 | 否 | `PUT /admin/ratelimits/*` — 多维度限流，超限返回 429 |
| 路由规则 | **是** | 修改 DocumentStore `routing_configs` 集合 → ConfigCenter 回调 → GraphRebuilder 重建 |
| 插件变更 | **是** | PluginManager.publish() → ChangeNotifier → PluginWatcher → GraphRebuilder 重建 |

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

#### 6.1 三层记忆

| 层级 | 机制 | 内容 | 状态 |
|------|------|------|:----:|
| L1 工作记忆 | 图 State（TypedDict） | 意图、活跃子代理、中间产物 | ✅ P0 |
| L2 会话记忆 | Checkpointer (per-thread) | 对话消息历史、图快照 | ✅ P2 |
| L3 长期记忆 | Store (跨 thread) | 用户画像、偏好、知识 | ✅ P2 |

#### 6.2 可插拔存储后端

Checkpointer 和 Store 均采用**注册表模式**，内置后端自动注册，自定义后端一行注册：

```python
from artipivot.memory.checkpointer import (
    create_checkpointer,
    register_checkpointer_backend,
    available_checkpointer_backends,
)
from artipivot.memory.store import (
    create_store,
    register_store_backend,
    available_store_backends,
)

# 使用内置后端
checkpointer = create_checkpointer("memory")
store = create_store("memory")

# 查看可用后端
print(available_checkpointer_backends())  # ["memory", "postgres"]
print(available_store_backends())         # ["memory", "postgres"]
```

**注册自定义后端**（如 MongoDB）：

```python
# 实现自定义后端
class MongoStore:
    """实现 LangGraph BaseStore 接口"""
    async def aget(self, namespace, key): ...
    async def aput(self, namespace, key, value): ...
    async def adelete(self, namespace, key): ...
    async def asearch(self, namespace, *, query, limit=10): ...
    async def alist(self, namespace): ...

# 注册 — 框架代码零修改
register_store_backend("mongodb", lambda **kw: MongoStore(kw["uri"]))

# 然后正常使用
store = create_store("mongodb", uri="mongodb://localhost:27017")
```

#### 6.3 长期记忆 Namespace 隔离

多 Agent 通过 namespace 前缀天然隔离：

```python
from artipivot.memory.namespace import profile_ns, knowledge_ns, agent_memory_ns

# Agent A 的用户画像
ns = profile_ns("code_agent", "user_123")       # ("code_agent", "user_123", "profile")

# Agent B 的用户画像（互不干扰）
ns = profile_ns("research_agent", "user_123")    # ("research_agent", "user_123", "profile")

# 子代理专属记忆
ns = agent_memory_ns("code_agent", "user_123", "code_writer")
# ("code_agent", "user_123", "agent", "code_writer")
```

#### 6.4 记忆提取 + 写入

对话结束后自动从对话中提取用户画像和知识，写入 Store：

```python
from artipivot.memory.extraction import write_memory

# 在 respond 节点中调用
await write_memory(store, agent_id, user_id, messages, model)
```

#### 6.5 记忆读取 + 注入

classify 节点自动将长期记忆注入 prompt：

```python
from artipivot.memory.retrieval import build_memory_context

# 读取用户画像 + 语义搜索相关知识
context = await build_memory_context(store, agent_id, user_id, query)
# 返回格式：
# [用户画像]
# {"name": "张三", "language": "Python"}
#
# [相关知识]
# - 用户偏好测试驱动开发
# - 用户的项目使用 FastAPI
```

#### 6.6 上下文窗口管理

长对话超出 token 阈值时自动压缩：

```python
from artipivot.memory.context_window import ContextWindowManager

mgr = ContextWindowManager(config)
new_messages = await mgr.maybe_compress(messages, model)
```

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `none` | 不压缩（默认） | 短对话 |
| `summarize` | LLM 摘要旧消息，保留最近 N 条 | 长对话（推荐） |
| `trim` | 直接截断，只保留最近 N 条 | 不想调 LLM |

#### 6.7 记忆配置（memory.yaml）

```yaml
# config/seed/memory.yaml
memory:
  embedding:
    enabled: false                    # 默认关闭向量搜索
    provider: openai                  # embedding 供应商
    model: text-embedding-3-small
    dims: 1536
    # base_url:                       # 兼容供应商地址
    # api_key:                        # 不填则读环境变量

  context_window:
    strategy: none                    # none | summarize | trim
    trigger_tokens: 100000
    keep_messages: 20
```

---

### 7. 多主 Agent 系统（Multi-Agent）

#### 7.1 AgentDef — 统一 Agent 定义

一个 dataclass 描述 Agent 的完整配置：

```python
from artipivot.gateway.agent_def import AgentDef

agent_def = AgentDef(
    agent_id="code_agent",
    model={"provider": "anthropic", "name": "claude-sonnet-4-6"},
    confidence_threshold=0.7,
    intent_map={"code_write": "code_writer", "debug": "code_writer"},
    declarative_sub_agents={
        "code_writer": DeclarativeSubAgentDef(
            name="code_writer", strategy="react",
            tools=["web_search", "code_exec"],
            system_prompt="You are a coding assistant.",
        )
    },
    prompts={"classify": "Classify intent."},
)
```

支持 `from_dict()` / `to_dict()` 序列化，可直接从 YAML 加载。

#### 7.2 AgentRegistry — 多 Agent 自动构建

```python
from artipivot.gateway.registry import AgentRegistry

registry = AgentRegistry(gateway, graph_factory, tool_registry)

# 一行注册 — 自动构建子代理 + 主图 + 挂载到 Gateway
registry.register_def(agent_def, checkpointer=cp, store=store)

# 查询
registry.list_agents()          # ["code_agent", "research_agent"]
registry.get_def("code_agent")  # AgentDef
```

#### 7.3 YAML 多 Agent 声明

在 `config/seed/agents.yaml` 中定义多个 Agent：

```yaml
agents:
  code_agent:
    model:
      provider: anthropic
      name: claude-sonnet-4-6
    routing:
      confidence_threshold: 0.7
      intents:
        code_write: code_writer
        debug: code_writer
    sub_agents:
      code_writer:
        strategy: react
        tools: [web_search, code_exec]
        system_prompt: "You are a coding assistant."
        strategy_config:
          max_iterations: 5

  research_agent:
    model:
      provider: openai
      name: gpt-4o
    routing:
      confidence_threshold: 0.6
      intents:
        search: researcher
    sub_agents:
      researcher:
        strategy: cot
        tools: [web_search]
```

加载方式：

```python
from artipivot.gateway.loader import load_agent_defs

defs = load_agent_defs("config/seed")
for agent_id, agent_def in defs.items():
    registry.register_def(agent_def, checkpointer=cp, store=store)
```

#### 7.4 多维度隔离

| 隔离维度 | 机制 | 说明 |
|----------|------|------|
| State | 独立图实例 | 每个 Agent 有自己的 CompiledStateGraph |
| thread_id | `agent_id:thread_id` 前缀 | Gateway 自动加前缀，同一线程 ID 不同 Agent 不冲突 |
| Namespace | `(agent_id, user_id, type)` 三元组 | Store 的长期记忆按 Agent 隔离 |
| Model | AgentDef.model | 各 Agent 可配置不同模型供应商和模型名 |
| Tool | ToolNode 白名单 | 各子代理按工具白名单过滤，互不可见 |

#### 7.5 GraphFactory 路由验证

构建时自动验证 routing 配置与子代理的一致性：

```python
# 如果 routing 配置指向不存在的子代理，构建时立即报错
factory.build("agent", sub_agent_nodes={...})
# ValueError: Routing config maps intent 'code_write' to sub-agent 'code_writer',
#             but no sub-agent graph provided. Available: [...]
```

---

### 8. 插件系统与图热重建（Plugin System）

#### 8.1 插件元数据管理

插件通过 `PluginManager` 管理，元数据持久化在 DocumentStore：

```python
from artipivot.plugins.manager import PluginManager, PluginDocument

pm = PluginManager(store, notifier)

# 发布插件
plugin = PluginDocument(
    plugin_type="sub_agent",     # sub_agent | tool | pipeline
    name="writer",
    version="1.0",
    agent_id="code_agent",       # 所属主 Agent
    manifest={                   # 完整配置
        "strategy": "react",
        "tools": ["web_search", "code_exec"],
        "system_prompt": "You are a coding assistant.",
        "strategy_config": {"max_iterations": 5},
    },
)
await pm.publish(plugin)        # 自动设置时间戳 + 触发 ChangeNotifier

# 查询
plugins = await pm.list_plugins(agent_id="code_agent", status="active")
plugin = await pm.get_plugin("sub_agent", "writer", "code_agent")

# 弃用
await pm.deprecate("sub_agent", "writer", "code_agent")
```

**Key 格式**：`{plugin_type}:{agent_id}:{name}`，如 `sub_agent:code_agent:writer`

#### 8.2 图热重建

路由或插件变更时，`GraphRebuilder` 自动重建受影响的 Agent 图并原子替换到 Gateway：

```python
from artipivot.plugins.rebuilder import GraphRebuilder

rebuilder = GraphRebuilder(gateway, factory, tools, pm)

# 手动触发重建
await rebuilder.rebuild_agent("code_agent")
```

**重建流程**：
1. 从 PluginManager 读取该 Agent 的所有 active 插件
2. 根据插件 manifest 构建子代理图
3. 构建主图
4. `gateway.register()` 原子替换（Python dict 赋值是原子的）

**隔离保证**：重建 Agent A 不会影响 Agent B 的图引用。

#### 8.3 PluginWatcher 自动重建

```python
from artipivot.plugins.watcher import PluginWatcher

watcher = PluginWatcher(notifier, rebuilder)
await watcher.start()  # 订阅 plugins 集合

# 此后任何 publish/deprecate 操作自动触发对应 Agent 的图重建
```

**端到端流程**：

```
pm.publish(plugin)
  → DocumentStore.put("plugins", key, data)
  → ChangeNotifier.notify("plugins", key, "upsert", data)
  → PluginWatcher._on_plugin_change()
  → GraphRebuilder.rebuild_agent(agent_id)
  → Gateway.register(agent_id, new_graph)  # 原子替换
```

#### 8.4 ConfigCenter 路由变更回调

路由配置变更时，ConfigCenter 通过回调触发图重建：

```python
from artipivot.config.center import ConfigCenter

config_center = ConfigCenter(store, notifier, on_routing_change=rebuilder.rebuild_agent)
await config_center.start()

# 修改路由配置 → 自动重建图
await store.put("routing_configs", "code_agent", {
    "agent_id": "code_agent",
    "confidence_threshold": 0.8,
    "intents": [...],
})
# → ConfigCenter._routing_change_handler()
# → rebuilder.rebuild_agent("code_agent")
```

#### 8.5 StorageBundle 统一存储工厂

```python
from artipivot.storage.bundle import StorageBundle, StorageConfig

# 从配置创建全套存储组件
config = StorageConfig(
    document_backend="memory",
    notifier_backend="memory",
    artifact_backend="memory",
    options={"artifact": {"base_dir": "/tmp/artifacts"}},
)
bundle = StorageBundle(config)

# 或从类方法
bundle = StorageBundle.from_config(StorageConfig())

bundle.document_store   # DocumentStore 实例
bundle.change_notifier  # ChangeNotifier 实例
bundle.artifact_store   # ArtifactStore 实例
```

---

### 9. 日志系统（Observability）

#### 9.1 八通道日志

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

#### 9.2 请求追踪

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

#### 9.3 配置

```bash
LOG_DIR=logs       # 日志输出目录
LOG_LEVEL=INFO     # 全局级别：DEBUG / INFO / WARNING / ERROR
```

---

### 10. 完整接入示例

以 demo.py 为参考，展示从零搭建多 Agent 系统的完整流程（含插件热重建）：

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
    from artipivot.tools.builtin.code_exec import code_exec
    tools = ToolRegistry({"web_search": web_search, "code_exec": code_exec})

    # ⑤ 初始化 Gateway + Factory + Registry
    from artipivot.gateway.gateway import AgentGateway
    from artipivot.graph.factory import GraphFactory
    from artipivot.gateway.registry import AgentRegistry
    from artipivot.memory.checkpointer import create_checkpointer
    from artipivot.memory.store import create_store

    gateway = AgentGateway(model_provider)
    factory = GraphFactory(config_center)
    registry = AgentRegistry(gateway, factory, tools)

    # ⑥ 从 YAML 加载多 Agent 定义（推荐）
    from artipivot.gateway.loader import load_agent_defs
    from artipivot.gateway.agent_def import AgentDef
    from artipivot.agents.declarative import DeclarativeSubAgentDef

    # 方式一：从 YAML 加载
    agent_defs = load_agent_defs("config/seed")

    # 方式二：手动构建
    agent_defs = {
        "code_agent": AgentDef(
            agent_id="code_agent",
            model={"provider": "anthropic", "name": "claude-sonnet-4-6"},
            intent_map={"code_write": "writer"},
            declarative_sub_agents={
                "writer": DeclarativeSubAgentDef(
                    name="writer", strategy="react",
                    tools=["web_search", "code_exec"],
                    system_prompt="You are a coding assistant.",
                ),
            },
        ),
    }

    # ⑦ 注册所有 Agent — 自动构建子代理 + 主图 + 挂载
    cp = create_checkpointer()
    st = create_store()
    for agent_def in agent_defs.values():
        registry.register_def(agent_def, checkpointer=cp, store=st)

    # ⑧ 启用插件热重建（可选）
    from artipivot.plugins.manager import PluginManager, PluginDocument
    from artipivot.plugins.rebuilder import GraphRebuilder
    from artipivot.plugins.watcher import PluginWatcher

    pm = PluginManager(store, notifier)
    rebuilder = GraphRebuilder(gateway, factory, tools, pm)
    watcher = PluginWatcher(notifier, rebuilder)
    await watcher.start()
    await notifier.start()

    # ⑨ 运行时发布插件 → 自动触发图重建
    plugin = PluginDocument(
        plugin_type="sub_agent", name="writer",
        version="1.0", agent_id="code_agent",
        manifest={"strategy": "react", "tools": ["web_search"]},
    )
    await pm.publish(plugin)
    # → ChangeNotifier → PluginWatcher → GraphRebuilder → Gateway 原子替换

    # ⑩ 调用不同 Agent
    result = await gateway.invoke("code_agent", "写个排序函数", "session_1")
    print(result["messages"][-1].content)

asyncio.run(main())
```

### 扩展点速查表

| 扩展点 | 接口/基类 | 注册方式 | 热更新 |
|--------|-----------|----------|:------:|
| 文档存储 | `DocumentStore` | 继承 + 工厂函数 | — |
| 变更通知 | `ChangeNotifier` | 继承 + 工厂函数 | — |
| 制品存储 | `ArtifactStore` | 继承 + 工厂函数 | — |
| 存储组件组合 | `StorageBundle` + `StorageConfig` | 配置切换后端 | — |
| 模型供应商 | `_factories[provider]` | 添加工厂函数 | ✓ |
| 自定义工具 | `@tool` 装饰器 | `registry.register(tool)` | — |
| 编程式子代理 | `SubAgentDef` + `build_programmatic_subagent()` | 挂载到 `sub_agent_nodes` | — |
| 声明式子代理 | `DeclarativeSubAgentDef` + `build_declarative_subagent()` | strategy 字段选择策略 | — |
| 子代理策略 | `Strategy` ABC | `register_strategy()` | — |
| Checkpointer 后端 | `BaseCheckpointSaver` | `register_checkpointer_backend()` | — |
| Store 后端 | `BaseStore` | `register_store_backend()` | — |
| 记忆提取 | `extract_profile()` / `extract_knowledge()` | 替换函数 | — |
| 上下文压缩 | `ContextWindowManager` | `strategy` 配置切换 | ✓ |
| Embedding 模型 | `EmbeddingConfig` | memory.yaml 配置 | ✓ |
| 多主 Agent | `AgentDef` | `AgentRegistry.register_def()` | — |
| 多 Agent 配置 | `agents.yaml` | `load_agent_defs()` | — |
| 插件元数据 | `PluginDocument` + `PluginManager` | `pm.publish()` | ✓（自动重建图） |
| 图热重建 | `GraphRebuilder` | `rebuilder.rebuild_agent()` | ✓ |
| 插件变更监听 | `PluginWatcher` | `watcher.start()` | ✓（实时响应） |
| 提示词 | `prompt_configs` 集合 | DocumentStore.put() | ✓ |
| 路由规则 | `routing_configs` 集合 | DocumentStore.put() | ✓（自动重建图） |
| 限流规则 | `ratelimit_configs` 集合 | DocumentStore.put() | ✓ |
| 熔断器 | `CircuitBreaker` | `CircuitRegistry.get_or_create()` | — |
| 重试策略 | `RetryPolicy` | 包装异步函数 | — |
| 节点容错 | `error_handler` | `add_node(..., error_handler=)` | — |
| MCP 工具 | `MCPToolAdapter` | `MCPRegistry.register_server()` | — |
| OTel 可观测 | `observability/otel.py` | `OTEL_ENABLED=true` | ✓ |
| REST API | FastAPI | `create_app()` | — |
| CLI 命令 | Typer | `artipivot` 入口 | — |
