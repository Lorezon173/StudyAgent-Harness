from app.infrastructure.rag.coordinator import RAGCoordinator
from app.infrastructure.rag.store import FakeRAGStore


def test_rag_coordinator_retrieve_empty():
    coord = RAGCoordinator()
    result = coord.retrieve("二分查找")
    assert result["found"] is False
    assert result["context"] == ""


def test_rag_coordinator_retrieve_with_docs():
    store = FakeRAGStore()
    store.index([{"content": "二分查找是一种搜索算法"}, {"content": "排序算法包括快速排序"}])
    coord = RAGCoordinator(store)
    result = coord.retrieve("二分查找")
    assert result["found"] is True
    assert len(result["citations"]) > 0


def test_fake_rag_store_query():
    store = FakeRAGStore()
    store.index([{"content": "Python 是一种编程语言"}])
    results = store.query("Python")
    assert len(results) == 1
    assert store.doc_count == 1
