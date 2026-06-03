"""文件提取服务（可选依赖）"""

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md", ".csv")


async def extract_text(file_path: str) -> str:
    """从文件中提取文本内容"""
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if ext not in ("pdf", "txt", "md", "csv"):
        return ""
    if ext in ("txt", "md", "csv"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""
