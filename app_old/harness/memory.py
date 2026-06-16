import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.harness.enums import MemoryScope


@dataclass
class MemoryItem:
    """记忆条目 — 统一数据模型"""
    id: str
    content: str
    scope: MemoryScope
    source: str
    score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    ttl_seconds: int | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        elapsed = (datetime.now() - self.created_at).total_seconds()
        return elapsed > self.ttl_seconds

    def touch(self):
        self.accessed_at = datetime.now()
        self.access_count += 1


class ShortTermStore:
    """短期记忆：LRU 缓存 + TTL 衰减"""

    DEFAULT_TTL = {
        MemoryScope.WORKING: 60,
        MemoryScope.EPISODE: 600,
        MemoryScope.SESSION: 3600,
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
            if query_lower in item.content.lower() or \
               any(t in query_lower for t in item.tags):
                relevance = item.score * (1 + item.access_count * 0.1)
                results.append((item, relevance))
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:top_k]]

    def remove(self, item_id: str) -> bool:
        if item_id in self._cache:
            del self._cache[item_id]
            return True
        return False

    def clear(self):
        self._cache.clear()

    def items_to_persist(self) -> list[MemoryItem]:
        return [
            item for item in self._cache.values()
            if item.scope in (MemoryScope.SESSION, MemoryScope.USER, MemoryScope.GLOBAL)
            and not item.is_expired
        ]

    def _evict(self):
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def _purge_expired(self):
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for k in expired:
            del self._cache[k]


class LongTermStore:
    """长期记忆：SQLite 持久化 + FTS5 检索 + LLM 摘要压缩"""

    def __init__(self, memory_store, llm=None):
        self._store = memory_store
        self._llm = llm

    async def recall(self, query: str, scopes: list[MemoryScope],
                     user_id: int | None = None, top_k: int = 5) -> list[MemoryItem]:
        return await self._store.search(query, scopes, user_id, top_k)

    async def memorize(self, item: MemoryItem, user_id: int | None = None) -> str:
        return await self._store.store(item, user_id)

    async def compress(self, user_id: int, session_id: str,
                       items: list[MemoryItem]) -> str | None:
        if not items or not self._llm:
            return None
        combined = "\n".join(f"[{i.scope}]{i.content}" for i in items)
        summary_text = self._llm.invoke(
            "你是一个学习记忆整理助手。请将以下学习记录压缩为简洁摘要，保留关键知识点和掌握程度。",
            combined,
        )
        source_ids = [i.id for i in items]
        return await self._store.store_summary(
            user_id, "session_compression", summary_text, source_ids
        )

    async def get_profile(self, user_id: int) -> dict | None:
        return await self._store.get_user_profile(user_id)

    async def update_profile(self, user_id: int, **fields) -> None:
        await self._store.update_user_profile(user_id, **fields)


class MemoryManager:
    """记忆管理门面 — 自动路由短期/长期，对节点透明"""

    def __init__(self, short_term: ShortTermStore,
                 long_term: LongTermStore | None = None):
        self._short = short_term
        self._long = long_term

    def recall(self, query: str, user_id: int | None,
               scopes: list[MemoryScope]) -> list[MemoryItem]:
        """同步查询：仅查短期记忆"""
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
        return self._short.remove(item_id)

    async def flush_session(self, session_id: str, user_id: int | None = None):
        items = self._short.items_to_persist()
        if self._long and items and user_id:
            await self._long.compress(user_id, session_id, items)
        self._short.clear()

    async def summarize(self, user_id: int, session_id: str) -> str | None:
        items = self._short.items_to_persist()
        if self._long and items:
            return await self._long.compress(user_id, session_id, items)
        return None
