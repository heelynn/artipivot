# 动态配置中心（ConfigCenter）

ConfigCenter 统一管理模型、提示词、路由、限流四类配置，从 DocumentStore 热读取，通过 ChangeNotifier 订阅变更。

## 架构

```
DocumentStore                     ConfigCenter
─────────────                     ────────────
model_configs    ───────────────── ModelProvider（热读取，每次 invoke 动态解析）
prompt_configs   ───────────────── PromptStore（热读取，节点执行时取最新）
routing_configs  ──┬────────────── RoutingConfig（热读取 + 变更回调 → 触发重建图）
                   │
ratelimit_configs ───────────────── RateLimiter（热读取，中间件层拦截）
plugins          ───────────────── PluginManager ─→ PluginWatcher ─→ GraphRebuilder
                   │
                   └─ ChangeNotifier 通知订阅者
```

## 配置分类

| 配置类型 | 重建图 | 更新方式 | 生效时机 |
|----------|:------:|----------|----------|
| 模型配置 | 否 | Admin API / `model_provider.update_*()` | 下次 invoke |
| 提示词 | 否 | Admin API / DocumentStore | 下次节点执行 |
| 限流参数 | 否 | Admin API / DocumentStore | 下次请求 |
| 路由规则 | **是** | Admin API → ConfigCenter 回调 → Rebuilder | 重建后 |
| 插件变更 | **是** | PluginManager → ChangeNotifier → Watcher | 重建后 |

---

## DocumentStore 中的配置集合

ConfigCenter 从 DocumentStore 的不同 collection 读取配置，下表列出 key 命名规范：

| Collection | Key 格式 | 内容 | 示例 |
|------------|----------|------|------|
| `model_configs` | `global` | 全局默认模型 + fallback | `{"provider": "openai", "name": "gpt-4o"}` |
| `model_configs` | `agent:{agent_id}` | Agent 级别模型 | `agent:code_agent` |
| `model_configs` | `agent:{agent_id}:sub:{name}` | 子代理级别模型（含独立 fallback） | `agent:code_agent:sub:code_writer` |
| `prompt_configs` | `{agent_id}:{node}` | 节点提示词 | `code_agent:classify` |
| `prompt_configs` | `{agent_id}:sub:{name}` | 子代理提示词 | `code_agent:sub:code_writer` |
| `prompt_configs` | `{agent_id}:respond` | 响应节点提示词 | `code_agent:respond` |
| `routing_configs` | `{agent_id}` | 路由规则 | `code_agent` |
| `ratelimit_configs` | `{agent_id}` | Agent 限流配置 | `code_agent` |
| `ratelimit_configs` | `tool:{tool_name}` | 工具限流配置 | `tool:web_search` |
| `plugins` | `{plugin_type}:{agent_id}:{name}` | 插件元数据 | `sub_agent:code_agent:writer` |

---

## 路由配置

```yaml
# config/seed/routing.yaml
agents:
  code_agent:
    confidence_threshold: 0.7
    intents:
      - name: code_write
        sub_agent: code_writer
        description: 代码编写、重构、调试
      - name: code_review
        sub_agent: code_reviewer
        description: 代码审查、风格检查
    fallback: fallback
    clarify: clarify
```

路由逻辑：`classify → 置信度 < threshold → clarify / 匹配到 intent → 对应子代理 / 无匹配 → fallback`

---

## 提示词配置

```yaml
# config/seed/prompts.yaml
prompts:
  "code_agent:classify":
    agent_id: code_agent
    node: classify
    system: |
      你是意图分类器。根据用户消息判断意图，返回 JSON：
      {"intent": "code_write|code_review|...", "confidence": 0.0-1.0}

  "code_agent:sub:code_writer":
    agent_id: code_agent
    node: sub_agent
    sub_agent: code_writer
    system: |
      你是专业编程助手，擅长 Python、Go 和系统设计。

  "code_agent:respond":
    agent_id: code_agent
    node: respond
    system: |
      你是响应格式化器。将子代理输出整理为用户友好的回复。
```

读取方式：

```python
from artipivot.config.center import ConfigCenter

cc = ConfigCenter(store, notifier)
await cc.start()

prompt = cc.prompts.get("code_agent", "classify")       # → classify 提示词
sub_prompt = cc.prompts.get("code_agent", "sub_agent", sub_agent="code_writer")
```

---

## 管理 API

```bash
# 路由
GET  /admin/routing/{agent_id}

# 提示词
PUT  /admin/prompts/{agent_id}/{node}
{"system": "新的系统提示词..."}

# 限流
GET  /admin/ratelimits
PUT  /admin/ratelimits/agent/{agent_id}
{"user_rpm": 30, "agent_rpm": 100, "tool_timeout_ms": 60000}
PUT  /admin/ratelimits/tool/{tool_name}
{"rpm": 50, "timeout_ms": 30000}

# 模型（由 models/provider.py 提供）
GET  /admin/models/{agent_id}
PUT  /admin/models/{agent_id}
{"provider": "anthropic", "name": "claude-opus-4-6"}
PUT  /admin/models/{agent_id}/{sub_agent}
{"provider": "openai", "name": "gpt-4o", "fallback": {"provider": "openai", "name": "gpt-4o-mini"}}
```

---

## 热更新流程

ConfigCenter 启动时从 DocumentStore 全量加载，同时订阅 ChangeNotifier：

```
启动 → 加载 model_configs → 加载 prompt_configs → 加载 routing_configs → 加载 ratelimit_configs
  │
  └→ subscribe("model_configs", callback)    → ModelProvider 刷新
  └→ subscribe("prompt_configs", callback)   → PromptStore 刷新
  └→ subscribe("routing_configs", callback)  → RoutingConfig 刷新 + 触发 GraphRebuilder
  └→ subscribe("ratelimit_configs", callback) → RateLimiter 刷新
```

运行时通过 Admin API 修改 → DocumentStore.put() → ChangeNotifier.notify() → 对应回调自动触发。

注意：**模型、提示词、限流的热更新不需要重建图**，只有路由规则变更才触发 `GraphRebuilder.rebuild_agent()`。
