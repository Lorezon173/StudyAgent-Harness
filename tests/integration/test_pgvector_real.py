"""PgVector 真实集成测试（阶段 A）。

用途：用户装 Docker 后跑真实 PG + 真实 embedding API 验证。

前置条件：
1. PostgreSQL + pgvector 已启动（Docker）：
   docker run --name pgvector-test -e POSTGRES_PASSWORD=test \\
       -e POSTGRES_DB=study_agent_test -p 5432:5432 -d pgvector/pgvector:pg16

2. 环境变量已配置：
   export OPENAI_API_KEY="your-api-key"
   export TEST_PG_URL="postgresql+psycopg://postgres:test@localhost/study_agent_test"

运行方式：
   pytest -m integration tests/integration/test_pgvector_real.py -v

标记说明：
- @pytest.mark.integration：默认跳过，需 `pytest -m integration` 才运行
- @pytest.mark.skipif：无 PG 连接或 API key 时自动跳过
"""

import os
import pytest
from sqlalchemy import create_engine, text
from app.infrastructure.rag.pgvector_provider import PgVectorProvider
from app.infrastructure.rag.embedding import EmbeddingService


def _pg_available() -> bool:
    """检查 PG 是否可连接。"""
    pg_url = os.getenv("TEST_PG_URL", "")
    if not pg_url:
        return False
    try:
        engine = create_engine(pg_url, echo=False)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _openai_api_key_available() -> bool:
    """检查 OpenAI API key 是否存在。"""
    return bool(os.getenv("OPENAI_API_KEY", ""))


@pytest.fixture
def pg_provider():
    """提供连接真实 PG 的 PgVectorProvider。

    清理策略：测试前清空 vector_chunks 表，测试后也清空。
    """
    pg_url = os.getenv("TEST_PG_URL", "postgresql+psycopg://postgres:test@localhost/study_agent_test")
    embedding_service = EmbeddingService()  # 使用真实 API
    provider = PgVectorProvider(embedding_service=embedding_service, db_url=pg_url)

    # 测试前清空表
    conn = provider._get_conn()
    try:
        # 创建表（如果不存在）
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vector_chunks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                scope TEXT DEFAULT 'global',
                content TEXT NOT NULL,
                embedding vector(1536),
                source TEXT DEFAULT 'vector',
                doc_id TEXT DEFAULT '',
                metadata_json JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()

        # 清空数据
        conn.execute(text("DELETE FROM vector_chunks"))
        conn.commit()
    except Exception as e:
        pytest.skip(f"无法初始化 PG 表：{e}")

    yield provider

    # 测试后清空
    try:
        conn.execute(text("DELETE FROM vector_chunks"))
        conn.commit()
    except Exception:
        pass
    finally:
        if provider._conn:
            provider._conn.close()


@pytest.mark.integration
@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 未连接，跳过集成测试")
@pytest.mark.skipif(not _openai_api_key_available(), reason="OPENAI_API_KEY 未配置，跳过集成测试")
def test_pgvector_real_index_and_search(pg_provider):
    """真实场景：索引中文 chunk + 语义检索。"""
    # 索引中文知识
    docs = [
        {"content": "机器学习是人工智能的一个分支，专注于让计算机从数据中学习。"},
        {"content": "深度学习使用多层神经网络来建模复杂模式。"},
        {"content": "自然语言处理是计算机理解和生成人类语言的技术。"},
        {"content": "Python 是最流行的机器学习编程语言。"},
    ]
    pg_provider.index(docs)

    # 验证索引成功
    assert pg_provider.doc_count == 4

    # 语义检索：查询相近内容
    results = pg_provider.search("什么是机器学习", top_k=3)

    # 验证返回结果
    assert len(results) > 0
    assert len(results) <= 3

    # 验证最相关的结果（应该是第一条）
    top_chunk = results[0]
    assert "机器学习" in top_chunk.content
    assert top_chunk.score > 0
    assert top_chunk.source == "vector"


@pytest.mark.integration
@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 未连接，跳过集成测试")
@pytest.mark.skipif(not _openai_api_key_available(), reason="OPENAI_API_KEY 未配置，跳过集成测试")
def test_pgvector_real_semantic_similarity(pg_provider):
    """验证语义相似度检索（非字面匹配）。"""
    # 索引不包含"深度学习"字样的描述
    docs = [
        {"content": "多层神经网络可以学习复杂的非线性映射关系。"},
        {"content": "卷积神经网络在图像识别任务中表现出色。"},
        {"content": "循环神经网络适合处理序列数据。"},
    ]
    pg_provider.index(docs)

    # 查询"深度学习"（字面上不在任何文档中）
    results = pg_provider.search("深度学习", top_k=2)

    # 应该能召回语义相关的文档（神经网络相关）
    assert len(results) > 0
    assert any("神经网络" in chunk.content for chunk in results)


@pytest.mark.integration
@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 未连接，跳过集成测试")
@pytest.mark.skipif(not _openai_api_key_available(), reason="OPENAI_API_KEY 未配置，跳过集成测试")
def test_pgvector_real_score_calibration(pg_provider):
    """验证 score 校准公式在真实数据上表现。"""
    docs = [
        {"content": "向量数据库用于存储和检索高维向量。"},
    ]
    pg_provider.index(docs)

    # 查询完全相同的文本（distance 应接近 0，score 接近 1）
    results = pg_provider.search("向量数据库用于存储和检索高维向量。", top_k=1)

    assert len(results) == 1
    # score = 1/(1+distance)，distance ≈ 0 时 score 应接近 1
    assert results[0].score > 0.9  # 允许一定误差


@pytest.mark.integration
@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 未连接，跳过集成测试")
@pytest.mark.skipif(not _openai_api_key_available(), reason="OPENAI_API_KEY 未配置，跳过集成测试")
def test_pgvector_real_metadata_preservation(pg_provider):
    """验证 metadata 在 PG 中正确存取。"""
    docs = [{
        "content": "测试文档",
        "metadata": {
            "file_path": "/path/to/doc.txt",
            "page": 42,
            "tags": ["机器学习", "教程"]
        }
    }]
    pg_provider.index(docs)

    results = pg_provider.search("测试", top_k=1)
    assert len(results) == 1

    metadata = results[0].metadata
    assert metadata["file_path"] == "/path/to/doc.txt"
    assert metadata["page"] == 42
    assert metadata["tags"] == ["机器学习", "教程"]


@pytest.mark.integration
@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 未连接，跳过集成测试")
@pytest.mark.skipif(not _openai_api_key_available(), reason="OPENAI_API_KEY 未配置，跳过集成测试")
def test_pgvector_real_empty_query_handling(pg_provider):
    """验证空查询返回空结果（真实环境）。"""
    pg_provider.index([{"content": "测试文档"}])
    results = pg_provider.search("", top_k=5)
    assert results == []


@pytest.mark.integration
@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 未连接，跳过集成测试")
@pytest.mark.skipif(not _openai_api_key_available(), reason="OPENAI_API_KEY 未配置，跳过集成测试")
def test_pgvector_real_top_k_limit(pg_provider):
    """验证 top_k 限制在真实检索中生效。"""
    docs = [{"content": f"文档{i}"} for i in range(10)]
    pg_provider.index(docs)

    results = pg_provider.search("文档", top_k=3)
    assert len(results) <= 3


@pytest.mark.integration
@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 未连接，跳过集成测试")
@pytest.mark.skipif(not _openai_api_key_available(), reason="OPENAI_API_KEY 未配置，跳过集成测试")
def test_pgvector_real_batch_indexing(pg_provider):
    """验证批量索引性能（真实 API 调用）。"""
    # 批量索引 20 条文档
    docs = [{"content": f"这是第{i}个测试文档，内容各不相同。"} for i in range(20)]
    pg_provider.index(docs)

    assert pg_provider.doc_count == 20

    # 验证能检索到特定文档
    results = pg_provider.search("第10个", top_k=5)
    assert len(results) > 0
