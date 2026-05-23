# L3 长期记忆接入设计

## Context

L3 长期记忆的接口已实现（`extraction.py` 写入、`retrieval.py` 读取、`context_window.py` 压缩），但没有被任何业务代码调用。需要将 L3 接入实际请求流程，使其在 sub_agent 执行时读取记忆、在请求完成后异步提取记忆。

设计原则：
- 图拓扑不变（不增加节点）
- L3 默认关闭，零开销
- 读取同步（影响回复质量），写入异步（不影响响应延迟）

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| L3 读取注入位置 | sub_agent 策略层 | 记忆是 prompt 的一部分，跟 system_prompt 一起构建 |
| L3 写入位置 | gateway 层 | 副作用不应阻塞用户响应 |
| L3 写入方式 | 异步 fire-and-forget | 提取是一次额外 LLM 调用，不应增加用户延迟 |
| 上下文压缩位置 | sub_agent 策略层 | 压缩在 LLM 调用前执行，与策略逻辑内聚 |

## 变更

### 1. AgentContext 增加 memory_config

`graph/context.py` — 新增字段：

```python
@dataclass
class AgentContext:
    agent_id: str
    user_id: str
    thread_id: str
    model: BaseChatModel
    available_tools: list[BaseTool] = field(default_factory=list)
    config_center: ConfigCenter | None = None
    memory_config: MemoryConfig | None = None  # 新增
```

Gateway invoke 时从全局配置构建 MemoryConfig，传入 AgentContext。

### 2. 策略层读取 L3 记忆 + 上下文压缩

`agents/strategies/react.py` 和 `function_calling.py` — 在构建给 LLM 的 messages 时：

```
1. 从 runtime.context.memory_config 取配置
2. 如果 memory_config 为 None → 跳过（L3 未启用）
3. 上下文压缩：ContextWindowManager.maybe_compress(messages, model)
4. L3 读取：build_memory_context(store, agent_id, user_id, query, embedding_config)
5. 追加到 system_prompt 末尾
```

伪代码：

```python
async def _build_prompt(state, runtime):
    ctx = runtime.context
    store = runtime.store
    mem_cfg = ctx.memory_config

    system_prompt = base_system_prompt

    if mem_cfg and store:
        # 上下文压缩
        if mem_cfg.context_window.enabled:
            mgr = ContextWindowManager(mem_cfg.context_window)
            compressed = await mgr.maybe_compress(messages, ctx.model)
            if compressed is not None:
                messages = compressed

        # L3 记忆读取
        query = _extract_user_query(messages)
        memory_text = await build_memory_context(
            store, ctx.agent_id, ctx.user_id, query, mem_cfg.embedding
        )
        if memory_text:
            system_prompt += f"\n\n{memory_text}"

    return system_prompt, messages
```

### 3. Gateway 层异步写入

`gateway/gateway.py` — invoke() 完成后：

```python
result = await graph.ainvoke(...)

# 异步提取长期记忆
if memory_config and memory_config.extraction.enabled:
    messages = result.get("messages", [])
    asyncio.create_task(
        write_memory(
            store, agent_id, user_id, messages, model,
            memory_config.extraction,
        )
    )

return result
```

store 从哪里来：Gateway 持有 StorageProvider 引用（通过 deps 注入），或直接从 graph 的 store 属性获取。

### 4. MemoryConfig 的来源

在 bootstrap.py 初始化时，从 YAML 的 `memory:` 块解析 MemoryConfig，存入 ConfigCenter 或直接注入 AgentContext。

两种获取方式（选其一）：
- A. ConfigCenter 持有全局 MemoryConfig，gateway invoke 时读取
- B. AgentContext 直接携带，在 invoke 时构建

选 B — 与现有 agent_id / user_id / model 的注入方式一致。

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `graph/context.py` | AgentContext 增加 `memory_config` 字段 |
| `gateway/gateway.py` | invoke() 完成后异步调 write_memory()；构造 AgentContext 时传入 memory_config |
| `agents/strategies/react.py` | LLM 调用前读取 L3 记忆 + 上下文压缩 |
| `agents/strategies/function_calling.py` | 同上 |
| `bootstrap.py` | 解析 YAML memory 块为 MemoryConfig，传给 gateway |

## 不变的文件

| 文件 | 原因 |
|------|------|
| `graph/root.py` | 图拓扑不变 |
| `graph/router.py` | classify 不需要 L3 记忆 |
| `memory/extraction.py` | 接口已就绪 |
| `memory/retrieval.py` | 接口已就绪 |
| `memory/context_window.py` | 接口已就绪 |
| `memory/config.py` | 配置结构已完整 |

## 验证

1. `memory.extraction.enabled=false`（默认）→ 零开销，不调 write_memory
2. `memory.embedding.enabled=true` + memory 后端 → 策略层读到记忆，拼进 prompt
3. `memory.embedding.enabled=true` + 不支持 asearch 的后端 → 抛 EmbeddingNotSupportedError
4. `memory.context_window.enabled=true` → 长对话自动压缩
5. 提取失败 → 不影响响应，日志记录错误
