"""项目级文档切块服务（RAG Gate 0）。

本模块只负责把规范化文本或元素转换为 ChunkDocument；不做文件 IO、embedding、
持久化或检索。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
import unicodedata
from typing import Any

DOC_PROTOCOL = "doc-v1"
NORMALIZER_VERSION = "doc-norm-1"
CHUNK_PROTOCOL = "chunk-v1"
DEFAULT_CHUNKING_SPEC_VERSION = "chunk-policy-1"


@dataclass(frozen=True)
class ChunkElement:
    """切块输入的一个有序元素。"""

    text: str
    element_type: str = "paragraph"
    source_locator: dict[str, Any] = field(default_factory=dict)
    atomic: bool = False


@dataclass(frozen=True)
class ChunkingContext:
    """生成 ChunkDocument 所需的显式摄入上下文。"""

    import_namespace: str
    source_format: str
    scope: str = "global"
    user_id: int | None = None
    source_locator: dict[str, Any] = field(default_factory=dict)
    chunking_spec_version: str = DEFAULT_CHUNKING_SPEC_VERSION


@dataclass(frozen=True)
class ChunkPolicy:
    """第一版按 Unicode code point 计数的切块策略。

    hard_limit 是 embedding 安全阈值（spec §3.3.3）：普通文本经二次切分后
    每块 <= chunk_size <= hard_limit；atomic 元素超限时整块保留并打
    ``oversized_hard_limit`` 标记（不切裂），由摄入编排转为 warning。
    默认值为项目保守默认，非模型实测上限；调整时须升级 chunking_spec_version。
    """

    chunk_size: int = 500
    chunk_overlap: int = 50
    hard_limit: int = 8192

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap 必须满足 0 <= chunk_overlap < chunk_size")
        if self.hard_limit < self.chunk_size:
            raise ValueError("hard_limit 必须大于等于 chunk_size")


def normalize_text(text: str) -> str:
    """严格实现 DEC-012 中固定的 doc-norm-1。"""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip(" \t") for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip("\n")


def _frame(name: str, value: bytes) -> bytes:
    return name.encode("ascii") + b"=" + str(len(value)).encode("ascii") + b":" + value


def _sha256(fields: list[tuple[str, bytes]]) -> str:
    payload = b"".join(_frame(name, value) for name, value in fields)
    return hashlib.sha256(payload).hexdigest()


def _canonical_range(
    start_element: int, start_offset: int, end_element: int, end_offset: int
) -> str:
    if min(start_element, start_offset, end_element, end_offset) < 0:
        raise ValueError("元素坐标不得为负数")
    if (end_element, end_offset) < (start_element, start_offset):
        raise ValueError("range 必须是非降序半开区间")
    return (
        '{"end":{"element":%d,"offset":%d},'
        '"start":{"element":%d,"offset":%d}}'
    ) % (end_element, end_offset, start_element, start_offset)


def compute_doc_id(import_namespace: str, text: str) -> tuple[str, str]:
    """返回 DEC-012 doc_id 及其 canonical 文本。"""
    if not import_namespace:
        raise ValueError("import_namespace 不得为空")
    canonical_text = normalize_text(text)
    doc_id = _sha256([
        ("protocol", DOC_PROTOCOL.encode("utf-8")),
        ("import_namespace", import_namespace.encode("utf-8")),
        ("normalizer_version", NORMALIZER_VERSION.encode("utf-8")),
        ("normalized_document_text", canonical_text.encode("utf-8")),
    ])
    return doc_id, canonical_text


def compute_chunk_id(
    doc_id: str,
    chunking_spec_version: str,
    start_element: int,
    start_offset: int,
    end_element: int,
    end_offset: int,
    canonical_chunk_text: str,
) -> str:
    """返回 DEC-012 chunk_id；range 使用 0-based code-point 半开区间。"""
    if not doc_id:
        raise ValueError("doc_id 不得为空")
    if not chunking_spec_version:
        raise ValueError("chunking_spec_version 不得为空")
    return _sha256([
        ("protocol", CHUNK_PROTOCOL.encode("utf-8")),
        ("doc_id", doc_id.encode("ascii")),
        ("chunking_spec_version", chunking_spec_version.encode("utf-8")),
        ("canonical_element_range", _canonical_range(
            start_element, start_offset, end_element, end_offset
        ).encode("utf-8")),
        ("canonical_chunk_text", canonical_chunk_text.encode("utf-8")),
    ])


class ChunkingService:
    """无状态 ChunkDocument 生产者。"""

    def chunk_text(
        self,
        text: str,
        context: ChunkingContext,
        policy: ChunkPolicy | None = None,
    ) -> list[dict[str, Any]]:
        """按空行适配纯文本后生成 ChunkDocument。"""
        canonical_text = normalize_text(text)
        if not canonical_text:
            return []
        elements = [ChunkElement(part) for part in re.split(r"\n\n+", canonical_text) if part]
        return self.chunk_elements(elements, context, policy)

    def chunk_elements(
        self,
        elements: list[ChunkElement],
        context: ChunkingContext,
        policy: ChunkPolicy | None = None,
    ) -> list[dict[str, Any]]:
        """把有序元素切成现有 index_documents 可消费的 docs dict。"""
        if not context.import_namespace:
            raise ValueError("import_namespace 不得为空")
        if not context.source_format:
            raise ValueError("source_format 不得为空")
        policy = policy or ChunkPolicy()
        # B3-01：canonical 元素流必须从 canonical 全文按 \n\n+ 重建（DEC-012），
        # 与 chunk_text 的 re.split 收敛——等价表示得到相同 element range / chunk_id。
        canonical_elements: list[ChunkElement] = []
        for element in elements:
            normalized = normalize_text(element.text)
            if not normalized:
                continue
            for part in re.split(r"\n\n+", normalized):
                if part:
                    canonical_elements.append(ChunkElement(
                        text=part,
                        element_type=element.element_type,
                        source_locator=element.source_locator,
                        atomic=element.atomic,
                    ))
        if not canonical_elements:
            return []

        doc_id, _ = compute_doc_id(
            context.import_namespace,
            "\n\n".join(element.text for element in canonical_elements),
        )
        docs: list[dict[str, Any]] = []
        pending: list[tuple[int, ChunkElement]] = []
        pending_size = 0

        def emit_pending() -> None:
            nonlocal pending, pending_size
            if not pending:
                return
            text = "\n\n".join(element.text for _, element in pending)
            start_index, first = pending[0]
            end_index, last = pending[-1]
            docs.extend(self._documents_for_text(
                text, doc_id, context, policy,
                start_index, 0, end_index, len(last.text),
                [element.element_type for _, element in pending],
                [element.source_locator for _, element in pending],
            ))
            pending = []
            pending_size = 0

        for element_index, element in enumerate(canonical_elements):
            if element.atomic or element.element_type in {"table", "formula"}:
                emit_pending()
                docs.extend(self._documents_for_text(
                    element.text, doc_id, context, policy,
                    element_index, 0, element_index, len(element.text),
                    [element.element_type], [element.source_locator], atomic=True,
                ))
                continue
            if pending and pending_size + 2 + len(element.text) > policy.chunk_size:
                emit_pending()
            # B3-03：separator_size 在 flush 之后按新 pending 组重算，
            # 避免 flush 前的旧值把新组首元素虚胖 2 字符。
            separator_size = 2 if pending else 0
            pending.append((element_index, element))
            pending_size += separator_size + len(element.text)
        emit_pending()

        for index, document in enumerate(docs):
            document["metadata"]["chunk_index"] = index
        return docs

    def _documents_for_text(
        self,
        text: str,
        doc_id: str,
        context: ChunkingContext,
        policy: ChunkPolicy,
        start_element: int,
        start_offset: int,
        end_element: int,
        end_offset: int,
        element_types: list[str],
        element_locators: list[dict[str, Any]],
        atomic: bool = False,
    ) -> list[dict[str, Any]]:
        pieces = [(text, start_offset, end_offset)]
        if not atomic and len(text) > policy.chunk_size:
            pieces = self._split_long_text(text, start_offset, policy)
        documents = []
        oversized = atomic and len(text) > policy.hard_limit
        for content, piece_start, piece_end in pieces:
            if not content.strip():
                continue
            chunk_id = compute_chunk_id(
                doc_id, context.chunking_spec_version,
                start_element, piece_start, end_element, piece_end, content,
            )
            locator = {
                **context.source_locator,
                "element_range": {
                    "start": {"element": start_element, "offset": piece_start},
                    "end": {"element": end_element, "offset": piece_end},
                },
            }
            if element_locators:
                locator["elements"] = element_locators
            documents.append({
                "content": content,
                "doc_id": doc_id,
                "source": "vector",
                "scope": context.scope,
                "user_id": context.user_id,
                "metadata": {
                    "doc_id": doc_id,
                    "chunk_id": chunk_id,
                    "chunk_index": 0,
                    "chunking_spec_version": context.chunking_spec_version,
                    "source_format": context.source_format,
                    "source_locator": locator,
                    "element_types": element_types,
                    "normalizer_version": NORMALIZER_VERSION,
                },
            })
            if oversized:
                # spec §3.3.3：超 hard_limit 的 atomic 块不可静默进入 embedding，
                # 整块保留 + 可观察标记，由摄入编排转为 warning。
                documents[-1]["metadata"]["oversized_hard_limit"] = True
        return documents

    @staticmethod
    def _split_long_text(
        text: str, start_offset: int, policy: ChunkPolicy
    ) -> list[tuple[str, int, int]]:
        """按句界/空白优先、硬切兜底的 Unicode code-point 窗口切分。

        B3-02 不变式：
        - 每块长度 <= chunk_size（marker 搜索窗为 [cursor+1, limit)，
          marker 命中于 limit 时放弃该切点，由 limit 硬切兜底）；
        - overlap 回退不产生退化碎片：marker 切点必须与 cursor 保持
          > chunk_overlap 的距离，保证回退后 cursor 每轮净前进 >= 1。
        """
        pieces = []
        cursor = 0
        while cursor < len(text):
            limit = min(cursor + policy.chunk_size, len(text))
            boundary = limit
            if limit < len(text):
                best = max(text.rfind(marker, cursor + 1, limit)
                           for marker in ("\n", "。", "！", "？", ".", "!", "?", " "))
                if best > cursor and best + 1 - cursor > policy.chunk_overlap:
                    boundary = best + 1
            content = text[cursor:boundary]
            pieces.append((content, start_offset + cursor, start_offset + boundary))
            if boundary == len(text):
                break
            cursor = max(boundary - policy.chunk_overlap, cursor + 1)
        return pieces
