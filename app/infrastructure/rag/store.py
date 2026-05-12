class FakeRAGStore:
    """开发环境用的内存 RAG 存储"""

    def __init__(self):
        self._documents: list[dict] = []

    def index(self, docs: list[dict]):
        self._documents.extend(docs)

    def query(self, query_text: str, top_k: int = 5) -> list[dict]:
        results = []
        for doc in self._documents:
            score = sum(1 for w in query_text if w in doc.get("content", ""))
            if score > 0:
                results.append({**doc, "score": score})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    @property
    def doc_count(self) -> int:
        return len(self._documents)


class RAGStore:
    """生产环境 RAG 存储（LlamaIndex 底座）"""

    def __init__(self, scope: str = "global"):
        self._scope = scope
        self._index = None

    def index(self, docs: list[dict]):
        self._documents = docs

    def query(self, query_text: str, top_k: int = 5) -> list[dict]:
        if self._index is None:
            return []
        return []
