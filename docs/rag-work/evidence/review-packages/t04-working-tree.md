# T04 working-tree review package
BASE: 6324b9442b6f1671ccb4a19cdacb42bb91597187
No commits; all six files are new. Snapshot after implement_t04 completion.

--- /dev/null
+++ app/infrastructure/rag/contracts.py
@@ -0,0 +1,409 @@
+"""Frozen, side-effect-free data contracts shared by the RAG ingestion flow."""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import math
+import re
+import uuid
+from collections.abc import Mapping, Sequence
+from dataclasses import dataclass, field
+from datetime import datetime, timedelta
+from types import MappingProxyType
+from typing import Any, TypeAlias
+
+
+JsonScalar: TypeAlias = type(None) | bool | int | float | str
+JsonValue: TypeAlias = JsonScalar | tuple[Any, ...] | Mapping[str, Any]
+ManifestRow: TypeAlias = Mapping[str, Any]
+
+_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
+_PUBLIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
+_RULE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
+_WARNING_RE = re.compile(
+    r"^chunk_index=(?:0|[1-9][0-9]*) 超过 embedding 安全阈值（hard_limit），已整块保留（atomic 不切裂）$"
+)
+_ROW_KEYS = frozenset(
+    {"doc_id", "chunk_id", "chunk_index", "content_sha256", "scope", "owner", "source_locator"}
+)
+_ISOLATION_KEYS = frozenset(
+    {"mode", "target_index_id", "manifest_sha256", "row_count", "verified_at", "resource_record_ref"}
+)
+_PHASE_SUMMARIES = {
+    "prepared": "摄入计划已准备",
+    "committed_unattested": "写入待证明",
+    "completed": "摄入已核验",
+    "failed": "摄入未完成",
+    "inconclusive": "摄入状态待核验",
+}
+_ERROR_CODES = frozenset(
+    {"backend_unavailable", "db_error", "embedding_failed", "provider_degraded", "invalid_request", "timeout"}
+)
+_FAILURE_ORDER = (
+    "schema_",
+    "version_",
+    "types_",
+    "source_",
+    "target_",
+    "identity_",
+    "count_",
+    "scope_",
+    "isolation_",
+)
+
+
+def _fail(rule_id: str) -> None:
+    raise ValueError(rule_id)
+
+
+def _nonempty_string(value: Any, rule_id: str = "types_invalid") -> str:
+    if not isinstance(value, str) or not value.strip():
+        _fail(rule_id)
+    return value
+
+
+def _public_id(value: Any, rule_id: str = "types_invalid") -> str:
+    text = _nonempty_string(value, rule_id)
+    if not _PUBLIC_ID_RE.fullmatch(text):
+        _fail(rule_id)
+    return text
+
+
+def _model_label(value: Any, rule_id: str = "types_invalid") -> str:
+    text = _nonempty_string(value, rule_id)
+    if "\n" in text or "\r" in text or "://" in text or re.search(
+        r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+|[^/@\s:]+:[^/@\s]+@", text
+    ):
+        _fail(rule_id)
+    return text
+
+
+def _positive_int(value: Any, rule_id: str = "types_invalid") -> int:
+    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
+        _fail(rule_id)
+    return value
+
+
+def _nonnegative_int(value: Any, rule_id: str = "types_invalid") -> int:
+    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
+        _fail(rule_id)
+    return value
+
+
+def _sha256(value: Any, rule_id: str = "types_invalid") -> str:
+    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
+        _fail(rule_id)
+    return value
+
+
+def _uuid_string(value: Any, rule_id: str = "types_invalid") -> str:
+    if not isinstance(value, str):
+        _fail(rule_id)
+    try:
+        uuid.UUID(value)
+    except (ValueError, AttributeError, TypeError):
+        _fail(rule_id)
+    return value
+
+
+def _utc_time(value: Any, rule_id: str = "types_invalid") -> str:
+    if not isinstance(value, str) or not value or "T" not in value:
+        _fail(rule_id)
+    try:
+        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
+    except (ValueError, OverflowError):
+        _fail(rule_id)
+    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
+        _fail(rule_id)
+    return value
+
+
+def _safe_reference(value: Any, rule_id: str = "types_invalid") -> str:
+    text = _nonempty_string(value, rule_id)
+    # Catch common accidental credential/URL forms. This is a narrow guard, not a
+    # general secret detector; callers still supply references from trusted config.
+    if "\n" in text or "\r" in text or "://" in text or re.search(
+        r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+|[^/@\s:]+:[^/@\s]+@", text
+    ):
+        _fail(rule_id)
+    return text
+
+
+def _scope_owner(scope: Any, owner: Any, rule_id: str = "scope_mismatch") -> None:
+    if not isinstance(scope, str):
+        _fail(rule_id)
+    if scope == "global" and owner is None:
+        return
+    if scope == "private" and isinstance(owner, int) and not isinstance(owner, bool) and owner > 0:
+        return
+    _fail(rule_id)
+
+
+def _freeze_json(value: Any) -> Any:
+    if value is None or isinstance(value, (bool, str)):
+        return value
+    if isinstance(value, int) and not isinstance(value, bool):
+        return value
+    if isinstance(value, float):
+        if not math.isfinite(value):
+            _fail("types_invalid")
+        return value
+    if isinstance(value, Mapping):
+        frozen: dict[str, Any] = {}
+        for key, item in value.items():
+            if not isinstance(key, str):
+                _fail("types_invalid")
+            frozen[key] = _freeze_json(item)
+        return MappingProxyType(frozen)
+    if isinstance(value, (list, tuple)):
+        return tuple(_freeze_json(item) for item in value)
+    _fail("types_invalid")
+
+
+def _thaw_json(value: Any) -> Any:
+    if isinstance(value, Mapping):
+        return {key: _thaw_json(item) for key, item in value.items()}
+    if isinstance(value, tuple):
+        return [_thaw_json(item) for item in value]
+    return value
+
+
+def _validate_manifest_row(row: Any) -> Mapping[str, Any]:
+    if not isinstance(row, Mapping) or set(row) != _ROW_KEYS:
+        _fail("types_invalid")
+    _nonempty_string(row["doc_id"])
+    _nonempty_string(row["chunk_id"])
+    _nonnegative_int(row["chunk_index"])
+    _sha256(row["content_sha256"])
+    _scope_owner(row["scope"], row["owner"])
+    if not isinstance(row["source_locator"], Mapping):
+        _fail("types_invalid")
+    frozen = _freeze_json(row)
+    return frozen
+
+
+def canonical_json_bytes(value: Any) -> bytes:
+    """Return strict canonical UTF-8 JSON bytes for JSON-compatible values."""
+    try:
+        frozen = _freeze_json(value)
+        return json.dumps(
+            _thaw_json(frozen),
+            sort_keys=True,
+            separators=(",", ":"),
+            ensure_ascii=False,
+            allow_nan=False,
+        ).encode("utf-8")
+    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeEncodeError):
+        _fail("types_invalid")
+
+
+def manifest_sha256(rows: Sequence[ManifestRow]) -> str:
+    """Hash full canonical rows as an order-independent, duplicate-preserving multiset."""
+    if isinstance(rows, (str, bytes, bytearray)) or not isinstance(rows, Sequence):
+        _fail("types_invalid")
+    try:
+        encoded_rows = sorted(canonical_json_bytes(_validate_manifest_row(row)) for row in rows)
+        digest_input = b"[" + b",".join(encoded_rows) + b"]"
+        return hashlib.sha256(digest_input).hexdigest()
+    except (TypeError, KeyError, RecursionError):
+        _fail("types_invalid")
+
+
+def _freeze_warnings(value: Any) -> tuple[str, ...]:
+    if not isinstance(value, (list, tuple)):
+        _fail("types_invalid")
+    warnings = tuple(value)
+    if any(not isinstance(item, str) or not _WARNING_RE.fullmatch(item) for item in warnings):
+        _fail("types_invalid")
+    return warnings
+
+
+def _failure_sort_key(rule_id: str) -> int:
+    for index, prefix in enumerate(_FAILURE_ORDER):
+        if rule_id.startswith(prefix):
+            return index
+    return len(_FAILURE_ORDER)
+
+
+@dataclass(frozen=True)
+class ContractCheck:
+    allowed: bool
+    failures: tuple[str, ...]
+
+    def __post_init__(self) -> None:
+        if type(self.allowed) is not bool or not isinstance(self.failures, tuple):
+            _fail("types_invalid")
+        if any(not isinstance(item, str) or not _RULE_ID_RE.fullmatch(item) for item in self.failures):
+            _fail("types_invalid")
+        unique = tuple(dict.fromkeys(self.failures))
+        ordered = tuple(sorted(unique, key=_failure_sort_key))
+        if ordered != self.failures:
+            object.__setattr__(self, "failures", ordered)
+        if self.allowed != (not self.failures):
+            _fail("types_invalid")
+
+
+@dataclass(frozen=True)
+class EmbeddingBinding:
+    service_id: str
+    deployment_id: str | None
+    model_version: str | None
+    expected_endpoint: str = field(repr=False)
+
+    def __post_init__(self) -> None:
+        _public_id(self.service_id)
+        if self.deployment_id is not None:
+            _public_id(self.deployment_id)
+        if self.model_version is not None:
+            _model_label(self.model_version)
+        _nonempty_string(self.expected_endpoint)
+
+
+@dataclass(frozen=True)
+class EmbeddingIdentity:
+    service_id: str
+    deployment_id: str | None
+    model: str
+    dimension: int
+    parameters: Mapping[str, Any]
+    model_version: str | None
+    version_binding: str
+    schema_version: str = "embedding-identity-v1"
+
+    def __post_init__(self) -> None:
+        if self.schema_version != "embedding-identity-v1":
+            _fail("version_unsupported")
+        _public_id(self.service_id)
+        if self.deployment_id is not None:
+            _public_id(self.deployment_id)
+        _model_label(self.model, "identity_mismatch")
+        _positive_int(self.dimension)
+        if self.model_version is not None:
+            _model_label(self.model_version, "identity_mismatch")
+        expected_binding = "pinned" if self.model_version is not None else "alias_unpinned"
+        if self.version_binding != expected_binding:
+            _fail("identity_mismatch")
+        if not isinstance(self.parameters, Mapping) or set(self.parameters) != {"dimensions", "encoding_format"}:
+            _fail("types_invalid")
+        dimensions = self.parameters["dimensions"]
+        if dimensions != "service_default":
+            _positive_int(dimensions, "types_invalid")
+        encoding_format = self.parameters["encoding_format"]
+        if encoding_format != "service_default":
+            _nonempty_string(encoding_format)
+        frozen = _freeze_json(self.parameters)
+        if any(isinstance(value, Mapping) or isinstance(value, tuple) for value in frozen.values()):
+            _fail("types_invalid")
+        object.__setattr__(self, "parameters", frozen)
+
+
+@dataclass(frozen=True)
+class IndexSnapshot:
+    target_index_id: str
+    database_id: str
+    schema_name: str
+    row_count: int
+    rows: Sequence[ManifestRow]
+    manifest_sha256: str
+
+    def __post_init__(self) -> None:
+        _safe_reference(self.target_index_id)
+        _nonempty_string(self.database_id)
+        _nonempty_string(self.schema_name)
+        _nonnegative_int(self.row_count)
+        _sha256(self.manifest_sha256)
+        if isinstance(self.rows, (str, bytes, bytearray)) or not isinstance(self.rows, Sequence):
+            _fail("types_invalid")
+        frozen_rows = tuple(_validate_manifest_row(row) for row in self.rows)
+        if self.row_count != len(frozen_rows):
+            _fail("count_mismatch")
+        if self.manifest_sha256 != manifest_sha256(frozen_rows):
+            _fail("identity_mismatch")
+        object.__setattr__(self, "rows", frozen_rows)
+
+
+@dataclass(frozen=True)
+class AttestationExpectation:
+    expected_source_sha256: str
+    expected_target_index_id: str
+    expected_embedding_fingerprint: str
+    expected_manifest_sha256: str
+    expected_scope: str
+    expected_owner: int | None
+    isolation_evidence: Mapping[str, Any]
+
+    def __post_init__(self) -> None:
+        _sha256(self.expected_source_sha256)
+        _safe_reference(self.expected_target_index_id, "target_mismatch")
+        _sha256(self.expected_embedding_fingerprint)
+        _sha256(self.expected_manifest_sha256)
+        _scope_owner(self.expected_scope, self.expected_owner)
+        if not isinstance(self.isolation_evidence, Mapping) or set(self.isolation_evidence) != _ISOLATION_KEYS:
+            _fail("isolation_unproven")
+        evidence = dict(self.isolation_evidence)
+        if evidence["mode"] != "isolated_db":
+            _fail("isolation_unproven")
+        _nonempty_string(evidence["target_index_id"], "isolation_unproven")
+        _sha256(evidence["manifest_sha256"], "isolation_unproven")
+        if evidence["target_index_id"] != self.expected_target_index_id:
+            _fail("isolation_unproven")
+        if evidence["manifest_sha256"] != self.expected_manifest_sha256:
+            _fail("isolation_unproven")
+        _positive_int(evidence["row_count"], "isolation_unproven")
+        _utc_time(evidence["verified_at"], "isolation_unproven")
+        _safe_reference(evidence["resource_record_ref"], "isolation_unproven")
+        object.__setattr__(self, "isolation_evidence", _freeze_json(evidence))
+
+
+@dataclass(frozen=True)
+class RAGRequestContext:
+    retrieval_id: str
+    attempt: int = 1
+    trace_id: str | None = None
+    session_id: str | None = None
+
+    def __post_init__(self) -> None:
+        _nonempty_string(self.retrieval_id)
+        if isinstance(self.attempt, bool) or self.attempt != 1 or not isinstance(self.attempt, int):
+            _fail("types_invalid")
+        if self.trace_id is not None:
+            _nonempty_string(self.trace_id)
+        if self.session_id is not None:
+            _nonempty_string(self.session_id)
+
+
+@dataclass(frozen=True)
+class RunRecord:
+    ingestion_run_id: str
+    phase: str
+    error_code: str | None
+    safe_summary: str
+    failures: tuple[str, ...]
+    attestation_path: str | None
+    schema_version: str = "ingestion-run-v1"
+
+    def __post_init__(self) -> None:
+        if self.schema_version != "ingestion-run-v1":
+            _fail("version_unsupported")
+        _uuid_string(self.ingestion_run_id)
+        if not isinstance(self.phase, str) or self.phase not in _PHASE_SUMMARIES:
+            _fail("types_invalid")
+        if self.error_code is not None and (
+            not isinstance(self.error_code, str) or self.error_code not in _ERROR_CODES
+        ):
+            _fail("types_invalid")
+        if self.safe_summary != _PHASE_SUMMARIES[self.phase]:
+            _fail("types_invalid")
+        if not isinstance(self.failures, tuple) or any(
+            not isinstance(item, str) or not _RULE_ID_RE.fullmatch(item) for item in self.failures
+        ):
+            _fail("types_invalid")
+        normalized_failures = tuple(sorted(set(self.failures)))
+        object.__setattr__(self, "failures", normalized_failures)
+        if self.phase == "completed":
+            if self.attestation_path is None:
+                _fail("isolation_unproven")
+            _safe_reference(self.attestation_path, "types_invalid")
+        elif self.attestation_path is not None:
+            _fail("types_invalid")

--- /dev/null
+++ app/infrastructure/rag/embedding_identity.py
@@ -0,0 +1,108 @@
+"""Describe and fingerprint the embedding configuration visible to this process."""
+
+from __future__ import annotations
+
+import hashlib
+from typing import Any
+
+from app.infrastructure.rag.contracts import (
+    EmbeddingBinding,
+    EmbeddingIdentity,
+    canonical_json_bytes,
+)
+
+
+def _validated_identity(identity: Any) -> EmbeddingIdentity:
+    if not isinstance(identity, EmbeddingIdentity):
+        raise ValueError("identity_mismatch") from None
+    try:
+        return EmbeddingIdentity(
+            service_id=identity.service_id,
+            deployment_id=identity.deployment_id,
+            model=identity.model,
+            dimension=identity.dimension,
+            parameters=identity.parameters,
+            model_version=identity.model_version,
+            version_binding=identity.version_binding,
+            schema_version=identity.schema_version,
+        )
+    except (AttributeError, TypeError, ValueError):
+        raise ValueError("identity_mismatch") from None
+
+
+def to_json_dict(identity: EmbeddingIdentity) -> dict[str, Any]:
+    """Return the exact public identity fields, excluding all binding secrets."""
+    validated = _validated_identity(identity)
+    return {
+        "schema_version": validated.schema_version,
+        "service_id": validated.service_id,
+        "deployment_id": validated.deployment_id,
+        "model": validated.model,
+        "dimension": validated.dimension,
+        "parameters": dict(validated.parameters),
+        "model_version": validated.model_version,
+        "version_binding": validated.version_binding,
+    }
+
+
+def fingerprint_embedding(identity: EmbeddingIdentity) -> str:
+    """Return the canonical identity SHA-256 as lowercase hexadecimal."""
+    try:
+        identity_dict = to_json_dict(identity)
+        return hashlib.sha256(canonical_json_bytes(identity_dict)).hexdigest()
+    except (AttributeError, TypeError, ValueError):
+        raise ValueError("identity_mismatch") from None
+
+
+def _read_configuration(service: Any) -> tuple[str, int, str]:
+    model = service.model
+    dimension = service.dim
+    client = service.client
+    endpoint_value = client.base_url
+    if not isinstance(model, str) or not model.strip():
+        raise ValueError("embedding_config_unobservable")
+    if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
+        raise ValueError("embedding_config_unobservable")
+    if endpoint_value is None:
+        raise ValueError("embedding_config_unobservable")
+    endpoint = str(endpoint_value)
+    if not endpoint:
+        raise ValueError("embedding_config_unobservable")
+    return model, dimension, endpoint
+
+
+def describe_embedding(service: Any, binding: EmbeddingBinding) -> EmbeddingIdentity:
+    """Read and validate the live service model, dimension, and cached SDK endpoint.
+
+    Accessing ``service.client`` may initialize the SDK object, but this function
+    never calls an embedding endpoint. The endpoint is compared in memory only.
+    """
+    if not isinstance(binding, EmbeddingBinding):
+        raise ValueError("embedding_binding_invalid") from None
+    try:
+        first = _read_configuration(service)
+        second = _read_configuration(service)
+    except Exception:
+        raise ValueError("embedding_config_unobservable") from None
+    if first != second:
+        raise ValueError("identity_config_drift") from None
+    model, dimension, endpoint = first
+    if endpoint != binding.expected_endpoint:
+        raise ValueError("endpoint_mismatch") from None
+    version_binding = "pinned" if binding.model_version is not None else "alias_unpinned"
+    try:
+        return EmbeddingIdentity(
+            schema_version="embedding-identity-v1",
+            service_id=binding.service_id,
+            deployment_id=binding.deployment_id,
+            model=model,
+            dimension=dimension,
+            parameters={
+                "dimensions": "service_default",
+                "encoding_format": "service_default",
+            },
+            model_version=binding.model_version,
+            version_binding=version_binding,
+        )
+    except (TypeError, ValueError):
+        raise ValueError("embedding_config_unobservable") from None

--- /dev/null
+++ app/harness/ingestion_attestation.py
@@ -0,0 +1,608 @@
+"""Pure construction and validation for the frozen RAG ingestion proof contract."""
+
+from __future__ import annotations
+
+import re
+import uuid
+from collections import Counter
+from collections.abc import Mapping, Sequence
+from typing import Any
+
+from app.harness.knowledge_ingestion import IngestResult
+from app.infrastructure.rag.contracts import (
+    AttestationExpectation,
+    ContractCheck,
+    EmbeddingIdentity,
+    IndexSnapshot,
+    canonical_json_bytes,
+    manifest_sha256,
+)
+from app.infrastructure.rag.embedding_identity import fingerprint_embedding, to_json_dict
+
+
+_CONTRACT_VERSION = "rag-mvp-contracts-v1.0.1"
+_ATTESTATION_VERSION = "ingestion-attestation-v1"
+_INTENT_VERSION = "ingestion-intent-v1"
+_MANIFEST_VERSION = "ingestion-manifest-v1"
+_PREPARATION_VERSION = "prepared-ingestion-v1"
+_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
+_RULE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
+_WARNING_RE = re.compile(
+    r"^chunk_index=(?:0|[1-9][0-9]*) 超过 embedding 安全阈值（hard_limit），已整块保留（atomic 不切裂）$"
+)
+_INTENT_KEYS = frozenset(
+    {
+        "schema_version", "ingestion_run_id", "created_at", "target_index_id", "database_id",
+        "schema_name", "source_sha256", "manifest_sha256", "embedding_fingerprint", "embedding_config",
+        "preparation", "before_row_count", "resource_record_ref", "exclusivity_record_ref",
+        "isolation_evidence_ref", "exclusive_target", "phase",
+    }
+)
+_PREPARATION_KEYS = frozenset(
+    {
+        "schema_version", "source_sha256", "source_format", "import_namespace", "doc_id", "scope",
+        "owner", "normalizer_version", "chunking_version", "doc_protocol", "chunk_protocol",
+        "chunk_policy", "warnings",
+    }
+)
+_MANIFEST_KEYS = frozenset(
+    {
+        "schema_version", "ingestion_run_id", "target_index_id", "doc_id", "source_sha256",
+        "embedding_fingerprint", "rows", "row_count", "manifest_sha256",
+    }
+)
+_IDENTITY_KEYS = frozenset(
+    {
+        "schema_version", "service_id", "deployment_id", "model", "dimension", "parameters",
+        "model_version", "version_binding",
+    }
+)
+_ATTESTATION_KEYS = frozenset(
+    {
+        "schema_version", "contract_version", "status", "ingestion_run_id", "created_at",
+        "source_sha256", "source_format", "import_namespace", "doc_id", "normalizer_version",
+        "chunking_version", "doc_protocol", "chunk_protocol", "chunk_policy", "planned_chunk_count",
+        "written_chunk_count", "failure_count", "backend", "provider", "dialect", "target_index_id",
+        "scope", "owner", "embedding_config", "embedding_fingerprint", "artifact_manifest_sha256",
+        "isolation_evidence_ref", "error_code", "safe_summary", "warnings",
+    }
+)
+
+
+def _fail(rule_id: str) -> None:
+    raise ValueError(rule_id) from None
+
+
+def _exact_mapping(value: Any, keys: frozenset[str]) -> Mapping[str, Any]:
+    if not isinstance(value, Mapping):
+        _fail("types_invalid")
+    actual = set(value)
+    if actual - keys:
+        _fail("schema_extra")
+    if keys - actual:
+        _fail("schema_missing")
+    return value
+
+
+def _string(value: Any, *, allow_empty: bool = False, rule_id: str = "types_invalid") -> str:
+    if not isinstance(value, str) or (not allow_empty and not value.strip()):
+        _fail(rule_id)
+    return value
+
+
+def _safe_ref(value: Any, rule_id: str = "types_invalid") -> str:
+    text = _string(value, rule_id=rule_id)
+    if "\n" in text or "\r" in text or "://" in text or re.search(
+        r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+|[^/@\s:]+:[^/@\s]+@", text
+    ):
+        _fail(rule_id)
+    return text
+
+
+def _sha(value: Any, rule_id: str = "types_invalid") -> str:
+    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
+        _fail(rule_id)
+    return value
+
+
+def _integer(value: Any, *, minimum: int, rule_id: str = "types_invalid") -> int:
+    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
+        _fail(rule_id)
+    return value
+
+
+def _utc(value: Any, rule_id: str = "types_invalid") -> str:
+    if not isinstance(value, str) or not value or "T" not in value:
+        _fail(rule_id)
+    try:
+        from datetime import datetime, timedelta
+
+        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
+    except (ValueError, OverflowError):
+        _fail(rule_id)
+    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
+        _fail(rule_id)
+    return value
+
+
+def _uuid(value: Any, rule_id: str = "types_invalid") -> str:
+    if not isinstance(value, str):
+        _fail(rule_id)
+    try:
+        uuid.UUID(value)
+    except (ValueError, TypeError, AttributeError):
+        _fail(rule_id)
+    return value
+
+
+def _scope_owner(scope: Any, owner: Any) -> None:
+    if scope == "global" and owner is None:
+        return
+    if scope == "private" and isinstance(owner, int) and not isinstance(owner, bool) and owner > 0:
+        return
+    _fail("scope_mismatch")
+
+
+def _policy(value: Any) -> dict[str, int]:
+    if not isinstance(value, Mapping):
+        _fail("types_invalid")
+    keys = {"chunk_size", "chunk_overlap", "hard_limit"}
+    actual = set(value)
+    if actual - keys:
+        _fail("schema_extra")
+    if keys - actual:
+        _fail("schema_missing")
+    size = _integer(value["chunk_size"], minimum=1)
+    overlap = _integer(value["chunk_overlap"], minimum=0)
+    hard_limit = _integer(value["hard_limit"], minimum=1)
+    if overlap >= size or hard_limit < size:
+        _fail("types_invalid")
+    return {"chunk_size": size, "chunk_overlap": overlap, "hard_limit": hard_limit}
+
+
+def _warnings(value: Any) -> list[str]:
+    if not isinstance(value, (list, tuple)):
+        _fail("types_invalid")
+    warnings = list(value)
+    if any(not isinstance(item, str) or not _WARNING_RE.fullmatch(item) for item in warnings):
+        _fail("types_invalid")
+    return warnings
+
+
+def _identity(value: Any) -> tuple[EmbeddingIdentity, dict[str, Any]]:
+    mapping = _exact_mapping(value, _IDENTITY_KEYS)
+    try:
+        identity = EmbeddingIdentity(**dict(mapping))
+        public_config = to_json_dict(identity)
+    except (TypeError, ValueError, AttributeError):
+        _fail("identity_mismatch")
+    return identity, public_config
+
+
+def _identity_argument(value: Any) -> tuple[EmbeddingIdentity, dict[str, Any]]:
+    if not isinstance(value, EmbeddingIdentity):
+        _fail("identity_mismatch")
+    try:
+        public_config = to_json_dict(value)
+        identity = EmbeddingIdentity(**public_config)
+    except (TypeError, ValueError, AttributeError):
+        _fail("identity_mismatch")
+    return identity, public_config
+
+
+def _rows(value: Any, *, doc_id: str, scope: str, owner: int | None) -> tuple[list[dict[str, Any]], str]:
+    if not isinstance(value, (list, tuple)) or not value:
+        _fail("count_mismatch")
+    try:
+        digest = manifest_sha256(value)
+        copies = [dict(row) for row in value]
+        indices: list[int] = []
+        chunk_ids: set[str] = set()
+        for item in copies:
+            if item["doc_id"] != doc_id or item["scope"] != scope or item["owner"] != owner:
+                _fail("scope_mismatch")
+            if item["chunk_id"] in chunk_ids:
+                _fail("count_mismatch")
+            chunk_ids.add(item["chunk_id"])
+            indices.append(item["chunk_index"])
+        if sorted(indices) != list(range(len(copies))):
+            _fail("count_mismatch")
+        return copies, digest
+    except (TypeError, KeyError, AttributeError):
+        _fail("types_invalid")
+
+
+def _multiset(rows: Sequence[Mapping[str, Any]]) -> Counter[bytes]:
+    return Counter(canonical_json_bytes(row) for row in rows)
+
+
+def _clone_snapshot(snapshot: Any) -> IndexSnapshot:
+    if not isinstance(snapshot, IndexSnapshot):
+        _fail("types_invalid")
+    try:
+        return IndexSnapshot(
+            target_index_id=snapshot.target_index_id,
+            database_id=snapshot.database_id,
+            schema_name=snapshot.schema_name,
+            row_count=snapshot.row_count,
+            rows=snapshot.rows,
+            manifest_sha256=snapshot.manifest_sha256,
+        )
+    except (AttributeError, TypeError, ValueError):
+        _fail("types_invalid")
+
+
+def _preparation(value: Any) -> dict[str, Any]:
+    prep = _exact_mapping(value, _PREPARATION_KEYS)
+    if prep["schema_version"] != _PREPARATION_VERSION:
+        _fail("version_unsupported")
+    for field in (
+        "source_sha256", "source_format", "import_namespace", "doc_id", "normalizer_version",
+        "chunking_version", "doc_protocol", "chunk_protocol",
+    ):
+        _safe_ref(prep[field])
+    _sha(prep["source_sha256"])
+    _scope_owner(prep["scope"], prep["owner"])
+    policy = _policy(prep["chunk_policy"])
+    warnings = _warnings(prep["warnings"])
+    return {
+        "schema_version": _PREPARATION_VERSION,
+        "source_sha256": prep["source_sha256"],
+        "source_format": prep["source_format"],
+        "import_namespace": prep["import_namespace"],
+        "doc_id": prep["doc_id"],
+        "scope": prep["scope"],
+        "owner": prep["owner"],
+        "normalizer_version": prep["normalizer_version"],
+        "chunking_version": prep["chunking_version"],
+        "doc_protocol": prep["doc_protocol"],
+        "chunk_protocol": prep["chunk_protocol"],
+        "chunk_policy": policy,
+        "warnings": warnings,
+    }
+
+
+def _intent(value: Any) -> tuple[dict[str, Any], dict[str, Any], EmbeddingIdentity, dict[str, Any]]:
+    intent = _exact_mapping(value, _INTENT_KEYS)
+    if intent["schema_version"] != _INTENT_VERSION:
+        _fail("version_unsupported")
+    _uuid(intent["ingestion_run_id"])
+    _utc(intent["created_at"])
+    for field in ("database_id", "schema_name"):
+        _string(intent[field])
+    _safe_ref(intent["target_index_id"], "target_mismatch")
+    _sha(intent["source_sha256"], "source_mismatch")
+    _sha(intent["manifest_sha256"], "identity_mismatch")
+    _sha(intent["embedding_fingerprint"], "identity_mismatch")
+    _integer(intent["before_row_count"], minimum=0)
+    if intent["before_row_count"] != 0:
+        _fail("isolation_unproven")
+    for field in ("resource_record_ref", "exclusivity_record_ref", "isolation_evidence_ref"):
+        _safe_ref(intent[field], "isolation_unproven")
+    if intent["exclusive_target"] is not True or intent["phase"] != "prepared":
+        _fail("isolation_unproven")
+    prep = _preparation(intent["preparation"])
+    identity_obj, identity_config = _identity(intent["embedding_config"])
+    return dict(intent), prep, identity_obj, identity_config
+
+
+def _manifest(value: Any, *, run_id: str, target: str, doc_id: str, source_sha: str, fingerprint: str,
+              scope: str, owner: int | None) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
+    manifest = _exact_mapping(value, _MANIFEST_KEYS)
+    if manifest["schema_version"] != _MANIFEST_VERSION:
+        _fail("version_unsupported")
+    _uuid(manifest["ingestion_run_id"])
+    _safe_ref(manifest["target_index_id"], "target_mismatch")
+    _safe_ref(manifest["doc_id"])
+    _sha(manifest["source_sha256"])
+    _sha(manifest["embedding_fingerprint"])
+    _sha(manifest["manifest_sha256"])
+    if manifest["row_count"] == 0:
+        _fail("count_mismatch")
+    _integer(manifest["row_count"], minimum=1)
+    if manifest["ingestion_run_id"] != run_id or manifest["target_index_id"] != target or manifest["doc_id"] != doc_id:
+        _fail("target_mismatch")
+    if manifest["source_sha256"] != source_sha:
+        _fail("source_mismatch")
+    if manifest["embedding_fingerprint"] != fingerprint:
+        _fail("identity_mismatch")
+    rows, actual_digest = _rows(manifest["rows"], doc_id=doc_id, scope=scope, owner=owner)
+    if manifest["row_count"] != len(rows):
+        _fail("count_mismatch")
+    if manifest["manifest_sha256"] != actual_digest:
+        _fail("identity_mismatch")
+    return dict(manifest), rows, actual_digest
+
+
+def _build_attestation(
+    *, intent: Any, manifest: Any, result: Any, snapshot: Any, identity: Any, verified_at: Any
+) -> dict[str, Any]:
+    intent_value, prep, intent_identity, intent_config = _intent(intent)
+    supplied_identity, supplied_config = _identity_argument(identity)
+    if intent_config != supplied_config or intent_identity != supplied_identity:
+        _fail("identity_mismatch")
+    try:
+        fingerprint = fingerprint_embedding(supplied_identity)
+    except ValueError:
+        _fail("identity_mismatch")
+    if fingerprint != intent_value["embedding_fingerprint"]:
+        _fail("identity_mismatch")
+    if prep["source_sha256"] != intent_value["source_sha256"]:
+        _fail("source_mismatch")
+    if prep["scope"] not in {"global", "private"}:
+        _fail("scope_mismatch")
+    manifest_value, planned_rows, actual_manifest_sha = _manifest(
+        manifest,
+        run_id=intent_value["ingestion_run_id"],
+        target=intent_value["target_index_id"],
+        doc_id=prep["doc_id"],
+        source_sha=intent_value["source_sha256"],
+        fingerprint=fingerprint,
+        scope=prep["scope"],
+        owner=prep["owner"],
+    )
+    if intent_value["manifest_sha256"] != actual_manifest_sha:
+        _fail("identity_mismatch")
+    actual_snapshot = _clone_snapshot(snapshot)
+    if actual_snapshot.target_index_id != intent_value["target_index_id"]:
+        _fail("target_mismatch")
+    if actual_snapshot.database_id != intent_value["database_id"] or actual_snapshot.schema_name != intent_value["schema_name"]:
+        _fail("target_mismatch")
+    if actual_snapshot.row_count <= 0 or actual_snapshot.row_count != manifest_value["row_count"]:
+        _fail("count_mismatch")
+    if actual_snapshot.manifest_sha256 != actual_manifest_sha:
+        _fail("identity_mismatch")
+    if _multiset(actual_snapshot.rows) != _multiset(planned_rows):
+        _fail("identity_mismatch")
+    if not isinstance(result, IngestResult):
+        _fail("types_invalid")
+    if result.status != "ok" or result.doc_id != prep["doc_id"]:
+        _fail("count_mismatch")
+    _integer(result.planned_chunk_count, minimum=1)
+    _integer(result.written_chunk_count, minimum=1)
+    if result.planned_chunk_count != actual_snapshot.row_count or result.written_chunk_count != actual_snapshot.row_count:
+        _fail("count_mismatch")
+    prep_warnings = prep["warnings"]
+    result_warnings = _warnings(result.warnings)
+    if result_warnings != prep_warnings:
+        _fail("types_invalid")
+    _utc(verified_at)
+    output = {
+        "schema_version": _ATTESTATION_VERSION,
+        "contract_version": _CONTRACT_VERSION,
+        "status": "ok",
+        "ingestion_run_id": intent_value["ingestion_run_id"],
+        "created_at": verified_at,
+        "source_sha256": intent_value["source_sha256"],
+        "source_format": prep["source_format"],
+        "import_namespace": prep["import_namespace"],
+        "doc_id": prep["doc_id"],
+        "normalizer_version": prep["normalizer_version"],
+        "chunking_version": prep["chunking_version"],
+        "doc_protocol": prep["doc_protocol"],
+        "chunk_protocol": prep["chunk_protocol"],
+        "chunk_policy": dict(prep["chunk_policy"]),
+        "planned_chunk_count": actual_snapshot.row_count,
+        "written_chunk_count": actual_snapshot.row_count,
+        "failure_count": 0,
+        "backend": "pgvector",
+        "provider": "PgVectorProvider",
+        "dialect": "postgresql",
+        "target_index_id": actual_snapshot.target_index_id,
+        "scope": prep["scope"],
+        "owner": prep["owner"],
+        "embedding_config": intent_config,
+        "embedding_fingerprint": fingerprint,
+        "artifact_manifest_sha256": actual_snapshot.manifest_sha256,
+        "isolation_evidence_ref": intent_value["isolation_evidence_ref"],
+        "error_code": None,
+        "safe_summary": "摄入已核验",
+        "warnings": list(prep_warnings),
+    }
+    return output
+
+
+def build_attestation(
+    *,
+    intent: dict[str, Any],
+    manifest: dict[str, Any],
+    result: IngestResult,
+    snapshot: IndexSnapshot,
+    identity: EmbeddingIdentity,
+    verified_at: str,
+) -> dict[str, Any]:
+    """Build a complete success proof after cross-checking plan, result, and snapshot."""
+    try:
+        return _build_attestation(
+            intent=intent, manifest=manifest, result=result, snapshot=snapshot,
+            identity=identity, verified_at=verified_at,
+        )
+    except ValueError as exc:
+        rule_id = str(exc)
+        if _RULE_ID_RE.fullmatch(rule_id):
+            raise ValueError(rule_id) from None
+        raise ValueError("types_invalid") from None
+    except Exception:
+        raise ValueError("types_invalid") from None
+
+
+def _validate_policy_value(value: Any, failures: list[str]) -> None:
+    try:
+        _policy(value)
+    except ValueError as exc:
+        failures.append(str(exc))
+
+
+def _validate_proof_identity(value: Any, self_fingerprint: Any, expected: Any, failures: list[str]) -> None:
+    try:
+        parsed, config = _identity(value)
+        calculated = fingerprint_embedding(parsed)
+        _sha(self_fingerprint, "identity_mismatch")
+        if calculated != self_fingerprint:
+            failures.append("identity_mismatch")
+        if calculated != expected.expected_embedding_fingerprint:
+            failures.append("identity_mismatch")
+        if config != to_json_dict(parsed):
+            failures.append("identity_mismatch")
+    except (AttributeError, TypeError, ValueError):
+        failures.append("identity_mismatch")
+
+
+def _validate_snapshot(snapshot: Any, failures: list[str]) -> IndexSnapshot | None:
+    try:
+        return _clone_snapshot(snapshot)
+    except (TypeError, ValueError, AttributeError):
+        failures.append("types_invalid")
+        return None
+
+
+def _validate_isolation(expected: Any, proof: Mapping[str, Any], snapshot: IndexSnapshot | None,
+                        failures: list[str]) -> None:
+    try:
+        if not isinstance(expected, AttestationExpectation):
+            failures.append("isolation_unproven")
+            return
+        evidence = expected.isolation_evidence
+        if set(evidence) != {"mode", "target_index_id", "manifest_sha256", "row_count", "verified_at", "resource_record_ref"}:
+            failures.append("isolation_unproven")
+            return
+        if evidence["mode"] != "isolated_db":
+            failures.append("isolation_unproven")
+        if evidence["target_index_id"] != expected.expected_target_index_id:
+            failures.append("isolation_unproven")
+        if evidence["target_index_id"] != proof.get("target_index_id"):
+            failures.append("isolation_unproven")
+        if evidence["manifest_sha256"] != expected.expected_manifest_sha256:
+            failures.append("isolation_unproven")
+        if evidence["manifest_sha256"] != proof.get("artifact_manifest_sha256"):
+            failures.append("isolation_unproven")
+        _integer(evidence["row_count"], minimum=1, rule_id="isolation_unproven")
+        _utc(evidence["verified_at"], "isolation_unproven")
+        if evidence["verified_at"] != proof.get("created_at"):
+            failures.append("isolation_unproven")
+        _safe_ref(evidence["resource_record_ref"], "isolation_unproven")
+        if proof.get("planned_chunk_count") != evidence["row_count"]:
+            failures.append("isolation_unproven")
+        if snapshot is not None and evidence["row_count"] != snapshot.row_count:
+            failures.append("isolation_unproven")
+        _safe_ref(proof.get("isolation_evidence_ref"), "isolation_unproven")
+    except (AttributeError, KeyError, TypeError, ValueError):
+        failures.append("isolation_unproven")
+
+
+def _validate_attestation(attestation: Any, *, expected: Any, snapshot: Any) -> ContractCheck:
+    failures: list[str] = []
+    if not isinstance(attestation, dict):
+        return ContractCheck(False, ("types_invalid",))
+    keys = set(attestation)
+    if keys - _ATTESTATION_KEYS:
+        failures.append("schema_extra")
+    if _ATTESTATION_KEYS - keys:
+        failures.append("schema_missing")
+    actual_snapshot = _validate_snapshot(snapshot, failures)
+    if not isinstance(expected, AttestationExpectation):
+        failures.append("types_invalid")
+    for field, fixed in (
+        ("schema_version", _ATTESTATION_VERSION),
+        ("contract_version", _CONTRACT_VERSION),
+        ("status", "ok"),
+    ):
+        value = attestation.get(field)
+        if not isinstance(value, str) or value != fixed:
+            failures.append("version_unsupported")
+    try:
+        _uuid(attestation.get("ingestion_run_id"))
+        _utc(attestation.get("created_at"))
+    except ValueError:
+        failures.append("types_invalid")
+    try:
+        _sha(attestation.get("source_sha256"), "source_mismatch")
+        if expected is not None and attestation.get("source_sha256") != expected.expected_source_sha256:
+            failures.append("source_mismatch")
+    except (AttributeError, ValueError):
+        failures.append("source_mismatch")
+    for field in (
+        "source_format", "import_namespace", "doc_id", "normalizer_version", "chunking_version",
+        "doc_protocol", "chunk_protocol", "backend", "provider", "dialect", "target_index_id",
+        "safe_summary",
+    ):
+        try:
+            _safe_ref(attestation.get(field))
+        except ValueError:
+            failures.append("types_invalid")
+    if attestation.get("backend") != "pgvector" or attestation.get("provider") != "PgVectorProvider" or attestation.get("dialect") != "postgresql":
+        failures.append("version_unsupported")
+    if attestation.get("safe_summary") != "摄入已核验":
+        failures.append("types_invalid")
+    if attestation.get("doc_protocol") != "doc-v1" or attestation.get("chunk_protocol") != "chunk-v1":
+        failures.append("version_unsupported")
+    if attestation.get("chunking_version") == attestation.get("chunk_protocol"):
+        failures.append("version_unsupported")
+    _validate_policy_value(attestation.get("chunk_policy"), failures)
+    if expected is not None:
+        target = attestation.get("target_index_id")
+        if target != expected.expected_target_index_id or (actual_snapshot and target != actual_snapshot.target_index_id):
+            failures.append("target_mismatch")
+    if actual_snapshot is not None:
+        if actual_snapshot.row_count <= 0:
+            failures.append("count_mismatch")
+        try:
+            if manifest_sha256(actual_snapshot.rows) != actual_snapshot.manifest_sha256:
+                failures.append("identity_mismatch")
+        except (TypeError, ValueError):
+            failures.append("identity_mismatch")
+        if attestation.get("artifact_manifest_sha256") != actual_snapshot.manifest_sha256:
+            failures.append("identity_mismatch")
+    try:
+        manifest_digest = _sha(attestation.get("artifact_manifest_sha256"), "identity_mismatch")
+        if expected is not None and manifest_digest != expected.expected_manifest_sha256:
+            failures.append("identity_mismatch")
+    except ValueError:
+        failures.append("identity_mismatch")
+    _validate_proof_identity(
+        attestation.get("embedding_config"), attestation.get("embedding_fingerprint"), expected, failures
+    )
+    for field in ("planned_chunk_count", "written_chunk_count", "failure_count"):
+        try:
+            _integer(attestation.get(field), minimum=0 if field == "failure_count" else 1, rule_id="count_mismatch")
+        except ValueError:
+            failures.append("count_mismatch")
+    if attestation.get("failure_count") != 0 or attestation.get("planned_chunk_count") != attestation.get("written_chunk_count"):
+        failures.append("count_mismatch")
+    if actual_snapshot is not None and (
+        attestation.get("planned_chunk_count") != actual_snapshot.row_count
+        or attestation.get("written_chunk_count") != actual_snapshot.row_count
+    ):
+        failures.append("count_mismatch")
+    try:
+        _scope_owner(attestation.get("scope"), attestation.get("owner"))
+        if expected is not None and (
+            attestation.get("scope") != expected.expected_scope or attestation.get("owner") != expected.expected_owner
+        ):
+            failures.append("scope_mismatch")
+        if actual_snapshot is not None:
+            for row_value in actual_snapshot.rows:
+                if row_value["scope"] != attestation.get("scope") or row_value["owner"] != attestation.get("owner"):
+                    failures.append("scope_mismatch")
+            _rows(actual_snapshot.rows, doc_id=attestation.get("doc_id"),
+                  scope=attestation.get("scope"), owner=attestation.get("owner"))
+    except (KeyError, TypeError, ValueError):
+        failures.append("scope_mismatch")
+    if attestation.get("error_code") is not None:
+        failures.append("types_invalid")
+    try:
+        _warnings(attestation.get("warnings"))
+    except ValueError:
+        failures.append("types_invalid")
+    _validate_isolation(expected, attestation, actual_snapshot, failures)
+    return ContractCheck(not failures, tuple(failures))
+
+
+def validate_attestation(
+    attestation: dict[str, Any], *, expected: AttestationExpectation, snapshot: IndexSnapshot
+) -> ContractCheck:
+    """Validate proof against independent expectations and the supplied full snapshot."""
+    try:
+        return _validate_attestation(attestation, expected=expected, snapshot=snapshot)
+    except Exception:
+        return ContractCheck(False, ("types_invalid",))

--- /dev/null
+++ tests/unit/infrastructure/test_rag_contracts.py
@@ -0,0 +1,351 @@
+from __future__ import annotations
+
+import builtins
+import hashlib
+import io
+import sys
+from copy import deepcopy
+from types import SimpleNamespace
+from pathlib import Path
+
+import pytest
+
+from app.core.config import settings
+from app.harness.knowledge_ingestion import IngestResult
+from app.infrastructure.rag.embedding import EmbeddingService
+from app.infrastructure.rag.pgvector_provider import PgVectorProvider
+from app.infrastructure.rag.contracts import (
+    AttestationExpectation,
+    ContractCheck,
+    EmbeddingBinding,
+    EmbeddingIdentity,
+    IndexSnapshot,
+    RAGRequestContext,
+    RunRecord,
+    canonical_json_bytes,
+    manifest_sha256,
+)
+
+
+ROW = {
+    "chunk_id": "chunk-0",
+    "chunk_index": 0,
+    "content_sha256": "77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a",
+    "doc_id": "doc-fixture",
+    "owner": None,
+    "scope": "global",
+    "source_locator": {"paragraph": 0},
+}
+IDENTITY = {
+    "schema_version": "embedding-identity-v1",
+    "service_id": "svc-public",
+    "deployment_id": None,
+    "model": "model-a",
+    "dimension": 2,
+    "parameters": {"dimensions": "service_default", "encoding_format": "service_default"},
+    "model_version": None,
+    "version_binding": "alias_unpinned",
+}
+
+
+@pytest.fixture(autouse=True)
+def offline_pgvector_boundary(monkeypatch):
+    """Make accidental network/database use fail, even under pgvector settings."""
+    calls = {"sdk_factory": 0, "embeddings_create": 0, "embed_one": 0, "embed_many": 0,
+             "sync_engine": 0, "async_engine": 0, "provider_connection": 0}
+
+    def trap(name):
+        def fail(*args, **kwargs):
+            calls[name] += 1
+            raise AssertionError(f"offline boundary: {name}")
+        return fail
+
+    def sdk_factory(*args, **kwargs):
+        calls["sdk_factory"] += 1
+        return SimpleNamespace(embeddings=SimpleNamespace(create=trap("embeddings_create")))
+
+    monkeypatch.setattr(settings, "rag_backend", "pgvector")
+    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=sdk_factory))
+    monkeypatch.setattr(EmbeddingService, "embed_one", trap("embed_one"))
+    monkeypatch.setattr(EmbeddingService, "embed_many", trap("embed_many"))
+    import sqlalchemy
+    import sqlalchemy.ext.asyncio
+    monkeypatch.setattr(sqlalchemy, "create_engine", trap("sync_engine"))
+    monkeypatch.setattr(sqlalchemy.ext.asyncio, "create_async_engine", trap("async_engine"))
+    monkeypatch.setattr(PgVectorProvider, "_get_conn", trap("provider_connection"))
+    yield calls
+    assert not any(calls.values())
+
+
+def test_contract_check_freezes_failures_and_uses_contract_category_order():
+    check = ContractCheck(
+        allowed=False,
+        failures=("target_mismatch", "schema_missing", "count_mismatch", "schema_missing", "identity_mismatch"),
+    )
+
+    assert check.allowed is False
+    assert check.failures == ("schema_missing", "target_mismatch", "identity_mismatch", "count_mismatch")
+    assert isinstance(check.failures, tuple)
+    with pytest.raises((AttributeError, TypeError)):
+        check.failures += ("types_invalid",)
+    with pytest.raises(ValueError):
+        ContractCheck(allowed=True, failures=("schema_missing",))
+    with pytest.raises(ValueError):
+        ContractCheck(allowed=False, failures=())
+    with pytest.raises(ValueError):
+        ContractCheck(allowed=1, failures=())
+    with pytest.raises(ValueError):
+        ContractCheck(allowed=False, failures=("secret-token-should-not-be-a-rule",))
+
+
+def test_embedding_binding_keeps_endpoint_out_of_repr_and_rejects_secret_like_ids():
+    binding = EmbeddingBinding(
+        service_id="svc-public",
+        deployment_id="deploy-a",
+        model_version=None,
+        expected_endpoint="https://user:secret@example.test/v1/",
+    )
+
+    assert "svc-public" in repr(binding)
+    assert "example.test" not in repr(binding)
+    assert "secret" not in repr(binding)
+    assert binding.deployment_id == "deploy-a"
+    assert binding.model_version is None
+    for unsafe in ("https://service.test", "user:password", "with space", "", "x@y"):
+        with pytest.raises(ValueError):
+            EmbeddingBinding(service_id=unsafe, deployment_id=None, model_version=None,
+                            expected_endpoint="https://service.test")
+    for unsafe_version in ("https://user:fake-secret@example.test/v1", "api_key=fake-secret", "token: fake-secret", "v1\napi_key=x"):
+        with pytest.raises(ValueError):
+            EmbeddingBinding(service_id="svc-public", deployment_id=None, model_version=unsafe_version,
+                            expected_endpoint="https://service.test")
+
+
+def test_embedding_identity_freezes_nested_parameters_and_has_exact_versioned_fields():
+    source = {"dimensions": "service_default", "encoding_format": "service_default"}
+    identity = EmbeddingIdentity(**{**IDENTITY, "parameters": source})
+    source["dimensions"] = 99
+
+    assert identity.schema_version == "embedding-identity-v1"
+    assert dict(identity.parameters) == {
+        "dimensions": "service_default", "encoding_format": "service_default"
+    }
+    with pytest.raises(TypeError):
+        identity.parameters["encoding_format"] = "base64"
+    with pytest.raises(ValueError):
+        EmbeddingIdentity(**{**IDENTITY, "schema_version": "embedding-identity-v2"})
+    for bad_dimension in (0, -1, True, 2.0, None):
+        with pytest.raises(ValueError):
+            EmbeddingIdentity(**{**IDENTITY, "dimension": bad_dimension})
+    for bad_parameters in (
+        {"dimensions": "service_default"},
+        {"dimensions": "service_default", "encoding_format": "service_default", "extra": 1},
+        {"dimensions": float("nan"), "encoding_format": "service_default"},
+        {"dimensions": {"secret": "x"}, "encoding_format": "service_default"},
+    ):
+        with pytest.raises(ValueError):
+            EmbeddingIdentity(**{**IDENTITY, "parameters": bad_parameters})
+    with pytest.raises(ValueError):
+        EmbeddingIdentity(**{**IDENTITY, "model_version": "v1"})
+    with pytest.raises(ValueError):
+        EmbeddingIdentity(**{**IDENTITY, "version_binding": "pinned"})
+    with pytest.raises(ValueError):
+        EmbeddingIdentity(**{**IDENTITY, "deployment_id": ""})
+    for unsafe_field in ("https://user:fake-secret@example.test/v1", "api_key=fake-secret", "token: fake-secret", "v1\npassword=x"):
+        with pytest.raises(ValueError):
+            EmbeddingIdentity(**{**IDENTITY, "model": unsafe_field})
+        with pytest.raises(ValueError):
+            EmbeddingIdentity(**{**IDENTITY, "model_version": unsafe_field, "version_binding": "pinned"})
+    public_variant = EmbeddingIdentity(
+        **{**IDENTITY, "model": "vendor/embedding-v2", "model_version": "snapshot/release-v2",
+           "version_binding": "pinned"}
+    )
+    assert public_variant.model == "vendor/embedding-v2"
+    assert public_variant.model_version == "snapshot/release-v2"
+
+
+def test_index_snapshot_copies_complete_rows_and_recomputes_duplicate_preserving_digest():
+    original = [deepcopy(ROW)]
+    snapshot = IndexSnapshot(
+        target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
+        row_count=1, rows=original, manifest_sha256="7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176",
+    )
+    original[0]["source_locator"]["paragraph"] = 99
+
+    assert snapshot.rows[0]["source_locator"]["paragraph"] == 0
+    assert snapshot.manifest_sha256 == "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
+    assert isinstance(snapshot.rows, tuple)
+    with pytest.raises(TypeError):
+        snapshot.rows[0]["doc_id"] = "changed"
+    assert manifest_sha256([ROW, ROW]) != manifest_sha256([ROW])
+    assert manifest_sha256([ROW, {**ROW, "chunk_id": "chunk-1", "chunk_index": 1}]) == manifest_sha256(
+        [{**ROW, "chunk_id": "chunk-1", "chunk_index": 1}, ROW]
+    )
+    with pytest.raises(ValueError):
+        IndexSnapshot(target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
+                      row_count=2, rows=[ROW], manifest_sha256="7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176")
+    with pytest.raises(ValueError):
+        IndexSnapshot(target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
+                      row_count=True, rows=[ROW], manifest_sha256="7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176")
+    with pytest.raises(ValueError):
+        IndexSnapshot(target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
+                      row_count=1, rows=[{**ROW, "owner": False}], manifest_sha256="0" * 64)
+    with pytest.raises(ValueError):
+        IndexSnapshot(target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
+                      row_count=0, rows=[], manifest_sha256="not-a-sha")
+    with pytest.raises(ValueError):
+        IndexSnapshot(target_index_id="https://user:FAKE_SECRET@example.test/rag", database_id="rag_fixture",
+                      schema_name="public", row_count=1, rows=[ROW],
+                      manifest_sha256="7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176")
+
+
+def test_attestation_expectation_deep_freezes_isolation_evidence():
+    isolation = {
+        "mode": "isolated_db", "target_index_id": "rag-t04-fixture",
+        "manifest_sha256": "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176",
+        "row_count": 1, "verified_at": "2026-10-16T00:00:00Z",
+        "resource_record_ref": "fixture/resources/t04",
+    }
+    expected = AttestationExpectation(
+        expected_source_sha256="1a89e8c34a455cfadab9c5730f68a2669a3ac1db4f8b490065353e261f2cb6e8",
+        expected_target_index_id="rag-t04-fixture",
+        expected_embedding_fingerprint="005a79e156e97b05af18abadbadeda7c40bab8418a0152e7f36ee08b19aa798a",
+        expected_manifest_sha256=isolation["manifest_sha256"], expected_scope="global", expected_owner=None,
+        isolation_evidence=isolation,
+    )
+    isolation["row_count"] = 0
+
+    assert expected.isolation_evidence["row_count"] == 1
+    with pytest.raises(TypeError):
+        expected.isolation_evidence["row_count"] = 0
+    with pytest.raises(ValueError, match="^target_mismatch$"):
+        AttestationExpectation(
+            expected_source_sha256=expected.expected_source_sha256,
+            expected_target_index_id="https://user:FAKE_SECRET@example.test/rag",
+            expected_embedding_fingerprint=expected.expected_embedding_fingerprint,
+            expected_manifest_sha256=expected.expected_manifest_sha256,
+            expected_scope="global", expected_owner=None,
+            isolation_evidence=expected.isolation_evidence,
+        )
+    for bad_owner in (0, -1, True, 1.5):
+        with pytest.raises(ValueError):
+            AttestationExpectation(
+                expected_source_sha256="1a89e8c34a455cfadab9c5730f68a2669a3ac1db4f8b490065353e261f2cb6e8",
+                expected_target_index_id="rag-t04-fixture", expected_embedding_fingerprint="0" * 64,
+                expected_manifest_sha256="0" * 64, expected_scope="private", expected_owner=bad_owner,
+                isolation_evidence=expected.isolation_evidence,
+            )
+
+
+def test_request_context_is_immutable_and_attempt_is_exactly_one():
+    context = RAGRequestContext(retrieval_id="retrieval-1", attempt=1, trace_id=None, session_id="session-1")
+
+    assert context.retrieval_id == "retrieval-1"
+    assert context.trace_id is None
+    for attempt in (0, 2, True, 1.0, None):
+        with pytest.raises(ValueError):
+            RAGRequestContext(retrieval_id="retrieval-1", attempt=attempt)
+    for retrieval_id in ("", None, 3):
+        with pytest.raises(ValueError):
+            RAGRequestContext(retrieval_id=retrieval_id)
+
+
+@pytest.mark.parametrize(
+    ("phase", "summary"),
+    [
+        ("prepared", "\u6444\u5165\u8ba1\u5212\u5df2\u51c6\u5907"),
+        ("committed_unattested", "\u5199\u5165\u5f85\u8bc1\u660e"),
+        ("completed", "\u6444\u5165\u5df2\u6838\u9a8c"),
+        ("failed", "\u6444\u5165\u672a\u5b8c\u6210"),
+        ("inconclusive", "\u6444\u5165\u72b6\u6001\u5f85\u6838\u9a8c"),
+    ],
+)
+def test_run_record_summary_and_failure_ids_follow_frozen_phase_contract(phase, summary):
+    kwargs = {"schema_version": "ingestion-run-v1", "ingestion_run_id": "00000000-0000-4000-8000-000000000004",
+              "phase": phase, "error_code": None, "safe_summary": summary,
+              "failures": ("z_rule", "a_rule", "z_rule"), "attestation_path": "proof.json" if phase == "completed" else None}
+    record = RunRecord(**kwargs)
+
+    assert record.failures == ("a_rule", "z_rule")
+    assert record.safe_summary == summary
+    with pytest.raises(ValueError):
+        RunRecord(**{**kwargs, "phase": "unknown"})
+    with pytest.raises(ValueError):
+        RunRecord(**{**kwargs, "safe_summary": "raw error text"})
+    with pytest.raises(ValueError):
+        RunRecord(**{**kwargs, "attestation_path": "proof.json" if phase != "completed" else None})
+    with pytest.raises(ValueError):
+        RunRecord(**{**kwargs, "error_code": "new_public_code"})
+
+
+def test_run_record_rejects_invalid_uuid_error_text_and_non_string_failures():
+    base = {"schema_version": "ingestion-run-v1", "ingestion_run_id": "00000000-0000-4000-8000-000000000004",
+            "phase": "failed", "error_code": "db_error", "safe_summary": "\u6444\u5165\u672a\u5b8c\u6210", "failures": (),
+            "attestation_path": None}
+    for bad_uuid in ("run-1", "", None):
+        with pytest.raises(ValueError):
+            RunRecord(**{**base, "ingestion_run_id": bad_uuid})
+    for failures in (("traceback with secret",), (1,), ("bad rule",)):
+        with pytest.raises(ValueError):
+            RunRecord(**{**base, "failures": failures})
+    with pytest.raises(ValueError):
+        RunRecord(**{**base, "schema_version": "ingestion-run-v2"})
+
+
+def test_canonical_json_fixed_vectors_use_unicode_utf8_and_no_extra_whitespace():
+    value = {"z": None, "a": "甲"}
+    encoded = canonical_json_bytes(value)
+
+    assert encoded == '{"a":"甲","z":null}'.encode("utf-8")
+    assert hashlib.sha256(encoded).hexdigest() == "815d7d75761381ceee22ca5c208ba165a97158ae816d7e968c885f41f1605634"
+    assert canonical_json_bytes({"a": "甲", "z": None}) == encoded
+    assert canonical_json_bytes("é") != canonical_json_bytes("e\u0301")
+    assert hashlib.sha256(canonical_json_bytes(IDENTITY)).hexdigest() == "005a79e156e97b05af18abadbadeda7c40bab8418a0152e7f36ee08b19aa798a"
+    assert hashlib.sha256(canonical_json_bytes([ROW])).hexdigest() == "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
+
+
+@pytest.mark.parametrize(
+    "bad_value",
+    [
+        {1: "non-string key"},
+        {"x": float("nan")},
+        {"x": float("inf")},
+        {"x": -float("inf")},
+        {"x": object()},
+        {"x": {"unsafe": object()}},
+    ],
+)
+def test_canonical_json_rejects_values_outside_strict_json(bad_value):
+    with pytest.raises(ValueError) as exc:
+        canonical_json_bytes(bad_value)
+    assert "object at" not in str(exc.value)
+    assert "nan" not in str(exc.value).lower()
+
+
+def test_manifest_digest_validates_full_row_schema_without_losing_duplicates():
+    expected = "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
+
+    assert manifest_sha256([ROW]) == expected
+    assert manifest_sha256([ROW, ROW]) != expected
+    with pytest.raises(ValueError):
+        manifest_sha256([{**ROW, "extra": True}])
+    with pytest.raises(ValueError):
+        manifest_sha256([{**ROW, "chunk_index": True}])
+
+
+def test_shared_contract_types_do_not_touch_sdk_database_embedding_methods_or_files(
+    offline_pgvector_boundary, monkeypatch
+):
+    def trap_open(*args, **kwargs):
+        raise AssertionError("file IO is forbidden")
+
+    monkeypatch.setattr(builtins, "open", trap_open)
+    monkeypatch.setattr(io, "open", trap_open)
+    monkeypatch.setattr(Path, "open", trap_open)
+    monkeypatch.setattr(Path, "read_text", trap_open)
+    monkeypatch.setattr(Path, "read_bytes", trap_open)
+
+    assert settings.rag_backend == "pgvector"
+    assert IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=1).status == "ok"
+    assert manifest_sha256([ROW]) == "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
+    assert not any(offline_pgvector_boundary.values())

--- /dev/null
+++ tests/unit/infrastructure/test_embedding_identity.py
@@ -0,0 +1,245 @@
+from __future__ import annotations
+
+import builtins
+import io
+import sys
+from types import SimpleNamespace
+from pathlib import Path
+
+import pytest
+
+from app.core.config import settings
+from app.infrastructure.rag.embedding import EmbeddingService
+from app.infrastructure.rag.pgvector_provider import PgVectorProvider
+from app.infrastructure.rag.contracts import EmbeddingBinding, EmbeddingIdentity
+from app.infrastructure.rag.embedding_identity import (
+    describe_embedding,
+    fingerprint_embedding,
+    to_json_dict,
+)
+
+
+@pytest.fixture(autouse=True)
+def offline_pgvector_boundary(monkeypatch):
+    calls = {"sdk_factory": 0, "embeddings_create": 0, "embed_one": 0, "embed_many": 0,
+             "sync_engine": 0, "async_engine": 0, "provider_connection": 0}
+
+    def trap(name):
+        def fail(*args, **kwargs):
+            calls[name] += 1
+            raise AssertionError(f"offline boundary: {name}")
+        return fail
+
+    class Client:
+        def __init__(self, base_url):
+            self.base_url = base_url
+            self.embeddings = SimpleNamespace(create=trap("embeddings_create"))
+
+    def sdk_factory(*, api_key, base_url):
+        calls["sdk_factory"] += 1
+        # Deliberately do not retain the key or URL in shared fixture state.
+        return Client(base_url or "https://api.openai.com/v1/")
+
+    monkeypatch.setattr(settings, "rag_backend", "pgvector")
+    monkeypatch.setattr(settings, "embedding_dim", 2)
+    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=sdk_factory))
+    monkeypatch.setattr(EmbeddingService, "embed_one", trap("embed_one"))
+    monkeypatch.setattr(EmbeddingService, "embed_many", trap("embed_many"))
+    import sqlalchemy
+    import sqlalchemy.ext.asyncio
+    monkeypatch.setattr(sqlalchemy, "create_engine", trap("sync_engine"))
+    monkeypatch.setattr(sqlalchemy.ext.asyncio, "create_async_engine", trap("async_engine"))
+    monkeypatch.setattr(PgVectorProvider, "_get_conn", trap("provider_connection"))
+    yield calls
+    assert calls["embeddings_create"] == 0
+    assert calls["embed_one"] == 0
+    assert calls["embed_many"] == 0
+    assert calls["sync_engine"] == 0
+    assert calls["async_engine"] == 0
+    assert calls["provider_connection"] == 0
+
+
+def binding(endpoint="https://embedding.example.test/v1/", *, version=None, deployment="deploy-a"):
+    return EmbeddingBinding(
+        service_id="svc-public",
+        deployment_id=deployment,
+        model_version=version,
+        expected_endpoint=endpoint,
+    )
+
+
+def test_describe_embedding_reads_live_instance_and_uses_only_current_default_request_parameters(offline_pgvector_boundary):
+    service = EmbeddingService(
+        model="vendor/embedding-v2", api_key="FAKE_API_KEY_DO_NOT_LEAK",
+        base_url="https://embedding.example.test/v1/",
+    )
+
+    identity = describe_embedding(service, binding())
+
+    assert identity.schema_version == "embedding-identity-v1"
+    assert identity.service_id == "svc-public"
+    assert identity.deployment_id == "deploy-a"
+    assert identity.model == "vendor/embedding-v2"
+    assert identity.dimension == 2
+    assert dict(identity.parameters) == {
+        "dimensions": "service_default",
+        "encoding_format": "service_default",
+    }
+    assert identity.version_binding == "alias_unpinned"
+    assert identity.model_version is None
+    assert offline_pgvector_boundary["sdk_factory"] == 1
+    assert settings.rag_backend == "pgvector"
+
+
+def test_identity_helpers_do_not_open_files(monkeypatch):
+    service = EmbeddingService(model="model-a", api_key="fake", base_url="https://embedding.example.test/v1/")
+    control = binding()
+
+    def trap_open(*args, **kwargs):
+        raise AssertionError("file IO is forbidden")
+
+    monkeypatch.setattr(builtins, "open", trap_open)
+    monkeypatch.setattr(io, "open", trap_open)
+    monkeypatch.setattr(Path, "open", trap_open)
+    monkeypatch.setattr(Path, "read_text", trap_open)
+    monkeypatch.setattr(Path, "read_bytes", trap_open)
+
+    identity = describe_embedding(service, control)
+
+    assert fingerprint_embedding(identity)
+    assert to_json_dict(identity)["model"] == "model-a"
+
+
+def test_identity_fingerprint_matches_fixed_vector_and_changes_for_semantic_fields():
+    identity = EmbeddingIdentity(
+        service_id="svc-public", deployment_id=None, model="model-a", dimension=2,
+        parameters={"dimensions": "service_default", "encoding_format": "service_default"},
+        model_version=None, version_binding="alias_unpinned",
+    )
+
+    assert fingerprint_embedding(identity) == "005a79e156e97b05af18abadbadeda7c40bab8418a0152e7f36ee08b19aa798a"
+    variants = (
+        {"model": "model-b"},
+        {"service_id": "svc-other"},
+        {"deployment_id": "deploy-other"},
+        {"parameters": {"dimensions": 3, "encoding_format": "service_default"}},
+        {"model_version": "release/v2", "version_binding": "pinned"},
+    )
+    for changes in variants:
+        changed = EmbeddingIdentity(
+            service_id=changes.get("service_id", identity.service_id),
+            deployment_id=changes.get("deployment_id", identity.deployment_id),
+            model=changes.get("model", identity.model), dimension=identity.dimension,
+            parameters=changes.get("parameters", identity.parameters),
+            model_version=changes.get("model_version", identity.model_version),
+            version_binding=changes.get("version_binding", identity.version_binding),
+        )
+        assert fingerprint_embedding(changed) != fingerprint_embedding(identity)
+
+
+def test_identity_json_export_is_exact_defensive_and_rejects_binding():
+    identity = EmbeddingIdentity(
+        service_id="svc-public", deployment_id=None, model="vendor/model-a", dimension=2,
+        parameters={"dimensions": "service_default", "encoding_format": "service_default"},
+        model_version=None, version_binding="alias_unpinned",
+    )
+    exported = to_json_dict(identity)
+
+    assert set(exported) == {
+        "schema_version", "service_id", "deployment_id", "model", "dimension",
+        "parameters", "model_version", "version_binding",
+    }
+    assert exported["parameters"] == {
+        "dimensions": "service_default", "encoding_format": "service_default"
+    }
+    exported["parameters"]["dimensions"] = 99
+    assert identity.parameters["dimensions"] == "service_default"
+    with pytest.raises(ValueError):
+        to_json_dict(binding())
+
+
+def test_endpoint_binding_is_strict_and_error_does_not_disclose_url_or_credentials():
+    endpoint = "https://user:FAKE_SECRET@embedding.example.test/v1/"
+    service = EmbeddingService(model="model-a", api_key="FAKE_API_KEY_DO_NOT_LEAK", base_url=endpoint)
+
+    identity = describe_embedding(service, binding(endpoint))
+    assert identity.model == "model-a"
+    with pytest.raises(ValueError) as exc:
+        describe_embedding(service, binding(endpoint.rstrip("/")))
+    message = str(exc.value)
+    assert "endpoint_mismatch" in message
+    assert "embedding.example.test" not in message
+    assert "FAKE_SECRET" not in message
+    assert "FAKE_API_KEY_DO_NOT_LEAK" not in message
+
+
+def test_cached_sdk_endpoint_is_authoritative_even_if_service_base_url_later_changes(offline_pgvector_boundary):
+    service = EmbeddingService(model="model-a", api_key="fake", base_url="https://endpoint-a.test/v1/")
+    cached = service.client
+    service.base_url = "https://endpoint-b.test/v1/"
+
+    identity = describe_embedding(service, binding("https://endpoint-a.test/v1/"))
+
+    assert identity.model == "model-a"
+    assert cached.base_url == "https://endpoint-a.test/v1/"
+    with pytest.raises(ValueError) as exc:
+        describe_embedding(service, binding("https://endpoint-b.test/v1/"))
+    assert "endpoint_mismatch" in str(exc.value)
+    assert "endpoint-b.test" not in str(exc.value)
+
+
+@pytest.mark.parametrize("drifting_field", ["model", "dimension", "endpoint"])
+def test_describe_embedding_rejects_observed_configuration_drift(drifting_field):
+    class DriftingService:
+        def __init__(self):
+            self.model_reads = 0
+            self.dimension_reads = 0
+            self.client_reads = 0
+
+        @property
+        def model(self):
+            self.model_reads += 1
+            if drifting_field == "model" and self.model_reads > 1:
+                return "model-b"
+            return "model-a"
+
+        @property
+        def dim(self):
+            self.dimension_reads += 1
+            if drifting_field == "dimension" and self.dimension_reads > 1:
+                return 3
+            return 2
+
+        @property
+        def client(self):
+            self.client_reads += 1
+            endpoint = "https://endpoint-b.test/v1/" if drifting_field == "endpoint" and self.client_reads > 1 else "https://endpoint-a.test/v1/"
+            return SimpleNamespace(base_url=endpoint)
+
+    with pytest.raises(ValueError) as exc:
+        describe_embedding(DriftingService(), binding("https://endpoint-a.test/v1/"))
+    assert "identity_config_drift" in str(exc.value)
+    assert "endpoint-b.test" not in str(exc.value)
+
+
+def test_describe_embedding_sanitizes_sdk_initialization_errors(monkeypatch):
+    def broken_factory(**kwargs):
+        raise RuntimeError("api_key=FAKE_SECRET https://user:pass@example.test")
+
+    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=broken_factory))
+    service = EmbeddingService(model="model-a", api_key="FAKE_SECRET", base_url="https://example.test/v1/")
+
+    with pytest.raises(ValueError) as exc:
+        describe_embedding(service, binding())
+    assert str(exc.value) == "embedding_config_unobservable"
+    assert "FAKE_SECRET" not in repr(exc.value)
+    assert "example.test" not in repr(exc.value)
+
+
+def test_fingerprint_rejects_non_identity_values_without_serializing_them():
+    secret_like = SimpleNamespace(api_key="FAKE_SECRET", endpoint="https://user:pass@example.test")
+    with pytest.raises(ValueError) as exc:
+        fingerprint_embedding(secret_like)
+    assert "identity_mismatch" in str(exc.value)
+    assert "FAKE_SECRET" not in str(exc.value)
+    assert "example.test" not in str(exc.value)

--- /dev/null
+++ tests/unit/harness/test_ingestion_attestation.py
@@ -0,0 +1,658 @@
+from __future__ import annotations
+
+import builtins
+import copy
+import io
+import sys
+from pathlib import Path
+from types import MappingProxyType, SimpleNamespace
+
+import pytest
+
+from app.core.config import settings
+from app.harness.knowledge_ingestion import IngestResult
+from app.infrastructure.rag.contracts import (
+    AttestationExpectation,
+    EmbeddingIdentity,
+    IndexSnapshot,
+    manifest_sha256,
+)
+from app.infrastructure.rag.embedding import EmbeddingService
+from app.infrastructure.rag.embedding_identity import fingerprint_embedding, to_json_dict
+from app.infrastructure.rag.pgvector_provider import PgVectorProvider
+from app.harness.ingestion_attestation import build_attestation, validate_attestation
+
+
+RUN_ID = "00000000-0000-4000-8000-000000000004"
+VERIFIED_AT = "2026-10-16T00:00:00Z"
+SOURCE_SHA = "1a89e8c34a455cfadab9c5730f68a2669a3ac1db4f8b490065353e261f2cb6e8"
+IDENTITY_SHA = "005a79e156e97b05af18abadbadeda7c40bab8418a0152e7f36ee08b19aa798a"
+ROW_SHA = "77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a"
+MANIFEST_SHA = "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
+TARGET = "rag-t04-fixture"
+WARNING = "chunk_index=0 超过 embedding 安全阈值（hard_limit），已整块保留（atomic 不切裂）"
+
+
+@pytest.fixture(autouse=True)
+def offline_pgvector_boundary(monkeypatch):
+    calls = {"sdk_factory": 0, "embeddings_create": 0, "embed_one": 0, "embed_many": 0,
+             "sync_engine": 0, "async_engine": 0, "provider_connection": 0}
+
+    def trap(name):
+        def fail(*args, **kwargs):
+            calls[name] += 1
+            raise AssertionError(f"offline boundary: {name}")
+        return fail
+
+    def sdk_factory(*, api_key, base_url):
+        calls["sdk_factory"] += 1
+        return SimpleNamespace(base_url=base_url, embeddings=SimpleNamespace(create=trap("embeddings_create")))
+
+    monkeypatch.setattr(settings, "rag_backend", "pgvector")
+    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=sdk_factory))
+    monkeypatch.setattr(EmbeddingService, "embed_one", trap("embed_one"))
+    monkeypatch.setattr(EmbeddingService, "embed_many", trap("embed_many"))
+    import sqlalchemy
+    import sqlalchemy.ext.asyncio
+    monkeypatch.setattr(sqlalchemy, "create_engine", trap("sync_engine"))
+    monkeypatch.setattr(sqlalchemy.ext.asyncio, "create_async_engine", trap("async_engine"))
+    monkeypatch.setattr(PgVectorProvider, "_get_conn", trap("provider_connection"))
+    yield calls
+    assert calls["embeddings_create"] == 0
+    assert calls["embed_one"] == 0
+    assert calls["embed_many"] == 0
+    assert calls["sync_engine"] == 0
+    assert calls["async_engine"] == 0
+    assert calls["provider_connection"] == 0
+
+
+def identity(*, model="model-a", service_id="svc-public", deployment_id=None,
+             model_version=None, parameters=None):
+    return EmbeddingIdentity(
+        schema_version="embedding-identity-v1", service_id=service_id,
+        deployment_id=deployment_id, model=model, dimension=2,
+        parameters=parameters or {"dimensions": "service_default", "encoding_format": "service_default"},
+        model_version=model_version,
+        version_binding="pinned" if model_version is not None else "alias_unpinned",
+    )
+
+
+def row(*, scope="global", owner=None, chunk_id="chunk-0", chunk_index=0, doc_id="doc-fixture"):
+    return {
+        "chunk_id": chunk_id,
+        "chunk_index": chunk_index,
+        "content_sha256": ROW_SHA,
+        "doc_id": doc_id,
+        "owner": owner,
+        "scope": scope,
+        "source_locator": {"paragraph": chunk_index},
+    }
+
+
+def bundle(*, scope="global", owner=None, warnings=None, use_fixed_digest=True):
+    warnings = [] if warnings is None else list(warnings)
+    rows = [row(scope=scope, owner=owner)]
+    row_digest = MANIFEST_SHA if use_fixed_digest and scope == "global" and owner is None and rows[0] == row() else manifest_sha256(rows)
+    config = identity()
+    prep = {
+        "schema_version": "prepared-ingestion-v1",
+        "source_sha256": SOURCE_SHA,
+        "source_format": "epub",
+        "import_namespace": "fixture-book",
+        "doc_id": "doc-fixture",
+        "scope": scope,
+        "owner": owner,
+        "normalizer_version": "doc-norm-1",
+        "chunking_version": "chunk-policy-1",
+        "doc_protocol": "doc-v1",
+        "chunk_protocol": "chunk-v1",
+        "chunk_policy": {"chunk_size": 500, "chunk_overlap": 50, "hard_limit": 8192},
+        "warnings": warnings,
+    }
+    intent = {
+        "schema_version": "ingestion-intent-v1",
+        "ingestion_run_id": RUN_ID,
+        "created_at": "2026-10-15T23:00:00Z",
+        "target_index_id": TARGET,
+        "database_id": "rag_fixture",
+        "schema_name": "public",
+        "source_sha256": SOURCE_SHA,
+        "manifest_sha256": row_digest,
+        "embedding_fingerprint": IDENTITY_SHA,
+        "embedding_config": to_json_dict(config),
+        "preparation": prep,
+        "before_row_count": 0,
+        "resource_record_ref": "fixture/resources/t04",
+        "exclusivity_record_ref": "fixture/leases/t04",
+        "isolation_evidence_ref": "fixture/run-t04/isolation-evidence.json",
+        "exclusive_target": True,
+        "phase": "prepared",
+    }
+    manifest = {
+        "schema_version": "ingestion-manifest-v1",
+        "ingestion_run_id": RUN_ID,
+        "target_index_id": TARGET,
+        "doc_id": "doc-fixture",
+        "source_sha256": SOURCE_SHA,
+        "embedding_fingerprint": IDENTITY_SHA,
+        "rows": rows,
+        "row_count": 1,
+        "manifest_sha256": row_digest,
+    }
+    snapshot = IndexSnapshot(
+        target_index_id=TARGET,
+        database_id="rag_fixture",
+        schema_name="public",
+        row_count=1,
+        rows=rows,
+        manifest_sha256=row_digest,
+    )
+    result = IngestResult(
+        status="ok", doc_id="doc-fixture", planned_chunk_count=1,
+        written_chunk_count=1, warnings=warnings,
+    )
+    isolation = {
+        "mode": "isolated_db",
+        "target_index_id": TARGET,
+        "manifest_sha256": row_digest,
+        "row_count": 1,
+        "verified_at": VERIFIED_AT,
+        "resource_record_ref": "fixture/resources/t04",
+    }
+    expected = AttestationExpectation(
+        expected_source_sha256=SOURCE_SHA,
+        expected_target_index_id=TARGET,
+        expected_embedding_fingerprint=IDENTITY_SHA,
+        expected_manifest_sha256=row_digest,
+        expected_scope=scope,
+        expected_owner=owner,
+        isolation_evidence=isolation,
+    )
+    return {"intent": intent, "manifest": manifest, "result": result, "snapshot": snapshot,
+            "identity": config, "verified_at": VERIFIED_AT, "expected": expected, "isolation": isolation}
+
+
+def build(bundle_value):
+    return build_attestation(
+        intent=bundle_value["intent"], manifest=bundle_value["manifest"],
+        result=bundle_value["result"], snapshot=bundle_value["snapshot"],
+        identity=bundle_value["identity"], verified_at=bundle_value["verified_at"],
+    )
+
+
+def test_build_and_validate_return_exact_success_contract_using_new_verification_time():
+    values = bundle()
+    intent_before = copy.deepcopy(values["intent"])
+    manifest_before = copy.deepcopy(values["manifest"])
+    result_warnings_before = list(values["result"].warnings)
+    attestation = build(values)
+
+    assert set(attestation) == {
+        "schema_version", "contract_version", "status", "ingestion_run_id", "created_at",
+        "source_sha256", "source_format", "import_namespace", "doc_id", "normalizer_version",
+        "chunking_version", "doc_protocol", "chunk_protocol", "chunk_policy", "planned_chunk_count",
+        "written_chunk_count", "failure_count", "backend", "provider", "dialect", "target_index_id",
+        "scope", "owner", "embedding_config", "embedding_fingerprint", "artifact_manifest_sha256",
+        "isolation_evidence_ref", "error_code", "safe_summary", "warnings",
+    }
+    assert attestation["schema_version"] == "ingestion-attestation-v1"
+    assert attestation["contract_version"] == "rag-mvp-contracts-v1.0.1"
+    assert attestation["status"] == "ok"
+    assert attestation["ingestion_run_id"] == RUN_ID
+    assert attestation["created_at"] == VERIFIED_AT
+    assert attestation["created_at"] != values["intent"]["created_at"]
+    assert attestation["chunking_version"] == "chunk-policy-1"
+    assert attestation["chunk_protocol"] == "chunk-v1"
+    assert attestation["backend"] == "pgvector"
+    assert attestation["provider"] == "PgVectorProvider"
+    assert attestation["dialect"] == "postgresql"
+    assert attestation["embedding_fingerprint"] == IDENTITY_SHA
+    assert attestation["artifact_manifest_sha256"] == MANIFEST_SHA
+    assert validate_attestation(attestation, expected=values["expected"], snapshot=values["snapshot"]).allowed
+    assert values["intent"] == intent_before
+    assert values["manifest"] == manifest_before
+    assert values["result"].warnings == result_warnings_before
+    assert build(values) == attestation
+
+
+def test_build_copies_preparation_fields_without_claiming_independent_validation():
+    values = bundle()
+    preparation = values["intent"]["preparation"]
+    preparation["source_format"] = "pdf"
+    preparation["import_namespace"] = "other-book"
+    preparation["normalizer_version"] = "other-normalizer"
+
+    proof = build(values)
+
+    assert proof["source_format"] == "pdf"
+    assert proof["import_namespace"] == "other-book"
+    assert proof["normalizer_version"] == "other-normalizer"
+    assert validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed
+
+
+def test_build_rejects_secret_like_target_even_when_all_target_sources_agree():
+    values = bundle()
+    unsafe_target = "https://user:FAKE_SECRET@example.invalid/rag"
+    values["intent"]["target_index_id"] = unsafe_target
+    values["manifest"]["target_index_id"] = unsafe_target
+    object.__setattr__(values["snapshot"], "target_index_id", unsafe_target)
+
+    with pytest.raises(ValueError) as exc:
+        build(values)
+
+    assert re_safe_rule_id(str(exc.value))
+    assert "FAKE_SECRET" not in str(exc.value)
+
+
+def test_private_owner_and_known_oversized_warning_are_valid_success_cases():
+    private = bundle(scope="private", owner=7, use_fixed_digest=False)
+    proof = build(private)
+    assert proof["scope"] == "private"
+    assert proof["owner"] == 7
+    assert validate_attestation(proof, expected=private["expected"], snapshot=private["snapshot"]).allowed
+
+    oversized = bundle(warnings=[WARNING])
+    warning_proof = build(oversized)
+    assert warning_proof["warnings"] == [WARNING]
+    assert validate_attestation(warning_proof, expected=oversized["expected"], snapshot=oversized["snapshot"]).allowed
+
+
+@pytest.mark.parametrize(
+    "mutation",
+    [
+        "missing_intent_field", "extra_intent_field", "intent_version", "before_row_count",
+        "exclusive_target", "missing_lock_ref", "missing_isolation_ref", "preparation_version",
+        "preparation_extra", "policy_size_zero", "policy_overlap_equal_size", "policy_hard_limit_small",
+        "policy_boolean", "manifest_version", "manifest_extra", "manifest_run_id", "manifest_target",
+        "manifest_doc", "manifest_source", "manifest_identity", "manifest_count_zero", "manifest_digest",
+        "row_order", "row_duplicate", "identity_model", "identity_fingerprint", "identity_dimension",
+        "snapshot_target", "snapshot_database", "snapshot_schema", "result_failed", "result_doc",
+        "result_planned_zero", "result_written_mismatch", "result_boolean_count", "warnings_mismatch",
+        "warning_secret", "verified_at_missing", "verified_at_invalid", "verified_at_non_utc",
+    ],
+)
+def test_build_rejects_each_single_field_contract_violation(mutation):
+    values = bundle()
+    if mutation == "missing_intent_field":
+        del values["intent"]["phase"]
+    elif mutation == "extra_intent_field":
+        values["intent"]["unexpected"] = "x"
+    elif mutation == "intent_version":
+        values["intent"]["schema_version"] = "ingestion-intent-v0"
+    elif mutation == "before_row_count":
+        values["intent"]["before_row_count"] = 1
+    elif mutation == "exclusive_target":
+        values["intent"]["exclusive_target"] = False
+    elif mutation == "missing_lock_ref":
+        values["intent"]["exclusivity_record_ref"] = ""
+    elif mutation == "missing_isolation_ref":
+        values["intent"]["isolation_evidence_ref"] = None
+    elif mutation == "preparation_version":
+        values["intent"]["preparation"]["schema_version"] = "prepared-ingestion-v0"
+    elif mutation == "preparation_extra":
+        values["intent"]["preparation"]["extra"] = True
+    elif mutation == "policy_size_zero":
+        values["intent"]["preparation"]["chunk_policy"]["chunk_size"] = 0
+    elif mutation == "policy_overlap_equal_size":
+        values["intent"]["preparation"]["chunk_policy"]["chunk_overlap"] = 500
+    elif mutation == "policy_hard_limit_small":
+        values["intent"]["preparation"]["chunk_policy"]["hard_limit"] = 499
+    elif mutation == "policy_boolean":
+        values["intent"]["preparation"]["chunk_policy"]["chunk_size"] = True
+    elif mutation == "manifest_version":
+        values["manifest"]["schema_version"] = "ingestion-manifest-v0"
+    elif mutation == "manifest_extra":
+        values["manifest"]["extra"] = 1
+    elif mutation == "manifest_run_id":
+        values["manifest"]["ingestion_run_id"] = "run-1"
+    elif mutation == "manifest_target":
+        values["manifest"]["target_index_id"] = "other-target"
+    elif mutation == "manifest_doc":
+        values["manifest"]["doc_id"] = "other-doc"
+    elif mutation == "manifest_source":
+        values["manifest"]["source_sha256"] = "0" * 64
+    elif mutation == "manifest_identity":
+        values["manifest"]["embedding_fingerprint"] = "0" * 64
+    elif mutation == "manifest_count_zero":
+        values["manifest"]["row_count"] = 0
+    elif mutation == "manifest_digest":
+        values["manifest"]["manifest_sha256"] = "0" * 64
+    elif mutation == "row_order":
+        values["manifest"]["rows"] = [{**values["manifest"]["rows"][0], "chunk_index": 1}]
+    elif mutation == "row_duplicate":
+        values["manifest"]["rows"] = [values["manifest"]["rows"][0], values["manifest"]["rows"][0]]
+        values["manifest"]["row_count"] = 2
+    elif mutation == "identity_model":
+        values["identity"] = identity(model="model-b")
+    elif mutation == "identity_fingerprint":
+        values["intent"]["embedding_fingerprint"] = "0" * 64
+    elif mutation == "identity_dimension":
+        values["identity"] = identity()
+        object.__setattr__(values["identity"], "dimension", 3)
+    elif mutation == "snapshot_target":
+        values["snapshot"] = IndexSnapshot(
+            target_index_id="other-target", database_id="rag_fixture", schema_name="public", row_count=1,
+            rows=[row()], manifest_sha256=MANIFEST_SHA,
+        )
+    elif mutation == "snapshot_database":
+        values["snapshot"] = IndexSnapshot(
+            target_index_id=TARGET, database_id="other-db", schema_name="public", row_count=1,
+            rows=[row()], manifest_sha256=MANIFEST_SHA,
+        )
+    elif mutation == "snapshot_schema":
+        values["snapshot"] = IndexSnapshot(
+            target_index_id=TARGET, database_id="rag_fixture", schema_name="other-schema", row_count=1,
+            rows=[row()], manifest_sha256=MANIFEST_SHA,
+        )
+    elif mutation == "result_failed":
+        values["result"] = IngestResult(status="db_error", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=1)
+    elif mutation == "result_doc":
+        values["result"] = IngestResult(status="ok", doc_id="other-doc", planned_chunk_count=1, written_chunk_count=1)
+    elif mutation == "result_planned_zero":
+        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=0, written_chunk_count=0)
+    elif mutation == "result_written_mismatch":
+        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=2)
+    elif mutation == "result_boolean_count":
+        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=True, written_chunk_count=True)
+    elif mutation == "warnings_mismatch":
+        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=1, warnings=[WARNING])
+    elif mutation == "warning_secret":
+        values["intent"]["preparation"]["warnings"] = ["api_key=FAKE_SECRET"]
+        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=1, warnings=["api_key=FAKE_SECRET"])
+    elif mutation == "verified_at_missing":
+        values["verified_at"] = None
+    elif mutation == "verified_at_invalid":
+        values["verified_at"] = "yesterday"
+    elif mutation == "verified_at_non_utc":
+        values["verified_at"] = "2026-10-16T09:00:00+09:00"
+
+    with pytest.raises(ValueError) as exc:
+        build(values)
+    assert re_safe_rule_id(str(exc.value))
+    assert "FAKE_SECRET" not in str(exc.value)
+
+
+def re_safe_rule_id(value):
+    import re
+    return re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) is not None
+
+
+@pytest.mark.parametrize(
+    ("field", "bad_value"),
+    [
+        ("source_sha256", "0" * 64),
+        ("doc_id", "other-doc"),
+        ("chunking_version", "chunk-v1"), ("doc_protocol", "chunk-v1"),
+        ("chunk_protocol", "doc-v1"), ("target_index_id", "other-target"),
+        ("scope", "private"), ("owner", 7), ("planned_chunk_count", 0),
+        ("written_chunk_count", 0), ("failure_count", 1), ("backend", "fake"),
+        ("provider", "OtherProvider"), ("dialect", "sqlite"),
+        ("artifact_manifest_sha256", "0" * 64), ("isolation_evidence_ref", ""),
+        ("error_code", "db_error"), ("safe_summary", "api_key=FAKE_SECRET"),
+    ],
+)
+def test_validator_rejects_individual_proof_field_mismatches(field, bad_value):
+    values = bundle()
+    proof = build(values)
+    proof[field] = bad_value
+
+    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+    assert checked.allowed is False
+    assert checked.failures
+    assert all(re_safe_rule_id(rule) for rule in checked.failures)
+    assert "FAKE_SECRET" not in repr(checked)
+
+
+@pytest.mark.parametrize("key", [
+    "schema_version", "contract_version", "status", "ingestion_run_id", "created_at", "source_sha256",
+    "source_format", "import_namespace", "doc_id", "normalizer_version", "chunking_version",
+    "doc_protocol", "chunk_protocol", "chunk_policy", "planned_chunk_count", "written_chunk_count",
+    "failure_count", "backend", "provider", "dialect", "target_index_id", "scope", "owner",
+    "embedding_config", "embedding_fingerprint", "artifact_manifest_sha256", "isolation_evidence_ref",
+    "error_code", "safe_summary", "warnings",
+])
+def test_validator_rejects_each_missing_top_level_field(key):
+    values = bundle()
+    proof = build(values)
+    del proof[key]
+
+    check = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+    assert not check.allowed
+    assert "schema_missing" in check.failures
+
+
+@pytest.mark.parametrize("extra", ["unexpected", "verified", "provenance_filter"])
+def test_validator_rejects_legacy_or_unfrozen_extra_fields(extra):
+    values = bundle()
+    proof = build(values)
+    proof[extra] = True
+
+    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+    assert not checked.allowed
+    assert "schema_extra" in checked.failures
+
+
+@pytest.mark.parametrize("field", [
+    "schema_version", "contract_version", "status", "ingestion_run_id", "created_at", "source_sha256",
+    "source_format", "import_namespace", "doc_id", "normalizer_version", "chunking_version",
+    "doc_protocol", "chunk_protocol", "chunk_policy", "planned_chunk_count", "written_chunk_count",
+    "failure_count", "backend", "provider", "dialect", "target_index_id", "scope", "embedding_config",
+    "embedding_fingerprint", "artifact_manifest_sha256", "isolation_evidence_ref", "safe_summary", "warnings",
+])
+def test_validator_rejects_null_in_every_non_nullable_top_level_field(field):
+    values = bundle()
+    proof = build(values)
+    proof[field] = None
+
+    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+    assert not checked.allowed
+    assert checked.failures
+
+
+@pytest.mark.parametrize(
+    "policy",
+    [
+        {"chunk_size": 0, "chunk_overlap": 0, "hard_limit": 8192},
+        {"chunk_size": 500, "chunk_overlap": -1, "hard_limit": 8192},
+        {"chunk_size": 500, "chunk_overlap": 500, "hard_limit": 8192},
+        {"chunk_size": 500, "chunk_overlap": 50, "hard_limit": 499},
+        {"chunk_size": True, "chunk_overlap": 50, "hard_limit": 8192},
+        {"chunk_size": 500, "chunk_overlap": False, "hard_limit": 8192},
+        {"chunk_size": 500, "chunk_overlap": 50, "hard_limit": True},
+        {"chunk_size": 500, "chunk_overlap": 50, "hard_limit": 8192, "extra": 1},
+    ],
+)
+def test_validator_rejects_invalid_or_extra_policy_fields(policy):
+    values = bundle()
+    proof = build(values)
+    proof["chunk_policy"] = policy
+
+    assert not validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed
+
+
+def test_validator_accepts_zero_overlap_and_rejects_identity_that_is_self_consistent_but_not_expected():
+    values = bundle()
+    proof = build(values)
+    proof["chunk_policy"]["chunk_overlap"] = 0
+    assert validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed
+
+    changed = identity(model="same-dimension-other-model")
+    proof["embedding_config"] = to_json_dict(changed)
+    proof["embedding_fingerprint"] = fingerprint_embedding(changed)
+    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+    assert not checked.allowed
+    assert "identity_mismatch" in checked.failures
+
+
+@pytest.mark.parametrize("changed", [
+    {"model": "model-b"}, {"service_id": "svc-other"}, {"deployment_id": "deploy-b"},
+    {"parameters": {"dimensions": 3, "encoding_format": "service_default"}},
+    {"model_version": "release/v2", "version_binding": "pinned"},
+])
+def test_validator_rejects_all_semantic_identity_changes_even_with_recomputed_fingerprint(changed):
+    values = bundle()
+    proof = build(values)
+    config = to_json_dict(values["identity"])
+    config.update(changed)
+    altered = identity(
+        model=config["model"], service_id=config["service_id"], deployment_id=config["deployment_id"],
+        model_version=config["model_version"], parameters=config["parameters"],
+    )
+    proof["embedding_config"] = to_json_dict(altered)
+    proof["embedding_fingerprint"] = fingerprint_embedding(altered)
+
+    check = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+    assert not check.allowed
+    assert "identity_mismatch" in check.failures
+
+
+@pytest.mark.parametrize("bad_value", [True, 1.0, -1, None, "1"])
+def test_validator_rejects_boolean_float_negative_or_null_counts(bad_value):
+    values = bundle()
+    proof = build(values)
+    proof["planned_chunk_count"] = bad_value
+
+    assert not validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed
+
+
+@pytest.mark.parametrize("owner", [None, 0, -1, True, 1.5, "7"])
+def test_validator_rejects_private_scope_without_a_positive_non_boolean_owner(owner):
+    values = bundle()
+    proof = build(values)
+    proof["scope"] = "private"
+    proof["owner"] = owner
+
+    assert not validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed
+
+
+def test_validator_rejects_global_scope_with_owner_and_expected_context_drift():
+    values = bundle()
+    proof = build(values)
+    proof["owner"] = 7
+    assert not validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed
+
+    for field, value in (
+        ("expected_source_sha256", "0" * 64),
+        ("expected_target_index_id", "other-target"),
+        ("expected_embedding_fingerprint", "0" * 64),
+        ("expected_manifest_sha256", "0" * 64),
+        ("expected_scope", "private"),
+    ):
+        isolation = dict(values["isolation"])
+        if field == "expected_target_index_id":
+            isolation["target_index_id"] = value
+        elif field == "expected_manifest_sha256":
+            isolation["manifest_sha256"] = value
+        drifted = AttestationExpectation(
+            expected_source_sha256=value if field == "expected_source_sha256" else values["expected"].expected_source_sha256,
+            expected_target_index_id=value if field == "expected_target_index_id" else values["expected"].expected_target_index_id,
+            expected_embedding_fingerprint=value if field == "expected_embedding_fingerprint" else values["expected"].expected_embedding_fingerprint,
+            expected_manifest_sha256=value if field == "expected_manifest_sha256" else values["expected"].expected_manifest_sha256,
+            expected_scope=value if field == "expected_scope" else values["expected"].expected_scope,
+            expected_owner=7 if field == "expected_scope" else values["expected"].expected_owner,
+            isolation_evidence=isolation,
+        )
+        proof = build(values)
+        assert not validate_attestation(proof, expected=drifted, snapshot=values["snapshot"]).allowed
+
+
+@pytest.mark.parametrize("isolation", [
+    {"verified": True},
+    {"mode": "provenance_filter", "target_index_id": TARGET, "manifest_sha256": MANIFEST_SHA,
+     "row_count": 1, "verified_at": VERIFIED_AT, "resource_record_ref": "fixture/resources/t04"},
+    {"mode": "isolated_db", "target_index_id": "other-target", "manifest_sha256": MANIFEST_SHA,
+     "row_count": 1, "verified_at": VERIFIED_AT, "resource_record_ref": "fixture/resources/t04"},
+    {"mode": "isolated_db", "target_index_id": TARGET, "manifest_sha256": "0" * 64,
+     "row_count": 1, "verified_at": VERIFIED_AT, "resource_record_ref": "fixture/resources/t04"},
+    {"mode": "isolated_db", "target_index_id": TARGET, "manifest_sha256": MANIFEST_SHA,
+     "row_count": 0, "verified_at": VERIFIED_AT, "resource_record_ref": "fixture/resources/t04"},
+    {"mode": "isolated_db", "target_index_id": TARGET, "manifest_sha256": MANIFEST_SHA,
+     "row_count": 1, "verified_at": "yesterday", "resource_record_ref": "fixture/resources/t04"},
+    {"mode": "isolated_db", "target_index_id": TARGET, "manifest_sha256": MANIFEST_SHA,
+     "row_count": 1, "verified_at": VERIFIED_AT, "resource_record_ref": ""},
+])
+def test_expectation_rejects_incomplete_or_untrusted_isolation_evidence(isolation):
+    with pytest.raises(ValueError):
+        AttestationExpectation(
+            expected_source_sha256=SOURCE_SHA, expected_target_index_id=TARGET,
+            expected_embedding_fingerprint=IDENTITY_SHA, expected_manifest_sha256=MANIFEST_SHA,
+            expected_scope="global", expected_owner=None, isolation_evidence=isolation,
+        )
+
+
+def test_build_and_validate_are_pure_repeatable_and_do_not_mutate_inputs(monkeypatch, offline_pgvector_boundary):
+    values = bundle()
+    opened = {"count": 0}
+
+    def trap_open(*args, **kwargs):
+        opened["count"] += 1
+        raise AssertionError("file IO is forbidden")
+
+    monkeypatch.setattr(builtins, "open", trap_open)
+    monkeypatch.setattr(io, "open", trap_open)
+    monkeypatch.setattr(Path, "open", trap_open)
+    monkeypatch.setattr(Path, "read_text", trap_open)
+    monkeypatch.setattr(Path, "read_bytes", trap_open)
+    proof = build(values)
+    first = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+    second = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+
+    assert first == second
+    assert first.allowed
+    assert opened["count"] == 0
+    assert offline_pgvector_boundary["embeddings_create"] == 0
+
+
+def test_validator_rejects_self_consistent_attestation_for_different_snapshot():
+    values = bundle()
+    proof = build(values)
+    other_row = {**row(), "doc_id": "other-doc"}
+    other_snapshot = IndexSnapshot(
+        target_index_id=TARGET, database_id="rag_fixture", schema_name="public", row_count=1,
+        rows=[other_row], manifest_sha256=manifest_sha256([other_row]),
+    )
+
+    checked = validate_attestation(proof, expected=values["expected"], snapshot=other_snapshot)
+    assert not checked.allowed
+    assert "identity_mismatch" in checked.failures or "count_mismatch" in checked.failures
+
+
+def test_multiple_failures_are_deduplicated_in_stable_contract_order_and_never_echo_secrets():
+    values = bundle()
+    proof = build(values)
+    proof["unexpected"] = "FAKE_SECRET"
+    proof["source_sha256"] = "invalid"
+    proof["target_index_id"] = "other-target"
+    proof["planned_chunk_count"] = True
+    proof["scope"] = "unknown"
+    proof["embedding_fingerprint"] = "0" * 64
+    proof["isolation_evidence_ref"] = ""
+    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+
+    assert not checked.allowed
+    assert checked.failures == tuple(dict.fromkeys(checked.failures))
+    assert all(re_safe_rule_id(rule) for rule in checked.failures)
+    assert "FAKE_SECRET" not in repr(checked)
+
+
+def test_validator_rejects_non_dict_outer_mapping_but_accepts_nested_contract_mappings():
+    values = bundle()
+    proof = build(values)
+    checked = validate_attestation(MappingProxyType(proof), expected=values["expected"], snapshot=values["snapshot"])
+
+    assert not checked.allowed
+    assert checked.failures == ("types_invalid",)
+
+    proof["chunk_policy"] = MappingProxyType(dict(proof["chunk_policy"]))
+    assert validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed
+
+
+def test_validator_requires_isolation_and_attestation_verification_times_to_match():
+    values = bundle()
+    proof = build(values)
+    proof["created_at"] = "2026-10-16T00:00:01Z"
+
+    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
+
+    assert not checked.allowed
+    assert "isolation_unproven" in checked.failures
