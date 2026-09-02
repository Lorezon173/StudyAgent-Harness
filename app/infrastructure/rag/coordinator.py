from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging

from app.infrastructure.rag.store import FakeRAGStore

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """检索结果的最小单元（§3.6 证据片段）。"""
    content: str
    score: float                         # 原始 similarity score
    source: str = "vector"               # "vector" | "ocr" | "code"
    metadata: dict = field(default_factory=dict)  # file_path, page, line, symbol, ...


@dataclass
class VisibilityContext:
    """受限检索可见性上下文（DEC-001：global + 当前 user 私有）。

    user_id 只来自受信任会话（get_current_user 验签），沿
    Retriever → Coordinator → Provider 单向传递；Provider 据此过滤，
    且过滤先于排序/去重/LIMIT。P0 仅支持 global/private。
    """
    user_id: int


@dataclass
class SearchResult:
    """多源聚合的检索结果。

    RAG-C Phase 2（C-09/DEC-008）：新增聚合 outcome 与 provider 尝试/失败明细。
    outcome ∈ {ok, empty, degraded, failed}；invalid-request 在 Retriever 入口
    拦截，Coordinator 侧对受限请求的非法 visibility / 非法 source 选择也归约
    为 failed + invalid_request 分类码。
    """
    chunks: list[Chunk]
    total_found: int
    sources_used: list[str]
    outcome: str = "empty"
    attempted_providers: list[str] = field(default_factory=list)
    failed_providers: list[str] = field(default_factory=list)
    error_code: str | None = None        # DEC-009 分类错误码（不含异常原文）


class IndexProvider(ABC):
    """检索后端协议：所有 provider（向量/OCR/代码）必须实现。"""

    name: str

    @abstractmethod
    def index(self, docs: list[dict]) -> int | None:
        """索引一批文档/文本块。

        返回可核验的写入确认条数；无法确认写入时返回 None
        （B3-06：coordinator 不得把 None 当成功推断）。
        """
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5, visibility=None) -> list[Chunk]:
        """检索并返回 Chunk 列表。

        visibility 为受限检索上下文（VisibilityContext，DEC-001）；
        未实现 visibility 契约的 provider 不得参与受限检索
        （Coordinator 受限路径只调用 vector provider）。
        """
        ...

    @property
    @abstractmethod
    def doc_count(self) -> int:
        """已索引的文档数。"""
        ...


class RAGCoordinator:
    """RAG 协调器：管理多源 IndexProvider，聚合检索结果（§3.6/§9 扩展）。"""

    def __init__(self, store=None, vector_provider: IndexProvider | None = None):
        self._store = store or FakeRAGStore()
        self._providers: dict[str, IndexProvider] = {}
        if vector_provider is not None:
            # 显式注入（DEC-007 在线 composition）：不依赖 settings 默认分支
            self._providers["vector"] = vector_provider
        else:
            self._register_default_vector_provider()

    def _register_default_vector_provider(self) -> None:
        """注册默认向量 provider：根据 settings.rag_backend 选择 pgvector 或 fake。"""
        from app.core.config import settings

        if settings.rag_backend == "pgvector":
            # 生产模式：使用真向量检索
            from app.infrastructure.rag.pgvector_provider import PgVectorProvider
            self._providers["vector"] = PgVectorProvider()
        else:
            # 测试/开发模式：包装 FakeRAGStore
            store_ref = self._store  # 闭包引用

            class _VectorStoreProvider(IndexProvider):
                name = "vector"

                def index(self, docs: list[dict]) -> int:
                    store_ref.index(docs)
                    return len(docs)

                def search(self, query: str, top_k: int = 5, visibility=None) -> list[Chunk]:
                    raw = store_ref.query(query, top_k, visibility=visibility)
                    return [
                        Chunk(content=r["content"], score=float(r.get("score", 0)),
                              source="vector", metadata=r.get("metadata", {}))
                        for r in raw
                    ]

                @property
                def doc_count(self) -> int:
                    return store_ref.doc_count

            self._providers["vector"] = _VectorStoreProvider()

    # --- Provider 管理 ---

    def register_provider(self, provider: IndexProvider) -> None:
        """注册一个检索后端（OCR/代码索引等）。"""
        self._providers[provider.name] = provider

    def unregister_provider(self, name: str) -> None:
        """注销指定检索后端（默认 vector 不可注销）。"""
        if name == "vector":
            return
        self._providers.pop(name, None)

    def get_provider(self, name: str) -> IndexProvider | None:
        """按名取已注册 provider（供在线 composition 校验 / 测试读取）。"""
        return self._providers.get(name)

    # --- 多源检索 ---

    def search(self, query: str, sources: list[str] | None = None,
               top_k: int = 5, visibility: VisibilityContext | None = None) -> SearchResult:
        """多源检索：聚合所有（或指定）provider 的结果，按 score 降序 + 去重。

        visibility=None：保持既有多源/全搜语义（OCR/code 等不受限，二参调用）。
        visibility=VisibilityContext：受限检索（DEC-001），仅 vector provider
        可参与；显式选中其他 provider 时安全失败（failed/invalid_request），
        不发起任何 provider 调用。

        Provider 异常不再静默吞没（DEC-009）：进内部日志并归约
        degraded / failed；对外只暴露分类错误码，不含异常原文。
        """
        if visibility is not None:
            if (not isinstance(visibility, VisibilityContext)
                    or isinstance(visibility.user_id, bool)
                    or not isinstance(visibility.user_id, int)):
                logger.warning("restricted search rejected invalid visibility context")
                return SearchResult(chunks=[], total_found=0, sources_used=[],
                                    outcome="failed", error_code="invalid_request")
            target = list(sources) if sources else ["vector"]
            non_vector = [n for n in target if n != "vector"]
            if non_vector:
                logger.warning(
                    "restricted search rejected non-vector sources: %s", non_vector)
                return SearchResult(chunks=[], total_found=0, sources_used=[],
                                    outcome="failed", error_code="invalid_request",
                                    failed_providers=non_vector)
        else:
            target = sources if sources else list(self._providers.keys())

        all_chunks: list[Chunk] = []
        sources_used: list[str] = []
        attempted: list[str] = []
        failed: list[str] = []
        last_exc: Exception | None = None

        for name in target:
            provider = self._providers.get(name)
            if provider is None:
                continue
            attempted.append(name)
            try:
                if visibility is not None:
                    chunks = provider.search(query, top_k=top_k, visibility=visibility)
                else:
                    chunks = provider.search(query, top_k=top_k)
                all_chunks.extend(chunks)
                if chunks:
                    sources_used.append(name)
            except Exception as exc:
                # DEC-009：完整异常只进内部日志；SearchResult 只带 provider 名与分类码
                failed.append(name)
                last_exc = exc
                logger.exception("RAG provider '%s' search failed", name)

        # 聚合归约（DEC-008 §E.2）
        succeeded = [n for n in attempted if n not in failed]
        if not attempted:
            outcome, error_code = "empty", None
        elif not succeeded:
            outcome = "failed"
            error_code = "timeout" if isinstance(last_exc, TimeoutError) else "db_error"
        elif failed:
            outcome, error_code = "degraded", "provider_degraded"
        else:
            outcome = "ok" if all_chunks else "empty"
            error_code = None

        # 去重：相同 content 只保留 score 最高的（仅对已授权结果，§D.3）
        seen: dict[str, Chunk] = {}
        for c in all_chunks:
            if c.content not in seen or c.score > seen[c.content].score:
                seen[c.content] = c

        # 按 score 降序排列
        deduped = sorted(seen.values(), key=lambda c: c.score, reverse=True)
        return SearchResult(
            chunks=deduped[:top_k],
            total_found=len(deduped),
            sources_used=sources_used,
            outcome=outcome,
            attempted_providers=attempted,
            failed_providers=failed,
            error_code=error_code,
        )

    # --- 向后兼容 ---

    def index_documents(self, docs: list[dict], source: str = "vector") -> int | None:
        """索引文档到指定 provider。默认写入 vector provider。

        B3-06：返回可核验的写入确认——provider 存在时返回其 index()
        的确认条数（provider 返回 None 表示未确认，原样传播）；
        provider 缺失时返回 None，不再静默 no-op。
        """
        provider = self._providers.get(source)
        if provider is None:
            return None
        return provider.index(docs)

    def retrieve(self, query: str, top_k: int = 5) -> dict:
        """保持旧接口兼容：仅检索 vector 源，返回旧 dict 格式。"""
        result = self.search(query, sources=["vector"], top_k=top_k)
        if not result.chunks:
            return {
                "context": "",
                "found": False,
                "citations": [],
                "confidence_level": "low",
                "source_count": 0,
                "strategy": "vector",
            }
        context = "\n".join(c.content for c in result.chunks)
        citations = [{"content": c.content, "score": c.score} for c in result.chunks]
        avg_score = sum(c.score for c in result.chunks) / len(result.chunks)

        # 阈值校准（适配向量检索的归一化 score）：
        # - pgvector 的 score = 1/(1+distance)，落在 (0, 1] 区间
        # - FakeRAGStore 的 score 是整数计数，通常 >= 1
        # 为兼容两者，采用自适应阈值：avg_score > 0.6 → high, > 0.3 → medium, 否则 low
        if avg_score > 0.6:
            confidence = "high"
        elif avg_score > 0.3:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "context": context,
            "found": True,
            "citations": citations,
            "confidence_level": confidence,
            "source_count": len(result.chunks),
            "strategy": "vector",
        }
