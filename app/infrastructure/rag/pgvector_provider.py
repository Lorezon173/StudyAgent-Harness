"""PgVectorProvider —— 真向量检索后端（阶段 A）。

实现 IndexProvider 协议，提供：
  - index(docs): 批量 embed + 写入 PG 向量表
  - search(query, top_k): embed query + 近邻检索 + 转 Chunk
  - doc_count: 已索引文档数

关键设计点：
  1. sync/async 边界：IndexProvider.search 是同步方法，但 PG 访问是 async。
     解决方案：向量表用同步 psycopg 连接（不与业务 async_session 混用）。
  2. score 校准：pgvector <=> 返回距离（越小越近），需转成"越大越相关"的 score。
     采用 score = 1 / (1 + distance)，使其落在 (0, 1] 区间。
"""

import json

from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.rag.coordinator import Chunk, IndexProvider
from app.infrastructure.rag.embedding import EmbeddingService


def _sql_or_metadata(sql_value, metadata: dict, key: str):
    """读侧 identity 归一：SQL 顶层值是权威来源（B3-05）。

    legacy 行 SQL 列为 NULL/空串时，回退保留 metadata 中合法的
    ``doc_id/chunk_id``，不抹掉 provenance；两者皆无时保留原 SQL
    值（None/空串），保证返回 metadata 的回传面键稳定。
    """
    if sql_value:
        return sql_value
    return metadata.get(key) or sql_value


class PgVectorProvider(IndexProvider):
    """PG + pgvector 向量检索后端（同步接口）。"""

    name = "vector"

    def __init__(self, embedding_service: EmbeddingService | None = None,
                 db_url: str | None = None):
        """初始化向量检索 provider。

        Args:
            embedding_service: embedding 服务（默认新建）
            db_url: 数据库连接 URL（默认从 settings 读取，转同步驱动）
        """
        self._embedding = embedding_service or EmbeddingService()
        self._db_url = db_url or self._make_sync_db_url(settings.database_url)
        self._conn = None

    @staticmethod
    def _make_sync_db_url(async_url: str) -> str:
        """将 async DB URL 转成同步驱动 URL。

        postgresql+asyncpg://... → postgresql+psycopg://...
        sqlite+aiosqlite://... → sqlite://...
        """
        if "+asyncpg" in async_url:
            return async_url.replace("+asyncpg", "+psycopg")
        if "+aiosqlite" in async_url:
            return async_url.replace("+aiosqlite", "")
        return async_url

    def _get_conn(self):
        """获取同步数据库连接（懒加载，复用单个连接）。"""
        if self._conn is None:
            from sqlalchemy import create_engine
            engine = create_engine(self._db_url, echo=False)
            self._conn = engine.connect()
        return self._conn

    def index(self, docs: list[dict]) -> int | None:
        """索引一批文档：embed + 写入向量表。

        Args:
            docs: 文档列表，每个 doc 含 {"content": str, "metadata": dict, ...}

        Returns:
            写入确认条数（commit 成功即确认）；空列表返回 0。
        """
        if not docs:
            return 0

        # 批量 embed
        contents = [d.get("content", "") for d in docs]
        embeddings = self._embedding.embed_many(contents)
        if len(embeddings) != len(docs):
            raise ValueError("embedding count must match document count")

        # 写入向量表
        conn = self._get_conn()
        dialect = conn.dialect.name

        try:
            for doc, emb in zip(docs, embeddings, strict=True):
                content = doc.get("content", "")
                metadata = doc.get("metadata", {})
                doc_id = doc.get("doc_id") or metadata.get("doc_id", "")
                chunk_id = doc.get("chunk_id") or metadata.get("chunk_id")
                source = doc.get("source", "vector")
                scope = doc.get("scope", "global")
                user_id = doc.get("user_id", None)

                if dialect == "postgresql":
                    # PostgreSQL: embedding 存为 pgvector 的 vector 类型
                    # 使用 CAST(:embedding AS vector) 避免 ::vector 与 psycopg3 参数解析冲突
                    emb_str = "[" + ",".join(map(str, emb)) + "]"
                    conn.execute(
                        text("""
                        INSERT INTO vector_chunks (user_id, scope, content, embedding, source, doc_id, chunk_id, metadata_json)
                        VALUES (:user_id, :scope, :content, CAST(:embedding AS vector), :source, :doc_id, :chunk_id, :metadata_json)
                        """),
                        {"user_id": user_id, "scope": scope, "content": content,
                         "embedding": emb_str, "source": source, "doc_id": doc_id,
                         "chunk_id": chunk_id, "metadata_json": json.dumps(metadata)}
                    )
                else:
                    # SQLite: embedding 存为 JSON 字符串
                    conn.execute(
                        text("""
                        INSERT INTO vector_chunks (user_id, scope, content, embedding, source, doc_id, chunk_id, metadata_json)
                        VALUES (:user_id, :scope, :content, :embedding, :source, :doc_id, :chunk_id, :metadata_json)
                        """),
                        {"user_id": user_id, "scope": scope, "content": content,
                         "embedding": json.dumps(emb), "source": source, "doc_id": doc_id,
                         "chunk_id": chunk_id, "metadata_json": json.dumps(metadata)}
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return len(docs)

    def search(self, query: str, top_k: int = 5, visibility=None) -> list[Chunk]:
        """检索：embed query + 近邻查询 + 转 Chunk。

        Args:
            query: 查询文本
            top_k: 返回前 k 个最相关 chunk
            visibility: 受限检索可见性上下文（DEC-001）；None 保持旧全量行为。
                PG/SQLite 分支执行同一授权谓词，且先于排序/LIMIT。

        Returns:
            Chunk 列表，按 score 降序（score 越大越相关）
        """
        if not query:
            return []

        # Embed query
        query_emb = self._embedding.embed_one(query)

        # 近邻检索
        conn = self._get_conn()
        dialect = conn.dialect.name

        if dialect == "postgresql":
            # PostgreSQL: 用 pgvector 的 <=> 计算余弦距离
            # 使用 CAST(:embedding AS vector) 避免 ::vector 与 psycopg3 参数解析冲突
            emb_str = "[" + ",".join(map(str, query_emb)) + "]"
            params = {"embedding": emb_str, "top_k": top_k}
            visibility_where = ""
            if visibility is not None:
                # DEC-001 授权谓词：global+无主 或 private+本人；歧义/未知 scope fail closed。
                # WHERE 先于 ORDER BY / LIMIT 执行（过滤在排序与限额之前）。
                visibility_where = """
                WHERE (scope = 'global' AND user_id IS NULL)
                   OR (scope = 'private' AND user_id = :uid)
                """
                params["uid"] = visibility.user_id
            result = conn.execute(
                text(f"""
                SELECT content, embedding <=> CAST(:embedding AS vector) AS distance, source, doc_id, chunk_id, metadata_json
                FROM vector_chunks
                {visibility_where}
                ORDER BY distance
                LIMIT :top_k
                """),
                params
            )
            rows = result.fetchall()
            chunks = []
            for row in rows:
                content, distance, source, doc_id, chunk_id, metadata_json = row
                score = 1.0 / (1.0 + float(distance))
                metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                metadata = metadata or {}
                metadata["doc_id"] = _sql_or_metadata(doc_id, metadata, "doc_id")
                metadata["chunk_id"] = _sql_or_metadata(chunk_id, metadata, "chunk_id")
                chunks.append(Chunk(
                    content=content,
                    score=score,
                    source=source,
                    metadata=metadata
                ))
            return chunks

        else:
            # SQLite: 无向量索引，降级为简单字符匹配（仅用于测试）
            # visibility 与 PG 分支同一授权谓词，在 SQL 内过滤（先于字符打分排序与截断）。
            params = {"limit": top_k * 10}
            visibility_where = ""
            if visibility is not None:
                visibility_where = """
                    WHERE (scope = 'global' AND user_id IS NULL)
                       OR (scope = 'private' AND user_id = :uid)
                """
                params["uid"] = visibility.user_id
            result = conn.execute(
                text(f"SELECT content, source, doc_id, chunk_id, metadata_json FROM vector_chunks{visibility_where} LIMIT :limit"),
                params
            )
            rows = result.fetchall()
            chunks = []
            for row in rows:
                content, source, doc_id, chunk_id, metadata_json = row
                # 简单字符重叠作为 score
                score = sum(1 for w in query if w in content)
                metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else {}
                metadata = metadata or {}
                metadata["doc_id"] = _sql_or_metadata(doc_id, metadata, "doc_id")
                metadata["chunk_id"] = _sql_or_metadata(chunk_id, metadata, "chunk_id")
                chunks.append(Chunk(
                    content=content,
                    score=float(score),
                    source=source,
                    metadata=metadata
                ))
            # 按 score 降序排序，取 top_k
            chunks.sort(key=lambda c: c.score, reverse=True)
            return chunks[:top_k]

    @property
    def dialect_name(self) -> str:
        """从同步 DB URL 推导 dialect（postgresql / sqlite）。

        供在线 composition fail-fast 校验（DEC-007）消费；不建立真实连接，
        连接不可达等运行时错误由检索时机的 db_error 分类承担。
        """
        from sqlalchemy.engine import make_url
        return make_url(self._db_url).get_backend_name()

    @property
    def doc_count(self) -> int:
        """返回已索引的文档数。"""
        conn = self._get_conn()
        result = conn.execute(text("SELECT COUNT(*) FROM vector_chunks"))
        return result.fetchone()[0]
