from app.harness.memory import MemoryManager
from app.harness.enums import MemoryScope


def test_memorize_and_recall():
    mgr = MemoryManager()
    mgr.memorize("二分查找的核心是折半", MemoryScope.GLOBAL)
    results = mgr.recall("二分查找", None, [MemoryScope.GLOBAL])
    assert len(results) == 1
    assert "二分查找" in results[0].content


def test_recall_filters_by_scope():
    mgr = MemoryManager()
    mgr.memorize("全局知识", MemoryScope.GLOBAL)
    mgr.memorize("会话记忆", MemoryScope.SESSION)
    results = mgr.recall("知识", None, [MemoryScope.GLOBAL])
    assert len(results) == 1
    assert results[0].scope == MemoryScope.GLOBAL


def test_recall_empty():
    mgr = MemoryManager()
    results = mgr.recall("不存在", None, [MemoryScope.GLOBAL])
    assert len(results) == 0


def test_memorize_returns_id():
    mgr = MemoryManager()
    mid = mgr.memorize("test", MemoryScope.WORKING)
    assert mid is not None
    assert len(mid) > 0
