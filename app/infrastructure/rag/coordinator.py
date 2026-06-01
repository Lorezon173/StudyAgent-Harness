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
    """RAG 协调器：组装检索组件"""

    def __init__(self, store=None):
        self._store = store or FakeRAGStore()

    def index_documents(self, docs: list[dict]):
        self._store.index(docs)

    def retrieve(self, query: str, top_k: int = 5) -> dict:
        results = self._store.query(query, top_k)
        if not results:
            return {
                "context": "",
                "found": False,
                "citations": [],
                "confidence_level": "low",
                "source_count": 0,
                "strategy": "vector",
            }
        context = "\n".join(r.get("content", "") for r in results)
        citations = [{"content": r.get("content", ""), "score": r.get("score", 0)} for r in results]
        avg_score = sum(r.get("score", 0) for r in results) / len(results)
        confidence = "high" if avg_score > 2 else "medium" if avg_score > 1 else "low"
        return {
            "context": context,
            "found": True,
            "citations": citations,
            "confidence_level": confidence,
            "source_count": len(results),
            "strategy": "vector",
        }
