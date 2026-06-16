"""纯文本文件提取器（txt/md/csv）。"""

from app.infrastructure.rag.extractors.base import Extractor


class TextExtractor(Extractor):
    extensions = [".txt", ".md", ".csv"]

    def extract(self, file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (IOError, UnicodeDecodeError):
            return ""
