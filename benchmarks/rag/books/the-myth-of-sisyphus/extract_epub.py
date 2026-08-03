#!/usr/bin/env python3
"""Extract the benchmark's licensed local EPUB body into deterministic JSONL."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
from zipfile import ZipFile
from xml.etree import ElementTree as ET

DEFAULT_EPUB = Path("/Users/ywwl/Downloads/6006-西西弗神话/西西弗神话.epub")
DEFAULT_OUTPUT = Path(__file__).with_name("corpus.local.jsonl")
BODY_SECTIONS = {
    "text/part0004_split_000.html": ("荒诞推理", "荒诞推理"),
    "text/part0004_split_001.html": ("荒诞推理", "卷首语"),
    "text/part0004_split_002.html": ("荒诞推理", "荒诞与自杀"),
    "text/part0004_split_003.html": ("荒诞推理", "荒诞的藩篱"),
    "text/part0004_split_004.html": ("荒诞推理", "哲学的自杀"),
    "text/part0004_split_005.html": ("荒诞推理", "荒诞自由"),
    "text/part0005_split_000.html": ("荒诞人", "荒诞人"),
    "text/part0005_split_001.html": ("荒诞人", "荒诞人"),
    "text/part0005_split_002.html": ("荒诞人", "唐璜主义"),
    "text/part0005_split_003.html": ("荒诞人", "戏剧"),
    "text/part0005_split_004.html": ("荒诞人", "征服"),
    "text/part0006_split_000.html": ("荒诞创作", "荒诞创作"),
    "text/part0006_split_001.html": ("荒诞创作", "哲学与小说"),
    "text/part0006_split_002.html": ("荒诞创作", "基里洛夫"),
    "text/part0006_split_003.html": ("荒诞创作", "没有前途的创作"),
    "text/part0007_split_000.html": ("西西弗神话", "西西弗神话"),
    "text/part0007_split_001.html": ("西西弗神话", "西西弗神话"),
}
BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6"}


class BlockTextParser(HTMLParser):
    """Collect text from paragraph and heading blocks in document order."""

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
            self._parts.append("\n")

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
        text = re.sub(r"\s+", " ", "".join(self._parts)).strip()
        if text:
            self.blocks.append(text)
        self._tag = None
        self._parts.clear()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _opf_path(archive: ZipFile) -> str:
    container = ET.fromstring(archive.read("META-INF/container.xml"))
    for element in container.iter():
        if _local_name(element.tag) == "rootfile":
            return element.attrib["full-path"]
    raise ValueError("EPUB container has no OPF rootfile")


def _spine_files(archive: ZipFile, opf_path: str) -> list[str]:
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


def extract(epub_path: Path) -> list[dict[str, object]]:
    """Return main-text paragraph records in OPF spine order."""
    records: list[dict[str, object]] = []
    with ZipFile(epub_path) as archive:
        for spine_index, source_file in enumerate(
            _spine_files(archive, _opf_path(archive))
        ):
            labels = BODY_SECTIONS.get(source_file)
            if labels is None:
                continue
            parser = BlockTextParser()
            parser.feed(archive.read(source_file).decode("utf-8"))
            parser.close()
            chapter, section = labels
            for paragraph_index, text in enumerate(parser.blocks, start=1):
                records.append(
                    {
                        "paragraph_id": (
                            f"sisyphus-spine-{spine_index:03d}-p-{paragraph_index:04d}"
                        ),
                        "spine_index": spine_index,
                        "source_file": str(PurePosixPath(source_file)),
                        "chapter": chapter,
                        "section": section,
                        "text": text,
                    }
                )
    return records


def write_jsonl(records: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, default=DEFAULT_EPUB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    records = extract(args.epub)
    write_jsonl(records, args.output)
    print(f"extracted {len(records)} paragraphs to {args.output}")


if __name__ == "__main__":
    main()
