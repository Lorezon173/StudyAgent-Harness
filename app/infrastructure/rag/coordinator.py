from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.infrastructure.rag.store import FakeRAGStore


@dataclass
class Chunk:
    """检索结果的最小单元（§3.6 证据片段）。"""
    content: str
    score: float                         # 原始 similarity score
    source: str = "vector"               # "vector" | "ocr" | "code"
    metadata: dict = field(default_factory=dict)  # file_path, page, line, symbol, ...


@dataclass
class SearchResult:
    """多源聚合的检索结果。"""
    chunks: list[Chunk]
    total_found: int
    sources_used: list[str]


class IndexProvider(ABC):
    """检索后端协议：所有 provider（向量/OCR/代码）必须实现。"""

    name: str

    @abstractmethod
    def index(self, docs: list[dict]) -> None:
        """索引一批文档/文本块。"""
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[Chunk]:
        """检索并返回 Chunk 列表。"""
        ...

    @property
    @abstractmethod
    def doc_count(self) -> int:
        """已索引的文档数。"""
        ...


class RAGCoordinator:
    """RAG 协调器：管理多源 IndexProvider，聚合检索结果（§3.6/§9 扩展）。"""

    def __init__(self, store=None):
        self._store = store or FakeRAGStore()
        self._providers: dict[str, IndexProvider] = {}
        self._register_default_vector_provider()

    def _register_default_vector_provider(self) -> None:
        """将现有 FakeRAGStore/RAGStore 包装为 VectorStoreProvider。"""
        store_ref = self._store  # 闭包引用

        class _VectorStoreProvider(IndexProvider):
            name = "vector"

            def index(self, docs: list[dict]) -> None:
                store_ref.index(docs)

            def search(self, query: str, top_k: int = 5) -> list[Chunk]:
                raw = store_ref.query(query, top_k)
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

    # --- 多源检索 ---

    def search(self, query: str, sources: list[str] | None = None,
               top_k: int = 5) -> SearchResult:
        """多源检索：聚合所有（或指定）provider 的结果，按 score 降序 + 去重。"""
        target = sources if sources else list(self._providers.keys())
        all_chunks: list[Chunk] = []
        sources_used: list[str] = []

        for name in target:
            provider = self._providers.get(name)
            if provider is None:
                continue
            try:
                chunks = provider.search(query, top_k)
                all_chunks.extend(chunks)
                if chunks:
                    sources_used.append(name)
            except Exception:
                continue

        # 去重：相同 content 只保留 score 最高的
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
        )

    # --- 向后兼容 ---

    def index_documents(self, docs: list[dict], source: str = "vector") -> None:
        """索引文档到指定 provider。默认写入 vector provider。"""
        provider = self._providers.get(source)
        if provider:
            provider.index(docs)

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
        confidence = "high" if avg_score > 2 else "medium" if avg_score > 1 else "low"
        return {
            "context": context,
            "found": True,
            "citations": citations,
            "confidence_level": confidence,
            "source_count": len(result.chunks),
            "strategy": "vector",
        }
