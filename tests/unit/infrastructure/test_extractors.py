import os
import tempfile
import pytest
from app.infrastructure.rag.extractors.base import Extractor, get_extractor
from app.infrastructure.rag.extractors.text_extractor import TextExtractor


def test_text_extractor_extensions():
    ext = TextExtractor()
    assert ".txt" in ext.extensions
    assert ".md" in ext.extensions


def test_text_extractor_extract_txt():
    ext = TextExtractor()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello World")
        tmp = f.name
    try:
        result = ext.extract(tmp)
        assert result == "Hello World"
    finally:
        os.unlink(tmp)


def test_text_extractor_extract_md():
    ext = TextExtractor()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Title\nContent")
        tmp = f.name
    try:
        result = ext.extract(tmp)
        assert "# Title" in result
    finally:
        os.unlink(tmp)


def test_get_extractor_returns_text_for_txt():
    e = get_extractor("/path/to/doc.txt")
    assert e is not None
    assert isinstance(e, TextExtractor)


def test_get_extractor_returns_text_for_md():
    e = get_extractor("readme.md")
    assert isinstance(e, TextExtractor)


def test_get_extractor_returns_none_for_unknown():
    e = get_extractor("image.xyz")
    assert e is None


def test_extractor_is_abstract():
    with pytest.raises(TypeError):
        Extractor()  # noqa
