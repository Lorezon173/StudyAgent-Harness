"""Extractor 抽象协议 + 工厂函数。"""

import os
from abc import ABC, abstractmethod
from typing import ClassVar


class Extractor(ABC):
    """文件文本提取器协议。"""

    extensions: ClassVar[list[str]] = []

    @abstractmethod
    def extract(self, file_path: str) -> str:
        """从文件中提取纯文本。"""
        ...


def get_extractor(file_path: str) -> "Extractor | None":
    """按文件扩展名匹配合适的提取器。"""
    from app.infrastructure.rag.extractors.docx_extractor import DocxExtractor
    from app.infrastructure.rag.extractors.epub_extractor import EpubExtractor
    from app.infrastructure.rag.extractors.pdf_extractor import PDFExtractor
    from app.infrastructure.rag.extractors.text_extractor import TextExtractor

    ext = os.path.splitext(file_path)[1].lower()  # 带点，如 ".txt"
    for cls in [TextExtractor, PDFExtractor, DocxExtractor, EpubExtractor]:
        if ext in cls.extensions:
            return cls()
    return None
