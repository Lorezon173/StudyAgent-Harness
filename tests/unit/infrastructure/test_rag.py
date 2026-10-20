import pytest

from app.infrastructure.rag.code_index import CodeIndexProvider
from app.infrastructure.rag.coordinator import (
    Chunk,
    IndexProvider,
    RAGCoordinator,
    SearchResult,
    VisibilityContext,
)
from app.infrastructure.rag.ocr import OCRProvider
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
        IndexProvider()  # 抽象类不可实例化


def test_index_provider_subclass_must_implement_all():
    """缺少抽象方法实现的子类不可实例化。"""

    class _BadProvider(IndexProvider):
        pass

    with pytest.raises(TypeError):
        _BadProvider()


# ===== Task 5: multi-provider orchestration =====



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


# ===== RAG-C Phase 2（C-09）：VisibilityContext 受限检索 + provider outcome =====



class _FailingProvider(IndexProvider):
    """总是抛异常的 provider；异常消息带敏感串，用于验证不外泄（DEC-009）。"""

    name = "boom"

    def __init__(self, exc: Exception):
        self._exc = exc
        self.calls = 0

    def index(self, docs): pass

    def search(self, query, top_k=5):
        self.calls += 1
        raise self._exc

    @property
    def doc_count(self): return 0


class _SpyProvider(IndexProvider):
    """记录 search 调用次数的 provider，用于证明受限路径未触达非 vector 源。"""

    name = "spy"

    def __init__(self):
        self.calls = 0

    def index(self, docs): pass

    def search(self, query, top_k=5):
        self.calls += 1
        return []

    @property
    def doc_count(self): return 0


def test_search_result_outcome_defaults_backward_compatible():
    """旧式三参构造 SearchResult 仍可用（回归边界）。"""
    sr = SearchResult(chunks=[], total_found=0, sources_used=[])
    assert sr.outcome == "empty"
    assert sr.attempted_providers == []
    assert sr.failed_providers == []
    assert sr.error_code is None


def test_restricted_fake_search_filters_cross_user():
    """受限检索：global 可见 + 本人 private 可见 + 他人 private 不可见（DEC-001）。"""
    coord = RAGCoordinator()
    coord.index_documents([
        {"content": "公共的用户手册", "scope": "global", "user_id": None},
        {"content": "用户1的私有笔记", "scope": "private", "user_id": 1},
        {"content": "用户2的私有笔记", "scope": "private", "user_id": 2},
    ])
    result = coord.search("用户", visibility=VisibilityContext(user_id=1))
    contents = [c.content for c in result.chunks]
    assert "公共的用户手册" in contents
    assert "用户1的私有笔记" in contents
    assert "用户2的私有笔记" not in contents
    assert result.outcome == "ok"


def test_restricted_fake_search_fail_closed_on_ambiguous_rows():
    """歧义行（private+无主 / global+有主 / 未知 scope）fail closed（DEC-001）。"""
    coord = RAGCoordinator()
    coord.index_documents([
        {"content": "无主私有X", "scope": "private", "user_id": None},
        {"content": "带主全局X", "scope": "global", "user_id": 9},
        {"content": "未知scopeX", "scope": "shared", "user_id": 1},
        {"content": "合法私有X", "scope": "private", "user_id": 1},
    ])
    result = coord.search("X", visibility=VisibilityContext(user_id=1))
    contents = [c.content for c in result.chunks]
    assert contents == ["合法私有X"]


def test_restricted_fake_search_filters_before_limit():
    """过滤先于排序/LIMIT：未授权高分行不得抢占 top-k（DEC-001 §D.3）。"""
    coord = RAGCoordinator()
    docs = [{"content": "机" * 20, "scope": "private", "user_id": 99}]
    docs += [{"content": f"机器学习讲义{i}", "scope": "global", "user_id": None}
             for i in range(3)]
    coord.index_documents(docs)
    result = coord.search("机", top_k=1, visibility=VisibilityContext(user_id=1))
    contents = [c.content for c in result.chunks]
    assert len(contents) == 1
    assert "讲义" in contents[0]
    assert "机" * 20 not in contents


def test_partial_provider_failure_returns_degraded():
    """部分 provider 失败 → degraded，成功证据保留，失败来源如实记录。"""
    coord = RAGCoordinator()
    coord.index_documents([{"content": "向量检索证据"}])
    coord.register_provider(_FailingProvider(RuntimeError(
        "psycopg connect failed: postgresql://admin:secret@10.0.0.1/db")))
    result = coord.search("向量", sources=["vector", "boom"])
    assert result.outcome == "degraded"
    assert result.sources_used == ["vector"]
    assert result.attempted_providers == ["vector", "boom"]
    assert result.failed_providers == ["boom"]
    assert result.error_code == "provider_degraded"
    assert [c.content for c in result.chunks] == ["向量检索证据"]
    # DEC-009：结果对象不携带原始异常文本
    assert "secret" not in repr(result)


def test_all_providers_failed_returns_failed():
    """全部 provider 失败 → failed + db_error 分类码，不再伪装空结果。"""
    coord = RAGCoordinator()
    coord.register_provider(_FailingProvider(RuntimeError("db down sqlite:///prod.db")))
    result = coord.search("任意", sources=["boom"])
    assert result.outcome == "failed"
    assert result.chunks == []
    assert result.error_code == "db_error"
    assert result.sources_used == []


def test_timeout_exception_classified_as_timeout():
    """TimeoutError 归类为 timeout 分类码（不再被所有异常复用）。"""
    coord = RAGCoordinator()
    coord.register_provider(_FailingProvider(TimeoutError("slow")))
    result = coord.search("任意", sources=["boom"])
    assert result.outcome == "failed"
    assert result.error_code == "timeout"


def test_all_success_zero_chunks_returns_empty():
    """全部成功但零结果 → empty（真没数据，不伪装失败）。"""
    coord = RAGCoordinator()
    coord.register_provider(_SpyProvider())
    result = coord.search("任何", sources=["spy"])
    assert result.outcome == "empty"
    assert result.failed_providers == []


def test_restricted_explicit_non_vector_source_fails_safely():
    """受限 visibility 下显式选中非 vector provider → 安全失败，不发起调用。"""
    spy = _SpyProvider()
    coord = RAGCoordinator()
    coord.register_provider(spy)
    result = coord.search("任何", sources=["spy"], visibility=VisibilityContext(user_id=1))
    assert result.outcome == "failed"
    assert result.error_code == "invalid_request"
    assert result.chunks == []
    assert spy.calls == 0


def test_restricted_sources_none_only_vector_participates():
    """受限 visibility + sources=None → 仅 vector 参与，其余 provider 不被触达。"""
    spy = _SpyProvider()
    coord = RAGCoordinator()
    coord.register_provider(spy)
    result = coord.search("任何", sources=None, visibility=VisibilityContext(user_id=1))
    assert spy.calls == 0
    assert result.outcome == "empty"  # vector(fake) 无数据
    assert result.sources_used == []


def test_restricted_invalid_visibility_fails_closed():
    """非类型化 visibility（如裸字符串）→ fail closed，不进入 provider。"""
    coord = RAGCoordinator()
    result = coord.search("任何", visibility="user-1")
    assert result.outcome == "failed"
    assert result.error_code == "invalid_request"
    assert result.chunks == []


def test_restricted_missing_user_id_fails_closed():
    """VisibilityContext 缺失认证身份（user_id=None）→ fail closed。"""
    coord = RAGCoordinator()
    result = coord.search("任何", visibility=VisibilityContext(user_id=None))
    assert result.outcome == "failed"
    assert result.error_code == "invalid_request"


def test_coordinator_accepts_explicit_vector_provider_injection():
    """显式注入 vector provider（DEC-007 在线 composition 的装配入口）。"""
    class _ExplicitVector(IndexProvider):
        name = "vector"
        def index(self, docs): pass
        def search(self, query, top_k=5, visibility=None): return []
        @property
        def doc_count(self): return 0

    explicit = _ExplicitVector()
    coord = RAGCoordinator(vector_provider=explicit)
    assert coord.get_provider("vector") is explicit


# ===== RAG-B B3-06：index_documents 写入确认 =====


def test_index_documents_missing_provider_returns_none():
    """provider 缺失时不得静默 no-op：返回 None 表示未写入（B3-06）。"""
    coord = RAGCoordinator()
    assert coord.index_documents([{"content": "x"}], source="nonexistent") is None


def test_index_documents_confirms_written_count():
    """默认 fake vector provider 调用成功后返回可核验的写入条数。"""
    coord = RAGCoordinator()
    written = coord.index_documents(
        [{"content": "甲"}, {"content": "乙"}], source="vector")
    assert written == 2


def test_index_documents_propagates_unconfirmed_provider():
    """provider index 返回 None 时写入未确认，coordinator 不得推断成功。"""
    class _UnconfirmedVector(IndexProvider):
        name = "vector"
        def index(self, docs): return None
        def search(self, query, top_k=5, visibility=None): return []
        @property
        def doc_count(self): return 0

    coord = RAGCoordinator(vector_provider=_UnconfirmedVector())
    assert coord.index_documents([{"content": "甲"}], source="vector") is None
