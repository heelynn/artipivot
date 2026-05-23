# 记忆系统（Memory）

记忆模块负责多层级记忆的持久化、提取、检索和上下文窗口管理。

## 模块结构

| 文件 | 职责 |
|------|------|
| `config.py` | 配置数据结构（`MemoryConfig` 及全部子配置） |
| `checkpointer.py` | Checkpointer 工厂（已委托至统一存储注册表，保留向后兼容接口） |
| `store.py` | Store 工厂（已委托至统一存储注册表，保留向后兼容接口） |
| `namespace.py` | Namespace 构造函数（多 Agent 隔离） |
| `extraction.py` | 从对话中提取用户画像和知识事实，写入 Store |
| `retrieval.py` | 从 Store 读取记忆并格式化为字符串 |
| `context_window.py` | 上下文窗口管理（压缩/截断/自定义策略） |

---

## 三层记忆模型

```mermaid
flowchart TB
    subgraph L1["L1 工作记忆 - 图 State"]
        direction LR
        S1["ArtiPivotState"]
        S2["SubAgentState"]
    end
    subgraph L2["L2 会话记忆 - Checkpointer"]
        direction LR
        C1["per-thread 持久化"]
        C2["消息历史 + 图快照"]
    end
    subgraph L3["L3 长期记忆 - Store"]
        direction LR
        K1["用户画像"]
        K2["知识事实"]
        K3["跨 thread 持久化"]
    end
    L1 --> L2
    L2 --> L3
```

| 层级 | 实现 | 作用域 | 后端 |
|------|------|--------|------|
| L1 | `ArtiPivotState` / `SubAgentState` | 单次图执行 | 内存 |
| L2 | `create_checkpointer()` | per-thread | Memory / PostgreSQL |
| L3 | `create_store()` | 跨 thread | Memory / PostgreSQL |

---

## 配置数据结构（config.py）

所有配置均为 dataclass，可通过 `MemoryConfig.from_dict()` 从字典构建。配置层级如下：

```mermaid
flowchart TD
    MC["MemoryConfig"] --> EC["EmbeddingConfig"]
    MC --> CWC["ContextWindowConfig"]
    MC --> EXC["ExtractionConfig"]
    MC --> RC["RetentionConfig"]

    CWC --> SC["SummarizeConfig"]
    CWC --> TC["TrimConfig"]

    EXC --> PEC["ProfileExtractionConfig"]
    EXC --> KEC["KnowledgeExtractionConfig"]
```

### EmbeddingConfig（从 `storage.search` 导入）

实际的 embedding 由 store 后端处理（例如 PostgresStore + pgvector）。此配置仅控制是否启用 store 的语义搜索能力。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `False` | 是否使用 store 的 `asearch` 进行语义检索 |

### SummarizeConfig

summarize 压缩策略的专用配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | `str \| None` | `None` | 专用摘要模型，`None` 表示使用 Agent 当前模型 |
| `prompt` | `str` | `""` | 自定义摘要 prompt，空字符串使用内置默认 |
| `max_summary_chars` | `int` | `2000` | 摘要输出最大字符数 |

### TrimConfig

trim 压缩策略的专用配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `keep_system` | `bool` | `True` | 是否保留系统消息 |
| `keep_first_n` | `int` | `0` | 始终保留的前 N 条消息（如开场问候语） |

### ContextWindowConfig

上下文窗口管理的完整配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `False` | 上下文压缩的总开关 |
| `strategy` | `str` | `"none"` | 压缩策略：`none` / `summarize` / `trim` / `custom` |
| `trigger_tokens` | `int` | `100000` | 触发压缩的 token 阈值 |
| `keep_messages` | `int` | `20` | 始终保留最近 N 条消息 |
| `summarize` | `SummarizeConfig` | `SummarizeConfig()` | summarize 策略子配置 |
| `trim` | `TrimConfig` | `TrimConfig()` | trim 策略子配置 |
| `custom_handler` | `str \| None` | `None` | 自定义策略入口（`"module:function"` 格式） |
| `summary_model` | `str \| None` | `None` | （遗留字段）摘要专用模型 |

### ProfileExtractionConfig

用户画像提取的配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `True` | 是否提取用户画像 |
| `prompt` | `str` | `""` | 自定义提取 prompt，空字符串使用内置默认 |

### KnowledgeExtractionConfig

知识事实提取的配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `True` | 是否提取知识事实 |
| `prompt` | `str` | `""` | 自定义提取 prompt，空字符串使用内置默认 |
| `max_facts` | `int` | `5` | 每次提取的最大事实数量 |

### ExtractionConfig

记忆提取（写入 L3 Store）的完整配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `False` | 是否将提取结果写入 L3 Store（默认关闭） |
| `max_messages` | `int` | `10` | 仅查看最近 N 条消息用于提取 |
| `max_chars_per_message` | `int` | `300` | 每条消息截断为前 N 个字符 |
| `profile` | `ProfileExtractionConfig` | `ProfileExtractionConfig()` | 画像提取子配置 |
| `knowledge` | `KnowledgeExtractionConfig` | `KnowledgeExtractionConfig()` | 知识提取子配置 |
| `write_on` | `str` | `"every_request"` | 提取触发时机：`every_request` / `every_n_messages` / `end_of_session` / `disabled` |
| `write_every_n` | `int` | `5` | `write_on=every_n_messages` 时，每隔 N 条消息提取一次 |

### RetentionConfig

记忆生命周期管理配置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `profile_ttl_days` | `int \| None` | `None` | 画像条目过期天数，`None` 表示永不过期 |
| `knowledge_ttl_days` | `int \| None` | `None` | 知识条目过期天数，`None` 表示永不过期 |
| `max_items_per_namespace` | `int \| None` | `None` | 每个命名空间最大条目数，`None` 表示不限（LRU 淘汰） |
| `dedup_enabled` | `bool` | `False` | 写入知识前检查相似度以避免重复 |

### MemoryConfig

顶层配置，聚合所有记忆相关设置。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `embedding` | `EmbeddingConfig` | `EmbeddingConfig()` | Embedding 配置 |
| `context_window` | `ContextWindowConfig` | `ContextWindowConfig()` | 上下文窗口配置 |
| `extraction` | `ExtractionConfig` | `ExtractionConfig()` | 记忆提取配置 |
| `retention` | `RetentionConfig` | `RetentionConfig()` | 生命周期管理配置 |

```python
from artipivot.memory.config import MemoryConfig

cfg = MemoryConfig.from_dict({
    "embedding": {"enabled": False},
    "context_window": {
        "enabled": True,
        "strategy": "summarize",
        "trigger_tokens": 80000,
        "summarize": {"model": "gpt-4o-mini", "max_summary_chars": 2000},
    },
    "extraction": {
        "enabled": True,
        "profile": {"enabled": True},
        "knowledge": {"enabled": True, "max_facts": 5},
        "write_on": "every_request",
    },
    "retention": {"knowledge_ttl_days": 90},
})
```

---

## Checkpointer 工厂（checkpointer.py）

> **注意**：此模块已委托至统一存储注册表（`artipivot.storage.registry`）。旧接口保留用于向后兼容。

### 核心函数

| 函数 | 说明 |
|------|------|
| `create_checkpointer(backend, **kwargs)` | 创建 Checkpointer 实例（委托至 `get_factory(backend).create(TYPE_CHECKPOINTER, kwargs)`） |
| `available_checkpointer_backends()` | 返回已注册的后端名称列表 |
| `setup_checkpointer(checkpointer)` | 初始化数据库表（调用 `checkpointer.setup()`，InMemory 为空操作） |
| `register_checkpointer_backend(name, factory)` | **已废弃** — 使用 `artipivot.storage.registry.register_factory()` 替代 |

### 内置后端

| 名称 | 实现 | 参数 |
|------|------|------|
| `"memory"` | `langgraph.checkpoint.memory.InMemorySaver` | 无 |
| `"postgres"` | `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver` | `uri` 或环境变量 `DATABASE_URI` |

```python
from artipivot.memory.checkpointer import create_checkpointer, setup_checkpointer

cp = create_checkpointer("memory")
await setup_checkpointer(cp)
```

```python
# PostgreSQL 后端
cp = create_checkpointer("postgres", uri="postgresql://user:pass@localhost/db")
```

---

## Store 工厂（store.py）

> **注意**：此模块已委托至统一存储注册表（`artipivot.storage.registry`）。旧接口保留用于向后兼容。

### 核心函数

| 函数 | 说明 |
|------|------|
| `create_store(backend, **kwargs)` | 创建 Store 实例（委托至 `get_factory(backend).create(TYPE_STORE, kwargs)`） |
| `available_store_backends()` | 返回已注册的后端名称列表 |
| `setup_store(store)` | 初始化数据库表和索引（调用 `store.setup()`，InMemory 为空操作） |
| `register_store_backend(name, factory)` | **已废弃** — 使用 `artipivot.storage.registry.register_factory()` 替代 |

### 内置后端

| 名称 | 实现 | 参数 |
|------|------|------|
| `"memory"` | `langgraph.store.memory.InMemoryStore` | 无 |
| `"postgres"` | `langgraph.store.postgres.PostgresStore` | `uri` 或环境变量 `DATABASE_URI`，可选 `index` |

```python
from artipivot.memory.store import create_store, setup_store

store = create_store("memory")
await setup_store(store)
```

```python
# PostgreSQL 后端
store = create_store("postgres", uri="postgresql://user:pass@localhost/db")
```

---

## Namespace 隔离（namespace.py）

Store 按 `(agent_id, user_id, scope, ...)` 组织，不同 Agent / 用户的知识库互不可见。所有函数返回 `tuple[str, ...]`。

| 函数 | 返回值 |
|------|--------|
| `profile_ns(agent_id, user_id)` | `(agent_id, user_id, "profile")` |
| `knowledge_ns(agent_id, user_id)` | `(agent_id, user_id, "knowledge")` |
| `preferences_ns(agent_id, user_id)` | `(agent_id, user_id, "preferences")` |
| `agent_memory_ns(agent_id, user_id, sub_name)` | `(agent_id, user_id, "agent", sub_name)` |

```python
from artipivot.memory.namespace import profile_ns, knowledge_ns, preferences_ns, agent_memory_ns

profile_ns("code_agent", "user_123")              # ("code_agent", "user_123", "profile")
knowledge_ns("code_agent", "user_123")             # ("code_agent", "user_123", "knowledge")
preferences_ns("code_agent", "user_123")           # ("code_agent", "user_123", "preferences")
agent_memory_ns("code_agent", "user_123", "writer")  # ("code_agent", "user_123", "agent", "writer")
```

---

## 记忆提取（extraction.py）

从对话消息中提取结构化信息，写入 Store。所有提取函数现在接受 `ExtractionConfig` 参数，通过配置控制行为。

### extract_profile(messages, model, config) -> dict | None

提取用户画像（姓名、语言偏好、技术栈、项目等）。

- **参数**：`config` 为 `ExtractionConfig`，若为 `None` 则使用默认值。
- 当 `config.profile.enabled == False` 时，直接返回 `None`。
- prompt 使用 `config.profile.prompt`，空字符串时使用内置默认 prompt。
- **返回值**：成功时返回 `dict`（例如 `{"name": "张三", "language": "Python"}`），无新画像信息或解析失败时返回 `None`。
- 内部使用 JSON mode 解析 LLM 输出，会自动去除 markdown 代码块包裹。
- 空对象 `{}` 的结果也会被转换为 `None` 返回。

### extract_knowledge(messages, model, config) -> list[str]

提取值得长期记住的知识事实。

- **参数**：`config` 为 `ExtractionConfig`，若为 `None` 则使用默认值。
- 当 `config.knowledge.enabled == False` 时，直接返回 `[]`。
- prompt 使用 `config.knowledge.prompt`，空字符串时使用内置默认 prompt。
- 提取结果受 `config.knowledge.max_facts` 限制，超过部分截断。
- **返回值**：字符串列表（例如 `["用户偏好测试驱动开发", "用户的项目使用 PostgreSQL"]`）。
- 无新知识或解析失败时返回空列表 `[]`。非字符串元素会被过滤。

### write_memory(store, agent_id, user_id, messages, model, config) -> None

串联提取与写入的完整流程：

```mermaid
flowchart TD
    A["write_memory"] --> CHECK{"config.enabled?"}
    CHECK -->|False| SKIP["直接返回"]
    CHECK -->|True| B["extract_profile"]
    B -->|返回 dict| C["合并已有 profile 并写入 Store"]
    B -->|返回 None| D["跳过 profile"]
    A --> E["extract_knowledge"]
    E --> F["逐条写入 Store（受 max_facts 限制）"]
```

- 当 `config.enabled == False` 时，整个流程直接跳过，不做任何提取或写入。
- Profile 写入时，会将新提取的画像与已有数据合并（新键覆盖旧键）。
- Knowledge 每条事实使用 `uuid.uuid4()` 生成独立 key 写入。

### _format_messages(messages, config)

构建提取 prompt 时使用 `config.max_messages` 和 `config.max_chars_per_message` 控制输入范围：

- 仅取最后 `config.max_messages` 条消息（默认 10 条）。
- 每条消息的内容截断为前 `config.max_chars_per_message` 个字符（默认 300 个）。
- 这意味着提取只基于近期对话，不会处理完整历史。

### 内置 prompt

模块内置了两个中文提取 prompt（`_PROFILE_PROMPT` 和 `_KNOWLEDGE_PROMPT`），当 `config.profile.prompt` 或 `config.knowledge.prompt` 为空字符串时使用。可通过配置字段覆盖为自定义 prompt。

---

## 记忆检索（retrieval.py）

### build_memory_context(store, agent_id, user_id, query, embedding_config) -> str

从 Store 读取记忆，格式化为**字符串**，用于拼接到系统提示词中。

**关键**：此函数返回一个格式化的字符串（`str`），不是字典。返回内容为空时返回空字符串 `""`。

#### 检索流程

```mermaid
flowchart TD
    A["build_memory_context"] --> B["读取 profile"]
    B --> C{"profile 存在?"}
    C -->|是| D["追加用户画像文本"]
    C -->|否| E["跳过"]
    A --> F["resolve_search_strategy"]
    F --> G{策略?}
    G -->|"semantic"| H["store.asearch 语义搜索 limit=3"]
    G -->|"none"| I["跳过知识检索"]
    F -->|backend 不支持 asearch| ERR["抛出 EmbeddingNotSupportedError"]
    H --> J{"有结果?"}
    J -->|是| K["追加知识文本"]
    J -->|否| L["跳过"]
    D --> M["拼接为字符串返回"]
    K --> M
    E --> M
    I --> M
    L --> M
```

#### 搜索策略

使用 `resolve_search_strategy(store, cfg)` 决定运行时检索策略：

| 策略 | 条件 | 行为 |
|------|------|------|
| `"semantic"` | `embedding.enabled == True` 且 store 支持 `asearch` | 调用 `store.asearch(ns, query=query, limit=3)` 向量相似度搜索 |
| `"none"` | `embedding.enabled == False` | 完全跳过知识检索 |
| 异常 | `embedding.enabled == True` 但 store 不支持 `asearch` | 抛出 `EmbeddingNotSupportedError` |

> **重要**：不存在静默回退或降级。如果 embedding 已启用但后端不支持语义搜索，直接报错。

#### 返回格式示例

```
[用户画像]
{"name": "张三", "language": "Python", "tech_stack": ["FastAPI"]}

[相关知识]
- 用户偏好测试驱动开发
- 用户的项目使用 PostgreSQL
```

#### 使用方式

```python
from artipivot.memory.retrieval import build_memory_context

context = await build_memory_context(store, "code_agent", "user_123", query="写个排序函数")
# context 是字符串，直接拼接到系统提示词中
system_prompt = f"{base_prompt}\n\n{context}"
```

---

## 上下文窗口管理（context_window.py）

当对话历史 token 数超过阈值时自动压缩，避免超出模型上下文窗口。

### 自定义策略注册

| 函数 | 说明 |
|------|------|
| `register_compression_strategy(name, handler)` | 注册自定义压缩函数。`handler` 签名为 `async (messages, config) -> list` |

### ContextWindowManager

```python
from artipivot.memory.context_window import ContextWindowManager, register_compression_strategy
from artipivot.memory.config import ContextWindowConfig, SummarizeConfig

# 使用 summarize 策略
cfg = ContextWindowConfig(
    enabled=True,
    strategy="summarize",
    trigger_tokens=80000,
    summarize=SummarizeConfig(model="gpt-4o-mini", max_summary_chars=2000),
)
mgr = ContextWindowManager(cfg)
new_messages = await mgr.maybe_compress(messages, model)
```

#### 压缩策略

| 策略 | 行为 | 适用场景 |
|------|------|----------|
| `none` | 不压缩（默认） | 短对话，token 不超限 |
| `summarize` | LLM 将旧消息压缩为摘要 | 长对话，需要保留语义 |
| `trim` | 截断保留最近 N 条 | 不需要历史语义，只保留最新上下文 |
| `custom` | 委托给已注册的自定义 handler | 特殊业务逻辑 |

#### maybe_compress(messages, model) -> list | None

检查是否需要压缩，满足条件时返回新的消息列表，否则返回 `None`。

- 当 `config.enabled == False` 或 `strategy == "none"` 时直接返回 `None`。
- 当 token 估算值低于 `trigger_tokens` 时返回 `None`。
- Token 估算方式：所有消息内容字符数总和 / 4（约 4 字符 = 1 token）。

#### _summarize(messages, model) -> list

将旧消息（除最近 `keep_messages` 条以外的）通过 LLM 生成摘要，拼接 `[对话摘要]` 后与最近消息一起返回。

- prompt 使用 `config.summarize.prompt`，空字符串时使用内置默认摘要 prompt。
- 每条旧消息的内容截断为前 200 个字符。
- 摘要输出受 `config.summarize.max_summary_chars` 限制。
- **如果摘要调用失败（抛出异常），会自动回退到 trim 策略**。

#### _trim(messages) -> list

直接截断，遵循 `TrimConfig` 设置：

- 若 `keep_system == True`，先保留所有系统消息。
- 若 `keep_first_n > 0`，保留前 N 条非系统消息。
- 最后保留最近 `keep_messages` 条非系统消息（扣除已保留的 leading 条数）。

#### _custom(messages) -> list

委托给已注册的自定义压缩函数：

- 先从内存注册表（`register_compression_strategy`）查找 `custom_handler` 名称。
- 未找到时，尝试以 `"module:function"` 格式动态导入（如 `"mypackage.compress:smart_trim"`）。
- handler 签名为 `async (messages, config) -> list`。
- 如果 handler 不存在或执行失败，回退到 trim 策略。

---

## L3 长期记忆的集成架构

L3 记忆的读写分别部署在系统的两个层次：**策略层读取**和 **Gateway 层写入**。

### 整体数据流

```mermaid
sequenceDiagram
    participant User
    participant API as API (chat.py)
    participant GW as AgentGateway
    participant SG as Sub-Agent 策略
    participant Store as Store (L3)

    User->>API: POST /chat/{agent_id}
    API->>GW: invoke(agent_id, message, memory_config)
    GW->>SG: 策略执行

    Note over SG,Store: ① L3 读取（同步，策略层）
    SG->>Store: build_memory_context()
    Store-->>SG: 记忆文本
    SG->>SG: 拼接到 system prompt

    Note over SG: LLM 调用 + 工具执行
    SG-->>GW: 结果

    Note over GW,Store: ② L3 写入（异步，Gateway 层）
    GW->>Store: _maybe_write_memory() [fire-and-forget]
    GW-->>API: 返回响应（不等待写入完成）
    API-->>User: ChatResponse
```

### L3 读取：策略层注入

读取发生在 `agents/strategies/memory.py` 的 `build_messages_with_memory()` 中。这个函数被 ReAct 和 Function Calling 两种策略共用。

**为什么在策略层而非主图节点**：

- L3 记忆是 prompt 内容（告诉 LLM "这个用户是谁、之前聊过什么"），不是对话消息
- 策略层是实际调用 LLM 的地方，在此注入可以精确控制 system prompt 的构成
- 避免在主图增加额外节点，保持路由图的简洁

**执行流程**：

1. 收集对话消息（`state.query` + `state.messages`）
2. 如果 `context_window.enabled`，执行上下文压缩（trim / summarize / custom）
3. 如果 `memory_config` 不为 None 且 store 可用，调用 `build_memory_context()` 读取 L3
4. 将记忆文本追加到 system prompt 尾部
5. 返回 `[SystemMessage(prompt+memory), *messages]`

**读取失败的容错**：L3 读取失败时捕获异常并 warning 日志，不阻断请求——agent 正常回复，只是没有长期记忆上下文。

### L3 写入：Gateway 层异步写入

写入发生在 `gateway/gateway.py` 的 `_maybe_write_memory()` 中，在 `invoke()` 成功返回前触发。

**为什么在 Gateway 层而非图节点**：

- L3 写入是副作用，不应阻塞用户响应
- 提取需要调用 LLM（解析画像和知识），耗时不可控
- 如果放在图节点里，失败会影响整个图的 trace 和重试逻辑
- Gateway 层用 `asyncio.create_task()` 实现 fire-and-forget，写入失败仅记日志

**触发条件**（全部满足才触发）：

| 条件 | 检查位置 |
|------|---------|
| `memory_config` 不为 None | `_maybe_write_memory()` |
| `memory_config.extraction.enabled == True` | `_maybe_write_memory()` |
| `storage_provider.store` 可用 | `_maybe_write_memory()` |
| `extraction.enabled == True`（双重检查） | `write_memory()` 内部 |

### extraction 与 embedding 的组合

`extraction` 控制**写入**，`embedding` 控制**读取**，两者独立：

| extraction | embedding | 写入 | 读取 |
|:---:|:---:|:---|:---|
| `false` | `false` | 不写入 | 不读取（L3 完全关闭） |
| `true` | `false` | 写入 profile + knowledge | 只读 profile（无语义搜索） |
| `false` | `true` | 不写入 | 读取 profile + 语义搜索 knowledge（如果之前有写入数据） |
| `true` | `true` | 写入 | 读取 profile + 语义搜索 knowledge |

**典型用法**：

- **开发环境**：两者都关闭（默认），零开销
- **只需要画像**：`extraction.enabled=true` + `embedding.enabled=false`，写入并读取用户画像，不做知识搜索
- **完整记忆**：两者都开启 + Postgres 后端（支持 asearch）

### 零开销设计

当 YAML 中没有 `memory:` 块，或所有功能都 disabled 时，bootstrap 将 `memory_config` 设为 `None`：

```python
# bootstrap.py
memory_config = MemoryConfig.from_dict(manifest.memory) if manifest.memory else None
if memory_config and (
    memory_config.extraction.enabled
    or memory_config.embedding.enabled
    or memory_config.context_window.enabled
):
    _log.info("bootstrap.memory_enabled", ...)
else:
    memory_config = None  # All disabled → None（零开销）
```

`memory_config is None` 时：
- Gateway 层 `_maybe_write_memory()` 第一个条件判断就 return，不创建任何异步任务
- 策略层 `build_messages_with_memory()` 跳过所有 memory 分支，直接返回原始消息

---

## Embedding 与语义搜索的扩展

### 当前架构

Embedding 配置极简——只有一个 `enabled: bool` 字段：

```yaml
memory:
  embedding:
    enabled: false
```

这是因为**实际的 embedding 计算由 store 后端自身处理**，不需要在 artipivot 层配置 embedding 模型。例如 PostgresStore + pgvector 扩展会自动将写入的文档转为向量并建立索引。

### 如何支持语义搜索

要启用语义搜索，需要：

1. **Store 后端支持 `asearch` 方法**：例如 PostgresStore（pgvector）
2. **YAML 配置**：

```yaml
storage:
  default: postgres
  uri: "${DATABASE_URI}"

memory:
  embedding:
    enabled: true            # 开启语义检索
  extraction:
    enabled: true            # 开启写入（提取画像和知识）
```

### 搜索策略的运行时决策

`storage/search.py` 中的 `resolve_search_strategy()` 在每次检索时运行：

```python
def resolve_search_strategy(store, embedding_config):
    if not embedding_config.enabled:
        return "none"                # 完全跳过
    if hasattr(store, "asearch"):
        return "semantic"            # 走向量检索
    raise EmbeddingNotSupportedError(...)  # 显式报错，不静默降级
```

**设计原则：不静默降级**。如果用户配置了 `embedding.enabled=true`，说明他期望语义搜索。如果后端不支持 `asearch`，应该立即报错让用户修正配置，而不是悄悄降级为全量取回（全量取回不是语义搜索，会产生误导性结果）。

### 扩展新的语义搜索后端

如果需要使用非 PostgreSQL 的向量数据库（如 Milvus、Weaviate、Qdrant），扩展步骤如下：

**1. 实现 BackendFactory**

```python
# src/artipivot_milvus/storage.py
from artipivot.storage.factory import BackendFactory

class MilvusFactory(BackendFactory):
    @property
    def name(self) -> str:
        return "milvus"

    def supports(self, type: str) -> bool:
        return type in ("store",)  # 只提供 Store + 向量检索

    @property
    def supports_search(self) -> bool:
        return True  # 支持语义搜索

    def create(self, type: str, config: dict):
        from milvus_store import MilvusLangGraphStore
        return MilvusLangGraphStore(
            uri=config.get("uri"),
            collection=config.get("collection", "artipivot"),
            embedding_dim=config.get("dims", 1536),
        )
```

关键要求：`create("store", config)` 返回的对象**必须实现 `asearch` 方法**，签名与 LangGraph Store 一致：

```python
async def asearch(self, namespace, *, query: str, limit: int = 10) -> list[Item]:
    """向量相似度搜索。"""
```

**2. 注册工厂**

方式一：代码注册

```python
from artipivot.storage import register_factory
from artipivot_milvus.storage import MilvusFactory

register_factory(MilvusFactory())
```

方式二：entry_points 自动发现（pyproject.toml）

```toml
[project.entry-points."artipivot.storage"]
milvus = "artipivot_milvus.storage:MilvusFactory"
```

**3. YAML 配置**

```yaml
storage:
  default: milvus
  uri: "http://localhost:19530"
  options:
    collection: artipivot
    dims: 1536

memory:
  embedding:
    enabled: true
  extraction:
    enabled: true
```

### 自定义 Embedding 模型

如果向量数据库不内置 embedding 计算（即需要 artipivot 侧先调用 embedding API 再传入向量），需要在自定义 Store 的 `aput` / `asearch` 中自行处理：

```python
class MyCustomStore(BaseStore):
    def __init__(self, ..., embedding_model="text-embedding-3-small"):
        from langchain_openai import OpenAIEmbeddings
        self._embed = OpenAIEmbeddings(model=embedding_model)

    async def aput(self, namespace, key, value):
        vector = await self._embed.aembed_query(str(value))
        # 写入向量数据库
        ...

    async def asearch(self, namespace, *, query, limit=10):
        vector = await self._embed.aembed_query(query)
        # 向量相似度搜索
        ...
```

这是 store 后端的内部实现细节，artipivot 层面不需要知道用了什么 embedding 模型。

---

## 完整配置参考

```yaml
memory:
  embedding:
    enabled: false                    # 开关：是否使用 store 的 asearch

  context_window:
    enabled: true                     # 总开关：是否启用上下文压缩
    strategy: summarize               # none | summarize | trim | custom
    trigger_tokens: 50000             # 触发压缩的 token 阈值
    keep_messages: 20                 # 始终保留最近 N 条消息
    summarize:
      model: null                     # 可选专用总结模型（null = 使用 Agent 当前模型）
      prompt: ""                      # 可选自定义总结 prompt（空 = 内置默认）
      max_summary_chars: 2000         # 摘要输出最大字符数
    trim:
      keep_system: true               # 是否保留系统消息
      keep_first_n: 0                 # 始终保留前 N 条消息
    custom_handler: null              # 自定义策略入口（"module:function" 格式）
    summary_model: null               # （遗留字段）

  extraction:
    enabled: true                     # 是否将提取结果写入 L3 Store
    max_messages: 10                  # 提取时仅查看最近 N 条消息
    max_chars_per_message: 300        # 每条消息截断为前 N 个字符
    profile:
      enabled: true                   # 是否提取用户画像
      prompt: ""                      # 自定义画像提取 prompt（空 = 内置默认）
    knowledge:
      enabled: true                   # 是否提取知识事实
      prompt: ""                      # 自定义知识提取 prompt（空 = 内置默认）
      max_facts: 5                    # 每次提取的最大事实数量
    write_on: every_request           # every_request | every_n_messages | end_of_session | disabled
    write_every_n: 5                  # write_on=every_n_messages 时的间隔

  retention:
    profile_ttl_days: null            # null = 永不过期
    knowledge_ttl_days: 90            # 知识条目过期天数
    max_items_per_namespace: 100      # 每个命名空间最大条目数
    dedup_enabled: false              # 是否在写入前做去重检查
```
