import tempfile
import os
import pytest
from app.infrastructure.rag.code_index import CodeIndexProvider
from app.infrastructure.rag.coordinator import Chunk


SAMPLE_CODE = '''
"""A simple math module."""

def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b

class Calculator:
    """A simple calculator class."""

    def __init__(self, initial: int = 0):
        self.value = initial

    def add(self, x: int) -> int:
        """Add x to the current value."""
        self.value += x
        return self.value
'''


def test_code_index_provider_name():
    provider = CodeIndexProvider()
    assert provider.name == "code"


def test_code_index_provider_implements_protocol():
    from app.infrastructure.rag.coordinator import IndexProvider
    assert isinstance(CodeIndexProvider(), IndexProvider)


def test_index_file_extracts_functions():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    assert provider.doc_count >= 3  # add, multiply, Calculator


def test_search_by_function_name():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    results = provider.search("add", top_k=5)
    assert len(results) >= 1
    # 函数名 add 应命中
    assert any("add" in c.content for c in results)


def test_search_by_docstring():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    results = provider.search("multiply two integers", top_k=3)
    assert len(results) >= 1
    assert any("multiply" in c.content.lower() for c in results)


def test_search_by_class_name():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    results = provider.search("Calculator", top_k=3)
    assert len(results) >= 1
    assert any("Calculator" in c.content for c in results)


def test_code_chunk_has_source_metadata():
    provider = CodeIndexProvider()
    provider.index_file("/fake/math.py", SAMPLE_CODE)
    results = provider.search("add", top_k=1)
    assert len(results) == 1
    assert results[0].source == "code"
    assert "file" in results[0].metadata


def test_code_search_empty():
    provider = CodeIndexProvider()
    assert provider.search("nonexistent", top_k=5) == []


def test_index_repo_scans_directory():
    provider = CodeIndexProvider()
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建两个 .py 文件
        with open(os.path.join(tmpdir, "a.py"), "w") as f:
            f.write("def foo():\n    return 42\n")
        with open(os.path.join(tmpdir, "b.py"), "w") as f:
            f.write("def bar():\n    return 99\n")
        count = provider.index_repo(tmpdir, glob_pattern="**/*.py")
        assert count >= 2
        # foo 可检索
        assert len(provider.search("foo", top_k=1)) == 1
        # bar 可检索
        assert len(provider.search("bar", top_k=1)) == 1
