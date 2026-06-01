import pytest

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


# ===== Task 1: IndexProvider protocol + Chunk/SearchResult data classes =====

from app.infrastructure.rag.coordinator import Chunk, SearchResult, IndexProvider


def test_chunk_defaults():
    c = Chunk(content="hello", score=0.9, source="vector")
    assert c.content == "hello"
    assert c.score == 0.9
    assert c.source == "vector"
    assert c.metadata == {}


def test_search_result_empty():
    sr = SearchResult(chunks=[], total_found=0, sources_used=[])
    assert sr.chunks == []
    assert sr.total_found == 0


def test_index_provider_is_abstract():
    """IndexProvider 是抽象协议，不能直接实例化。"""
    with pytest.raises(TypeError):
        IndexProvider()  # noqa  # 抽象类不可实例化


def test_index_provider_subclass_must_implement_all():
    """缺少抽象方法实现的子类不可实例化。"""

    class _BadProvider(IndexProvider):
        pass

    with pytest.raises(TypeError):
        _BadProvider()  # noqa
