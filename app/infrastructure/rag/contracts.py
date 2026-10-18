"""Frozen, side-effect-free data contracts shared by the RAG ingestion flow."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, TypeAlias


JsonScalar: TypeAlias = type(None) | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | tuple[Any, ...] | Mapping[str, Any]
ManifestRow: TypeAlias = Mapping[str, Any]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RULE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_WARNING_RE = re.compile(
    r"^chunk_index=(?:0|[1-9][0-9]*) 超过 embedding 安全阈值（hard_limit），已整块保留（atomic 不切裂）$"
)
_ROW_KEYS = frozenset(
    {"doc_id", "chunk_id", "chunk_index", "content_sha256", "scope", "owner", "source_locator"}
)
_ISOLATION_KEYS = frozenset(
    {"mode", "target_index_id", "manifest_sha256", "row_count", "verified_at", "resource_record_ref"}
)
_PHASE_SUMMARIES = {
    "prepared": "摄入计划已准备",
    "committed_unattested": "写入待证明",
    "completed": "摄入已核验",
    "failed": "摄入未完成",
    "inconclusive": "摄入状态待核验",
}
_ENCODING_FORMATS = frozenset({"service_default", "float", "base64"})
_ERROR_CODES = frozenset(
    {"backend_unavailable", "db_error", "embedding_failed", "provider_degraded", "invalid_request", "timeout"}
)
_FAILURE_ORDER = (
    "schema_",
    "version_",
    "types_",
    "source_",
    "target_",
    "identity_",
    "count_",
    "scope_",
    "isolation_",
)


def _fail(rule_id: str) -> None:
    raise ValueError(rule_id)


def _nonempty_string(value: Any, rule_id: str = "types_invalid") -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(rule_id)
    return value


def _public_id(value: Any, rule_id: str = "types_invalid") -> str:
    text = _nonempty_string(value, rule_id)
    if not _PUBLIC_ID_RE.fullmatch(text):
        _fail(rule_id)
    return text


def _model_label(value: Any, rule_id: str = "types_invalid") -> str:
    text = _nonempty_string(value, rule_id)
    if "\n" in text or "\r" in text or "://" in text or re.search(
        r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+|[^/@\s:]+:[^/@\s]+@", text
    ):
        _fail(rule_id)
    return text


def _positive_int(value: Any, rule_id: str = "types_invalid") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(rule_id)
    return value


def _nonnegative_int(value: Any, rule_id: str = "types_invalid") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(rule_id)
    return value


def _sha256(value: Any, rule_id: str = "types_invalid") -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail(rule_id)
    return value


def _uuid_string(value: Any, rule_id: str = "types_invalid") -> str:
    if not isinstance(value, str):
        _fail(rule_id)
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        _fail(rule_id)
    return value


def _utc_time(value: Any, rule_id: str = "types_invalid") -> str:
    if not isinstance(value, str) or not value or "T" not in value:
        _fail(rule_id)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except (ValueError, OverflowError):
        _fail(rule_id)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _fail(rule_id)
    return value


def _safe_reference(value: Any, rule_id: str = "types_invalid") -> str:
    text = _nonempty_string(value, rule_id)
    # Catch common accidental credential/URL forms. This is a narrow guard, not a
    # general secret detector; callers still supply references from trusted config.
    if "\n" in text or "\r" in text or "://" in text or re.search(
        r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+|[^/@\s:]+:[^/@\s]+@", text
    ):
        _fail(rule_id)
    return text


def _scope_owner(scope: Any, owner: Any, rule_id: str = "scope_mismatch") -> None:
    if not isinstance(scope, str):
        _fail(rule_id)
    if scope == "global" and owner is None:
        return
    if scope == "private" and isinstance(owner, int) and not isinstance(owner, bool) and owner > 0:
        return
    _fail(rule_id)


def _freeze_json(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("types_invalid")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("types_invalid")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    _fail("types_invalid")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _validate_manifest_row(row: Any) -> Mapping[str, Any]:
    if not isinstance(row, Mapping) or set(row) != _ROW_KEYS:
        _fail("types_invalid")
    _nonempty_string(row["doc_id"])
    _nonempty_string(row["chunk_id"])
    _nonnegative_int(row["chunk_index"])
    _sha256(row["content_sha256"])
    _scope_owner(row["scope"], row["owner"])
    if not isinstance(row["source_locator"], Mapping):
        _fail("types_invalid")
    frozen = _freeze_json(row)
    return frozen


def canonical_json_bytes(value: Any) -> bytes:
    """Return strict canonical UTF-8 JSON bytes for JSON-compatible values."""
    try:
        frozen = _freeze_json(value)
        return json.dumps(
            _thaw_json(frozen),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeEncodeError):
        _fail("types_invalid")


def manifest_sha256(rows: Sequence[ManifestRow]) -> str:
    """Hash full canonical rows as an order-independent, duplicate-preserving multiset."""
    if isinstance(rows, (str, bytes, bytearray)) or not isinstance(rows, Sequence):
        _fail("types_invalid")
    try:
        encoded_rows = sorted(canonical_json_bytes(_validate_manifest_row(row)) for row in rows)
        digest_input = b"[" + b",".join(encoded_rows) + b"]"
        return hashlib.sha256(digest_input).hexdigest()
    except (TypeError, KeyError, RecursionError):
        _fail("types_invalid")


def _freeze_warnings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _fail("types_invalid")
    warnings = tuple(value)
    if any(not isinstance(item, str) or not _WARNING_RE.fullmatch(item) for item in warnings):
        _fail("types_invalid")
    return warnings


def _failure_sort_key(rule_id: str) -> int:
    for index, prefix in enumerate(_FAILURE_ORDER):
        if rule_id.startswith(prefix):
            return index
    return len(_FAILURE_ORDER)


@dataclass(frozen=True)
class ContractCheck:
    allowed: bool
    failures: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool or not isinstance(self.failures, tuple):
            _fail("types_invalid")
        if any(not isinstance(item, str) or not _RULE_ID_RE.fullmatch(item) for item in self.failures):
            _fail("types_invalid")
        unique = tuple(dict.fromkeys(self.failures))
        ordered = tuple(sorted(unique, key=_failure_sort_key))
        if ordered != self.failures:
            object.__setattr__(self, "failures", ordered)
        if self.allowed != (not self.failures):
            _fail("types_invalid")


@dataclass(frozen=True)
class EmbeddingBinding:
    service_id: str
    deployment_id: str | None
    model_version: str | None
    expected_endpoint: str = field(repr=False)

    def __post_init__(self) -> None:
        _public_id(self.service_id)
        if self.deployment_id is not None:
            _public_id(self.deployment_id)
        if self.model_version is not None:
            _model_label(self.model_version)
        _nonempty_string(self.expected_endpoint)


@dataclass(frozen=True)
class EmbeddingIdentity:
    service_id: str
    deployment_id: str | None
    model: str
    dimension: int
    parameters: Mapping[str, Any]
    model_version: str | None
    version_binding: str
    schema_version: str = "embedding-identity-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "embedding-identity-v1":
            _fail("version_unsupported")
        _public_id(self.service_id)
        if self.deployment_id is not None:
            _public_id(self.deployment_id)
        _model_label(self.model, "identity_mismatch")
        _positive_int(self.dimension)
        if self.model_version is not None:
            _model_label(self.model_version, "identity_mismatch")
        expected_binding = "pinned" if self.model_version is not None else "alias_unpinned"
        if self.version_binding != expected_binding:
            _fail("identity_mismatch")
        if not isinstance(self.parameters, Mapping) or set(self.parameters) != {"dimensions", "encoding_format"}:
            _fail("types_invalid")
        dimensions = self.parameters["dimensions"]
        if dimensions != "service_default":
            _positive_int(dimensions, "types_invalid")
        encoding_format = self.parameters["encoding_format"]
        if not isinstance(encoding_format, str) or encoding_format not in _ENCODING_FORMATS:
            _fail("types_invalid")
        frozen = _freeze_json(self.parameters)
        if any(isinstance(value, Mapping) or isinstance(value, tuple) for value in frozen.values()):
            _fail("types_invalid")
        object.__setattr__(self, "parameters", frozen)


@dataclass(frozen=True)
class IndexSnapshot:
    target_index_id: str
    database_id: str
    schema_name: str
    row_count: int
    rows: Sequence[ManifestRow]
    manifest_sha256: str

    def __post_init__(self) -> None:
        _safe_reference(self.target_index_id)
        _nonempty_string(self.database_id)
        _nonempty_string(self.schema_name)
        _nonnegative_int(self.row_count)
        _sha256(self.manifest_sha256)
        if isinstance(self.rows, (str, bytes, bytearray)) or not isinstance(self.rows, Sequence):
            _fail("types_invalid")
        frozen_rows = tuple(_validate_manifest_row(row) for row in self.rows)
        if self.row_count != len(frozen_rows):
            _fail("count_mismatch")
        if self.manifest_sha256 != manifest_sha256(frozen_rows):
            _fail("identity_mismatch")
        object.__setattr__(self, "rows", frozen_rows)


@dataclass(frozen=True)
class AttestationExpectation:
    expected_source_sha256: str
    expected_target_index_id: str
    expected_embedding_fingerprint: str
    expected_manifest_sha256: str
    expected_scope: str
    expected_owner: int | None
    isolation_evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        _sha256(self.expected_source_sha256)
        _safe_reference(self.expected_target_index_id, "target_mismatch")
        _sha256(self.expected_embedding_fingerprint)
        _sha256(self.expected_manifest_sha256)
        _scope_owner(self.expected_scope, self.expected_owner)
        if not isinstance(self.isolation_evidence, Mapping) or set(self.isolation_evidence) != _ISOLATION_KEYS:
            _fail("isolation_unproven")
        evidence = dict(self.isolation_evidence)
        if evidence["mode"] != "isolated_db":
            _fail("isolation_unproven")
        _nonempty_string(evidence["target_index_id"], "isolation_unproven")
        _sha256(evidence["manifest_sha256"], "isolation_unproven")
        if evidence["target_index_id"] != self.expected_target_index_id:
            _fail("isolation_unproven")
        if evidence["manifest_sha256"] != self.expected_manifest_sha256:
            _fail("isolation_unproven")
        _positive_int(evidence["row_count"], "isolation_unproven")
        _utc_time(evidence["verified_at"], "isolation_unproven")
        _safe_reference(evidence["resource_record_ref"], "isolation_unproven")
        object.__setattr__(self, "isolation_evidence", _freeze_json(evidence))


@dataclass(frozen=True)
class RAGRequestContext:
    retrieval_id: str
    attempt: int = 1
    trace_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        _nonempty_string(self.retrieval_id)
        if isinstance(self.attempt, bool) or self.attempt != 1 or not isinstance(self.attempt, int):
            _fail("types_invalid")
        if self.trace_id is not None:
            _nonempty_string(self.trace_id)
        if self.session_id is not None:
            _nonempty_string(self.session_id)


@dataclass(frozen=True)
class RunRecord:
    ingestion_run_id: str
    phase: str
    error_code: str | None
    safe_summary: str
    failures: tuple[str, ...]
    attestation_path: str | None
    schema_version: str = "ingestion-run-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "ingestion-run-v1":
            _fail("version_unsupported")
        _uuid_string(self.ingestion_run_id)
        if not isinstance(self.phase, str) or self.phase not in _PHASE_SUMMARIES:
            _fail("types_invalid")
        if self.error_code is not None and (
            not isinstance(self.error_code, str) or self.error_code not in _ERROR_CODES
        ):
            _fail("types_invalid")
        if self.safe_summary != _PHASE_SUMMARIES[self.phase]:
            _fail("types_invalid")
        if not isinstance(self.failures, tuple) or any(
            not isinstance(item, str) or not _RULE_ID_RE.fullmatch(item) for item in self.failures
        ):
            _fail("types_invalid")
        normalized_failures = tuple(sorted(set(self.failures)))
        object.__setattr__(self, "failures", normalized_failures)
        if self.phase == "completed":
            if self.attestation_path is None:
                _fail("isolation_unproven")
            _safe_reference(self.attestation_path, "types_invalid")
        elif self.attestation_path is not None:
            _fail("types_invalid")
