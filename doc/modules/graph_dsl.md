# Graph DSL — YAML 驱动的任意图拓扑

## 概述

子代理默认提供两种固定策略（ReAct / Function Calling），覆盖常见场景。但某些流程需要自定义拓扑，例如"搜索 + 代码执行并行 → 合并结果 → 回复"。Graph DSL 让用户在 YAML 中定义任意图结构，无需编写 Python 代码。

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

        merge:
          type: transform
          handler: merge_results

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
          to: merge
        - from: execute
          to: merge
        - from: merge
          to: respond
        - from: respond
          to: review
        - from: review
          to: END
```

---

## 节点类型

| type | 必填字段 | 说明 |
|------|---------|------|
| `llm` | `system_prompt`（可选） | LLM 调用，从 runtime context 获取 model，或通过 `model` 字段覆盖 |
| `tool` | `tool` | 单工具节点，从 ToolRegistry 获取 |
| `tools` | `tools` | ToolNode（多工具），从 ToolRegistry 获取 |
| `transform` | `handler` | 数据变换，从 TransformRegistry 获取。可配 `input_key`/`output_key`（默认 `"metadata"`） |
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
    to: merge
  - from: execute
    to: merge
```

### 条件边（三种机制）

**1. 字段映射** — 读 state 字段值，映射到目标节点：

```yaml
- from: classify
  to: [search, fallback]
  condition:
    field: intent
    mapping:
      search_query: search
      _: fallback              # _ 是默认兜底
```

**2. 内置函数** — 常见模式：

```yaml
- from: llm_call
  to: [tools, END]
  condition:
    builtin: has_tool_calls
```

内置函数：`has_tool_calls`（最后消息有 tool_calls → 第一个目标）、`no_tool_calls`（无 tool_calls → 第一个目标）。

**3. Transform 路由** — 复用 TransformRegistry，支持热加载：

```yaml
- from: classify
  to: [search, fallback]
  condition:
    transform: classify_intent
```

路由 Transform 接收 state dict，返回目标节点名（str，必须是 targets 之一）。必须是同步函数。

---

## DSL 增强（P0-P3）

### P0 — Human-in-the-loop

任意节点可暂停等人工审批，审批后恢复执行。依赖 LangGraph 原生 `interrupt_before` / `interrupt_after` + Checkpointer。

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

### P1 — 循环保护 max_iterations

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

### P2 — 节点级 retry

任意节点可配置重试策略，失败后自动重试。使用 `RetryPolicy`（指数退避 + 抖动）。

```yaml
nodes:
  call_api:
    type: tool
    tool: web_search
    retry:
      max_attempts: 3        # 总尝试次数（含首次）
      delay_seconds: 1       # 初始延迟（秒），指数递增
```

**行为：**
- 首次失败后延迟重试，最多 `max_attempts` 次
- 延迟按指数递增，带随机抖动
- 全部失败后抛出 `RetryExhaustedError`

### P3 — 节点级多模型

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

**模型解析优先级：** 节点级 `model` > runtime context 中的默认模型。

当指定了 `model` 字段且 `build_dsl_graph()` 传入了 `model_provider` 时，直接通过 `ModelProvider._factories` 创建模型实例。

---

## 可视化调试（P4）

### Mermaid 流程图

从 GraphDef 生成 Mermaid 流程图字符串，可在 Markdown、文档或 Mermaid Live Editor 中渲染。

```python
from artipivot.graph.visual import graph_to_mermaid

mermaid = graph_to_mermaid(graph_def)
print(mermaid)
```

**节点形状：**

| 节点类型 | Mermaid 形状 | 视觉效果 |
|---------|-------------|---------|
| `llm` | `([ ])` stadium | 圆角矩形 |
| `tool` / `tools` | `[[ ]]` subroutine | 双线矩形 |
| `transform` | `{{ }}` hexagon | 六边形 |
| `sub_agent` | `[ ]` rectangle | 矩形 |

**条件边**使用虚线箭头 `-.->` 并标注条件类型。

### Admin API

```
GET /admin/graph/{agent_id}/mermaid      # 返回所有 DSL 子代理的 Mermaid 文本
GET /admin/graph/{agent_id}/structure    # 返回 DSL 子代理的结构 JSON
```

---

## 核心函数

`src/artipivot/graph/dsl.py`

| 函数 | 说明 |
|------|------|
| `parse_graph_def(name, graph_cfg)` | 解析 YAML dict → GraphDef，含语法校验 |
| `validate_graph_def(graph_def, *)` | 运行时校验（工具/transform/子 agent 是否存在），返回 warning 列表 |
| `build_dsl_graph(graph_def, *)` | 构建 CompiledStateGraph，创建节点 + 连边 + 编译。支持 checkpointer、model_provider |

`src/artipivot/graph/visual.py`

| 函数 | 说明 |
|------|------|
| `graph_to_mermaid(graph_def)` | 从 GraphDef 生成 Mermaid 流程图字符串 |

---

## 数据模型

```python
@dataclass
class NodeDef:        # 节点定义（含 interrupt、retry、model）
@dataclass
class EdgeDef:        # 边定义（固定 / 条件）
@dataclass
class ConditionDef:   # 条件路由（字段映射 / 内置 / Transform）
@dataclass
class GraphDef:       # 完整图定义（含 max_iterations）
```

---

## 集成点

### agents/loader.py

`load_sub_agent_defs()` 检测 `graph:` 键。有则调 `parse_graph_def()`，无则走现有 `DeclarativeSubAgentDef`。返回类型变为 `dict[str, DeclarativeSubAgentDef | GraphDef]`。

### gateway/agent_def.py

`AgentDef` 新增 `graph_sub_agents: dict[str, GraphDef]` 字段。`from_dict()` 自动检测 `graph:` 键。

### gateway/registry.py

`_build_sub_agents()` 新增分枝：`GraphDef` → `build_dsl_graph()`。`compiled_sub_agents=result` 允许 `sub_agent` 类型节点引用同一定义中更早构建的子代理。传 `checkpointer` 和 `model_provider` 支持 HITL 和多模型。

### plugins/rebuilder.py

`GraphRebuilder.__init__` 新增 `transform_registry` 参数。`_build_sub_agents()` 检测 manifest 中的 `graph:` 键，走 DSL 构建。

### api/deps.py

新增 `get_agent_registry()` 访问器，供 Admin API 查询 GraphDef。

### api/admin.py

新增 `/admin/graph/{agent_id}/mermaid` 和 `/admin/graph/{agent_id}/structure` 端点。

---

## 热加载

DSL 图中的 `transform` 节点复用 TransformRegistry 的热加载机制 — 替换函数后下次执行自动生效，无需重建图。

发布含 `graph:` 键的插件时，GraphRebuilder 重建图（与 strategy 插件行为一致）。

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `graph/dsl.py` | 数据模型、解析、校验、构建（含 HITL、循环保护、重试、多模型） |
| `graph/visual.py` | Mermaid 流程图生成 |
| `graph/state.py` | SubAgentState（含 metadata 字段） |
| `agents/loader.py` | YAML 加载（检测 graph/strategy 键） |
| `gateway/agent_def.py` | AgentDef（含 graph_sub_agents） |
| `gateway/registry.py` | AgentRegistry（构建 DSL 图，传 checkpointer 和 model_provider） |
| `plugins/rebuilder.py` | GraphRebuilder（插件热重建） |
| `quickstart.py` | 一行代码启动（P2） |
| `tests/test_graph_dsl.py` | 48 个测试（解析、校验、构建、条件路由、HITL、循环保护、重试、多模型） |
| `tests/test_visual.py` | 6 个测试（Mermaid 生成：线性/并行/条件/节点形状） |
