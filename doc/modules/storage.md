# 存储层（Registry / StorageProvider / SQLite）

存储层采用 **两槽注册表 + 门面 + DocumentStore** 架构。`memory` 模式用 SQLite 本地持久化，`persistent` 模式接外部数据库。

## 目录结构

```
src/artipivot/storage/
  __init__.py    # 公共 API 导出
  base.py        # ABC：DocumentStore, ChangeNotifier
  sqlite.py      # SQLite 本地持久化实现
  memory.py      # InProcessNotifier（变更通知）
  factory.py     # BackendFactory ABC + MemoryFactory + PostgresFactory
  registry.py    # 两槽注册表（memory + persistent）
  provider.py    # StorageProvider 门面 + StorageConfig
  search.py      # EmbeddingConfig + resolve_search_strategy
  bundle.py      # StorageBundle（已弃用）
```

## 技术配置——不进 YAML

存储是技术/运维决策，通过 `.env` 配置：

```bash
# .env
# 默认 memory → SQLite 本地持久化（.artipivot/data.db），零配置
ARTIPIVOT_STORAGE_MODE=memory

# 生产环境 → 外部数据库
# ARTIPIVOT_STORAGE_MODE=persistent
# DATABASE_URI=postgresql://user:password@localhost:5432/artipivot
```

代码注册持久化后端：

```python
from artipivot.storage.registry import register_persistent
from artipivot.storage.factory import PostgresFactory

register_persistent(PostgresFactory())
```

## 存储类型常量（factory.py）

4 种存储类型：

| 常量 | 值 | 用途 |
|------|----|------|
| `TYPE_CHECKPOINTER` | `"checkpointer"` | 图状态持久化（LangGraph checkpointer） |
| `TYPE_STORE` | `"store"` | 跨线程长期记忆（LangGraph store） |
| `TYPE_DOCUMENT_STORE` | `"document_store"` | 文档 CRUD（tool/sub-agent/配置记录） |
| `TYPE_CHANGE_NOTIFIER` | `"change_notifier"` | 变更订阅/通知 |

## BackendFactory（factory.py）

```python
class BackendFactory(ABC):
    @property
    def name(self) -> str                    # 唯一标识，如 "memory"、"postgres"

    def supports(self, type: str) -> bool    # 是否支持某种存储类型

    @property
    def supports_search(self) -> bool        # store 是否支持向量搜索（默认 False）

    def create(self, type: str, config: dict) -> Any  # 创建后端实例
```

### MemoryFactory

默认工厂，所有类型均使用进程内/本地实现：

| 类型 | 实现 |
|------|------|
| `TYPE_CHECKPOINTER` | `langgraph.checkpoint.memory.InMemorySaver` |
| `TYPE_STORE` | `langgraph.store.memory.InMemoryStore` |
| `TYPE_DOCUMENT_STORE` | `SQLiteDocumentStore` → `.artipivot/data.db` |
| `TYPE_CHANGE_NOTIFIER` | `InProcessNotifier` |

### PostgresFactory

生产级后端，需要 `uri` 参数或 `DATABASE_URI` 环境变量。`supports_search = True`（pgvector）。

## 注册表（registry.py）

两槽设计——`memory` 内置，`persistent` 开发者注册：

```python
# 内置，始终可用
_memory_factory = MemoryFactory()

# 持久化槽位，开发者注册
_persistent_factory: BackendFactory | None = None
```

API：

| 函数 | 说明 |
|------|------|
| `register_persistent(factory)` | 注册持久化后端工厂 |
| `get_persistent()` | 获取已注册的持久化工厂（或 None） |
| `resolve(mode, type_key)` | 按 mode 解析工厂："memory" → MemoryFactory，"persistent" → 已注册工厂 |
| `available_backends(type=None)` | 列出可用后端名称 |

## StorageProvider（provider.py）

```python
from artipivot.storage.provider import StorageProvider, StorageConfig

config = StorageConfig(mode="memory")   # 或 "persistent"
provider = StorageProvider(config)
await provider.setup()

# 懒加载属性
checkpointer = provider.checkpointer      # LangGraph checkpointer
store = provider.store                    # LangGraph store
doc_store = provider.document_store       # DocumentStore
notifier = provider.change_notifier       # ChangeNotifier

# 健康检查
health = await provider.health_check()
# {"checkpointer": "ok", "store": "ok", "document_store": "ok", "change_notifier": "ok"}
```

## SQLiteDocumentStore（sqlite.py）

Python 内置 `sqlite3`，零外部依赖，数据落盘 `.artipivot/data.db`。

```sql
-- 表结构（自动创建）
CREATE TABLE documents (
    collection TEXT NOT NULL,    -- 集合名（tools / sub_agents / plugins / ...）
    key         TEXT NOT NULL,    -- 文档 key
    data        TEXT NOT NULL,    -- JSON 文档体
    PRIMARY KEY (collection, key)
);
CREATE INDEX idx_collection ON documents(collection);
```

查询使用 `json_extract(data, '$.field')` 做字段级过滤。不同 collection 存不同 JSON 结构——同一张表，集合隔离。

## DocumentStore API

```python
class DocumentStore(ABC):
    async def get(self, collection: str, key: str) -> dict | None       # 获取文档
    async def put(self, collection: str, key: str, data: dict) -> None   # 写入（upsert）
    async def delete(self, collection: str, key: str) -> None            # 删除
    async def query(self, collection: str, filter: dict) -> list[dict]   # 条件查询
```

当前使用的 collection：

| collection | key | 内容 |
|-----------|-----|------|
| `tools` | tool 名称 | `{name, type, module, function, status}` |
| `sub_agents` | sub-agent 名称 | `{name, strategy, tools, system_prompt, graph, status}` |
| `plugins` | `{type}:{agent_id}:{name}` | PluginDocument |
| `model_configs` | scope key | 模型配置 |
| `prompt_configs` | prompt key | 提示词模板 |
| `routing_configs` | agent_id | 路由配置 |
| `ratelimit_configs` | scope key | 限流配置 |

## ChangeNotifier — 热加载驱动

```python
class ChangeNotifier(ABC):
    async def subscribe(self, collection: str, callback: Callable) -> None
    async def notify(self, collection: str, key: str, action: str, data: dict) -> None
```

`InProcessNotifier` 在进程内维护 `collection → [callback]` 列表，同步 `await` 所有回调。

热加载链路：

```
DocumentStore.put("tools", "new_tool", {...})
  → ChangeNotifier.notify("tools", ...)
  → ToolWatcher._on_change()
  → ToolReloader.reload_one_tool()
  → ToolRegistry → AgentRegistry.rebuild_agent()
  → AgentGateway.register() 原子替换
```

## 使用示例

### 基础用法（默认 SQLite）

```python
from artipivot.storage.provider import StorageProvider, StorageConfig

provider = StorageProvider(StorageConfig(mode="memory"))
await provider.setup()

cp = provider.checkpointer      # InMemorySaver
ds = provider.document_store    # SQLiteDocumentStore → .artipivot/data.db
cn = provider.change_notifier   # InProcessNotifier
```

### 生产环境（PostgreSQL）

```python
import os
os.environ["DATABASE_URI"] = "postgresql://user:pass@localhost:5432/artipivot"

from artipivot.storage.registry import register_persistent
from artipivot.storage.factory import PostgresFactory
register_persistent(PostgresFactory())

provider = StorageProvider(StorageConfig(mode="persistent"))
await provider.setup()
```

### 注册自定义后端

```python
from artipivot.storage.factory import BackendFactory, TYPE_DOCUMENT_STORE
from artipivot.storage.registry import register_persistent

class MongoFactory(BackendFactory):
    @property
    def name(self): return "mongodb"

    def supports(self, type): return type == TYPE_DOCUMENT_STORE

    def create(self, type, config):
        uri = config.get("uri") or os.environ["MONGO_URI"]
        return MongoDocumentStore(uri)

register_persistent(MongoFactory())
```
