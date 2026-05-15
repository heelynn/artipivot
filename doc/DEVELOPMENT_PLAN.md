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

---
---

# Plan: ArtiPivot P1 — 声明式子代理策略引擎

## Context

P0 已完成骨架搭建（39 个测试全部通过），包含：
- 编程式子代理 `build_programmatic_subagent()` — 硬编码的 ReAct 循环
- `SubAgentDef` 数据结构 — 只有一种策略参数（max_iterations）

P1 目标：将子代理从"代码里写死怎么跑"升级为"配置文件声明怎么跑"。

**核心交付**：
1. 三种策略图（ReAct / CoT / Function Calling），各自独立的图拓扑
2. 策略引擎，根据配置自动选择策略并构建子图
3. YAML 声明式子代理定义，加载后注册到图
4. 所有策略通过 `ToolNode` 复用 P0 的工具注册表

**不改变**：
- P0 已有的 `build_programmatic_subagent()` 保持向后兼容
- `SubAgentDef` 保持不变，新增 `DeclarativeSubAgentDef` 并行使用
- `SubAgentState`、`AgentContext`、`ToolRegistry` 无需修改
- 主图构建流程（`build_root_graph`、`GraphFactory`）无需修改

### 进度总览

> 每个 Step 完成后，将状态从 `⬜` 更新为 `✅` 并填写完成日期和备注。

| Step | 状态 | 完成日期 | 关键产出 | 备注 |
|------|------|----------|----------|------|
| Step 12: 策略抽象接口 | ✅ | 2026-05-15 | `Strategy` ABC + 策略注册表 | 所有策略的统一协议 |
| Step 13: ReAct 策略 | ✅ | 2026-05-15 | `agents/strategies/react.py` | 从 programmatic.py 提取，支持配置 |
| Step 14: CoT 策略 | ✅ | 2026-05-15 | `agents/strategies/cot.py` | plan → execute → synthesize 三节点线性链 |
| Step 15: Function Calling 策略 | ✅ | 2026-05-15 | `agents/strategies/function_calling.py` | 单次 LLM → ToolNode，无循环 |
| Step 16: 策略引擎 | ✅ | 2026-05-15 | `agents/declarative.py` | 配置 → 策略选择 → 子图构建 |
| Step 17: YAML 声明式加载 | ✅ | 2026-05-15 | `agents/loader.py` + seed YAML | 配置文件 → DeclarativeSubAgentDef |
| Step 18: 集成验证 + 测试 | ✅ | 2026-05-15 | 全策略测试 + demo 更新 | 61 个测试全部通过 |

---

## Step 12: 策略抽象接口

**目标**: 定义所有子代理策略的统一协议，使策略引擎可以面向接口编程

**文件**:
- `src/artipivot/agents/strategies/__init__.py` — 包初始化 + 策略注册表
- `src/artipivot/agents/strategies/base.py` — `Strategy` ABC

**关键设计**:

```python
from abc import ABC, abstractmethod
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from artipivot.agents.base import SubAgentDef

class Strategy(ABC):
    """子代理策略抽象 — 每种策略对应不同的图拓扑"""

    @abstractmethod
    def build(self, sub_def: SubAgentDef, tool_node: ToolNode) -> CompiledStateGraph:
        """根据 SubAgentDef 构建对应策略的子图"""
        ...

# 策略注册表
_strategies: dict[str, type[Strategy]] = {}

def register_strategy(name: str, strategy_cls: type[Strategy]) -> None:
    _strategies[name] = strategy_cls

def get_strategy(name: str) -> Strategy:
    cls = _strategies.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}")
    return cls()
```

**注册方式**: 每个策略模块在导入时自注册
```python
# strategies/react.py 底部
register_strategy("react", ReActStrategy)
```

**验证**: `pytest` — 注册 → 查询 → 未知策略抛异常

---

## Step 13: ReAct 策略

**目标**: 将 P0 的 `build_programmatic_subagent()` 重构为可配置的 ReAct 策略

**文件**:
- `src/artipivot/agents/strategies/react.py` — `ReActStrategy`

**关键实现**:

从 `programmatic.py` 提取逻辑，增加配置能力：

```python
class ReActStrategy(Strategy):
    """ReAct 策略 — think → ToolNode → think 循环"""

    def build(self, sub_def: SubAgentDef, tool_node: ToolNode) -> CompiledStateGraph:
        # 与 P0 programmatic.py 相同的拓扑：
        # START → llm_call → conditional(should_continue) → {tools, END}
        # tools → llm_call (循环)
        #
        # 新增：支持 max_iterations 中断（防止无限循环）
        ...
```

**与 P0 的关系**:
- `build_programmatic_subagent()` 内部改为调用 `ReActStrategy().build()`（向后兼容，不破坏 demo.py）
- 或者保持 `programmatic.py` 不变，让 ReAct 策略独立实现，确保 P0 测试不受影响

**验证**: 复用 P0 的 `test_agents.py` 用例 + 新增策略注册测试

---

## Step 14: CoT 策略

**目标**: 实现 Chain-of-Thought 策略 — 三节点线性链

**文件**:
- `src/artipivot/agents/strategies/cot.py` — `CoTStrategy`

**图拓扑**:

```
START → plan → execute → synthesize → END
```

**节点职责**:

| 节点 | 职责 | 说明 |
|---|---|---|
| `plan` | 规划步骤 | LLM 分析 query，输出执行计划（JSON steps） |
| `execute` | 按计划逐步执行 | 依次调用工具或 LLM，每步结果追加到 artifacts |
| `synthesize` | 总结输出 | 汇总所有步骤结果，生成最终回复 |

**与 ReAct 的区别**:
- ReAct 是动态循环（LLM 自己决定什么时候停）
- CoT 是线性流水线（先规划再执行，步骤数在 plan 阶段确定）

**SubAgentState 使用**:
- `plan` → 将计划写入 `artifacts`（后续节点读取）
- `execute` → 按计划逐步调用工具，结果追加到 `messages` 和 `artifacts`
- `synthesize` → 读取 `artifacts`，生成最终回复写入 `messages`

**配置参数** (在 SubAgentDef 中通过 strategy_config 传入):
```yaml
strategy: cot
strategy_config:
  max_plan_steps: 5        # 计划最大步骤数
  auto_execute: true       # 是否自动执行全部步骤
```

**验证**: 构建图 → 打印拓扑 → 验证三个节点和线性边

---

## Step 15: Function Calling 策略

**目标**: 实现单次 Function Calling 策略 — 无循环，一次调用即返回

**文件**:
- `src/artipivot/agents/strategies/function_calling.py` — `FunctionCallingStrategy`

**图拓扑**:

```
START → llm_call → conditional(has_tool_calls) → {tools, END}
```

**与 ReAct 的关键区别**:
- ReAct: `tools → llm_call`（循环）
- Function Calling: `tools → END`（单次，不循环）

**适用场景**: 简单的查询/转换任务，不需要多步推理

**节点职责**:

| 节点 | 职责 |
|---|---|
| `llm_call` | LLM 推理 + 决定是否调用工具 |
| `tools` | 执行工具调用（如果有） |

**验证**: 构建图 → 验证 tools 后直接到 END（无回边）

---

## Step 16: 策略引擎

**目标**: 声明式子代理定义 + 策略引擎，根据配置自动构建子图

**文件**:
- `src/artipivot/agents/declarative.py` — `DeclarativeSubAgentDef` + `build_declarative_subagent()`

**关键实现**:

```python
@dataclass
class DeclarativeSubAgentDef:
    """声明式子代理定义 — 通过配置选择策略"""
    name: str
    strategy: str                      # "react" | "cot" | "function_calling"
    tools: list[str]                   # 工具名列表
    system_prompt: str = ""
    strategy_config: dict = field(default_factory=dict)  # 策略专属参数
    # ReAct: {"max_iterations": 10}
    # CoT:   {"max_plan_steps": 5, "auto_execute": true}
    # FC:    {} (无额外参数)

def build_declarative_subagent(
    defn: DeclarativeSubAgentDef,
    tool_node: ToolNode,
) -> CompiledStateGraph:
    """策略引擎 — 根据 strategy 字段选择策略并构建子图"""
    strategy = get_strategy(defn.strategy)
    sub_def = SubAgentDef(
        name=defn.name,
        tools=defn.tools,
        system_prompt=defn.system_prompt,
    )
    # 将 strategy_config 传递给策略（策略自行读取需要的参数）
    return strategy.build(sub_def, tool_node, config=defn.strategy_config)
```

**策略接口调整**: `Strategy.build()` 签名增加可选 `config` 参数
```python
class Strategy(ABC):
    @abstractmethod
    def build(self, sub_def: SubAgentDef, tool_node: ToolNode,
              *, config: dict | None = None) -> CompiledStateGraph:
        ...
```

**验证**: 三种策略均能通过 `build_declarative_subagent()` 构建

---

## Step 17: YAML 声明式加载

**目标**: 通过 YAML 文件声明子代理配置，启动时加载

**文件**:
- `src/artipivot/agents/loader.py` — YAML → DeclarativeSubAgentDef 加载器
- `config/seed/sub_agents.yaml` — 声明式子代理配置种子文件
- `src/artipivot/models/loader.py` — 在 `load_seed_if_empty()` 中增加 sub_agents 加载

**YAML 格式**:

```yaml
# config/seed/sub_agents.yaml
#
# 声明式子代理配置 — 首次启动加载到 DocumentStore，之后通过 REST API 管理

sub_agents:
  code_writer:
    strategy: react                   # 必填，策略名
    tools:                            # 必填，工具名列表
      - web_search
      - code_exec
      - file_io
    system_prompt: "You are a professional coding assistant."
    strategy_config:                  # 可选，策略专属参数
      max_iterations: 5

  code_reviewer:
    strategy: cot
    tools:
      - web_search
      - file_io
    system_prompt: "You are a code reviewer."
    strategy_config:
      max_plan_steps: 3

  quick_query:
    strategy: function_calling
    tools:
      - web_search
    system_prompt: "Answer user questions concisely."
```

**加载流程**:

```python
# agents/loader.py
async def load_sub_agent_defs(seed_dir: str | Path = "config/seed") -> dict[str, DeclarativeSubAgentDef]:
    """从 YAML 加载子代理定义"""
    ...
```

**集成到 seed 加载**: 在 `models/loader.py` 的 `load_seed_if_empty()` 中增加 sub_agents.yaml 的处理

**验证**: 加载 YAML → 得到 DeclarativeSubAgentDef → 构建子图 → 验证策略正确

---

## Step 18: 集成验证 + 测试

**目标**: 三种策略端到端验证 + demo 更新

**文件**:
- `tests/test_strategies.py` — 策略单元测试
- `tests/test_declarative.py` — 声明式引擎 + YAML 加载测试
- `demo.py` — 增加 CoT / Function Calling 演示（可选）

**测试覆盖**:

```
tests/
├── test_strategies.py          # 新增
│   ├── TestStrategyRegistry     # 策略注册/查询/未知策略
│   ├── TestReActStrategy        # ReAct 图构建 + 拓扑验证
│   ├── TestCoTStrategy          # CoT 图构建 + 拓扑验证（plan→execute→synthesize）
│   └── TestFCStrategy           # FC 图构建 + 拓扑验证（无循环）
├── test_declarative.py         # 新增
│   ├── TestDeclarativeDef       # DeclarativeSubAgentDef 数据结构
│   ├── TestBuildDeclarative     # 三种策略均能通过引擎构建
│   └── TestSubAgentLoader       # YAML 加载 → DeclarativeSubAgentDef
└── test_agents.py              # 保持 P0 测试不变
```

**验证标准**:
1. `pytest tests/` 全部通过（P0 + P1）
2. 每种策略的图拓扑符合设计（通过节点名和边验证）
3. YAML 加载 → 策略构建 → 子图可被主图挂载

---

## 依赖关系图

```
Step 12 (策略 ABC + 注册表)
  ├─→ Step 13 (ReAct 策略)
  ├─→ Step 14 (CoT 策略)     ──┐
  └─→ Step 15 (FC 策略)      ──┤
                               │
          Step 16 (策略引擎) ←─┘
               │
          Step 17 (YAML 加载)
               │
          Step 18 (集成验证)
```

**可并行的步骤**:
- Step 13, 14, 15 互不依赖，可同时开发（都只依赖 Step 12）

---

## 验证策略

每个 Step 完成后:
1. `python -c "from artipivot.agents.strategies import ..."` — 导入检查
2. 对应单元测试通过
3. 无 import 错误

Step 18 完成后:
1. `pytest tests/` — P0 + P1 全部通过
2. 三种策略均能通过 `build_declarative_subagent()` 构建
3. YAML 配置加载 → 子图构建 → 挂载到主图 → demo 可运行

---
---

# Plan: ArtiPivot P2 — 记忆系统

## Context

P1 已完成声明式子代理策略引擎（61 个测试通过）。P2 目标是实现完整的记忆系统，从 P0 的纯内存模式升级为生产级持久化 + 上下文管理 + 长期记忆读写。

**MEMORY.md 定义了三层记忆模型**：

| 层级 | 机制 | 内容 | 当前状态 |
|------|------|------|----------|
| L1 工作记忆 | 图 State（TypedDict） | 意图、活跃子代理、中间产物 | ✅ P0 已实现 |
| L2 会话记忆 | Checkpointer (per-thread) | 对话消息历史、图快照 | ⚠️ 只有 InMemory |
| L3 长期记忆 | Store (跨 thread) | 用户画像、偏好、知识 | ❌ 未实现 |

**P2 要补齐的**：
- L2: PostgreSQL 后端 + 上下文窗口管理（摘要压缩）
- L3: Store 配置 + namespace 设计 + 记忆提取/写入节点 + 语义搜索

**设计原则**：
- 不引入 langchain 高层包，记忆管理节点用纯 langgraph 实现
- Postgres 后端可选，InMemory 后端继续工作（零依赖开发模式不受影响）
- 记忆读写集成到主图的 classify（读）和 respond（写）节点

**不改变**：
- P0/P1 已有代码和测试不变
- 图拓扑（主图和子代理图）不变
- 记忆作为新增能力，通过可选配置启用

### 进度总览

| Step | 状态 | 完成日期 | 关键产出 | 备注 |
|------|------|----------|----------|------|
| Step 19: Checkpointer/Store 工厂扩展 | ✅ | 2026-05-15 | postgres 后端 + URI 校验 | L2/L3 工厂 |
| Step 20: MemoryConfig + memory.yaml | ✅ | 2026-05-15 | EmbeddingConfig + ContextWindowConfig | 配置层 |
| Step 21: 上下文窗口管理 | ✅ | 2026-05-15 | ContextWindowManager summarize/trim | L2 压缩 |
| Step 22: 记忆提取 + 写入 | ✅ | 2026-05-15 | extract_profile/knowledge + write_memory | L3 写入 |
| Step 23: 记忆读取 + 注入 | ✅ | 2026-05-15 | build_memory_context + embedding 开关 | L3 读取 |
| Step 24: Namespace 设计 | ✅ | 2026-05-15 | profile/knowledge/preferences/agent 命名空间 | L3 隔离 |
| Step 25: 集成验证 + 测试 | ✅ | 2026-05-15 | test_memory.py 23 个测试 | 84 个测试全部通过 |

---

## Step 19: PostgreSQL Checkpointer

**目标**: 扩展 `create_checkpointer()` 支持 PostgreSQL 后端

**文件**:
- `src/artipivot/memory/checkpointer.py` — 新增 `postgres` 分支
- `src/artipivot/memory/connection.py` — 数据库连接管理（新增）

**关键实现**:

```python
# memory/checkpointer.py
def create_checkpointer(backend: str = "memory", **kwargs):
    match backend:
        case "memory":
            return InMemorySaver()
        case "postgres":
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            uri = kwargs.get("uri") or os.environ.get("DATABASE_URI")
            return AsyncPostgresSaver.from_conn_string(uri)
        case _:
            raise ValueError(f"Unsupported checkpointer backend: {backend}")

async def setup_checkpointer(checkpointer):
    """调用 setup() 初始化数据库表（仅 postgres 需要）"""
    if hasattr(checkpointer, "setup"):
        await checkpointer.setup()
```

**新增依赖**（可选，按需安装）:
```toml
[project.optional-dependencies]
postgres = ["langgraph-checkpoint-postgres>=2.0"]
```

**验证**: InMemory 分支不受影响 + Postgres 分支可实例化（需数据库或 mock）

---

## Step 20: PostgreSQL Store

**目标**: 扩展 `create_store()` 支持 PostgreSQL 后端 + 语义搜索

**文件**:
- `src/artipivot/memory/store.py` — 新增 `postgres` 分支

**关键实现**:

```python
# memory/store.py
def create_store(backend: str = "memory", **kwargs):
    match backend:
        case "memory":
            return InMemoryStore()
        case "postgres":
            from langgraph.store.postgres import PostgresStore
            uri = kwargs.get("uri") or os.environ.get("DATABASE_URI")
            index = kwargs.get("index")  # 语义搜索配置
            return PostgresStore.from_conn_string(uri, index=index)
        case _:
            raise ValueError(f"Unsupported store backend: {backend}")

async def setup_store(store):
    """调用 setup() 初始化数据库表 + 索引"""
    if hasattr(store, "setup"):
        await store.setup()
```

**语义搜索配置**:
```python
index_config = {
    "embed": "openai:text-embedding-3-small",
    "dims": 1536,
    "fields": ["$"],
}
store = create_store("postgres", index=index_config)
```

**验证**: InMemory 分支不受影响 + Postgres 分支可实例化

---

## Step 21: 上下文窗口管理

**目标**: 实现自建的上下文窗口压缩节点，替代 langchain SummarizationMiddleware

**文件**:
- `src/artipivot/memory/context_window.py` — `SummarizeNode` / `TrimNode`（新增）

**关键实现**:

```python
class ContextWindowManager:
    """上下文窗口管理 — 在图节点中调用"""

    def __init__(self, strategy: str = "summarize", trigger_tokens: int = 100000,
                 keep_messages: int = 20, summary_model: str | None = None):
        self.strategy = strategy
        self.trigger_tokens = trigger_tokens
        self.keep_messages = keep_messages
        self.summary_model = summary_model

    async def maybe_compress(self, messages: list, model) -> list | None:
        """检查是否需要压缩，返回压缩后的 messages 或 None"""
        token_count = self._estimate_tokens(messages)
        if token_count < self.trigger_tokens:
            return None  # 不需要压缩

        match self.strategy:
            case "summarize":
                return await self._summarize(messages, model)
            case "trim":
                return self._trim(messages)
            case _:
                return None

    async def _summarize(self, messages, model) -> list:
        """摘要压缩：用 summary_model 摘要旧消息，保留最近 N 条"""
        ...

    def _trim(self, messages) -> list:
        """截断：保留最近 N 条消息"""
        ...

    def _estimate_tokens(self, messages) -> int:
        """粗略估算 token 数（按 4 字符 ≈ 1 token）"""
        total = sum(len(m.content) if hasattr(m, "content") else len(str(m)) for m in messages)
        return total // 4
```

**集成方式**: 在主图的 classify 节点前加一个可选的 `context_check` 节点：
```
START → context_check → classify → ...
```
当 `context_window.strategy = "none"` 时跳过（P0 默认行为）。

**验证**: mock messages → 触发压缩 → 验证输出

---

## Step 22: 记忆提取 + 写入

**目标**: 在 respond 节点中提取长期记忆并写入 Store

**文件**:
- `src/artipivot/memory/extraction.py` — `extract_profile()` / `extract_knowledge()`（新增）

**关键实现**:

```python
async def extract_profile(messages: list, model) -> dict | None:
    """从对话中提取用户画像更新"""
    prompt = """分析以下对话，提取用户画像信息（姓名、语言偏好、技术栈等）。
    返回 JSON，如：{"name": "张三", "language": "Python", "tech_stack": ["FastAPI"]}
    如果没有新信息，返回 null。"""
    ...

async def extract_knowledge(messages: list, model) -> list[str]:
    """从对话中提取可长期保存的知识条目"""
    prompt = """分析以下对话，提取值得长期记住的知识事实。
    返回 JSON 数组，如：["用户偏好测试驱动开发", "用户的项目使用 PostgreSQL"]
    如果没有新知识，返回空数组。"""
    ...
```

**集成到 respond 节点**:
```python
async def respond(state, runtime):
    # ... 原有逻辑 ...

    # 写入长期记忆（Store 可用时）
    if runtime.store:
        profile = await extract_profile(state["messages"], runtime.context.model)
        if profile:
            await runtime.store.aput(
                (agent_id, user_id, "profile"), "main", profile
            )
        knowledge = await extract_knowledge(state["messages"], runtime.context.model)
        for k in knowledge:
            await runtime.store.aput(
                (agent_id, user_id, "knowledge"), str(uuid4()), {"fact": k}
            )
```

**验证**: mock 对话 → extract_profile → extract_knowledge → 验证输出格式

---

## Step 23: 记忆读取 + 注入

**目标**: 在 classify 节点中将长期记忆注入 prompt

**文件**:
- `src/artipivot/memory/retrieval.py` — `build_memory_context()`（新增）

**关键实现**:

```python
async def build_memory_context(store, agent_id: str, user_id: str, query: str) -> str:
    """从 Store 读取长期记忆，构建注入 prompt 的上下文字符串"""
    parts = []

    # 1. 用户画像
    profile = await store.aget((agent_id, user_id, "profile"), "main")
    if profile and profile.value:
        parts.append(f"[用户画像]\n{json.dumps(profile.value, ensure_ascii=False)}")

    # 2. 语义搜索相关知识
    try:
        results = await store.asearch(
            (agent_id, user_id, "knowledge"),
            query=query,
            limit=3,
        )
        if results:
            facts = [r.value.get("fact", "") for r in results if r.value]
            parts.append(f"[相关知识]\n" + "\n".join(f"- {f}" for f in facts))
    except Exception:
        pass  # 语义搜索不可用时静默跳过

    return "\n\n".join(parts) if parts else ""
```

**集成到 classify 节点**:
```python
async def classify(state, runtime):
    # 原有逻辑 ...
    # 新增：读取长期记忆
    memory_ctx = ""
    if runtime.store:
        memory_ctx = await build_memory_context(
            runtime.store, agent_id, user_id, state["messages"][-1].content
        )
    # 将 memory_ctx 附加到 system prompt
```

**验证**: mock Store → build_memory_context → 验证输出

---

## Step 24: Namespace 设计 + 记忆配置

**目标**: 规范化 namespace 隔离 + YAML 声明式记忆配置

**文件**:
- `src/artipivot/memory/namespace.py` — namespace 构建工具（新增）
- `src/artipivot/memory/config.py` — `MemoryConfig` 数据类（新增）

**Namespace 规范**:

```python
def profile_ns(agent_id: str, user_id: str) -> tuple[str, ...]:
    return (agent_id, user_id, "profile")

def knowledge_ns(agent_id: str, user_id: str) -> tuple[str, ...]:
    return (agent_id, user_id, "knowledge")

def preferences_ns(agent_id: str, user_id: str) -> tuple[str, ...]:
    return (agent_id, user_id, "preferences")

def agent_memory_ns(agent_id: str, user_id: str, sub_name: str) -> tuple[str, ...]:
    return (agent_id, user_id, "agent", sub_name)
```

**MemoryConfig 数据类**:

```python
@dataclass
class MemoryConfig:
    """记忆配置 — 从 YAML 加载"""
    # L2 会话记忆
    session_mode: str = "per-invocation"  # per-invocation | per-thread | stateless
    # 上下文窗口
    context_strategy: str = "none"       # summarize | trim | none
    trigger_tokens: int = 100000
    keep_messages: int = 20
    summary_model: str | None = None
    # L3 长期记忆
    long_term_read: list[str] = field(default_factory=lambda: ["profile", "knowledge"])
    long_term_write: list[str] = field(default_factory=lambda: ["knowledge"])
```

**YAML 配置扩展**（追加到 sub_agents.yaml 或 routing.yaml）:
```yaml
memory:
  session: per-invocation
  context_window:
    strategy: summarize
    trigger_tokens: 100000
    keep_messages: 20
    summary_model: claude-haiku-4-5-20251001
  long_term:
    read: [profile, knowledge]
    write: [knowledge]
```

**验证**: namespace 构建 + MemoryConfig 从 dict 构建

---

## Step 25: 集成验证 + 测试

**目标**: 全记忆层端到端验证

**文件**:
- `tests/test_memory.py` — 记忆系统单元测试（新增）
- `demo.py` — 可选增加记忆演示

**测试覆盖**:

```
tests/test_memory.py
├── TestCheckpointerFactory     # memory + postgres 分支
├── TestStoreFactory            # memory + postgres 分支
├── TestContextWindow           # SummarizeNode / TrimNode 压缩
├── TestMemoryExtraction        # extract_profile / extract_knowledge
├── TestMemoryRetrieval         # build_memory_context
├── TestNamespace               # namespace 构建函数
└── TestMemoryConfig            # MemoryConfig 数据类
```

**验证标准**:
1. `pytest tests/` — P0 + P1 + P2 全部通过
2. InMemory 模式下记忆读写正常
3. PostgreSQL 工厂可实例化（无数据库时跳过集成测试）
4. 上下文窗口压缩逻辑正确触发

---

## 依赖关系图

```
Step 19 (PG Checkpointer) ──┐
Step 20 (PG Store) ─────────┤
                             ▼
                       Step 21 (上下文窗口)
                             │
                       Step 22 (记忆提取)
                             │
                       Step 23 (记忆读取)
                             │
                       Step 24 (Namespace + 配置)
                             │
                       Step 25 (集成验证)
```

**可并行的步骤**:
- Step 19, 20 互不依赖，可同时开发
- Step 21, 22 互不依赖，可同时开发

---

## 验证策略

每个 Step 完成后:
1. `python -c "from artipivot.memory.xxx import ..."` — 导入检查
2. 对应单元测试通过
3. P0 + P1 测试不被破坏

Step 25 完成后:
1. `pytest tests/` — 全部通过
2. InMemory 模式完整可用（无需 PostgreSQL）
3. PostgreSQL 工厂可创建实例（需数据库或 mock）

---
---

# Plan: ArtiPivot P3 — 多主 Agent

## Context

P2 已完成记忆系统（86 个测试通过）。P3 目标是实现完整的多主 Agent 并行运行能力。

**当前状态**：
- `AgentGateway` 已有 `register(agent_id, graph)` + `invoke(agent_id, ...)` 基础结构
- 但 demo 只硬编码了一个 `code_agent`，所有配置在 demo.py 中手动构造
- `GraphFactory` 接受 `sub_agent_nodes` 参数但不读取 routing 配置
- 没有统一的 Agent 定义结构

**P3 要补齐的**：
1. AgentDef — 统一的 Agent 定义数据结构（模型、路由、子代理、工具、记忆策略）
2. AgentRegistry — 多 Agent 注册表，自动构建 + 生命周期管理
3. GraphFactory 增强 — 根据 AgentDef + routing 配置自动构建完整主图
4. YAML 多 Agent 声明 — 一个配置文件定义多个 Agent 的完整拓扑
5. 隔离验证 — State / 会话记忆 / 长期记忆 / 路由 / 工具权限完全隔离

**不改变**：
- P0/P1/P2 已有代码和测试不变
- `AgentGateway` 接口不变（register + invoke + stream）
- 子代理策略系统不变

### 进度总览

| Step | 状态 | 完成日期 | 关键产出 | 备注 |
|------|------|----------|----------|------|
| Step 26: AgentDef 数据结构 | ✅ | 2026-05-14 | `AgentDef` dataclass | 统一 Agent 定义 |
| Step 27: AgentRegistry | ✅ | 2026-05-14 | `AgentRegistry` 注册 + 自动构建 | 多 Agent 生命周期 |
| Step 28: GraphFactory 增强 | ✅ | 2026-05-14 | routing 配置验证 | 从配置构建图 |
| Step 29: YAML 多 Agent 声明 | ✅ | 2026-05-14 | `agents.yaml` + loader | 声明式多 Agent 配置 |
| Step 30: 隔离验证 + 测试 | ✅ | 2026-05-14 | 21 个多 Agent 隔离测试 | 107 tests 全部通过 |

---

## Step 26: AgentDef 数据结构

**目标**: 定义统一的 Agent 描述结构，包含构建完整主图所需的一切信息

**文件**:
- `src/artipivot/gateway/agent_def.py`（新增）

**关键实现**:

```python
@dataclass
class AgentDef:
    """完整的 Agent 定义 — 包含构建主图所需的所有信息"""
    agent_id: str

    # 模型
    model: dict  # {"provider": ..., "name": ...}

    # 路由
    confidence_threshold: float = 0.7
    intent_map: dict[str, str] = field(default_factory=dict)
    # {"code_write": "code_writer", "debug": "code_writer"}

    # 子代理
    sub_agents: dict[str, SubAgentDef] = field(default_factory=dict)
    # {"code_writer": SubAgentDef(...), ...}

    # 或使用声明式子代理定义
    declarative_sub_agents: dict[str, DeclarativeSubAgentDef] = field(default_factory=dict)

    # 工具
    tools: list[str] = field(default_factory=list)
    # 全局工具白名单

    # 提示词
    prompts: dict[str, str] = field(default_factory=dict)
    # {"classify": "...", "respond": "...", "code_writer": "..."}

    # 记忆策略
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)
```

**验证**: 数据结构创建 + from_dict / to_dict

---

## Step 27: AgentRegistry

**目标**: 多 Agent 注册表 — 管理多个 AgentDef 的构建、注册、查询

**文件**:
- `src/artipivot/gateway/registry.py`（新增）

**关键实现**:

```python
class AgentRegistry:
    """多 Agent 注册表 — 根据 AgentDef 自动构建并注册到 Gateway"""

    def __init__(
        self,
        gateway: AgentGateway,
        graph_factory: GraphFactory,
        tool_registry: ToolRegistry,
    ):
        self._gateway = gateway
        self._factory = graph_factory
        self._tools = tool_registry
        self._defs: dict[str, AgentDef] = {}

    def register_def(self, agent_def: AgentDef) -> None:
        """注册 Agent 定义并自动构建主图"""
        # 1. 构建子代理
        sub_agent_nodes = self._build_sub_agents(agent_def)

        # 2. 构建主图
        graph = self._factory.build(
            agent_id=agent_def.agent_id,
            sub_agent_nodes=sub_agent_nodes,
        )

        # 3. 注册到 Gateway
        self._gateway.register(agent_def.agent_id, graph)
        self._defs[agent_def.agent_id] = agent_def

    def get_def(self, agent_id: str) -> AgentDef | None:
        return self._defs.get(agent_id)

    def list_agents(self) -> list[str]:
        return list(self._defs)

    def _build_sub_agents(self, agent_def: AgentDef) -> dict[str, CompiledStateGraph]:
        """根据 AgentDef 构建所有子代理图"""
        result = {}
        for name, sub_def in agent_def.sub_agents.items():
            tool_node = self._tools.get_tool_node(sub_def.tools)
            result[name] = build_programmatic_subagent(sub_def, tool_node)

        for name, defn in agent_def.declarative_sub_agents.items():
            tool_node = self._tools.get_tool_node(defn.tools)
            result[name] = build_declarative_subagent(defn, tool_node)

        return result
```

**验证**: 注册多个 AgentDef → list_agents → get_def

---

## Step 28: GraphFactory 增强

**目标**: GraphFactory 根据 routing 配置自动验证子代理挂载，无需手动传 sub_agent_nodes 名称

**文件**:
- `src/artipivot/graph/factory.py`（修改）

**当前问题**:
- `build_root_graph()` 不验证 sub_agent_nodes 是否和 routing config 的 intent_map 匹配
- 如果 routing 配置指向一个不存在的子代理，运行时才会报错

**改进**:

```python
class GraphFactory:
    def build(
        self,
        agent_id: str,
        sub_agent_nodes: dict[str, object] | None = None,
        checkpointer=None,
        store=None,
    ) -> CompiledStateGraph:
        # 验证：routing config 的 intent_map 值 必须在 sub_agent_nodes 中
        if sub_agent_nodes:
            self._validate_routing(agent_id, sub_agent_nodes)

        builder = build_root_graph(...)
        return builder.compile(checkpointer=checkpointer, store=store)

    def _validate_routing(self, agent_id, sub_agent_nodes):
        """验证 routing 配置和子代理节点的一致性"""
        intent_map = self._config_center.routing.get_intent_map(agent_id)
        for intent, sub_name in intent_map.items():
            if sub_name not in sub_agent_nodes:
                raise ValueError(
                    f"Routing config for '{agent_id}' maps intent '{intent}' "
                    f"to sub-agent '{sub_name}', but no sub-agent graph provided. "
                    f"Available: {list(sub_agent_nodes)}"
                )
```

**验证**: 路由配置指向不存在的子代理 → 构建时报错

---

## Step 29: YAML 多 Agent 声明

**目标**: 通过 YAML 文件声明多个 Agent 的完整定义

**文件**:
- `src/artipivot/gateway/loader.py`（新增）— YAML → AgentDef
- `config/seed/agents.yaml`（新增）— 多 Agent 配置种子文件

**YAML 格式**:

```yaml
# config/seed/agents.yaml
#
# 多 Agent 声明配置 — 定义每个 Agent 的模型、路由、子代理、工具
# 首次启动加载，之后通过 REST API 管理

agents:
  code_agent:
    model:
      provider: anthropic
      name: claude-sonnet-4-6
    routing:
      confidence_threshold: 0.7
      intents:
        code_write: code_writer
        code_review: code_writer
        debug: code_writer
    sub_agents:
      code_writer:
        strategy: react
        tools: [web_search, code_exec, file_io]
        system_prompt: "You are a professional coding assistant."
        strategy_config:
          max_iterations: 5
    prompts:
      classify: "Classify the user message into one of: {intents}."
      respond: "Based on the sub-agent result, compose a helpful response."

  research_agent:
    model:
      provider: openai
      name: gpt-4o
    routing:
      confidence_threshold: 0.6
      intents:
        search: researcher
        summarize: researcher
    sub_agents:
      researcher:
        strategy: cot
        tools: [web_search]
        system_prompt: "You are a research assistant."
        strategy_config:
          max_plan_steps: 3
```

**加载逻辑**:

```python
# gateway/loader.py
def load_agent_defs(seed_dir: str | Path = "config/seed") -> dict[str, AgentDef]:
    """从 agents.yaml 加载多 Agent 定义"""
    ...
```

**验证**: 加载 YAML → 得到多个 AgentDef → 注册到 AgentRegistry → 查询验证

---

## Step 30: 隔离验证 + 测试

**目标**: 多 Agent 并行运行的隔离验证 + demo 更新

**文件**:
- `tests/test_multi_agent.py`（新增）— 多 Agent 隔离测试
- `demo.py` — 更新为多 Agent 演示

**测试覆盖**:

```
tests/test_multi_agent.py
├── TestAgentDef              # AgentDef 数据结构
├── TestAgentRegistry         # 注册多个 Agent + list/get
├── TestGraphFactoryValidate  # routing 配置验证
├── TestAgentLoader           # YAML 加载多 Agent
└── TestMultiAgentIsolation   # 隔离验证
    ├── test_state_isolation       # 不同 Agent 的 State 互不干扰
    ├── test_thread_id_isolation   # thread_id 前缀隔离
    ├── test_namespace_isolation   # Store namespace 隔离
    └── test_model_isolation      # 各 Agent 可用不同模型
```

**验证标准**:
1. `pytest tests/` — P0 + P1 + P2 + P3 全部通过
2. 多 Agent 可并行注册、各自 invoke 正常
3. 隔离验证全部通过（State / 会话 / 记忆 / 模型）
4. YAML 加载 → 多 Agent 注册 → Gateway 分发 → 正确路由

---

## 依赖关系图

```
Step 26 (AgentDef)
  │
  ├─→ Step 27 (AgentRegistry)
  │         │
  │         ├─→ Step 28 (GraphFactory 增强)
  │         │
  │         └─→ Step 29 (YAML 声明)
  │                   │
  └───────────────────┤
                      ▼
               Step 30 (集成验证)
```

**可并行的步骤**:
- Step 28, 29 可并行开发（都依赖 Step 27）

---

## 验证策略

每个 Step 完成后:
1. 导入检查通过
2. 对应单元测试通过
3. P0 + P1 + P2 测试不被破坏

Step 30 完成后:
1. `pytest tests/` — 全部通过
2. 多 Agent YAML 配置 → 自动构建 → Gateway 分发 → 正确响应
3. 两个 Agent 使用不同模型、不同子代理、不同工具，互不干扰
