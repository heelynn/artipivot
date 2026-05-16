# Transform 系统 — 数据编排与热加载

## 概述

子代理的输出（多个 tool 调用结果、多个子代理返回值）经常需要合并、过滤、格式化等数据变换。Transform 系统提供一种轻量机制：**Python 函数管数据变换，注册表管生命周期，热加载即时生效。**

核心原则：**Transform 变更不触发图重建。** 图节点在执行时（而非构建时）从注册表获取函数引用，因此替换函数后下一次图执行自动生效。这和 PromptStore 的模式一致 — 提示词更新不重建图，下次节点执行读到新值。

---

## 注册来源

Transform 函数可以来自任意位置 — 本地文件、pip 包、git 仓库 — 框架只关心"能不能 import 到"。

| 来源 | 时机 | 需重启 | 适用 |
|------|------|:------:|------|
| **Entry Points** | 启动自动发现 | 是 | pip 包分发，团队共享 |
| **YAML 配置** | 启动加载 + 热加载 | 否 | 部署时配置，运行时调整 |
| **REST API** | 运行时即时注册 | 否 | 临时调试，动态操作 |

### Entry Points（pip 包）

外部包声明 entry point，`pip install` 后自动发现：

```toml
# my-transforms / pyproject.toml
[project.entry-points."artipivot.transforms"]
merge_results = "my_transforms.merge:merge_results"
```

```python
registry = TransformRegistry()
registry.discover_entry_points()  # 扫描所有已安装包
```

新增包需 `pip install` + 重启（`importlib.metadata` 读的是安装时元数据）。

### YAML 配置

```yaml
# config/seed/transforms.yaml
transforms:
  merge_results:
    module: my_transforms.merge
    function: merge_results
```

启动时通过 `load_transforms_seed(registry)` 加载。运行时通过 DocumentStore → ChangeNotifier → TransformWatcher 热加载，改配置不重启。

单个 transform 导入失败时跳过并记录 warning，不阻塞其余 transform。

### REST API

```bash
# 注册（即时生效）
curl -X POST http://localhost:8000/admin/transforms/register \
  -d '{"name": "merge", "module": "my_transforms.merge", "function": "merge_results"}'

# 列出
curl http://localhost:8000/admin/transforms

# 注销
curl -X DELETE http://localhost:8000/admin/transforms/merge
```

---

## TransformRegistry

`src/artipivot/transforms/registry.py` — 核心注册表，线程安全（`threading.RLock`）。

### API

| 方法 | 说明 |
|------|------|
| `register(name, fn, *, source)` | 注册函数。非 callable 抛 TypeError，同名覆盖 |
| `unregister(name)` | 注销。不存在抛 KeyError |
| `get(name) -> TransformFn` | 获取函数。不存在抛 KeyError（含可用名称列表） |
| `has(name) -> bool` | 是否已注册 |
| `list_transforms() -> list[dict]` | 所有元数据 |
| `names -> list[str]` | 所有注册名 |
| `discover_entry_points() -> list[str]` | 从 importlib.metadata 自动发现 |
| `register_module(name, module_path, fn_name, *, source, reload=False)` | 动态导入并注册。`reload=True` 强制重载已导入模块 |
| `async invoke(name, data) -> dict` | 调用函数，自动区分 sync/async。失败时记录日志后 re-raise |

### 元数据

每次注册自动记录来源信息，`list_transforms()` 返回：

```python
{"name": "merge_results", "source": "yaml", "is_async": True, "module": "my_transforms.merge", "qualname": "merge_results"}
```

`source` 取值：`manual` / `entry_point` / `yaml` / `api` / `hot_reload`

---

## TransformWatcher

`src/artipivot/transforms/watcher.py` — 订阅 ChangeNotifier 的 `transform_configs` 集合，收到变更后替换注册表中的函数引用。

### 和 PluginWatcher 的区别

| | PluginWatcher | TransformWatcher |
|---|---|---|
| 变更后动作 | 触发 GraphRebuilder 重建整个图 | 只替换注册表中的函数引用 |
| 影响范围 | 整个 Agent 的 CompiledStateGraph | 仅该 Transform 的后续调用 |
| 开销 | 需重新编译 StateGraph | dict 赋值，几乎无开销 |

### 热加载链路

```
DocumentStore.put("transform_configs", ...)
    ↓
ChangeNotifier.notify()
    ↓
TransformWatcher.apply()
    ├── delete → registry.unregister()
    └── upsert → registry.register_module(source="hot_reload")
         ├── 成功 → 函数引用替换，下次执行生效
         └── ImportError/AttributeError → 记录 warning，跳过
```

---

## 图节点集成

`src/artipivot/transforms/nodes.py` — `make_transform_node()` 返回 LangGraph 兼容的异步节点。

```python
from artipivot.transforms import make_transform_node

node = make_transform_node(
    "merge_results",       # 注册表中的名称
    registry,              # TransformRegistry 实例
    input_key="metadata",  # 从 State 读哪个 key（默认 "metadata"）
    output_key="metadata", # 写到 State 哪个 key（默认 "metadata"）
)

builder = StateGraph(MyState)
builder.add_node("merge", node)
```

**为什么热加载不需要重建图：** 节点闭包持有 `registry` + `transform_name`，每次执行时调用 `registry.invoke(name, data)` 动态获取当前函数。注册表中替换函数后，下一次执行自动使用新函数。

---

## Transform 函数规范

签名：`(data: dict) -> dict`，支持 sync 和 async。

```python
# sync
def merge_results(data: dict) -> dict:
    return {**data, "summary": " | ".join(r["content"] for r in data.get("results", []))}

# async（需要 IO 时）
async def enrich(data: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.example.com/{data['id']}")
    return {**data, "context": resp.json()}
```

建议：返回新 dict 而非修改输入，用 `data.get()` 避免 KeyError。

---

## ConfigCenter 集成

ConfigCenter 启动时自动加载 Transform 配置并订阅变更：

```python
config_center = ConfigCenter(store, notifier, transform_registry=registry)
await config_center.start()
#   1. _load_all() → 从 DocumentStore 读取 transform_configs → 触发注册
#   2. subscribe("transform_configs", TransformWatcher.apply)
```

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `transforms/__init__.py` | 模块导出 |
| `transforms/registry.py` | 核心注册表 |
| `transforms/watcher.py` | 热加载 |
| `transforms/loader.py` | YAML 种子加载 |
| `transforms/nodes.py` | LangGraph 节点工厂 |
| `config/seed/transforms.yaml` | 种子配置 |
