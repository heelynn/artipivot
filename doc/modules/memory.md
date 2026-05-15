# 记忆系统（Memory）

## 三层记忆模型

```
请求入口
  │
  ▼
┌──────────────────────────────────────────────────┐
│ L1 · 工作记忆（图 State）                          │
│ ArtiPivotState / SubAgentState                    │
│ 意图、活跃子代理、中间产物、本轮消息                  │
│ 作用域：单次图执行，请求结束即释放                    │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ L2 · 会话记忆（Checkpointer）                      │
│ per-thread 持久化，自动保存/恢复完整 State            │
│ 对话消息历史、图执行快照                             │
│ 作用域：同一 thread_id 内                          │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│ L3 · 长期记忆（Store）                             │
│ 跨 thread 持久化，按 namespace 隔离                  │
│ 用户画像、知识事实、偏好设置、Agent 专属记忆           │
│ 作用域：同一 (agent_id, user_id) 内                 │
└──────────────────────────────────────────────────┘
```

| 层级 | 实现 | 作用域 | 后端 |
|------|------|--------|------|
| L1 | `ArtiPivotState` / `SubAgentState` | 单次图执行 | 内存 |
| L2 | `register_checkpointer_backend()` | per-thread | Memory / PostgreSQL |
| L3 | `register_store_backend()` | 跨 thread | Memory / PostgreSQL |

---

## 可插拔后端

```python
from artipivot.memory.checkpointer import create_checkpointer, register_checkpointer_backend
from artipivot.memory.store import create_store, register_store_backend

# 内置后端
cp = create_checkpointer("memory")   # 或 "postgres"
store = create_store("memory")       # 或 "postgres"

# 自定义后端
register_store_backend("mongodb", lambda **kw: MongoStore(kw["uri"]))
store = create_store("mongodb", uri="mongodb://localhost:27017")
```

---

## Namespace 隔离

Store 按 `(agent_id, user_id, scope)` 组织，不同 Agent/用户的知识库互不可见：

```python
from artipivot.memory.namespace import profile_ns, knowledge_ns, preferences_ns, agent_memory_ns

profile_ns("code_agent", "user_123")       # → ("code_agent", "user_123", "profile")
knowledge_ns("code_agent", "user_123")      # → ("code_agent", "user_123", "knowledge")
preferences_ns("code_agent", "user_123")    # → ("code_agent", "user_123", "preferences")
agent_memory_ns("code_agent", "user_123", "writer")  # → ("code_agent", "user_123", "agent", "writer")
```

---

## 记忆提取

从对话中提取结构化信息，写入 Store：

```python
from artipivot.memory.extraction import extract_profile, extract_knowledge, write_memory

# extract_profile 提取用户画像（角色、技能、偏好）
# → {"role": "后端工程师", "skills": ["Python", "Go"], "preferred_language": "中文"}

# extract_knowledge 提取知识点（事实、决策、上下文）
# → {"facts": ["项目使用 PostgreSQL 作为主库", "API 端口为 8080"]}

# write_memory 串联提取 + 写入 + 合并已有配置
await write_memory(store, "code_agent", "user_123", messages, model)
# 内部流程：extract_profile() → extract_knowledge() → store.put() 合并
```

每一步都是 LLM 调用，使用结构化输出（JSON mode）确保格式正确。

---

## 记忆检索与注入

从 Store 读取记忆，格式化后注入系统提示词：

```python
from artipivot.memory.retrieval import build_memory_context

# 读取用户画像、知识、偏好，生成注入文本
context = await build_memory_context(store, "code_agent", "user_123", query="写个排序函数")

# context 结构：
# {
#     "profile": "用户是后端工程师，擅长 Python 和 Go...",
#     "knowledge": "项目使用 PostgreSQL，API 端口 8080...",
#     "preferences": "偏好中文回复，代码风格倾向简洁...",
#     "agent_memory": {"writer": "上次讨论过排序算法..."}
# }
```

在构建系统提示词时注入：

```python
system_prompt = f"{base_prompt}\n\n## 用户信息\n{context['profile']}\n## 已知信息\n{context['knowledge']}"
```

### 语义搜索（可选）

启用 embedding 后，检索时用向量相似度匹配最相关的记忆片段：

```yaml
# config/seed/memory.yaml
memory:
  embedding:
    enabled: true
    provider: openai                # 当前支持 openai embedding
    model: text-embedding-3-small
```

未启用时，回退到全量列表读取（适合记忆量小的场景）。

---

## 上下文窗口管理

当对话历史 token 数超过阈值时自动压缩，避免超出模型上下文窗口：

| 策略 | 行为 | 适用场景 |
|------|------|----------|
| `none` | 不压缩（默认） | 短对话，token 不超限 |
| `summarize` | LLM 将旧消息压缩为摘要 | 长对话，需要保留语义 |
| `trim` | 截断只保留最近 N 条 | 不需要历史语义，只保留最新上下文 |

```yaml
memory:
  context_window:
    strategy: summarize
    trigger_tokens: 100000        # 超过此阈值触发压缩
    keep_messages: 20             # trim 策略下保留最近 N 条
```

---

## 配置总览

```yaml
# config/seed/memory.yaml
memory:
  checkpointer:
    backend: memory               # memory | postgres
  store:
    backend: memory               # memory | postgres
  embedding:
    enabled: false
    provider: openai
    model: text-embedding-3-small
  extraction:
    enabled: true                 # 是否在每轮对话后自动提取
    extract_profile: true
    extract_knowledge: true
  context_window:
    strategy: none
    trigger_tokens: 100000
    keep_messages: 20
```
