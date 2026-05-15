# 可观测性与 API（Observability + API + CLI）

## 可观测性架构

```
请求入口                      structlog                     输出
────────                     ────────                     ────
Gateway.invoke()  ──→  bind_trace_id()            ┌──→  文件日志（按日轮转）
     │                   contextvars 自动传播       │
     ├─ classify 节点 ──── trace_id/agent_id/user_id ├──→  8 通道 JSON
     ├─ 子代理节点    ──── 全链路不断裂              │
     ├─ 工具调用      ────                            │
     └─ respond 节点  ──── clear_trace()            └──→  OTel（可选）
```

## 8 通道日志

| 通道 | 覆盖范围 | 典型事件 |
|------|---------|---------|
| **trace** | 请求全生命周期 | `request.start` → `request.end`，含耗时 |
| **session** | 会话级（thread_id） | 会话创建、会话恢复 |
| **llm** | 模型调用 | prompt、response、token 用量 |
| **tool** | 工具调用 | 工具名、入参、结果、耗时 |
| **memory** | 记忆操作 | Checkpointer 保存/读取、Store 读写 |
| **error** | 异常 | ERROR+ 级别含完整堆栈（保留 90 天） |
| **audit** | 管理操作 | 配置变更、插件发布（保留 365 天） |
| **main** | 全量聚合 | INFO+ 级别，所有通道的汇总 |

### 使用方式

```python
from artipivot.observability.logging import configure_logging, get_logger
from artipivot.observability.trace import bind_trace_id, generate_trace_id, clear_trace

configure_logging(log_dir="logs", level="INFO")

# 请求入口（Gateway 自动处理）
trace_id = generate_trace_id()
bind_trace_id(trace_id, agent_id="code_agent", user_id="alice", thread_id="s1")

logger = get_logger("llm")
logger.info("llm.call", model="claude-sonnet-4-6", prompt_tokens=150, response_tokens=300)
logger.info("llm.response", content="这是回复内容")

# 请求结束（Gateway 自动处理）
clear_trace()
```

**注意**：trace_id 的绑定和清理由 `AgentGateway.invoke()` 自动处理，业务代码无需手动调用。

---

## OpenTelemetry（可选）

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

启用后自动采集：

| 指标类型 | 内容 |
|----------|------|
| Histogram | 请求耗时、classify 耗时、工具调用耗时 |
| Counter | 工具错误数、意图分布、熔断器打开次数 |

未启用时零开销。

```python
from artipivot.observability.otel import setup_otel

# FastAPI 自动埋点
setup_otel(app)  # 在 create_app() 中自动调用
```

---

## REST API 端点

### Chat API

```bash
POST /api/v1/chat/{agent_id}
Content-Type: application/json

{
  "message": "写个快速排序",
  "thread_id": "session_1",    # 可选，不传自动生成
  "user_id": "alice"           # 必填
}

# 响应
{
  "message": "以下是快速排序的 Python 实现...",
  "agent_id": "code_agent",
  "thread_id": "session_1",
  "trace_id": "a1b2c3d4..."
}
```

### 管理 API

健康检查：

```bash
GET /health
GET /admin/health
```

插件管理：

```bash
GET    /admin/plugins
GET    /admin/plugins?agent_id=code_agent&status=active

POST   /admin/plugins
{
  "plugin_type": "sub_agent",
  "name": "writer",
  "version": "1.0.0",
  "agent_id": "code_agent",
  "manifest": {
    "strategy": "react",
    "tools": ["web_search", "code_exec"],
    "system_prompt": "You are a coding assistant."
  }
}

DELETE /admin/plugins/{type}/{agent_id}/{name}
```

模型配置：

```bash
GET  /admin/models/{agent_id}

PUT  /admin/models/{agent_id}
{"provider": "anthropic", "name": "claude-sonnet-4-6"}

PUT  /admin/models/{agent_id}/{sub_agent}
{"provider": "openai", "name": "gpt-4o"}
```

路由配置：

```bash
GET  /admin/routing/{agent_id}
```

限流配置：

```bash
GET  /admin/ratelimits

PUT  /admin/ratelimits/agent/{agent_id}
{"user_rpm": 30, "agent_rpm": 100}

PUT  /admin/ratelimits/tool/{tool_name}
{"rpm": 50, "timeout_ms": 30000}
```

---

## CLI 命令

```bash
# 启动服务器
artipivot serve --port 8000
artipivot serve --host 0.0.0.0 --port 8000 --reload

# 插件
artipivot plugin init my_plugin --template react
artipivot plugin publish my_plugin --agent-id code_agent

# 列出已注册 Agent
artipivot agents
```

---

## 接入流程

最小化启动的完整步骤：

```python
import asyncio

async def main():
    # 1. 存储
    from artipivot.storage.memory import InMemoryDocumentStore, InProcessNotifier
    store = InMemoryDocumentStore()
    notifier = InProcessNotifier()

    # 2. 种子配置
    from artipivot.models.loader import load_seed_if_empty
    await load_seed_if_empty(store, "config/seed")

    # 3. 模型 + 配置中心
    from artipivot.models.provider import ModelProvider
    from artipivot.config.center import ConfigCenter
    model_provider = ModelProvider(store, notifier)
    config_center = ConfigCenter(store, notifier)
    await model_provider.start()
    await config_center.start()

    # 4. 工具注册
    from artipivot.tools.registry import ToolRegistry
    from artipivot.tools.builtin.web_search import web_search
    from artipivot.tools.builtin.code_exec import code_exec
    tools = ToolRegistry({"web_search": web_search, "code_exec": code_exec})

    # 5. Gateway + 注册 Agent
    from artipivot.gateway.gateway import AgentGateway
    from artipivot.graph.factory import GraphFactory
    from artipivot.gateway.registry import AgentRegistry
    from artipivot.gateway.loader import load_agent_defs

    gateway = AgentGateway(model_provider)
    factory = GraphFactory(config_center)
    registry = AgentRegistry(gateway, factory, tools)

    for agent_def in load_agent_defs("config/seed").values():
        registry.register_def(agent_def)

    # 6. 调用
    result = await gateway.invoke("code_agent", "写个排序函数", "session_1")
    print(result["messages"][-1].content)

asyncio.run(main())
```
