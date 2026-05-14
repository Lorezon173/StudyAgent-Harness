# 记忆系统重写 — 三层设计文档

> 日期：2026-05-13
> 方案：方案B — 核心一次性重写（Observability + Memory + LLM 联动）
> 优先级：第二阶段（可观测系统之后）
> 设计来源：brainstorming 产出的完整规划，后续 spec 编写以此为据

---

## 第一层：总览

```
目标：将 MemoryManager 从内存字典+子串匹配升级为
      短期记忆（会话级，TTL 衰减）+ 长期记忆（跨会话，摘要压缩+用户画像）
      的双层架构，持久化到 SQLite。

改动范围：
  - 重写 app/harness/memory.py（核心重写）
  - 重写 app/harness/state/memory.py（扩展 MemoryState）
  - 新增 app/infrastructure/storage/memory_store.py（SQLite 持久化）
  - 修改 app/harness/enums.py（扩展 MemoryScope）
  - 修改 app/infrastructure/llm.py（记忆摘要调用）
  - 新增 tests/unit/harness/test_memory.py（重写）
  - 新增 tests/unit/infrastructure/test_memory_store.py

不动：
  - 节点代码（通过 MemoryManager 接口不变）
  - specs/ 规范文件
  - 可观测系统（已完成设计，记忆模块可接入）
```

## 第二层：概述

```
┌─────────────────────────────────────────────────────┐
│                MemoryManager (门面)                  │
│  recall() / memorize() / forget() / summarize()     │
│  自动路由到短期或长期存储                              │
├────────────────────┬────────────────────────────────┤
│   短期记忆层        │   长期记忆层                    │
│   ShortTermStore   │   LongTermStore                │
│   ┌──────────────┐ │   ┌──────────────────────────┐ │
│   │内存 LRU 缓存  │ │   │ SQLite 持久化            │ │
│   │TTL 衰减      │ │   │ FTS5 全文检索             │ │
│   │会话结束清空   │ │   │ 摘要压缩（LLM 生成）     │ │
│   └──────────────┘ │   │ 用户画像持久化            │ │
│                    │   └──────────────────────────┘ │
├────────────────────┴────────────────────────────────┤
│  MemoryStore (SQLite) — 统一持久化层                 │
│  表: memory_entries / memory_summaries / user_profiles│
└─────────────────────────────────────────────────────┘
```

| 组件 | 职责 | 存储 | 生命周期 |
|------|------|------|----------|
| `MemoryManager` | 门面，自动路由短期/长期 | — | 随应用 |
| `ShortTermStore` | 当前会话的即时记忆 | 内存 LRU + TTL | 会话结束清空 |
| `LongTermStore` | 跨会话的持久记忆 | SQLite | 永久 |
| `MemoryStore` | SQLite CRUD | SQLite 文件 | 永久 |
| `MemoryScope` | 扩展为 5 级 | — | — |
| `MemoryState` | 扩展状态字段 | — | — |

## 第三层：详细实施计划

### 3.1 MemoryScope 扩展

```python
# app/harness/enums.py — 修改 MemoryScope

class MemoryScope(StrEnum):
    """记忆作用域 — 5级"""
    WORKING = "working"        # 当前轮次，即用即弃
    EPISODE = "episode"        # 当前会话内（新增）
    SESSION = "session"        # 单次会话，会话结束可压缩为长期
    USER = "user"              # 跨会话的用户级记忆
    GLOBAL = "global"          # 全局知识
```

> 新增 `EPISODE`：比 SESSION 更细，对应一次教学循环（诊断→讲解→评估），多个 episode 组成一个 session。

### 3.2 MemoryState 扩展

```python
# app/harness/state/memory.py — 扩展后

from typing import TypedDict, List, Optional

class MemoryState(TypedDict, total=False):
    # ── 现有字段 ──
    topic: Optional[str]
    topic_confidence: float
    topic_changed: bool
    topic_reason: str
    topic_context: str
    topic_segments: List[dict]
    comparison_mode: bool
    history: List[str]
    has_history: bool
    history_summary: str
    history_mastery: str
    # ── 新增字段 ──
    short_term_ids: List[str]       # 当前会话短期记忆条目 ID
    long_term_context: str          # 从长期记忆检索到的上下文
    user_profile_summary: str       # 用户画像摘要
    mastery_history: List[dict]     # 历次掌握度记录 [{"topic":..., "score":..., "date":...}]
```

### 3.3 MemoryItem 升级

```python
# app/harness/memory.py

from dataclasses import dataclass, field
from datetime import datetime
from app.harness.enums import MemoryScope

@dataclass
class MemoryItem:
    """记忆条目 — 统一数据模型"""
    id: str
    content: str
    scope: MemoryScope
    source: str                           # 来源节点/用户
    score: float = 0.0                    # 相关度/重要性
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    ttl_seconds: int | None = None        # None=永不过期
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        elapsed = (datetime.now() - self.created_at).total_seconds()
        return elapsed > self.ttl_seconds

    def touch(self):
        """访问时更新统计"""
        self.accessed_at = datetime.now()
        self.access_count += 1
```

### 3.4 ShortTermStore 实现

```python
from collections import OrderedDict
from typing import Optional

class ShortTermStore:
    """短期记忆：LRU 缓存 + TTL 衰减，会话级生命周期"""

    DEFAULT_TTL = {
        MemoryScope.WORKING: 60,       # 1分钟
        MemoryScope.EPISODE: 600,      # 10分钟
        MemoryScope.SESSION: 3600,     # 1小时
    }

    def __init__(self, max_size: int = 200):
        self._cache: OrderedDict[str, MemoryItem] = OrderedDict()
        self._max_size = max_size

    def put(self, item: MemoryItem) -> str:
        if item.ttl_seconds is None:
            item.ttl_seconds = self.DEFAULT_TTL.get(item.scope, 3600)
        self._cache[item.id] = item
        self._cache.move_to_end(item.id)
        self._evict()
        return item.id

    def get(self, item_id: str) -> Optional[MemoryItem]:
        item = self._cache.get(item_id)
        if item is None:
            return None
        if item.is_expired:
            del self._cache[item_id]
            return None
        item.touch()
        self._cache.move_to_end(item_id)
        return item

    def recall(self, query: str, scopes: list[MemoryScope],
               top_k: int = 5) -> list[MemoryItem]:
        self._purge_expired()
        results = []
        query_lower = query.lower()
        for item in self._cache.values():
            if item.scope not in scopes:
                continue
            # 关键词匹配 + 重要性加权
            if query_lower in item.content.lower() or \
               any(t in query_lower for t in item.tags):
                relevance = item.score * (1 + item.access_count * 0.1)
                results.append((item, relevance))
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:top_k]]

    def clear(self):
        self._cache.clear()

    def remove(self, item_id: str) -> bool:
        """移除指定条目，返回是否成功"""
        if item_id in self._cache:
            del self._cache[item_id]
            return True
        return False

    def items_to_persist(self) -> list[MemoryItem]:
        """会话结束时，返回 SESSION/USER/GLOBAL 级别的条目供长期存储"""
        return [
            item for item in self._cache.values()
            if item.scope in (MemoryScope.SESSION, MemoryScope.USER, MemoryScope.GLOBAL)
            and not item.is_expired
        ]

    # ── 内部 ──

    def _evict(self):
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def _purge_expired(self):
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for k in expired:
            del self._cache[k]
```

### 3.5 MemoryStore (SQLite 持久化层)

```python
# app/infrastructure/storage/memory_store.py

import aiosqlite
from datetime import datetime
from pathlib import Path
from app.harness.enums import MemoryScope
from app.harness.memory import MemoryItem

class MemoryStore:
    """SQLite 持久化存储 — 长期记忆"""

    def __init__(self, db_path: str = "data/memory.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                scope TEXT NOT NULL,
                source TEXT,
                score REAL DEFAULT 0,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                accessed_at TEXT,
                access_count INTEGER DEFAULT 0,
                user_id INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_scope ON memory_entries(scope);
            CREATE INDEX IF NOT EXISTS idx_user ON memory_entries(user_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                USING fts5(id, content, tags);
            CREATE TABLE IF NOT EXISTS memory_summaries (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                scope TEXT NOT NULL,
                summary TEXT NOT NULL,
                source_ids TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                topics TEXT DEFAULT '[]',
                mastery_summary TEXT DEFAULT '{}',
                learning_style TEXT DEFAULT '',
                total_sessions INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );
        """)
        await self._db.commit()

    async def store(self, item: MemoryItem, user_id: int | None = None) -> str:
        import json
        await self._db.execute(
            """INSERT OR REPLACE INTO memory_entries
               (id, content, scope, source, score, tags, metadata,
                created_at, accessed_at, access_count, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.id, item.content, item.scope, item.source, item.score,
             json.dumps(item.tags), json.dumps(item.metadata),
             item.created_at.isoformat(), item.accessed_at.isoformat(),
             item.access_count, user_id)
        )
        await self._db.execute(
            "INSERT OR REPLACE INTO memory_fts (id, content, tags) VALUES (?, ?, ?)",
            (item.id, item.content, " ".join(item.tags))
        )
        await self._db.commit()
        return item.id

    async def search(self, query: str, scopes: list[MemoryScope],
                     user_id: int | None = None, top_k: int = 5) -> list[MemoryItem]:
        import json
        scope_clause = ",".join("?" for _ in scopes)
        sql = f"""
            SELECT m.* FROM memory_entries m
            JOIN memory_fts f ON m.id = f.id
            WHERE m.scope IN ({scope_clause})
            AND memory_fts MATCH ?
        """
        params = [*scopes, query]
        if user_id is not None:
            sql += " AND m.user_id = ?"
            params.append(user_id)
        sql += " ORDER BY m.score DESC LIMIT ?"
        params.append(top_k)

        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._row_to_item(r, cursor) for r in rows]

    async def store_summary(self, user_id: int, scope: str,
                            summary: str, source_ids: list[str]) -> str:
        import json, uuid
        sid = str(uuid.uuid4())
        await self._db.execute(
            """INSERT INTO memory_summaries
               (id, user_id, scope, summary, source_ids, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sid, user_id, scope, summary, json.dumps(source_ids),
             datetime.now().isoformat())
        )
        await self._db.commit()
        return sid

    async def get_user_profile(self, user_id: int) -> dict | None:
        import json
        cursor = await self._db.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        result = dict(zip(cols, row))
        result["topics"] = json.loads(result.get("topics", "[]"))
        result["mastery_summary"] = json.loads(result.get("mastery_summary", "{}"))
        return result

    async def update_user_profile(self, user_id: int, **fields) -> None:
        import json
        sets, params = [], []
        for k, v in fields.items():
            sets.append(f"{k} = ?")
            params.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
        params.append(datetime.now().isoformat())
        params.append(user_id)
        sql = f"UPDATE user_profiles SET {', '.join(sets)}, updated_at = ? WHERE user_id = ?"
        await self._db.execute(sql, params)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    def _row_to_item(self, row, cursor) -> MemoryItem:
        """通过列名映射而非位置索引，防止表结构变更时静默出错"""
        import json
        cols = [d[0] for d in cursor.description]
        r = dict(zip(cols, row))
        return MemoryItem(
            id=r["id"], content=r["content"], scope=MemoryScope(r["scope"]),
            source=r.get("source", "") or "", score=r.get("score", 0) or 0.0,
            tags=json.loads(r.get("tags", "[]") or "[]"),
            metadata=json.loads(r.get("metadata", "{}") or "{}"),
            created_at=datetime.fromisoformat(r["created_at"]),
            accessed_at=datetime.fromisoformat(r["accessed_at"]) if r.get("accessed_at") else datetime.now(),
            access_count=r.get("access_count", 0) or 0,
        )
```

### 3.6 LongTermStore 实现

```python
# app/harness/memory.py (续)

class LongTermStore:
    """长期记忆：SQLite 持久化 + FTS5 检索 + LLM 摘要压缩

    注意：compress() 内部调用 LLM 是同步的（self._llm.invoke），
    这是设计意图 —— 摘要压缩在会话结束时同步执行，
    不在节点主路径上，不会阻塞图执行。
    其他方法（recall/memorize）全部 async。
    """

    def __init__(self, memory_store: MemoryStore, llm=None):
        self._store = memory_store
        self._llm = llm  # LLMService 或 FakeLLM，用于摘要压缩

    async def recall(self, query: str, scopes: list[MemoryScope],
                     user_id: int | None = None, top_k: int = 5) -> list[MemoryItem]:
        return await self._store.search(query, scopes, user_id, top_k)

    async def memorize(self, item: MemoryItem, user_id: int | None = None) -> str:
        return await self._store.store(item, user_id)

    async def compress(self, user_id: int, session_id: str,
                       items: list[MemoryItem]) -> str | None:
        """将一批短期记忆压缩为摘要，存入长期记忆"""
        if not items or not self._llm:
            return None
        combined = "\n".join(f"[{i.scope}]{i.content}" for i in items)
        summary_text = self._llm.invoke(
            "你是一个学习记忆整理助手。请将以下学习记录压缩为简洁摘要，保留关键知识点和掌握程度。",
            combined,
        )
        source_ids = [i.id for i in items]
        summary_id = await self._store.store_summary(
            user_id, "session_compression", summary_text, source_ids
        )
        return summary_id

    async def get_profile(self, user_id: int) -> dict | None:
        return await self._store.get_user_profile(user_id)

    async def update_profile(self, user_id: int, **fields) -> None:
        await self._store.update_user_profile(user_id, **fields)
```

### 3.7 MemoryManager 重写（门面）

```python
class MemoryManager:
    """记忆管理门面 — 自动路由短期/长期，对节点透明"""

    def __init__(self, short_term: ShortTermStore,
                 long_term: LongTermStore | None = None):
        self._short = short_term
        self._long = long_term

    # ── 对节点暴露的接口（签名不变）──

    def recall(self, query: str, user_id: int | None,
               scopes: list[MemoryScope]) -> list[MemoryItem]:
        """同步查询：仅查短期记忆（LRU 缓存），不触发 SQLite IO。
        需要长期记忆时请使用 recall_async()。
        """
        return self._short.recall(query, scopes)

    async def recall_async(self, query: str, user_id: int | None,
                           scopes: list[MemoryScope],
                           top_k: int = 5) -> list[MemoryItem]:
        """异步全量检索：短期 + 长期"""
        short_results = self._short.recall(query, scopes, top_k)
        long_results = []
        if self._long:
            long_scopes = [s for s in scopes
                           if s in (MemoryScope.USER, MemoryScope.GLOBAL)]
            if long_scopes:
                long_results = await self._long.recall(
                    query, long_scopes, user_id, top_k - len(short_results)
                )
        # 去重
        seen = {r.id for r in short_results}
        for r in long_results:
            if r.id not in seen:
                short_results.append(r)
                seen.add(r.id)
        return short_results

    def memorize(self, content: str, scope: MemoryScope,
                 user_id: int | None = None,
                 metadata: dict | None = None,
                 tags: list[str] | None = None) -> str:
        """写入短期记忆（长期由 flush 自动处理）"""
        import uuid
        item = MemoryItem(
            id=f"{scope.value}_{uuid.uuid4().hex[:8]}",
            content=content,
            scope=scope,
            source=f"user_{user_id or 'anon'}",
            tags=tags or [],
            metadata=metadata or {},
        )
        return self._short.put(item)

    async def memorize_persistent(self, content: str, scope: MemoryScope,
                                  user_id: int | None = None,
                                  metadata: dict | None = None,
                                  tags: list[str] | None = None) -> str:
        """直接写入长期记忆"""
        import uuid
        item = MemoryItem(
            id=f"{scope.value}_{uuid.uuid4().hex[:8]}",
            content=content,
            scope=scope,
            source=f"user_{user_id or 'anon'}",
            tags=tags or [],
            metadata=metadata or {},
        )
        if self._long:
            return await self._long.memorize(item, user_id)
        return self._short.put(item)

    def forget(self, item_id: str) -> bool:
        """从短期记忆移除"""
        return self._short.remove(item_id)

    # ── 会话生命周期 ──

    async def flush_session(self, session_id: str, user_id: int | None = None):
        """会话结束：短期→长期压缩 + 用户画像更新"""
        items = self._short.items_to_persist()
        if self._long and items and user_id:
            await self._long.compress(user_id, session_id, items)
        self._short.clear()

    async def summarize(self, user_id: int, session_id: str) -> str | None:
        """生成会话学习摘要"""
        items = self._short.items_to_persist()
        if self._long and items:
            return await self._long.compress(user_id, session_id, items)
        return None
```

### 3.8 LLMService 新增 summarize_memories 方法

```python
# app/infrastructure/llm.py — 新增

class LLMService:
    # ... 现有方法 ...

    def summarize_memories(self, memories: list[str]) -> str:
        """压缩多条记忆为摘要"""
        combined = "\n".join(f"- {m}" for m in memories)
        return self.invoke(
            "你是一个学习记忆整理助手。请将以下学习记录压缩为简洁摘要，保留关键知识点和掌握程度。",
            combined,
        )
```

### 3.9 测试计划

| 测试文件 | 覆盖内容 | 用例数 |
|----------|----------|--------|
| `test_memory.py` | MemoryItem TTL 过期判断 | 3 |
| `test_memory.py` | ShortTermStore LRU 淘汰 | 3 |
| `test_memory.py` | ShortTermStore TTL 清理 | 2 |
| `test_memory.py` | ShortTermStore recall 关键词+标签匹配 | 3 |
| `test_memory.py` | ShortTermStore items_to_persist 过滤 | 2 |
| `test_memory.py` | MemoryManager.recall 短期优先 | 2 |
| `test_memory.py` | MemoryManager.memorize 写入短期 | 2 |
| `test_memory.py` | MemoryManager.flush_session 压缩+清空 | 3 |
| `test_memory_store.py` | MemoryStore SQLite CRUD | 4 |
| `test_memory_store.py` | MemoryStore FTS5 全文检索 | 3 |
| `test_memory_store.py` | MemoryStore 用户画像读写 | 3 |
| `test_memory_store.py` | MemoryStore 摘要存储 | 2 |

合计：32 个测试用例
