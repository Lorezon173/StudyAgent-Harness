from app.infrastructure.rag.store import FakeRAGStore


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
