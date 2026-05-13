import asyncio
import time
from datetime import datetime, timedelta

from app.harness.memory import MemoryItem, ShortTermStore, MemoryManager
from app.harness.enums import MemoryScope


# ── MemoryItem ──

def test_memory_item_defaults():
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.WORKING, source="user_1")
    assert item.id == "t1"
    assert item.score == 0.0
    assert item.access_count == 0
    assert item.tags == []
    assert item.metadata == {}
    assert isinstance(item.created_at, datetime)


def test_memory_item_not_expired():
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.WORKING,
                      source="user_1", ttl_seconds=3600)
    assert item.is_expired is False


def test_memory_item_expired():
    past = datetime.now() - timedelta(seconds=100)
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.WORKING,
                      source="user_1", ttl_seconds=10, created_at=past)
    assert item.is_expired is True


def test_memory_item_no_ttl_never_expires():
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.USER, source="user_1")
    assert item.is_expired is False


def test_memory_item_touch():
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.WORKING, source="user_1")
    old_accessed = item.accessed_at
    old_count = item.access_count
    time.sleep(0.01)
    item.touch()
    assert item.accessed_at > old_accessed
    assert item.access_count == old_count + 1


# ── ShortTermStore ──

def _make_item(item_id="t1", scope=MemoryScope.WORKING, content="test content",
               score=1.0, tags=None, ttl=None):
    return MemoryItem(id=item_id, content=content, scope=scope,
                      source="test", score=score, tags=tags or [], ttl_seconds=ttl)


def test_sts_put_and_get():
    store = ShortTermStore()
    item = _make_item()
    store.put(item)
    result = store.get("t1")
    assert result is not None
    assert result.content == "test content"


def test_sts_get_expired():
    store = ShortTermStore()
    item = _make_item(ttl=0)
    store.put(item)
    time.sleep(0.01)
    assert store.get("t1") is None


def test_sts_lru_eviction():
    store = ShortTermStore(max_size=3)
    for i in range(5):
        store.put(_make_item(item_id=f"t{i}", scope=MemoryScope.SESSION))
    assert len(store._cache) == 3
    assert store.get("t0") is None
    assert store.get("t1") is None
    assert store.get("t4") is not None


def test_sts_recall_keyword_match():
    store = ShortTermStore()
    store.put(_make_item(item_id="t1", content="二分查找算法", scope=MemoryScope.SESSION))
    store.put(_make_item(item_id="t2", content="快速排序", scope=MemoryScope.SESSION))
    results = store.recall("二分", [MemoryScope.SESSION])
    assert len(results) == 1
    assert results[0].id == "t1"


def test_sts_recall_tag_match():
    store = ShortTermStore()
    store.put(_make_item(item_id="t1", content="算法分析", scope=MemoryScope.SESSION,
                         tags=["二分查找", "时间复杂度"]))
    results = store.recall("二分查找", [MemoryScope.SESSION])
    assert len(results) == 1


def test_sts_recall_scope_filter():
    store = ShortTermStore()
    store.put(_make_item(item_id="t1", content="global info", scope=MemoryScope.GLOBAL))
    store.put(_make_item(item_id="t2", content="session info", scope=MemoryScope.SESSION))
    results = store.recall("info", [MemoryScope.GLOBAL])
    assert len(results) == 1
    assert results[0].scope == MemoryScope.GLOBAL


def test_sts_items_to_persist_filters():
    store = ShortTermStore()
    store.put(_make_item(item_id="t1", content="working", scope=MemoryScope.WORKING))
    store.put(_make_item(item_id="t2", content="session", scope=MemoryScope.SESSION))
    store.put(_make_item(item_id="t3", content="global", scope=MemoryScope.GLOBAL))
    persistable = store.items_to_persist()
    ids = {i.id for i in persistable}
    assert "t2" in ids
    assert "t3" in ids
    assert "t1" not in ids


def test_sts_clear():
    store = ShortTermStore()
    store.put(_make_item())
    store.clear()
    assert len(store._cache) == 0


def test_sts_remove():
    store = ShortTermStore()
    store.put(_make_item(item_id="r1"))
    assert store.remove("r1") is True
    assert store.remove("r1") is False
    assert store.get("r1") is None


# ── MemoryManager ──

def _make_mgr():
    return MemoryManager(short_term=ShortTermStore())


def test_mgr_memorize_returns_id():
    mgr = _make_mgr()
    mid = mgr.memorize("二分查找核心", MemoryScope.SESSION)
    assert mid.startswith("session_")


def test_mgr_memorize_with_tags():
    mgr = _make_mgr()
    mgr.memorize("test", MemoryScope.SESSION, tags=["算法"])
    results = mgr.recall("算法", None, [MemoryScope.SESSION])
    assert len(results) == 1


def test_mgr_recall_short_term_only():
    mgr = _make_mgr()
    mgr.memorize("hello world", MemoryScope.SESSION)
    results = mgr.recall("hello", None, [MemoryScope.SESSION])
    assert len(results) == 1


def test_mgr_recall_empty():
    mgr = _make_mgr()
    results = mgr.recall("nothing", None, [MemoryScope.SESSION])
    assert len(results) == 0


def test_mgr_forget():
    mgr = _make_mgr()
    mid = mgr.memorize("to forget", MemoryScope.SESSION)
    assert mgr.forget(mid) is True
    assert mgr.forget("nonexistent") is False


def test_mgr_flush_clears():
    mgr = _make_mgr()
    mgr.memorize("temp", MemoryScope.WORKING)
    mgr.memorize("persist", MemoryScope.SESSION)
    asyncio.run(mgr.flush_session("s1"))
    assert len(mgr.recall("temp", None, [MemoryScope.WORKING])) == 0
    assert len(mgr.recall("persist", None, [MemoryScope.SESSION])) == 0


# ── Episode scope ──

def test_episode_scope_exists():
    assert MemoryScope.EPISODE == "episode"


def test_memory_scope_has_5_values():
    assert len(MemoryScope) == 5
    assert set(MemoryScope.__members__.keys()) == {
        "WORKING", "EPISODE", "SESSION", "USER", "GLOBAL"
    }
