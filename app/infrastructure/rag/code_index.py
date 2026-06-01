"""代码仓库 AST 切片索引 Provider（§9 RAG 扩展）。

实现 IndexProvider 协议，用 Python ast 标准库解析源码，
按函数/类/方法粒度建索引。
"""

import ast
import glob
import os

from app.infrastructure.rag.coordinator import Chunk, IndexProvider
from app.infrastructure.rag.store import FakeRAGStore


class CodeIndexProvider(IndexProvider):
    """代码仓库索引 Provider。

    用法：
        provider = CodeIndexProvider()
        provider.index_repo("/path/to/repo")
        results = provider.search("def train")
    """

    name = "code"

    def __init__(self):
        self._store = FakeRAGStore()

    # --- AST 解析 ---

    def index_file(self, file_path: str, source_code: str) -> list[dict]:
        """解析单个 Python 文件，为每个函数/类建立索引项。"""
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []

        docs = []
        module_doc = ast.get_docstring(tree) or ""

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = self._node_to_doc(node, file_path, module_doc)
                if doc:
                    docs.append(doc)
        self._store.index(docs)
        return docs

    def _node_to_doc(self, node: ast.AST, file_path: str, module_doc: str) -> dict | None:
        """将 AST 节点转为可索引的文档 dict。"""
        name = node.name
        docstring = ast.get_docstring(node) or ""
        try:
            source_snippet = ast.unparse(node)
        except Exception:
            source_snippet = ""

        # 索引内容 = 符号名 + docstring + 模块 doc + 源码前 500 字符
        content_parts = [name]
        if docstring:
            content_parts.append(docstring)
        if module_doc:
            content_parts.append(module_doc)
        if source_snippet:
            content_parts.append(source_snippet[:500])
        content = "\n".join(content_parts)

        node_type = "class" if isinstance(node, ast.ClassDef) else "function"
        return {
            "content": content,
            "metadata": {
                "file": file_path,
                "symbol_name": name,
                "symbol_type": node_type,
                "has_docstring": bool(docstring),
            }
        }

    # --- 仓库级索引 ---

    def index_repo(self, repo_path: str, glob_pattern: str = "**/*.py") -> int:
        """扫描仓库目录，索引所有匹配的 Python 文件。返回索引的符号总数。"""
        pattern = os.path.join(repo_path, glob_pattern)
        files = glob.glob(pattern, recursive=True)
        total = 0
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    source = f.read()
            except (IOError, UnicodeDecodeError):
                continue
            docs = self.index_file(fp, source)
            total += len(docs)
        return total

    # --- IndexProvider 协议 ---

    def index(self, docs: list[dict]) -> None:
        """批量索引已解析的代码文档。"""
        self._store.index(docs)

    def search(self, query: str, top_k: int = 5) -> list[Chunk]:
        """按符号名/docstring/代码内容检索。"""
        raw = self._store.query(query, top_k)
        return [
            Chunk(content=r["content"], score=float(r.get("score", 0)),
                  source="code", metadata=r.get("metadata", {}))
            for r in raw
        ]

    @property
    def doc_count(self) -> int:
        return self._store.doc_count
