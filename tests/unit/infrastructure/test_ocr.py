import pytest
from app.infrastructure.rag.ocr import OCRProvider
from app.infrastructure.rag.coordinator import Chunk


def test_ocr_provider_name():
    provider = OCRProvider()
    assert provider.name == "ocr"


def test_ocr_provider_implements_protocol():
    """OCRProvider 应实现 IndexProvider 协议。"""
    from app.infrastructure.rag.coordinator import IndexProvider
    assert isinstance(OCRProvider(), IndexProvider)


def test_ocr_index_and_search():
    provider = OCRProvider()
    # 模拟 OCR 提取的文本
    provider.index([
        {"content": "深度学习中的注意力机制允许模型关注输入的特定部分",
         "metadata": {"file": "slide1.png", "page": 1}},
        {"content": "Transformer 架构完全基于注意力机制",
         "metadata": {"file": "slide2.png", "page": 1}},
    ])
    assert provider.doc_count == 2

    results = provider.search("注意力机制", top_k=5)
    assert len(results) >= 1
    assert all(isinstance(c, Chunk) for c in results)
    assert all(c.source == "ocr" for c in results)
    # 最相关的结果应包含"注意力机制"
    assert any("注意力机制" in c.content for c in results)


def test_ocr_search_empty():
    provider = OCRProvider()
    results = provider.search("不存在的内容", top_k=5)
    assert results == []


def test_ocr_doc_count_zero_initially():
    provider = OCRProvider()
    assert provider.doc_count == 0


def test_ocr_chunk_metadata_preserved():
    provider = OCRProvider()
    provider.index([
        {"content": "测试文本", "metadata": {"file": "test.png", "page": 3}},
    ])
    results = provider.search("测试", top_k=1)
    assert len(results) == 1
    assert results[0].metadata["file"] == "test.png"
    assert results[0].metadata["page"] == 3
