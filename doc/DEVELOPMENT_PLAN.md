# Plan: ArtiPivot P0 骨架开发 — 详细步骤拆解

## Context

ArtiPivot 项目已完成设计文档（DESIGN.md / ARCHITECTURE.md / MEMORY.md），依赖已安装，但没有任何源代码。需要从零搭建 P0 骨架，按 ARCHITECTURE.md §15 的阶段规划，以「可运行的最小闭环」为目标逐步构建。

每个步骤作为一个独立 Task，完成后可单独验证，支持断点续开发。所有代码放在 `src/artipivot/` 下，由 `pyproject.toml` 的 `[tool.hatch.build.targets.wheel]` 或 `[project.scripts]` 管理入口。

### 进度总览

> 每个 Step 完成后，将状态从 `⬜` 更新为 `✅` 并填写完成日期和备注。

| Step | 状态 | 完成日期 | 关键产出 | 备注 |
|------|------|----------|----------|------|
| Step 0: 项目骨架 | ✅ | 2026-05-14 | 包结构 + pyproject.toml | 12 个包目录，pytest 配置 |
| Step 1: 日志基础设施 | ✅ | 2026-05-14 | structlog 配置 | 8 通道 JSON 日志 + trace_id 绑定 |
| Step 2: 存储抽象 | ✅ | 2026-05-14 | DocumentStore + ChangeNotifier ABC + InMemory 实现 | 3 个 ABC + 3 个内存实现 |
| Step 3: 模型配置 | ✅ | 2026-05-14 | ModelProvider + YAML seed | 三级 fallback + 动态热更新 |
| Step 4: 动态配置中心 | ✅ | 2026-05-14 | ConfigCenter + PromptStore + RoutingConfig | 含 YAML seed 文件 |
| Step 5: 图结构 | ✅ | 2026-05-14 | State + Context + 主图构建器 | classify/clarify/fallback/respond + 条件路由 |
| Step 6: 工具层 | ✅ | 2026-05-14 | ToolRegistry + 3 个 stub 工具 | web_search, code_exec, file_io |
| Step 7: 子代理 | ✅ | 2026-05-14 | 编程式子代理 (ReAct) | llm_call → tools 循环 |
| Step 8: Gateway | ✅ | 2026-05-14 | AgentGateway 分发层 | invoke + stream |
| Step 9: Memory | ✅ | 2026-05-14 | InMemory Checkpointer + Store 工厂 | InMemorySaver + InMemoryStore |
| Step 10: 集成 demo | ✅ | 2026-05-14 | 端到端可运行 demo | demo.py 交互式脚本 |
| Step 11: 测试套件 | ✅ | 2026-05-14 | 全模块单元测试 | 38 个测试全部通过 |

### 开发参考文档

开发过程中，**使用 `langchain-docs` MCP 获取 LangChain / LangGraph 最新官方文档**。这是获取 API 用法、代码示例、最佳实践的主要途径。

使用方式：
1. `list_doc_sources` — 列出可用的文档源（LangChain、LangGraph 等）及其 URL
2. `fetch_docs(url)` — 抓取指定文档页面的完整内容

典型场景：
- 构建 StateGraph、添加节点/边 → 查 LangGraph Graph 文档
- ToolNode、@tool 装饰器 → 查 LangGraph Tools 文档
- Checkpointer、Store → 查 LangGraph Persistence 文档
- Runtime[Context]、context_schema → 查 LangGraph Dependency Injection 文档
- RetryPolicy、NodeError、Command → 查 LangGraph Error Handling 文档

> 开发时应先通过 langchain-docs MCP 确认 API 签名和用法，再编写代码，避免依赖过时或不存在的 API。

---

## Step 0: 项目骨架 + 包结构

**目标**: 创建完整的目录结构和所有 `__init__.py`，配置 `pyproject.toml` 入口点

**文件清单**:
```
src/artipivot/__init__.py              # version
src/artipivot/gateway/__init__.py
src/artipivot/graph/__init__.py
src/artipivot/agents/__init__.py
src/artipivot/tools/__init__.py
src/artipivot/tools/builtin/__init__.py
src/artipivot/memory/__init__.py
src/artipivot/models/__init__.py
src/artipivot/config/__init__.py
src/artipivot/storage/__init__.py
src/artipivot/observability/__init__.py
src/artipivot/resilience/__init__.py
config/seed/.gitkeep
tests/__init__.py
tests/conftest.py
```

**pyproject.toml 变更**:
- 添加 `[tool.hatch.build.targets.wheel] packages = ["src/artipivot"]`
- 添加 dev 依赖: `pytest`, `pytest-asyncio`

**验证**: `python -c "import artipivot"` 成功

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________: Observability — 日志基础设施

**目标**: 建立 structlog 配置，后续所有模块直接使用

**文件**:
- `src/artipivot/observability/logging.py` — structlog 配置 + 多通道 Handler
- `src/artipivot/observability/trace.py` — TraceLogger（请求级 trace_id 绑定）

**关键实现**:
- structlog JSON 输出到 stdout + 文件日志（`logs/trace.log`）
- `bind_trace_id(trace_id)` 上下文绑定
- 日志轮转配置

**验证**: 能创建 logger 并输出 JSON 格式日志

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## Step 2: Storage — 可插拔存储抽象（内存实现）

**目标**: 实现 DESIGN.md §6 定义的三个接口，先用 InMemory 实现

**文件**:
- `src/artipivot/storage/base.py` — `DocumentStore`, `ChangeNotifier`, `ArtifactStore` ABC
- `src/artipivot/storage/memory.py` — `InMemoryDocumentStore`, `InProcessNotifier`

**接口定义** (来自 DESIGN.md §6):
```python
class DocumentStore(ABC):
    async def get(self, collection: str, key: str) -> dict | None
    async def put(self, collection: str, key: str, data: dict) -> None
    async def delete(self, collection: str, key: str) -> None
    async def query(self, collection: str, filter: dict) -> list[dict]

class ChangeNotifier(ABC):
    async def subscribe(self, collection: str, callback: Callable) -> None
    async def notify(self, collection: str, event: dict) -> None
    async def start(self) -> None
    async def stop(self) -> None
```

**验证**: 单元测试 — put/get/query 订阅/通知

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## Step 3: Models — 模型配置 + ModelProvider（InMemory 后端）

**目标**: 模型配置数据结构 + YAML seed 加载 + 动态模型解析

**文件**:
- `src/artipivot/models/config.py` — `ModelConfig` dataclass
- `src/artipivot/models/provider.py` — `ModelProvider`（依赖 DocumentStore + ChangeNotifier）
- `src/artipivot/models/loader.py` — YAML seed → DocumentStore 加载
- `config/seed/models.yaml` — 初始模型配置

**关键实现**:
- `ModelConfig`: provider, name, temperature, timeout, fallback
- `ModelProvider.__init__(store, notifier)` — 从 DocumentStore 加载配置
- `ModelProvider.get_model(agent_id, sub_name)` — 三级 fallback 链解析
- `ModelProvider.update_agent_model(agent_id, model)` — 更新配置
- `loader.py`: 检测 DocumentStore 为空时从 YAML 加载

**验证**: 单元测试 — 加载 YAML → 查询模型 → fallback 链解析

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## Step 4: Config — 动态配置中心（InMemory 后端）

**目标**: ConfigCenter 骨架 + PromptStore + RoutingConfig

**文件**:
- `src/artipivot/config/center.py` — `ConfigCenter` 统一入口
- `src/artipivot/config/prompts.py` — `PromptStore` 提示词管理
- `src/artipivot/config/routing.py` — `RoutingConfig` 路由规则
- `src/artipivot/config/ratelimit.py` — `RateLimiter` 骨架（P0 先不做实际限流）
- `config/seed/prompts.yaml`
- `config/seed/routing.yaml`

**关键实现**:
- `ConfigCenter.__init__(store, notifier)` — 持有 PromptStore + RoutingConfig + RateLimiter
- `ConfigCenter.start()` — 从 DocumentStore 加载配置 + 注册订阅
- 各子组件的 `apply(data)` 回调

**验证**: 单元测试 — 加载 seed → 查询配置 → 变更通知生效

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## Step 5: Graph — State + Context + 主图构建

**目标**: 核心图结构 — State 定义、Context Schema、主图构建器

**文件**:
- `src/artipivot/graph/state.py` — `ArtiPivotState`, `SubAgentState`
- `src/artipivot/graph/context.py` — `AgentContext` dataclass
- `src/artipivot/graph/router.py` — classify 节点 + `route_by_intent` 条件边
- `src/artipivot/graph/root.py` — `build_root_graph()` 构建单个主图
- `src/artipivot/graph/factory.py` — `GraphFactory` 按 agent_id 构建主图（P0 先硬编码一个 agent）

**关键实现**:
- `classify` 节点: LLM structured output → `{intent, confidence}`
- `route_by_intent`: 条件边 — threshold 检查 → intent_map 映射
- `clarify` 节点: 追问消息
- `respond` 节点: 格式化输出
- `fallback` 节点: 兜底回复
- `build_root_graph()`: START → classify → conditional_edges → {sub_agents, clarify, fallback} → respond → END

**验证**: 构建图 → 打印图结构 → 验证节点和边正确

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## Step 6: Tools — 工具注册 + 内置工具

**目标**: ToolRegistry + 3 个内置工具的 stub 实现

**文件**:
- `src/artipivot/tools/registry.py` — `ToolRegistry`
- `src/artipivot/tools/builtin/web_search.py` — `web_search` 工具 stub
- `src/artipivot/tools/builtin/code_exec.py` — `code_exec` 工具 stub
- `src/artipivot/tools/builtin/file_io.py` — `file_io` 工具 stub

**关键实现**:
- `ToolRegistry.__init__(tools: dict[str, BaseTool])`
- `ToolRegistry.get_for_agent(agent_id, allowed: list[str]) -> list[BaseTool]`
- `ToolRegistry.get_tool_node(agent_id, allowed) -> ToolNode`
- 三个 stub 工具用 `@tool` 装饰器，返回固定结果

**验证**: 单元测试 — 注册工具 → 按权限过滤 → 生成 ToolNode

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## Step 7: Agents — 编程式子代理

**目标**: 构建一个 ReAct 风格的编程式子代理

**文件**:
- `src/artipivot/agents/base.py` — `SubAgentDef` 数据结构
- `src/artipivot/agents/programmatic.py` — `build_programmatic_subagent()`

**关键实现**:
- `SubAgentDef`: name, tools, system_prompt, max_iterations
- `build_programmatic_subagent()`:
  ```
  START → llm_call → conditional(should_continue) → {tools, END}
  tools → llm_call (循环)
  ```
- `llm_call` 节点: 使用 `runtime.context.model` 调用 LLM
- `should_continue`: 检查是否有 tool_calls

**验证**: 构建子图 → 打印图结构 → 验证循环拓扑

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## Step 8: Gateway — Agent 分发层

**目标**: AgentGateway + 第一个完整的端到端调用

**文件**:
- `src/artipivot/gateway/gateway.py` — `AgentGateway`
- `src/artipivot/gateway/config.py` — agent 注册表

**关键实现**:
- `AgentGateway.__init__(checkpointer, store, model_provider, config_center)`
- `AgentGateway.register(agent_id, graph)`
- `AgentGateway.invoke(agent_id, message, thread_id, *, user_id)`
  - 解析模型
  - 构建 config (thread_id)
  - 构建 context (AgentContext)
  - 调用 `graph.ainvoke()`
- `AgentGateway.stream()` — 流式调用（可选，P0 先做 ainvoke）

**验证**: 端到端测试 — gateway.invoke() → 分类 → 路由 → 子代理 → 响应

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## Step 9: Memory — InMemory Checkpointer + Store

**目标**: 使用 LangGraph 内置的 InMemorySaver 和 InMemoryStore

**文件**:
- `src/artipivot/memory/checkpointer.py` — checkpointer 工厂（P0: InMemorySaver）
- `src/artipivot/memory/store.py` — store 工厂（P0: InMemoryStore）

**关键实现**:
- `create_checkpointer(backend="memory")` → `InMemorySaver()`
- `create_store(backend="memory")` → `InMemoryStore()`
- 简单工厂函数，P0 只做 memory 后端

**验证**: Gateway 使用 InMemory checkpointer + store 运行完整对话

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## Step 10: 集成验证 — 完整 P0 闭环

**目标**: 一个可运行的 demo，包含 1 个主 Agent + 1 个子代理 + 3 个 stub 工具

**文件**:
- `src/artipivot/__main__.py` — CLI 入口
- `demo.py`（项目根目录）— 交互式 demo 脚本

**关键实现**:
```python
# demo.py — 端到端演示
1. 初始化 InMemoryStorage + InMemoryCheckpointer
2. 加载 seed 配置（models.yaml, routing.yaml）
3. 构建 ModelProvider + ConfigCenter
4. 构建 ToolRegistry + 注册内置工具
5. 构建子代理图
6. 构建主图
7. 注册到 Gateway
8. 交互循环：输入 → gateway.invoke() → 输出
```

**验证**:
- `python demo.py` 启动交互式对话
- 输入 "帮我写一段排序代码" → 分类 → 路由到 code_writer → 返回结果
- 日志输出到 `logs/trace.log`

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

**目标**: 为 P0 所有模块编写测试

**文件**:
- `tests/test_storage.py`
- `tests/test_models.py`
- `tests/test_config.py`
- `tests/test_graph.py`
- `tests/test_tools.py`
- `tests/test_agents.py`
- `tests/test_gateway.py`
- `tests/conftest.py` — 共享 fixtures

**验证**: `pytest tests/` 全部通过

**完成记录**:
- 状态: ⬜ 未开始 | 🔄 进行中 | ✅ 已完成
- 完成日期: ________
- 备注: ________

---

## 依赖关系图

```
Step 0 (骨架)
  ├─→ Step 1 (日志)
  ├─→ Step 2 (存储抽象)
  │     ├─→ Step 3 (模型)
  │     └─→ Step 4 (配置中心)
  ├─→ Step 5 (图结构)
  │     └─→ Step 7 (子代理) ──→ Step 8 (Gateway)
  ├─→ Step 6 (工具) ──→ Step 7 (子代理)
  └─→ Step 9 (Memory) ──→ Step 8 (Gateway)

Step 8 ──→ Step 10 (集成 demo)
Step 10 ──→ Step 11 (测试)
```

**可并行的步骤**:
- Step 1, 2, 6 互不依赖，可同时开发
- Step 3, 4 依赖 Step 2，可并行
- Step 5 依赖 Step 0，可与其他并行

---

## 验证策略

每个 Step 完成后:
1. `python -c "from artipivot.xxx import Yyy"` — 导入检查
2. 对应单元测试通过
3. 无 import 错误

Step 10 完成后:
1. `python demo.py` — 交互式对话正常运行
2. 日志文件正确输出
3. 完整对话链路: 输入 → 分类 → 路由 → 子代理 → 工具 → 响应
