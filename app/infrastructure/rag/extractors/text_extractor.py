"""纯文本文件提取器（txt/md/csv）。"""

from typing import ClassVar

from app.infrastructure.rag.extractors.base import Extractor


class TextExtractor(Extractor):
    extensions: ClassVar[list[str]] = [".txt", ".md", ".csv"]

    def extract(self, file_path: str) -> str:
        try:
            with open(file_path, encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            return ""
