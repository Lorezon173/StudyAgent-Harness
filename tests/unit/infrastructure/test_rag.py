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


# ===== Task 5: multi-provider orchestration =====

from app.infrastructure.rag.ocr import OCRProvider
from app.infrastructure.rag.code_index import CodeIndexProvider


def test_rag_coordinator_register_provider():
    coord = RAGCoordinator()
    ocr = OCRProvider()
    coord.register_provider(ocr)
    ocr.index([{"content": "注意力机制是深度学习的核心"}])
    result = coord.search("注意力", sources=["ocr"])
    assert result.total_found >= 1
    assert "ocr" in result.sources_used


def test_rag_coordinator_unregister_provider():
    coord = RAGCoordinator()
    ocr = OCRProvider()
    coord.register_provider(ocr)
    coord.unregister_provider("ocr")
    result = coord.search("注意力", sources=["ocr"])
    assert result.total_found == 0


def test_rag_coordinator_multi_source_search():
    coord = RAGCoordinator()
    coord.register_provider(OCRProvider())
    coord.register_provider(CodeIndexProvider())
    coord.index_documents([{"content": "RAG 是检索增强生成"}], source="vector")
    for p in coord._providers.values():
        if p.name == "ocr":
            p.index([{"content": "OCR 提取自图片的文本"}])
        if p.name == "code":
            p.index([{"content": "def train_model(): pass"}])
    result = coord.search("检索", sources=None, top_k=10)
    assert result.total_found >= 1
    assert len(result.sources_used) >= 1


def test_rag_coordinator_search_deduplicates():
    coord = RAGCoordinator()
    coord.index_documents([{"content": "完全相同的文本"}], source="vector")
    ocr = OCRProvider()
    ocr.index([{"content": "完全相同的文本"}])
    coord.register_provider(ocr)
    result = coord.search("完全相同", sources=None, top_k=10)
    contents = [c.content for c in result.chunks]
    assert contents.count("完全相同的文本") == 1


def test_rag_coordinator_retrieve_backward_compat():
    """Task 5 不破坏现有 retrieve() 签名。"""
    store = FakeRAGStore()
    store.index([{"content": "二分查找"}])
    coord = RAGCoordinator(store)
    result = coord.retrieve("二分查找")
    assert result["found"] is True
    assert len(result["citations"]) > 0


def test_rag_coordinator_search_sorts_by_score():
    coord = RAGCoordinator()
    coord.index_documents([
        {"content": "不太相关"},
        {"content": "高度相关高度相关高度相关"},
    ])
    result = coord.search("高度相关")
    assert len(result.chunks) >= 2
    assert result.chunks[0].score >= result.chunks[1].score


def test_rag_coordinator_search_default_sources_is_all():
    coord = RAGCoordinator()
    ocr = OCRProvider()
    ocr.index([{"content": "OCR 文本"}])
    coord.register_provider(ocr)
    result = coord.search("OCR")
    assert result.total_found >= 1


def test_rag_coordinator_vector_provider_registered_by_default():
    coord = RAGCoordinator()
    coord.index_documents([{"content": "默认向量存储"}])
    result = coord.search("向量")
    assert result.total_found >= 1
    assert "vector" in result.sources_used
