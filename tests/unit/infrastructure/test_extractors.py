import os
import tempfile
import zipfile

import pytest

from app.infrastructure.rag.extractors.base import Extractor, get_extractor
from app.infrastructure.rag.extractors.epub_extractor import EpubExtractor
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
        Extractor()


# ---------- EPUB ----------

CONTAINER_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles>'
    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    '</rootfiles>'
    '</container>'
)


def _xhtml(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
        f"<body>{body}</body></html>"
    )


def _make_opf(
    manifest_items: list[tuple[str, str, str]], spine_ids: list[str]
) -> str:
    """按 manifest 列出顺序生成 OPF；spine 顺序由 spine_ids 单独控制。"""
    items = "\n".join(
        f'    <item id="{iid}" href="{href}" media-type="{mtype}"/>'
        for iid, href, mtype in manifest_items
    )
    itemrefs = "\n".join(f'    <itemref idref="{rid}"/>' for rid in spine_ids)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="uid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:identifier id="uid">test-epub</dc:identifier>\n'
        '    <dc:title>Test EPUB</dc:title>\n'
        '    <dc:language>en</dc:language>\n'
        '  </metadata>\n'
        '  <manifest>\n'
        f"{items}\n"
        '  </manifest>\n'
        '  <spine>\n'
        f"{itemrefs}\n"
        '  </spine>\n'
        '</package>\n'
    )


def _build_epub(path: str, entries: list[tuple[str, bytes | str]]) -> None:
    """按 entries 列表顺序（即 ZIP 写入顺序）构建 EPUB。"""
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries:
            zf.writestr(name, data)


def test_get_extractor_returns_epub_for_lowercase():
    e = get_extractor("book.epub")
    assert isinstance(e, EpubExtractor)


def test_get_extractor_returns_epub_for_uppercase():
    e = get_extractor("BOOK.EPUB")
    assert isinstance(e, EpubExtractor)


def test_epub_extract_follows_spine_order_and_br_normalization():
    """ZIP 写入顺序、manifest 列出顺序均与 spine 顺序不同，输出仍严格按 spine。"""
    ext = EpubExtractor()
    ch1 = _xhtml(
        "<h1>Chapter One</h1>"
        "<p>First page paragraph.</p>"
        "<p>A<br>B</p>"
    )
    ch3 = _xhtml(
        "<h3>Chapter Three</h3>"
        "<p>Entity &amp; &lt; &gt;</p>"
        "<p>A   B</p>"
    )
    ch2 = _xhtml(
        "<h2>Chapter Two</h2>"
        "<p>A <br> B</p>"
        "<p>A<br><br>B</p>"
    )
    # manifest 顺序 ch2/ch1/ch3；spine 顺序 ch1/ch3/ch2
    opf = _make_opf(
        [
            ("ch2", "text/ch2.xhtml", "application/xhtml+xml"),
            ("ch1", "text/ch1.xhtml", "application/xhtml+xml"),
            ("ch3", "text/ch3.xhtml", "application/xhtml+xml"),
        ],
        ["ch1", "ch3", "ch2"],
    )
    entries = [
        ("META-INF/container.xml", CONTAINER_XML),
        ("OEBPS/content.opf", opf),
        ("OEBPS/text/ch3.xhtml", ch3),
        ("OEBPS/text/ch2.xhtml", ch2),
        ("OEBPS/text/ch1.xhtml", ch1),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "book.epub")
        _build_epub(epub, entries)
        result = ext.extract(epub)
    expected = "\n\n".join(
        [
            "Chapter One",
            "First page paragraph.",
            "A\nB",
            "Chapter Three",
            "Entity & < >",
            "A B",
            "Chapter Two",
            "A\nB",
            "A\n\nB",
        ]
    )
    assert result == expected
    # 额外显式顺序断言
    assert result.index("Chapter One") < result.index("Chapter Three")
    assert result.index("Chapter Three") < result.index("Chapter Two")


def test_epub_br_normalization_exact():
    """冻结的 <br> 归一化精确输出表。"""
    ext = EpubExtractor()
    body = (
        "<p>A<br>B</p>"
        "<p>A <br> B</p>"
        "<p>A\t<br>\n B</p>"
        "<p>A<br><br>B</p>"
        "<p>A   B</p>"
    )
    opf = _make_opf([("c1", "text/c1.xhtml", "application/xhtml+xml")], ["c1"])
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "br.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", CONTAINER_XML),
                ("OEBPS/content.opf", opf),
                ("OEBPS/text/c1.xhtml", _xhtml(body)),
            ],
        )
        result = ext.extract(epub)
    assert result == "A\nB\n\nA\nB\n\nA\nB\n\nA\n\nB\n\nA B"


def test_epub_extract_nonexistent_returns_empty():
    assert EpubExtractor().extract("/no/such/file.epub") == ""


def test_epub_extract_corrupt_zip_returns_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "bad.epub")
        with open(epub, "wb") as f:
            f.write(b"this is not a zip archive at all")
        assert EpubExtractor().extract(epub) == ""


def test_epub_extract_missing_container_returns_empty():
    ext = EpubExtractor()
    opf = _make_opf([("c1", "text/c1.xhtml", "application/xhtml+xml")], ["c1"])
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "nocontainer.epub")
        _build_epub(
            epub,
            [
                ("OEBPS/content.opf", opf),
                ("OEBPS/text/c1.xhtml", _xhtml("<p>Hello</p>")),
            ],
        )
        assert ext.extract(epub) == ""


def test_epub_extract_missing_opf_returns_empty():
    ext = EpubExtractor()
    # container 指向不存在的 OPF 文件
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles>'
        '<rootfile full-path="OEBPS/nope.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles>'
        '</container>'
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "noopf.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", container),
                ("OEBPS/text/c1.xhtml", _xhtml("<p>Hello</p>")),
            ],
        )
        assert ext.extract(epub) == ""


def test_epub_extract_missing_spine_resource_returns_empty():
    ext = EpubExtractor()
    # manifest 声明 c1 -> text/missing.xhtml，但该资源未写入 ZIP
    opf = _make_opf(
        [("c1", "text/missing.xhtml", "application/xhtml+xml")], ["c1"]
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "missres.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", CONTAINER_XML),
                ("OEBPS/content.opf", opf),
            ],
        )
        assert ext.extract(epub) == ""


def test_epub_extract_invalid_utf8_returns_empty():
    ext = EpubExtractor()
    opf = _make_opf([("c1", "text/c1.xhtml", "application/xhtml+xml")], ["c1"])
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "badutf.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", CONTAINER_XML),
                ("OEBPS/content.opf", opf),
                ("OEBPS/text/c1.xhtml", b"\xff\xfe"),
            ],
        )
        assert ext.extract(epub) == ""


def test_epub_br_only_block_filtered():
    """只含 <br> 的纯空白块应被过滤，不产出多余空行。"""
    ext = EpubExtractor()
    body = "<p>A</p><p><br></p><p>B</p>"
    opf = _make_opf([("c1", "text/c1.xhtml", "application/xhtml+xml")], ["c1"])
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "bronly.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", CONTAINER_XML),
                ("OEBPS/content.opf", opf),
                ("OEBPS/text/c1.xhtml", _xhtml(body)),
            ],
        )
        assert ext.extract(epub) == "A\n\nB"


def test_epub_br_only_book_returns_empty():
    """全书仅含 <br> 的块应返回空串，而不是单个换行。"""
    ext = EpubExtractor()
    body = "<p><br></p>"
    opf = _make_opf([("c1", "text/c1.xhtml", "application/xhtml+xml")], ["c1"])
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "bronlybook.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", CONTAINER_XML),
                ("OEBPS/content.opf", opf),
                ("OEBPS/text/c1.xhtml", _xhtml(body)),
            ],
        )
        assert ext.extract(epub) == ""


def test_epub_href_url_decoding_and_fragment():
    """href 的 URL 解码、去 fragment、相对 OPF 目录 POSIX 规范化。"""
    ext = EpubExtractor()
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles>'
        '<rootfile full-path="OEBPS/books/content.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles>'
        '</container>'
    )
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:identifier id="uid">test</dc:identifier>\n'
        '    <dc:title>T</dc:title>\n'
        '  </metadata>\n'
        '  <manifest>\n'
        '    <item id="c1" href="../text/my%20file.xhtml#sec1" media-type="application/xhtml+xml"/>\n'
        '  </manifest>\n'
        '  <spine>\n'
        '    <itemref idref="c1"/>\n'
        '  </spine>\n'
        '</package>\n'
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "href.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", container),
                ("OEBPS/books/content.opf", opf),
                ("OEBPS/text/my file.xhtml", _xhtml("<p>Decoded Path</p>")),
            ],
        )
        assert ext.extract(epub) == "Decoded Path"


def test_epub_br_at_block_edges():
    """块首/块尾 <br> 的换行应被收敛，不产生多余空行；块中间 <br> 语义不变。"""
    ext = EpubExtractor()
    body = "<p>A<br></p><p><br>B</p><p>A<br>B</p>"
    opf = _make_opf([("c1", "text/c1.xhtml", "application/xhtml+xml")], ["c1"])
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "bredges.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", CONTAINER_XML),
                ("OEBPS/content.opf", opf),
                ("OEBPS/text/c1.xhtml", _xhtml(body)),
            ],
        )
        assert ext.extract(epub) == "A\n\nB\n\nA\nB"


def test_epub_container_without_rootfile_returns_empty():
    """container.xml 有内容但无 rootfile 元素 → 空串。"""
    ext = EpubExtractor()
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles></rootfiles>'
        '</container>'
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "norootfile.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", container),
            ],
        )
        assert ext.extract(epub) == ""


def test_epub_spine_idref_missing_from_manifest_returns_empty():
    """spine 的 idref 不在 manifest 中 → 空串。"""
    ext = EpubExtractor()
    opf = _make_opf([("c1", "text/c1.xhtml", "application/xhtml+xml")], ["missing"])
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "badref.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", CONTAINER_XML),
                ("OEBPS/content.opf", opf),
            ],
        )
        assert ext.extract(epub) == ""


def test_epub_malformed_xml_returns_empty():
    """container.xml 或 OPF 为畸形 XML → 空串。"""
    ext = EpubExtractor()
    with tempfile.TemporaryDirectory() as tmpdir:
        epub = os.path.join(tmpdir, "badxml.epub")
        _build_epub(
            epub,
            [
                ("META-INF/container.xml", "this is not xml at all"),
            ],
        )
        assert ext.extract(epub) == ""

