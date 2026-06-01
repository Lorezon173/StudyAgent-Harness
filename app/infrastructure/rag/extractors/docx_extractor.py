"""DOCX 文本提取器（可选依赖 python-docx）。"""

from app.infrastructure.rag.extractors.base import Extractor


class DocxExtractor(Extractor):
    extensions = [".docx"]

    def extract(self, file_path: str) -> str:
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except ImportError:
            return ""
        except Exception:
            return ""
