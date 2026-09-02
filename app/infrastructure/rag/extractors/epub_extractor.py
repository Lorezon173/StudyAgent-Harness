"""EPUB 文本提取器（标准库实现，无第三方依赖）。

按 OPF spine/itemref 顺序抽取段落与标题块纯文本；任一环节失败整体返回空串。
"""

import posixpath
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from app.infrastructure.rag.extractors.base import Extractor

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6"}
_BR_SENTINEL = "\x00BR\x00"


def _local_name(tag: str) -> str:
    """去掉命名空间前缀，返回本地标签名。"""
    return tag.rsplit("}", 1)[-1]


def _opf_path(archive: zipfile.ZipFile) -> str:
    """从 container.xml 解析 OPF 根文件路径。"""
    container = ET.fromstring(archive.read("META-INF/container.xml"))
    for element in container.iter():
        if _local_name(element.tag) == "rootfile":
            full_path = element.attrib.get("full-path")
            if full_path:
                return full_path
    raise ValueError("EPUB container has no OPF rootfile")


def _spine_files(archive: zipfile.ZipFile, opf_path: str) -> list[str]:
    """按 OPF spine/itemref 顺序解析内容文件路径（非 ZIP/manifest 顺序）。

    href 需 URL 解码、去 fragment，并以 OPF 目录为基准做 POSIX 路径规范化。
    """
    opf = ET.fromstring(archive.read(opf_path))
    manifest = {
        element.attrib["id"]: element.attrib["href"]
        for element in opf.iter()
        if _local_name(element.tag) == "item"
        and "id" in element.attrib
        and "href" in element.attrib
    }
    opf_dir = posixpath.dirname(opf_path)
    files: list[str] = []
    for element in opf.iter():
        if _local_name(element.tag) != "itemref":
            continue
        href = unquote(manifest[element.attrib["idref"]]).split("#", 1)[0]
        files.append(posixpath.normpath(posixpath.join(opf_dir, href)))
    return files


def _normalize_block(text: str) -> str:
    """冻结契约：<br> 哨兵切分、逐片段折叠空白、用真实 \\n 回连。

    每个 <br> 恰好产生一个 "\\n"；普通空白折叠为单个 ASCII 空格并去除首尾空白。
    """
    return "\n".join(
        " ".join(fragment.split()) for fragment in text.split(_BR_SENTINEL)
    )


class _BlockTextParser(HTMLParser):
    """按文档顺序收集段落与标题块文本；<br> 视为受保护行内换行。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._tag: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BLOCK_TAGS:
            self._finish_block()
            self._tag = tag
        elif tag == "br" and self._tag is not None:
            self._parts.append(_BR_SENTINEL)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._tag:
            self._finish_block()

    def handle_data(self, data: str) -> None:
        if self._tag is not None:
            self._parts.append(data)

    def close(self) -> None:
        super().close()
        self._finish_block()

    def _finish_block(self) -> None:
        if self._tag is None:
            self._parts.clear()
            return
        text = _normalize_block("".join(self._parts)).strip()
        if text:
            self.blocks.append(text)
        self._tag = None
        self._parts.clear()


class EpubExtractor(Extractor):
    extensions = [".epub"]

    def extract(self, file_path: str) -> str:
        """提取 EPUB 纯文本；任一环节失败返回空串，不抛异常到上层。"""
        try:
            with zipfile.ZipFile(file_path) as archive:
                blocks: list[str] = []
                for content_path in _spine_files(archive, _opf_path(archive)):
                    parser = _BlockTextParser()
                    parser.feed(archive.read(content_path).decode("utf-8"))
                    parser.close()
                    blocks.extend(parser.blocks)
                return "\n\n".join(blocks)
        except Exception:
            return ""
