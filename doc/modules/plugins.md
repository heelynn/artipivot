# 插件系统与图热重建

## 架构

```mermaid
flowchart LR
    PM["PluginManager<br/>publish()"] --> DS["DocumentStore<br/>plugins 集合"]
    PM --> CN["ChangeNotifier<br/>notify()"]

    CN --> PW["PluginWatcher<br/>subscribe('plugins')"]
    PW --> GR["GraphRebuilder<br/>rebuild_agent()"]

    subgraph Rebuild["热重建流程"]
        GR --> |"1. 读取插件"| List["list_plugins(active)"]
        GR --> |"2. 构建子代理"| Subs["_build_sub_agents()"]
        GR --> |"3. 构建主图"| Factory["GraphFactory.build()"]
        GR --> |"4. 原子替换"| GW["Gateway.register()"]
    end

    CC["ConfigCenter"] --> |"on_routing_change"| GR

    subgraph Key["Key 格式"]
        Format["{plugin_type}:{agent_id}:{name}<br/>例: sub_agent:code_agent:writer"]
    end
```

## 插件元数据管理

```python
from artipivot.plugins.manager import PluginManager, PluginDocument

pm = PluginManager(store, notifier)

plugin = PluginDocument(
    plugin_type="sub_agent",     # sub_agent | tool | pipeline
    name="writer",
    version="1.0",
    agent_id="code_agent",
    manifest={
        "strategy": "react",
        "tools": ["web_search", "code_exec"],
        "system_prompt": "You are a coding assistant.",
        "strategy_config": {"max_iterations": 5},
    },
)
await pm.publish(plugin)  # 自动设置时间戳 + 触发 ChangeNotifier
```

查询与弃用：

```python
plugins = await pm.list_plugins(agent_id="code_agent", status="active")
plugin = await pm.get_plugin("sub_agent", "writer", "code_agent")
await pm.deprecate("sub_agent", "writer", "code_agent")
```

## 图热重建

```python
from artipivot.plugins.rebuilder import GraphRebuilder

rebuilder = GraphRebuilder(gateway, factory, tools, pm)
await rebuilder.rebuild_agent("code_agent")
```

重建流程：读取插件 → 构建子代理 → 构建主图 → `gateway.register()` 原子替换（dict 赋值）

**隔离保证**：重建 Agent A 不影响 Agent B 的图引用。

## PluginWatcher 自动重建

```python
from artipivot.plugins.watcher import PluginWatcher

watcher = PluginWatcher(notifier, rebuilder)
await watcher.start()
# 此后 publish/deprecate 自动触发图重建
```

端到端流程：`publish → DocumentStore.put → ChangeNotifier.notify → PluginWatcher → GraphRebuilder → Gateway.register`

## ConfigCenter 路由回调

```python
config_center = ConfigCenter(store, notifier, on_routing_change=rebuilder.rebuild_agent)
await config_center.start()
# 路由配置变更 → 自动重建图
```
