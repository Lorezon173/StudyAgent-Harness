class FakeRAGStore:
    """开发环境用的内存 RAG 存储"""

    def __init__(self):
        self._documents: list[dict] = []

    def index(self, docs: list[dict]):
        self._documents.extend(docs)

    def query(self, query_text: str, top_k: int = 5, visibility=None) -> list[dict]:
        """字符重叠打分检索；visibility 非空时先按 DEC-001 矩阵过滤文档。

        过滤发生在打分/排序/截断之前（与 PgVectorProvider 的
        PG/SQLite 谓词同语义）；无 scope/user_id 的历史文档在受限
        检索下按未知 scope fail closed。
        """
        docs = self._documents
        if visibility is not None:
            uid = getattr(visibility, "user_id", None)
            docs = [d for d in docs if self._doc_visible(d, uid)]
        results = []
        for doc in docs:
            score = sum(1 for w in query_text if w in doc.get("content", ""))
            if score > 0:
                results.append({**doc, "score": score})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    @staticmethod
    def _doc_visible(doc: dict, uid) -> bool:
        """DEC-001 授权矩阵：global+无主 或 private+本人；歧义/未知 fail closed。"""
        scope = doc.get("scope")
        owner = doc.get("user_id")
        if scope == "global":
            return owner is None
        if scope == "private":
            return owner is not None and owner == uid
        return False

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
