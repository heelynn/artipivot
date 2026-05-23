# Graph DSL -- YAML 驱动的任意图拓扑

## 概述

子代理默认提供两种固定策略（ReAct / Function Calling），覆盖常见场景。但某些流程需要自定义拓扑，例如"搜索 + 代码执行并行 -> 合并结果 -> 回复"。Graph DSL 让用户在 YAML 中定义任意图结构，无需编写 Python 代码。

**设计原则：** 有 `graph:` 键走 DSL，有 `strategy:` 键走现有策略，向后兼容。

---

## YAML 语法

```yaml
# config/seed/sub_agents.yaml
sub_agents:
  # 现有策略方式（不变）
  code_writer:
    strategy: react
    tools: [web_search, code_exec]
    system_prompt: "You are a coding assistant."

  # DSL 方式
  research_and_code:
    graph:
      max_iterations: 15
      nodes:
        search:
          type: tool
          tool: web_search
          retry: { max_attempts: 3, delay_seconds: 1 }

        execute:
          type: tool
          tool: code_exec

        respond:
          type: llm
          system_prompt: "Based on the results, compose a response."
          model: { provider: anthropic, name: claude-sonnet-4-6 }

        review:
          type: llm
          system_prompt: "Review the proposed changes"
          interrupt: before

      edges:
        - from: START
          to: search
        - from: START
          to: execute
        - from: search
          to: respond
        - from: execute
          to: respond
        - from: respond
          to: review
        - from: review
          to: END
```

---

## 节点类型

合法节点类型由 `VALID_NODE_TYPES = frozenset({"llm", "tool", "tools", "sub_agent"})` 定义。

| type | 必填字段 | 说明 |
|------|---------|------|
| `llm` | `system_prompt`（可选） | LLM 调用，从 runtime context 获取 model，或通过 `model` 字段覆盖。可绑定工具（`tools` 字段） |
| `tool` | `tool` | 单工具节点，从 ToolRegistry 获取 |
| `tools` | `tools` | ToolNode（多工具），通过 `tool_registry.get_tool_node()` 创建 |
| `sub_agent` | `ref` | 嵌套子 agent，引用另一个已编译图 |

---

## 边定义

### 固定边

```yaml
edges:
  - from: START
    to: step1
  - from: step1
    to: step2
  - from: step2
    to: END
```

### 扇出（多个目标）

```yaml
edges:
  - from: START
    targets: [search, execute]   # 同时触发两个节点
  - from: search
    to: respond
  - from: execute
    to: respond
```

`to` 字段也可以是列表形式：

```yaml
edges:
  - from: START
    to: [search, execute]       # 等同于 targets
```

### 条件边（两种机制）

**1. 字段映射** -- 读 state 字段值，映射到目标节点：

```yaml
- from: classify
  to: [search, fallback]
  condition:
    field: intent
    mapping:
      search_query: search
      _: fallback              # _ 是默认兜底
```

**2. 内置函数** -- 常见模式：

```yaml
- from: llm_call
  to: [tools, END]
  condition:
    builtin: has_tool_calls
```

内置函数：
- `has_tool_calls` -- 最后消息有 tool_calls 时返回第一个目标，否则返回第二个目标（默认 END）
- `no_tool_calls` -- 最后消息无 tool_calls 时返回第一个目标，有 tool_calls 时返回第二个目标（默认 END）

---

## DSL 增强特性

### Human-in-the-loop

任意节点可暂停等人工审批，审批后恢复执行。依赖 LangGraph 原生 `interrupt_before` / `interrupt_after` + Checkpointer。

合法值由 `_VALID_INTERRUPTS = frozenset({"before", "after"})` 定义。

```yaml
nodes:
  validate:
    type: llm
    system_prompt: "Review the proposed changes"
    interrupt: before        # "before" | "after"
```

**运行时流程：**

1. 图执行到 `validate` 节点前暂停
2. 调用方通过 `graph.get_state(config)` 获取当前状态
3. 人工审批后调用 `graph.invoke(None, config)` 恢复执行

**前提：** 必须配置 Checkpointer（如 `MemorySaver`），否则 interrupt 无效。

### 循环保护 max_iterations

DSL 图中循环路径有最大迭代保护，防止无限循环。

```yaml
graph:
  max_iterations: 15         # 图级，限制最大迭代次数
  nodes: ...
  edges: ...
```

**实现：** 编译后的图在 `graph.max_iterations` 属性中存储该值，调用方在 config 中注入 `recursion_limit`：

```python
config = {"recursion_limit": graph.max_iterations}
await graph.ainvoke(state, config)
```

超过限制后 LangGraph 抛出 `GraphRecursionError`。

**校验：** `max_iterations` 必须是正整数，否则 `parse_graph_def()` 抛出 `ValueError`。

### 节点级 retry

任意节点可配置重试策略，失败后自动重试。

```yaml
nodes:
  call_api:
    type: tool
    tool: web_search
    retry:
      max_attempts: 3        # 总尝试次数（含首次），必填
      delay_seconds: 1       # 初始延迟（秒），指数递增，默认 1.0
```

**行为：**
- 首次失败后延迟重试，最多 `max_attempts` 次
- 延迟按指数递增，带随机抖动
- 内部通过 `RetryPolicy(max_retries=max_attempts-1, base_delay=delay_seconds)` 实现
- 重试包装函数命名为 `retry:{node_name}`
- `sub_agent` 类型节点不包装 retry

**校验：** `retry` 字典中必须包含 `max_attempts`，否则 `parse_graph_def()` 抛出 `ValueError`。

### 节点级多模型

LLM 节点可指定独立的模型配置，覆盖默认模型。支持同一图中不同节点使用不同模型。

```yaml
nodes:
  classify:
    type: llm
    model: { provider: anthropic, name: claude-haiku-4-5 }
  generate:
    type: llm
    model: { provider: openai, name: gpt-4o }
```

**模型解析优先级：** 节点级 `model` + `model_provider` > runtime context 中的默认模型。

当指定了 `model` 字段且 `build_dsl_graph()` 传入了 `model_provider` 时，通过 `ModelConfig(**model_cfg)` 构建配置，再从 `model_provider._factories[cfg.provider]` 获取工厂函数创建模型实例。

---

## 可视化调试

### Mermaid 流程图

从 GraphDef 生成 Mermaid 流程图字符串，可在 Markdown、文档或 Mermaid Live Editor 中渲染。

```python
from artipivot.graph.visual import graph_to_mermaid

mermaid = graph_to_mermaid(graph_def)
print(mermaid)
```

输出为 `flowchart TD` 格式，节点声明带形状修饰，条件边使用虚线箭头。

**节点形状：**

| 节点类型 | Mermaid 形状 | 视觉效果 |
|---------|-------------|---------|
| `llm` | `([ ])` stadium | 圆角矩形 |
| `tool` / `tools` | `[[ ]]` subroutine | 双线矩形 |
| `sub_agent` | `[ ]` rectangle | 矩形 |

**节点标签：** 格式为 `{类型前缀}: {节点名}`，如 `LLM: respond`、`Tool: search`、`SubAgent: planner`。

**条件边标签：** 字段映射显示为 `field:{字段名}`，内置函数显示为 `fn:{函数名}`，其他显示为 `cond`。

### Admin API

端点定义在 `api/admin.py`，不在 graph 模块内。

```
GET /admin/graph/{agent_id}/mermaid      # 返回所有 DSL 子代理的 Mermaid 文本
GET /admin/graph/{agent_id}/structure    # 返回 DSL 子代理的结构 JSON
```

两个端点都从 `AgentRegistry` 获取 `AgentDef`，然后读取其 `graph_sub_agents` 字段。如果 agent 不存在或没有 DSL 图，返回 404。

---

## 核心函数

`src/artipivot/graph/dsl.py`

| 函数 | 签名 | 说明 |
|------|------|------|
| `parse_graph_def` | `(name: str, graph_cfg: dict) -> GraphDef` | 解析 YAML dict 为 GraphDef。校验节点类型、边引用、条件目标、interrupt 值、retry 必填字段、max_iterations 正整数 |
| `validate_graph_def` | `(graph_def, *, tool_registry, compiled_sub_agents) -> list[str]` | 运行时校验（工具/子 agent 是否存在），返回 warning 列表。不抛异常 |
| `build_dsl_graph` | `(graph_def, *, tool_registry, compiled_sub_agents, checkpointer, model_provider) -> CompiledStateGraph` | 构建 CompiledStateGraph：创建节点 + 连边 + 编译。支持 interrupt、checkpointer、max_iterations 属性 |

**内部节点工厂：**

| 函数 | 说明 |
|------|------|
| `_build_node` | 根据 NodeDef.type 分发到具体工厂，retry 在此处包装 |
| `_make_llm_node` | 创建异步 LLM 调用节点，支持 system_prompt、工具绑定、模型覆盖 |
| `_make_tool_node` | 创建单工具执行节点，从消息中取最后一个 tool_call 并执行 |
| `_make_tools_node` | 通过 `tool_registry.get_tool_node()` 创建 ToolNode |
| `_make_sub_agent_node` | 返回已编译子代理图，直接用作节点（不包装 retry） |
| `_wrap_with_retry` | 用 `RetryPolicy` 包装节点函数，实现指数退避重试 |

`src/artipivot/graph/visual.py`

| 函数 | 说明 |
|------|------|
| `graph_to_mermaid` | 从 GraphDef 生成 Mermaid flowchart TD 字符串 |

---

## 数据模型

```python
@dataclass
class NodeDef:
    """节点定义"""
    name: str
    type: str                          # "llm" | "tool" | "tools" | "sub_agent"
    tool: str | None = None            # type="tool"
    tools: list[str] | None = None     # type="tools" 或 type="llm"（工具绑定）
    system_prompt: str = ""            # type="llm"
    ref: str | None = None             # type="sub_agent"
    interrupt: str | None = None       # "before" | "after" | None
    retry: dict | None = None          # {"max_attempts": int, "delay_seconds": float}
    model: dict | None = None          # {"provider": str, "name": str}

@dataclass
class ConditionDef:
    """条件路由定义"""
    field: str | None = None           # 字段映射：字段名
    mapping: dict[str, str] | None = None  # 字段映射：值 -> 目标节点
    builtin: str | None = None         # 内置函数名

    def make_router(self, *, targets: list[str]) -> Callable  # 构建路由函数
    def _field_mapping_router(self, targets) -> Callable       # 字段映射路由
    def _builtin_router(self, name, targets) -> Callable       # 内置函数路由

@dataclass
class EdgeDef:
    """边定义"""
    source: str
    target: str | None = None          # 固定边：单目标
    targets: list[str] | None = None   # 条件边或扇出：多目标
    condition: ConditionDef | None = None

@dataclass
class GraphDef:
    """完整图定义"""
    name: str
    nodes: dict[str, NodeDef]
    edges: list[EdgeDef]
    max_iterations: int | None = None
```

---

## 解析与校验流程

### parse_graph_def 详细校验

1. `nodes` 必须存在且非空
2. 每个节点的 `type` 必须在 `VALID_NODE_TYPES` 中（`llm`/`tool`/`tools`/`sub_agent`）
3. `interrupt` 值必须在 `_VALID_INTERRUPTS` 中（`before`/`after`），或为 `None`
4. `retry` 字典必须包含 `max_attempts` 键
5. 边的 `from` 必填
6. 条件边必须有 `targets`（或列表形式的 `to`）
7. 固定边必须有 `to`
8. 所有目标节点名必须是已定义节点或 `START`/`END`
9. 条件定义必须包含 `field`+`mapping` 或 `builtin` 之一
10. `max_iterations` 必须是正整数

### validate_graph_def 运行时校验

- `tool` 类型节点：检查工具是否在 ToolRegistry 中
- `tools` 类型节点：逐个检查工具是否在 ToolRegistry 中
- `sub_agent` 类型节点：检查 ref 是否在 compiled_sub_agents 中
- 返回 `list[str]`（警告列表），不抛异常

---

## 集成点

### agents/loader.py

`load_sub_agent_defs()` 检测 `graph:` 键。有则调 `parse_graph_def()`，无则走现有 `DeclarativeSubAgentDef`。

### gateway/agent_def.py

`AgentDef` 新增 `graph_sub_agents: dict[str, GraphDef]` 字段。`from_dict()` 自动检测 `graph:` 键。

### gateway/registry.py

`_build_sub_agents()` 新增分支：`GraphDef` 走 `build_dsl_graph()`。`compiled_sub_agents=result` 允许 `sub_agent` 类型节点引用同一定义中更早构建的子代理。传 `checkpointer` 和 `model_provider` 支持 HITL 和多模型。

### api/admin.py

新增 `GET /admin/graph/{agent_id}/mermaid` 和 `GET /admin/graph/{agent_id}/structure` 端点。从 `AgentRegistry` 查询 `AgentDef.graph_sub_agents`。

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `graph/dsl.py` | 数据模型、解析、校验、构建（含 HITL、循环保护、重试、多模型） |
| `graph/visual.py` | Mermaid 流程图生成 |
| `graph/state.py` | SubAgentState（DSL 图的运行时状态） |
| `api/admin.py` | Admin API 端点（Mermaid 和 structure） |
