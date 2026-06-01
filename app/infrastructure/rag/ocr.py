"""OCR 文本提取与索引 Provider（§9 RAG 扩展）。

实现 IndexProvider 协议，内部用 FakeRAGStore 做存储。
生产环境可接入 pytesseract / 云 OCR API。
"""

from app.infrastructure.rag.coordinator import Chunk, IndexProvider
from app.infrastructure.rag.store import FakeRAGStore


class OCRProvider(IndexProvider):
    """OCR 图片文本索引 Provider。

    生产用法：
        provider = OCRProvider()
        provider.index_image(image_bytes, metadata={"file": "slide.png"})
        results = provider.search("注意力机制")
    """

    name = "ocr"

    def __init__(self):
        self._store = FakeRAGStore()

    # --- 文本提取（可选依赖 pytesseract） ---

    def extract_text(self, image_bytes: bytes) -> str:
        """从图片字节提取文本。pytesseract 不可用时返回空字符串。"""
        try:
            import pytesseract
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img) or ""
        except ImportError:
            return ""

    # --- IndexProvider 协议 ---

    def index(self, docs: list[dict]) -> None:
        """索引已提取文本的文档列表。每项含 content 和可选的 metadata。"""
        self._store.index(docs)

    def index_image(self, image_bytes: bytes, metadata: dict | None = None) -> str:
        """提取图片文本并按段落分块索引。返回提取的文本。"""
        text = self.extract_text(image_bytes)
        if not text:
            return ""
        meta = metadata or {}
        # 按双换行分块
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        docs = [{"content": p, "metadata": {**meta, "chunk_idx": i}}
                for i, p in enumerate(paragraphs)]
        self.index(docs)
        return text

    def search(self, query: str, top_k: int = 5) -> list[Chunk]:
        """检索 OCR 文本中的相关内容。"""
        raw = self._store.query(query, top_k)
        return [
            Chunk(content=r["content"], score=float(r.get("score", 0)),
                  source="ocr", metadata=r.get("metadata", {}))
            for r in raw
        ]

    @property
    def doc_count(self) -> int:
        return self._store.doc_count
