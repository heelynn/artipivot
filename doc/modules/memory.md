# 记忆系统（Memory）

## 架构

```mermaid
flowchart TD
    subgraph Memory["三层记忆模型"]
        direction TB
        L1["L1 工作记忆<br/>图 State（TypedDict）<br/>意图、活跃子代理、中间产物"]
        L2["L2 会话记忆<br/>Checkpointer (per-thread)<br/>对话消息历史、图快照"]
        L3["L3 长期记忆<br/>Store (跨 thread)<br/>用户画像、偏好、知识"]
    end

    L1 --> L2
    L2 --> L3

    subgraph ContextWindow["上下文窗口管理"]
        None["none — 不压缩"]
        Summarize["summarize — LLM 摘要"]
        Trim["trim — 截断保留最近 N 条"]
    end

    L2 --> |"超阈值"| ContextWindow

    subgraph L3Ops["L3 读写"]
        Extract["记忆提取<br/>extract_profile()<br/>extract_knowledge()"]
        Retrieve["记忆读取<br/>build_memory_context()"]
        Write["记忆写入<br/>write_memory()"]
    end

    L3 --> Extract
    L3 --> Retrieve
    L3 --> Write

    subgraph Namespace["Namespace 隔离"]
        Profile["(agent_id, user_id, profile)"]
        Knowledge["(agent_id, user_id, knowledge)"]
        Prefs["(agent_id, user_id, preferences)"]
        AgentMem["(agent_id, user_id, agent, sub_name)"]
    end

    L3 --> Namespace

    subgraph Backends["可插拔后端"]
        InMem["InMemorySaver / InMemoryStore"]
        PG["PostgresSaver / PostgresStore"]
        Custom["自定义后端<br/>register_*_backend()"]
    end

    L2 --- Backends
    L3 --- Backends
```

## 三层记忆

| 层级 | 机制 | 内容 |
|------|------|------|
| L1 | 图 State | 意图、活跃子代理、中间产物 |
| L2 | Checkpointer (per-thread) | 对话消息历史、图快照 |
| L3 | Store (跨 thread) | 用户画像、偏好、知识 |

## 可插拔后端

```python
from artipivot.memory.checkpointer import create_checkpointer, register_checkpointer_backend
from artipivot.memory.store import create_store, register_store_backend

cp = create_checkpointer("memory")
store = create_store("memory")

# 自定义后端
register_store_backend("mongodb", lambda **kw: MongoStore(kw["uri"]))
store = create_store("mongodb", uri="mongodb://localhost:27017")
```

## Namespace 隔离

```python
from artipivot.memory.namespace import profile_ns, knowledge_ns, agent_memory_ns

profile_ns("code_agent", "user_123")              # ("code_agent", "user_123", "profile")
agent_memory_ns("code_agent", "user_123", "writer") # ("code_agent", "user_123", "agent", "writer")
```

## 记忆提取 + 写入

```python
from artipivot.memory.extraction import write_memory
await write_memory(store, agent_id, user_id, messages, model)
```

## 记忆读取 + 注入

```python
from artipivot.memory.retrieval import build_memory_context
context = await build_memory_context(store, agent_id, user_id, query)
```

## 上下文窗口管理

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `none` | 不压缩（默认） | 短对话 |
| `summarize` | LLM 摘要旧消息 | 长对话（推荐） |
| `trim` | 截断保留最近 N 条 | 不想调 LLM |

## 配置

```yaml
# config/seed/memory.yaml
memory:
  embedding:
    enabled: false
  context_window:
    strategy: none
    trigger_tokens: 100000
    keep_messages: 20
```
