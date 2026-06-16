"""PDF 文本提取器（可选依赖 PyPDF2/pdfplumber）。"""

from app.infrastructure.rag.extractors.base import Extractor


class PDFExtractor(Extractor):
    extensions = [".pdf"]

    def extract(self, file_path: str) -> str:
        # 尝试 pdfplumber（更好的文本提取）
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n\n".join(pages)
        except ImportError:
            pass
        # 回退 PyPDF2
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(pages)
        except ImportError:
            return ""
        except Exception:
            return ""
