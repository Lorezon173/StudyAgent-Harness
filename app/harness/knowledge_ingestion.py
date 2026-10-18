"""新增通用文档 Gate 0 的薄摄入编排。"""

from __future__ import annotations

import json
import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from pathlib import Path
from typing import Any

from app.harness.chunking_service import (
    CHUNK_PROTOCOL,
    DOC_PROTOCOL,
    NORMALIZER_VERSION,
    ChunkingContext,
    ChunkingService,
    ChunkPolicy,
)
from app.infrastructure.rag.coordinator import RAGCoordinator
from app.infrastructure.rag.extractors.base import get_extractor


@dataclass(frozen=True)
class IngestResult:
    status: str
    doc_id: str | None = None
    planned_chunk_count: int = 0
    written_chunk_count: int = 0
    warnings: list[str] = field(default_factory=list)


_PREPARATION_SUMMARIES = {
    "unsupported": "不支持的文档格式",
    "extraction_empty": "未提取到可用文本",
    "invalid_request": "摄入参数无效",
}


class IngestionPreparationError(ValueError):
    """仅携带冻结状态与安全摘要的准备阶段错误。"""

    def __init__(self, status: str, field_name: str | None = None) -> None:
        if status not in _PREPARATION_SUMMARIES:
            raise ValueError("未知的准备阶段错误状态")
        self.status = status
        self.safe_summary = _PREPARATION_SUMMARIES[status]
        # 只允许内部固定字段名帮助兼容旧调用方，不接纳路径、正文或错误原文。
        safe_fields = {
            "import_namespace", "scope", "user_id", "chunking_spec_version", "policy",
            "global", "private",
        }
        suffix = f" ({field_name})" if field_name in safe_fields else ""
        super().__init__(f"{self.safe_summary}{suffix}")


def _freeze_json(value: Any) -> Any:
    """递归复制 JSON 值并冻结映射、数组；拒绝非 JSON 与非有限数。"""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON 对象键必须为字符串")
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ValueError("值必须是严格 JSON 数据")


def _thaw_json(value: Any) -> Any:
    """将冻结 JSON 值递归复制为彼此隔离的普通 dict/list。"""
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _canonical_json(value: Any) -> bytes:
    """序列化冻结契约规定的规范 JSON 字节。"""
    return json.dumps(
        _thaw_json(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _manifest_sha256(rows: list[dict[str, Any]] | tuple[Any, ...]) -> str:
    """按完整规范行字节排序，保留重复行后计算 prepared-manifest 摘要。"""
    ordered_rows = [json.loads(row_bytes) for row_bytes in sorted(
        _canonical_json(row) for row in rows
    )]
    return hashlib.sha256(_canonical_json(ordered_rows)).hexdigest()


def _safe_warnings(documents: Any) -> tuple[str, ...]:
    """仅从合法的 oversized 标记生成固定、无正文的产品 warning。"""
    if not isinstance(documents, (list, tuple)):
        raise ValueError("prepared warnings 无效")
    warnings = []
    for doc in documents:
        if not isinstance(doc, Mapping) or not isinstance(doc.get("metadata"), Mapping):
            raise ValueError("prepared warnings 无效")
        metadata = doc["metadata"]
        if "oversized_hard_limit" not in metadata:
            continue
        oversized = metadata["oversized_hard_limit"]
        if not isinstance(oversized, bool):
            raise ValueError("prepared warnings 无效")
        if not oversized:
            continue
        chunk_index = metadata.get("chunk_index")
        if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
            raise ValueError("prepared warnings 无效")
        warnings.append(
            f"chunk_index={chunk_index} 超过 embedding 安全阈值"
            "（hard_limit），已整块保留（atomic 不切裂）"
        )
    return tuple(warnings)


@dataclass(frozen=True)
class PreparedIngestion:
    """不含运行绑定的摄入快照；所有可变输入在构造时深复制并冻结。"""

    schema_version: str
    source_sha256: str
    source_format: str
    import_namespace: str
    doc_id: str
    scope: str
    owner: int | None
    normalizer_version: str
    chunking_version: str
    doc_protocol: str
    chunk_protocol: str
    chunk_policy: Mapping[str, int]
    documents: tuple[Mapping[str, Any], ...]
    manifest: Mapping[str, Any]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("owner", "chunk_policy", "documents", "manifest", "warnings"):
            object.__setattr__(self, name, _freeze_json(getattr(self, name)))
        if (
            not isinstance(self.warnings, tuple)
            or any(not isinstance(warning, str) for warning in self.warnings)
            or self.warnings != _safe_warnings(self.documents)
        ):
            raise ValueError("prepared warnings 无效")

    def to_intent_metadata(self) -> dict[str, Any]:
        """返回不含正文、且与快照相互隔离的 JSON 元数据副本。"""
        KnowledgeIngestionService._validate_prepared(self)
        keys = (
            "schema_version", "source_sha256", "source_format", "import_namespace",
            "doc_id", "scope", "owner", "normalizer_version", "chunking_version",
            "doc_protocol", "chunk_protocol", "chunk_policy", "warnings",
        )
        result = {key: _thaw_json(getattr(self, key)) for key in keys}
        result["warnings"] = list(result["warnings"])
        return result


class KnowledgeIngestionService:
    """extract → adapt → chunk → index 的薄编排；不接管 OCR/Code 专用路径。"""

    def __init__(
        self,
        coordinator: RAGCoordinator,
        chunker: ChunkingService | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._chunker = chunker or ChunkingService()

    @staticmethod
    def _warnings_for_documents(documents: list[dict[str, Any]]) -> list[str]:
        return list(_safe_warnings(documents))

    def prepare_file(
        self,
        file_path: str,
        *,
        import_namespace: str,
        scope: str = "global",
        user_id: int | None = None,
        chunking_spec_version: str = "chunk-policy-1",
        policy: ChunkPolicy | None = None,
    ) -> PreparedIngestion:
        """提取并切块一次，交付不可变快照；本阶段不做 embedding 或写入。"""
        if not isinstance(file_path, str) or not file_path:
            raise IngestionPreparationError("invalid_request")
        if not isinstance(import_namespace, str) or not import_namespace:
            raise IngestionPreparationError("invalid_request", "import_namespace")
        if not isinstance(chunking_spec_version, str) or not chunking_spec_version:
            raise IngestionPreparationError("invalid_request", "chunking_spec_version")
        if scope == "global":
            if user_id is not None:
                raise IngestionPreparationError("invalid_request", "global")
            owner = None
        elif scope == "private":
            if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
                raise IngestionPreparationError("invalid_request", "private")
            owner = user_id
        else:
            raise IngestionPreparationError("invalid_request", "scope")

        active_policy = policy if policy is not None else ChunkPolicy()
        if not isinstance(active_policy, ChunkPolicy):
            raise IngestionPreparationError("invalid_request", "policy")
        policy_values = {
            "chunk_size": active_policy.chunk_size,
            "chunk_overlap": active_policy.chunk_overlap,
            "hard_limit": active_policy.hard_limit,
        }
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in policy_values.values()
        ):
            raise IngestionPreparationError("invalid_request", "policy")
        chunk_size = policy_values["chunk_size"]
        overlap = policy_values["chunk_overlap"]
        hard_limit = policy_values["hard_limit"]
        if chunk_size <= 0 or not 0 <= overlap < chunk_size or hard_limit < chunk_size:
            raise IngestionPreparationError("invalid_request", "policy")

        source_path = Path(file_path)
        source_format = source_path.suffix.lower().lstrip(".")
        extractor = get_extractor(file_path)
        if extractor is None:
            raise IngestionPreparationError("unsupported")

        source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
        text = extractor.extract(file_path)
        context = ChunkingContext(
            import_namespace=import_namespace,
            source_format=source_format,
            scope=scope,
            user_id=user_id,
            source_locator={"file_path": file_path},
            chunking_spec_version=chunking_spec_version,
        )
        documents = (
            self._chunker.chunk_text(text, context, active_policy)
            if isinstance(text, str) and text
            else []
        )
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != source_sha256:
            raise IngestionPreparationError("invalid_request")
        if not text:
            raise IngestionPreparationError("extraction_empty")
        if not isinstance(text, str):
            raise IngestionPreparationError("invalid_request")
        if not documents:
            raise IngestionPreparationError("extraction_empty")

        rows = self._build_manifest_rows(
            documents,
            doc_id=documents[0].get("doc_id"),
            scope=scope,
            owner=owner,
            source_format=source_format,
            chunking_spec_version=chunking_spec_version,
        )
        doc_id = rows[0]["doc_id"]
        manifest = {
            "schema_version": "prepared-manifest-v1",
            "doc_id": doc_id,
            "rows": rows,
            "row_count": len(rows),
            "manifest_sha256": _manifest_sha256(rows),
        }
        warnings = self._warnings_for_documents(documents)
        return PreparedIngestion(
            schema_version="prepared-ingestion-v1",
            source_sha256=source_sha256,
            source_format=source_format,
            import_namespace=import_namespace,
            doc_id=doc_id,
            scope=scope,
            owner=owner,
            normalizer_version=NORMALIZER_VERSION,
            chunking_version=chunking_spec_version,
            doc_protocol=DOC_PROTOCOL,
            chunk_protocol=CHUNK_PROTOCOL,
            chunk_policy=policy_values,
            documents=documents,
            manifest=manifest,
            warnings=warnings,
        )

    @staticmethod
    def _build_manifest_rows(
        documents: list[dict[str, Any]],
        *,
        doc_id: Any,
        scope: str,
        owner: int | None,
        source_format: str,
        chunking_spec_version: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(doc_id, str) or not doc_id or not documents:
            raise ValueError("ChunkDocument 身份或数量无效")
        if scope == "global":
            if owner is not None:
                raise ValueError("ChunkDocument owner 与 scope 不一致")
        elif scope == "private":
            if isinstance(owner, bool) or not isinstance(owner, int) or owner <= 0:
                raise ValueError("ChunkDocument owner 与 scope 不一致")
        else:
            raise ValueError("ChunkDocument scope 无效")
        rows: list[dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()
        for expected_index, doc in enumerate(documents):
            if not isinstance(doc, Mapping):
                raise ValueError("ChunkDocument 格式无效")
            metadata = doc.get("metadata")
            if not isinstance(metadata, Mapping):
                raise ValueError("ChunkDocument metadata 无效")
            chunk_index = metadata.get("chunk_index")
            chunk_id = metadata.get("chunk_id")
            content = doc.get("content")
            document_owner = doc.get("user_id")
            source_locator = metadata.get("source_locator")
            if scope == "global":
                owner_matches = document_owner is None
            else:
                owner_matches = (
                    not isinstance(document_owner, bool)
                    and isinstance(document_owner, int)
                    and document_owner > 0
                    and document_owner == owner
                )
            if (
                doc.get("doc_id") != doc_id
                or doc.get("source") != "vector"
                or metadata.get("doc_id") != doc_id
                or doc.get("scope") != scope
                or not owner_matches
                or isinstance(chunk_index, bool)
                or not isinstance(chunk_index, int)
                or chunk_index != expected_index
                or not isinstance(chunk_id, str)
                or not chunk_id
                or chunk_id in seen_chunk_ids
                or metadata.get("normalizer_version") != NORMALIZER_VERSION
                or metadata.get("chunking_spec_version") != chunking_spec_version
                or metadata.get("source_format") != source_format
                or not isinstance(content, str)
                or not content
                or not isinstance(source_locator, Mapping)
            ):
                raise ValueError("ChunkDocument provenance 校验失败")
            try:
                _canonical_json(source_locator)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("ChunkDocument source_locator 不是严格 JSON 对象") from exc
            seen_chunk_ids.add(chunk_id)
            rows.append({
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "chunk_index": chunk_index,
                "scope": scope,
                "owner": owner,
                "source_locator": _thaw_json(source_locator),
            })
        return rows

    @staticmethod
    def _validate_prepared(prepared: PreparedIngestion) -> list[dict[str, Any]]:
        """重新验证快照身份、docs 与无正文 manifest 的逐行一致性。"""
        if not isinstance(prepared, PreparedIngestion):
            raise ValueError("prepared 类型无效")
        if (
            prepared.schema_version != "prepared-ingestion-v1"
            or not isinstance(prepared.source_sha256, str)
            or len(prepared.source_sha256) != 64
            or any(char not in "0123456789abcdef" for char in prepared.source_sha256)
            or not isinstance(prepared.source_format, str)
            or not prepared.source_format
            or not isinstance(prepared.import_namespace, str)
            or not prepared.import_namespace
            or not isinstance(prepared.doc_id, str)
            or not prepared.doc_id
            or prepared.normalizer_version != NORMALIZER_VERSION
            or prepared.doc_protocol != DOC_PROTOCOL
            or prepared.chunk_protocol != CHUNK_PROTOCOL
            or not isinstance(prepared.chunking_version, str)
            or not prepared.chunking_version
        ):
            raise ValueError("prepared 身份或版本无效")
        if prepared.scope == "global":
            if prepared.owner is not None:
                raise ValueError("prepared owner 与 scope 不一致")
        elif prepared.scope == "private":
            if (
                isinstance(prepared.owner, bool)
                or not isinstance(prepared.owner, int)
                or prepared.owner <= 0
            ):
                raise ValueError("prepared owner 与 scope 不一致")
        else:
            raise ValueError("prepared scope 无效")

        policy = prepared.chunk_policy
        if not isinstance(policy, Mapping) or set(policy) != {
            "chunk_size", "chunk_overlap", "hard_limit"
        }:
            raise ValueError("prepared chunk_policy 无效")
        policy_values = [policy[key] for key in ("chunk_size", "chunk_overlap", "hard_limit")]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in policy_values):
            raise ValueError("prepared chunk_policy 无效")
        chunk_size, overlap, hard_limit = policy_values
        if chunk_size <= 0 or not 0 <= overlap < chunk_size or hard_limit < chunk_size:
            raise ValueError("prepared chunk_policy 无效")

        if not isinstance(prepared.documents, tuple) or not prepared.documents:
            raise ValueError("prepared documents 无效")
        docs = [_thaw_json(doc) for doc in prepared.documents]
        rows = KnowledgeIngestionService._build_manifest_rows(
            docs,
            doc_id=prepared.doc_id,
            scope=prepared.scope,
            owner=prepared.owner,
            source_format=prepared.source_format,
            chunking_spec_version=prepared.chunking_version,
        )
        if not isinstance(prepared.manifest, Mapping) or set(prepared.manifest) != {
            "schema_version", "doc_id", "rows", "row_count", "manifest_sha256"
        }:
            raise ValueError("prepared manifest 无效")
        manifest = _thaw_json(prepared.manifest)
        actual_rows = manifest.get("rows")
        row_keys = {
            "doc_id", "chunk_id", "content_sha256", "chunk_index",
            "scope", "owner", "source_locator",
        }
        if not isinstance(actual_rows, list) or any(
            not isinstance(row, Mapping) or set(row) != row_keys for row in actual_rows
        ):
            raise ValueError("prepared manifest rows 无效")
        try:
            actual_row_bytes = tuple(_canonical_json(row) for row in actual_rows)
            expected_row_bytes = tuple(_canonical_json(row) for row in rows)
            actual_manifest_digest = _manifest_sha256(actual_rows)
            expected_manifest_digest = _manifest_sha256(rows)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("prepared manifest rows 无效") from exc
        row_count = manifest.get("row_count")
        if (
            manifest.get("schema_version") != "prepared-manifest-v1"
            or manifest.get("doc_id") != prepared.doc_id
            or actual_row_bytes != expected_row_bytes
            or isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or row_count != len(actual_rows)
            or actual_manifest_digest != manifest.get("manifest_sha256")
            or actual_manifest_digest != expected_manifest_digest
        ):
            raise ValueError("prepared manifest 与 documents 不一致")
        if not isinstance(prepared.warnings, tuple) or any(
            not isinstance(warning, str) for warning in prepared.warnings
        ):
            raise ValueError("prepared warnings 无效")
        if _safe_warnings(docs) != prepared.warnings:
            raise ValueError("prepared warnings 与 documents 不一致")
        return docs

    def ingest_prepared(self, prepared: PreparedIngestion) -> IngestResult:
        """校验准备快照后恰好 index 一次；不重新提取或切块。"""
        docs = self._validate_prepared(prepared)
        planned = len(docs)
        written = self._coordinator.index_documents(docs, source="vector")
        warnings = list(prepared.warnings)
        if isinstance(written, int) and not isinstance(written, bool) and written == planned:
            return IngestResult(
                status="ok",
                doc_id=prepared.doc_id,
                planned_chunk_count=planned,
                written_chunk_count=written,
                warnings=warnings,
            )

        confirmed_count = (
            written
            if isinstance(written, int)
            and not isinstance(written, bool)
            and 0 <= written <= planned
            else 0
        )
        warnings.append("写入未确认，计数0不代表已确认零写入")
        return IngestResult(
            status="index_unconfirmed",
            doc_id=prepared.doc_id,
            planned_chunk_count=planned,
            written_chunk_count=confirmed_count,
            warnings=warnings,
        )

    def ingest_file(
        self,
        file_path: str,
        *,
        import_namespace: str,
        scope: str = "global",
        user_id: int | None = None,
        chunking_spec_version: str = "chunk-policy-1",
        policy: ChunkPolicy | None = None,
    ) -> IngestResult:
        try:
            prepared = self.prepare_file(
                file_path,
                import_namespace=import_namespace,
                scope=scope,
                user_id=user_id,
                chunking_spec_version=chunking_spec_version,
                policy=policy,
            )
        except IngestionPreparationError as exc:
            if exc.status in {"unsupported", "extraction_empty"}:
                return IngestResult(status=exc.status)
            raise
        return self.ingest_prepared(prepared)
