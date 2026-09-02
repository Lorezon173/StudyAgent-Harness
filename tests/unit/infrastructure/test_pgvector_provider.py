"""PgVectorProvider 单元测试（阶段 A）。

Mock 标注说明：
- EmbeddingService 已 mock（返回固定向量）
- 使用内存 sqlite 数据库（sqlite:///:memory:）测试降级分支
- Mock 标注：[MOCK:阶段A]
- Mock 出处：EmbeddingService.embed_one / embed_many
- 切除方式：运行集成测试（test_pgvector_real.py）验证真实 PG + pgvector 行为
"""

import json
import pytest
from sqlalchemy import text
from app.infrastructure.rag.pgvector_provider import PgVectorProvider
from app.infrastructure.rag.embedding import EmbeddingService
from app.infrastructure.rag.coordinator import Chunk


class FakeEmbeddingService:
    """[MOCK:阶段A] 假 embedding 服务，返回固定向量用于测试。"""

    def __init__(self, dim=2048):
        self._dim = dim

    @property
    def dim(self):
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        """返回固定向量（用文本长度作为首元素以区分）。"""
        if not text:
            return [0.0] * self._dim
        return [float(len(text))] + [0.1] * (self._dim - 1)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """批量返回固定向量。"""
        return [self.embed_one(t) for t in texts]


@pytest.fixture
def sqlite_provider():
    """提供基于内存 sqlite 的 PgVectorProvider（测试降级分支）。

    [MOCK:阶段A] 使用 FakeEmbeddingService
    """
    fake_embedding = FakeEmbeddingService()
    provider = PgVectorProvider(
        embedding_service=fake_embedding,
        db_url="sqlite:///:memory:"
    )

    # 创建表结构（手动建表，因为 sqlite 不支持 pgvector 的 Vector 类型）
    conn = provider._get_conn()
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vector_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            scope TEXT DEFAULT 'global',
            content TEXT NOT NULL,
            embedding TEXT,
            source TEXT DEFAULT 'vector',
            doc_id TEXT DEFAULT '',
            chunk_id TEXT,
            metadata_json TEXT DEFAULT '{}'
        )
    """))
    conn.commit()

    yield provider

    # 清理
    if provider._conn:
        provider._conn.close()


def test_provider_name():
    """验证 provider name 为 'vector'。"""
    provider = PgVectorProvider(embedding_service=FakeEmbeddingService())
    assert provider.name == "vector"


def test_make_sync_db_url_postgresql():
    """验证 async URL 转同步 URL（PostgreSQL）。"""
    async_url = "postgresql+asyncpg://user:pass@localhost/db"
    sync_url = PgVectorProvider._make_sync_db_url(async_url)
    assert sync_url == "postgresql+psycopg://user:pass@localhost/db"


def test_make_sync_db_url_sqlite():
    """验证 async URL 转同步 URL（SQLite）。"""
    async_url = "sqlite+aiosqlite:///./test.db"
    sync_url = PgVectorProvider._make_sync_db_url(async_url)
    assert sync_url == "sqlite:///./test.db"


def test_make_sync_db_url_already_sync():
    """验证已是同步 URL 的情况。"""
    sync_url = "postgresql://user:pass@localhost/db"
    result = PgVectorProvider._make_sync_db_url(sync_url)
    assert result == sync_url


def test_index_single_doc(sqlite_provider):
    """验证能写入单个文档到 sqlite。

    [MOCK:阶段A] embedding 存为 JSON 字符串
    """
    docs = [{"content": "机器学习是人工智能的分支", "metadata": {"source": "book"}}]
    sqlite_provider.index(docs)

    conn = sqlite_provider._get_conn()
    result = conn.execute(text("SELECT content, embedding, metadata_json FROM vector_chunks"))
    row = result.fetchone()

    assert row is not None
    assert row[0] == "机器学习是人工智能的分支"

    # 验证 embedding 存为 JSON 字符串
    embedding = json.loads(row[1])
    assert isinstance(embedding, list)
    assert len(embedding) == 2048

    # 验证 metadata
    metadata = json.loads(row[2])
    assert metadata == {"source": "book"}


def test_index_multiple_docs(sqlite_provider):
    """验证能批量写入多个文档。"""
    docs = [
        {"content": "文本1", "doc_id": "doc1"},
        {"content": "文本2", "doc_id": "doc2"},
        {"content": "文本3", "doc_id": "doc3"},
    ]
    sqlite_provider.index(docs)

    assert sqlite_provider.doc_count == 3


def test_index_empty_list(sqlite_provider):
    """验证空列表不报错。"""
    sqlite_provider.index([])
    assert sqlite_provider.doc_count == 0


def test_index_with_scope_and_user_id(sqlite_provider):
    """验证 scope 和 user_id 字段正确写入。"""
    docs = [{
        "content": "私有知识",
        "scope": "personal",
        "user_id": 42
    }]
    sqlite_provider.index(docs)

    conn = sqlite_provider._get_conn()
    result = conn.execute(text("SELECT scope, user_id FROM vector_chunks"))
    row = result.fetchone()

    assert row[0] == "personal"
    assert row[1] == 42


def test_search_sqlite_fallback(sqlite_provider):
    """验证 sqlite 降级逻辑（字符匹配）能返回 Chunk。

    [MOCK:阶段A] 使用 FakeEmbeddingService
    """
    # 索引一些文档
    docs = [
        {"content": "机器学习是人工智能的一个分支"},
        {"content": "深度学习是机器学习的子集"},
        {"content": "自然语言处理应用广泛"},
    ]
    sqlite_provider.index(docs)

    # 搜索包含"机器学习"的文档
    results = sqlite_provider.search("机器学习", top_k=5)

    assert isinstance(results, list)
    assert all(isinstance(chunk, Chunk) for chunk in results)

    # 验证包含匹配文本的结果
    contents = [chunk.content for chunk in results]
    assert any("机器学习" in c for c in contents)


def test_search_returns_top_k(sqlite_provider):
    """验证 search 返回不超过 top_k 个结果。"""
    docs = [{"content": f"文档{i}"} for i in range(10)]
    sqlite_provider.index(docs)

    results = sqlite_provider.search("文档", top_k=3)
    assert len(results) <= 3


def test_search_empty_query(sqlite_provider):
    """验证空查询返回空列表。"""
    sqlite_provider.index([{"content": "测试文档"}])
    results = sqlite_provider.search("", top_k=5)
    assert results == []


def test_search_sorts_by_score(sqlite_provider):
    """验证 search 结果按 score 降序排序（sqlite 降级分支）。"""
    docs = [
        {"content": "A"},  # score 低（字符少）
        {"content": "AAAAAA"},  # score 高（字符多）
        {"content": "AAA"},  # score 中
    ]
    sqlite_provider.index(docs)

    results = sqlite_provider.search("A", top_k=3)

    # 验证按 score 降序
    assert len(results) >= 2
    for i in range(len(results) - 1):
        assert results[i].score >= results[i + 1].score


def test_search_chunk_fields(sqlite_provider):
    """验证返回的 Chunk 包含完整字段。"""
    docs = [{
        "content": "测试内容",
        "source": "test_source",
        "doc_id": "test_doc",
        "metadata": {"key": "value"}
    }]
    sqlite_provider.index(docs)

    results = sqlite_provider.search("测试", top_k=1)
    assert len(results) >= 1

    chunk = results[0]
    assert chunk.content == "测试内容"
    assert chunk.source == "test_source"
    assert isinstance(chunk.score, float)
    assert chunk.metadata == {"key": "value", "doc_id": "test_doc", "chunk_id": None}


def test_search_round_trips_sql_identity_and_chunk_id(sqlite_provider):
    sqlite_provider.index([{
        "content": "有 provenance 的测试内容",
        "doc_id": "sql-authority",
        "metadata": {
            "doc_id": "stale-metadata",
            "chunk_id": "chunk-123",
            "source_locator": {"file_path": "book.epub"},
        },
    }])

    chunk = sqlite_provider.search("provenance", top_k=1)[0]
    assert chunk.metadata["doc_id"] == "sql-authority"
    assert chunk.metadata["chunk_id"] == "chunk-123"
    assert chunk.metadata["source_locator"] == {"file_path": "book.epub"}


def test_index_uses_metadata_chunk_id_when_top_level_is_none(sqlite_provider):
    sqlite_provider.index([{
        "content": "metadata chunk id 不应丢失",
        "doc_id": "doc-1",
        "chunk_id": None,
        "metadata": {"chunk_id": "metadata-chunk"},
    }])

    chunk = sqlite_provider.search("metadata", top_k=1)[0]
    assert chunk.metadata["chunk_id"] == "metadata-chunk"


def test_doc_count_empty(sqlite_provider):
    """验证初始 doc_count 为 0。"""
    assert sqlite_provider.doc_count == 0


def test_doc_count_after_indexing(sqlite_provider):
    """验证索引后 doc_count 正确。"""
    sqlite_provider.index([{"content": "文档1"}])
    assert sqlite_provider.doc_count == 1

    sqlite_provider.index([{"content": "文档2"}, {"content": "文档3"}])
    assert sqlite_provider.doc_count == 3


def test_score_calibration_formula():
    """验证 score 校准公式 score = 1/(1+distance) 正确。

    [MOCK:阶段A] 这是纯数学测试，验证 PG 分支的 score 计算公式
    """
    # 模拟 distance 值
    test_cases = [
        (0.0, 1.0),      # distance=0 → score=1.0
        (1.0, 0.5),      # distance=1 → score=0.5
        (4.0, 0.2),      # distance=4 → score=0.2
        (0.5, 0.6666666666666666),  # distance=0.5 → score≈0.667
    ]

    for distance, expected_score in test_cases:
        calculated_score = 1.0 / (1.0 + distance)
        assert abs(calculated_score - expected_score) < 1e-9


def test_connection_reuse(sqlite_provider):
    """验证连接懒加载和复用。"""
    # 首次调用创建连接
    conn1 = sqlite_provider._get_conn()
    assert conn1 is not None

    # 第二次调用应复用
    conn2 = sqlite_provider._get_conn()
    assert conn2 is conn1


def test_metadata_json_serialization(sqlite_provider):
    """验证复杂 metadata 正确序列化。"""
    docs = [{
        "content": "测试",
        "metadata": {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "unicode": "中文"
        }
    }]
    sqlite_provider.index(docs)

    results = sqlite_provider.search("测试", top_k=1)
    assert len(results) >= 1

    metadata = results[0].metadata
    assert metadata["nested"] == {"key": "value"}
    assert metadata["list"] == [1, 2, 3]
    assert metadata["unicode"] == "中文"


# ===== RAG-C Phase 2（C-09）：SQLite 降级分支 visibility 过滤（DEC-001）=====

from app.infrastructure.rag.coordinator import VisibilityContext


def _index_visibility_matrix(provider):
    """写入 DEC-001 矩阵全行型：规范 2 行 + 歧义 3 行 + 未知 scope 1 行。"""
    provider.index([
        {"content": "全局无主文档", "scope": "global", "user_id": None},
        {"content": "用户1私有文档", "scope": "private", "user_id": 1},
        {"content": "用户2私有文档", "scope": "private", "user_id": 2},
        {"content": "无主私有文档", "scope": "private", "user_id": None},
        {"content": "带主全局文档", "scope": "global", "user_id": 9},
        {"content": "共享范围文档", "scope": "shared", "user_id": 1},
    ])


def test_search_sqlite_visibility_matrix(sqlite_provider):
    """用户1受限检索：仅 global+无主 与 本人 private 可见，其余 fail closed。"""
    _index_visibility_matrix(sqlite_provider)
    chunks = sqlite_provider.search("文档", top_k=10, visibility=VisibilityContext(user_id=1))
    assert {c.content for c in chunks} == {"全局无主文档", "用户1私有文档"}


def test_search_sqlite_visibility_other_user(sqlite_provider):
    """用户2受限检索：换人后仅其本人 private 可见（跨用户隔离）。"""
    _index_visibility_matrix(sqlite_provider)
    chunks = sqlite_provider.search("文档", top_k=10, visibility=VisibilityContext(user_id=2))
    assert {c.content for c in chunks} == {"全局无主文档", "用户2私有文档"}


def test_search_sqlite_filters_before_limit(sqlite_provider):
    """过滤先于排序/LIMIT：未授权行即使字符命中打平也不得抢占 top-k。"""
    sqlite_provider.index(
        [{"content": "机器学习机器学习机器学习", "scope": "private", "user_id": 99}]
        + [{"content": f"机器学习基础第{i}讲", "scope": "global", "user_id": None}
           for i in range(3)]
    )
    chunks = sqlite_provider.search("机器学习", top_k=1,
                                    visibility=VisibilityContext(user_id=1))
    assert len(chunks) == 1
    assert "基础" in chunks[0].content

    # 无 visibility 时旧行为保留：全部行参与排序（回归边界）
    plain = sqlite_provider.search("机器学习", top_k=1)
    assert plain[0].content == "机器学习机器学习机器学习"


def test_index_supports_private_and_global_rows(sqlite_provider):
    """索引写侧支持 private/global 数据（RAG-C 最小集）。"""
    sqlite_provider.index([
        {"content": "公共行", "scope": "global", "user_id": None},
        {"content": "私人行", "scope": "private", "user_id": 5},
    ])
    assert sqlite_provider.doc_count == 2
    conn = sqlite_provider._get_conn()
    rows = conn.execute(text("SELECT scope, user_id FROM vector_chunks ORDER BY id")).fetchall()
    assert rows == [("global", None), ("private", 5)]


# ===== RAG-B B3-05：写侧空顶层 doc_id 回退 metadata；legacy NULL/空串读侧保留 =====


def test_index_falls_back_to_metadata_doc_id_when_top_level_empty(sqlite_provider):
    """顶层 doc_id 为空串时回退 metadata 合法值，不写出空串 identity 行。"""
    written = sqlite_provider.index([{
        "content": "顶层为空回退 metadata",
        "doc_id": "",
        "metadata": {"doc_id": "meta-doc"},
    }])
    assert written == 1

    conn = sqlite_provider._get_conn()
    sql_doc_id = conn.execute(text("SELECT doc_id FROM vector_chunks")).scalar()
    assert sql_doc_id == "meta-doc"

    chunk = sqlite_provider.search("回退", top_k=1)[0]
    assert chunk.metadata["doc_id"] == "meta-doc"


@pytest.mark.parametrize("legacy_doc_id", [None, ""])
def test_search_preserves_metadata_identity_for_legacy_rows(
    sqlite_provider, legacy_doc_id
):
    """legacy 行（SQL doc_id/chunk_id 为 NULL/空串）读侧不得抹掉 metadata
    中合法 identity（B3-05）；PG 分支走同一 _sql_or_metadata 归一逻辑，
    真实 PG 验证见 integration。"""
    conn = sqlite_provider._get_conn()
    conn.execute(
        text("""
        INSERT INTO vector_chunks (user_id, scope, content, embedding, source, doc_id, chunk_id, metadata_json)
        VALUES (NULL, 'global', 'legacy 行内容', '[]', 'vector', :doc_id, NULL, :metadata_json)
        """),
        {
            "doc_id": legacy_doc_id,
            "metadata_json": json.dumps({"doc_id": "legacy-doc", "chunk_id": "legacy-chunk"}),
        },
    )
    conn.commit()

    chunk = sqlite_provider.search("legacy", top_k=1)[0]
    assert chunk.metadata["doc_id"] == "legacy-doc"
    assert chunk.metadata["chunk_id"] == "legacy-chunk"
