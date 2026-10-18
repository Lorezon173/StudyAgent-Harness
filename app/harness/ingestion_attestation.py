"""Pure construction and validation for the frozen RAG ingestion proof contract."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from app.harness.knowledge_ingestion import IngestResult
from app.infrastructure.rag.contracts import (
    AttestationExpectation,
    ContractCheck,
    EmbeddingIdentity,
    IndexSnapshot,
    canonical_json_bytes,
    manifest_sha256,
)
from app.infrastructure.rag.embedding_identity import fingerprint_embedding, to_json_dict


_CONTRACT_VERSION = "rag-mvp-contracts-v1.0.1"
_ATTESTATION_VERSION = "ingestion-attestation-v1"
_INTENT_VERSION = "ingestion-intent-v1"
_MANIFEST_VERSION = "ingestion-manifest-v1"
_PREPARATION_VERSION = "prepared-ingestion-v1"
_SOURCE_FORMAT = "epub"
_NORMALIZER_VERSION = "doc-norm-1"
_CHUNKING_VERSION = "chunk-policy-1"
_DOC_PROTOCOL = "doc-v1"
_CHUNK_PROTOCOL = "chunk-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RULE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_WARNING_RE = re.compile(
    r"^chunk_index=(?:0|[1-9][0-9]*) 超过 embedding 安全阈值（hard_limit），已整块保留（atomic 不切裂）$"
)
_INTENT_KEYS = frozenset(
    {
        "schema_version", "ingestion_run_id", "created_at", "target_index_id", "database_id",
        "schema_name", "source_sha256", "manifest_sha256", "embedding_fingerprint", "embedding_config",
        "preparation", "before_row_count", "resource_record_ref", "exclusivity_record_ref",
        "isolation_evidence_ref", "exclusive_target", "phase",
    }
)
_PREPARATION_KEYS = frozenset(
    {
        "schema_version", "source_sha256", "source_format", "import_namespace", "doc_id", "scope",
        "owner", "normalizer_version", "chunking_version", "doc_protocol", "chunk_protocol",
        "chunk_policy", "warnings",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_version", "ingestion_run_id", "target_index_id", "doc_id", "source_sha256",
        "embedding_fingerprint", "rows", "row_count", "manifest_sha256",
    }
)
_IDENTITY_KEYS = frozenset(
    {
        "schema_version", "service_id", "deployment_id", "model", "dimension", "parameters",
        "model_version", "version_binding",
    }
)
_ATTESTATION_KEYS = frozenset(
    {
        "schema_version", "contract_version", "status", "ingestion_run_id", "created_at",
        "source_sha256", "source_format", "import_namespace", "doc_id", "normalizer_version",
        "chunking_version", "doc_protocol", "chunk_protocol", "chunk_policy", "planned_chunk_count",
        "written_chunk_count", "failure_count", "backend", "provider", "dialect", "target_index_id",
        "scope", "owner", "embedding_config", "embedding_fingerprint", "artifact_manifest_sha256",
        "isolation_evidence_ref", "error_code", "safe_summary", "warnings",
    }
)


def _fail(rule_id: str) -> None:
    raise ValueError(rule_id) from None


def _exact_mapping(value: Any, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("types_invalid")
    actual = set(value)
    if actual - keys:
        _fail("schema_extra")
    if keys - actual:
        _fail("schema_missing")
    return value


def _string(value: Any, *, allow_empty: bool = False, rule_id: str = "types_invalid") -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        _fail(rule_id)
    return value


def _safe_ref(value: Any, rule_id: str = "types_invalid") -> str:
    text = _string(value, rule_id=rule_id)
    if "\n" in text or "\r" in text or "://" in text or re.search(
        r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+|[^/@\s:]+:[^/@\s]+@", text
    ):
        _fail(rule_id)
    return text


def _sha(value: Any, rule_id: str = "types_invalid") -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail(rule_id)
    return value


def _integer(value: Any, *, minimum: int, rule_id: str = "types_invalid") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(rule_id)
    return value


def _utc(value: Any, rule_id: str = "types_invalid") -> str:
    if not isinstance(value, str) or not value or "T" not in value:
        _fail(rule_id)
    try:
        from datetime import datetime, timedelta

        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except (ValueError, OverflowError):
        _fail(rule_id)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _fail(rule_id)
    return value


def _uuid(value: Any, rule_id: str = "types_invalid") -> str:
    if not isinstance(value, str):
        _fail(rule_id)
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        _fail(rule_id)
    return value


def _scope_owner(scope: Any, owner: Any) -> None:
    if scope == "global" and owner is None:
        return
    if scope == "private" and isinstance(owner, int) and not isinstance(owner, bool) and owner > 0:
        return
    _fail("scope_mismatch")


def _policy(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        _fail("types_invalid")
    keys = {"chunk_size", "chunk_overlap", "hard_limit"}
    actual = set(value)
    if actual - keys:
        _fail("schema_extra")
    if keys - actual:
        _fail("schema_missing")
    size = _integer(value["chunk_size"], minimum=1)
    overlap = _integer(value["chunk_overlap"], minimum=0)
    hard_limit = _integer(value["hard_limit"], minimum=1)
    if overlap >= size or hard_limit < size:
        _fail("types_invalid")
    return {"chunk_size": size, "chunk_overlap": overlap, "hard_limit": hard_limit}


def _warnings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        _fail("types_invalid")
    warnings = list(value)
    if any(not isinstance(item, str) or not _WARNING_RE.fullmatch(item) for item in warnings):
        _fail("types_invalid")
    return warnings


def _identity(value: Any) -> tuple[EmbeddingIdentity, dict[str, Any]]:
    mapping = _exact_mapping(value, _IDENTITY_KEYS)
    try:
        identity = EmbeddingIdentity(**dict(mapping))
        public_config = to_json_dict(identity)
    except (TypeError, ValueError, AttributeError):
        _fail("identity_mismatch")
    return identity, public_config


def _identity_argument(value: Any) -> tuple[EmbeddingIdentity, dict[str, Any]]:
    if not isinstance(value, EmbeddingIdentity):
        _fail("identity_mismatch")
    try:
        public_config = to_json_dict(value)
        identity = EmbeddingIdentity(**public_config)
    except (TypeError, ValueError, AttributeError):
        _fail("identity_mismatch")
    return identity, public_config


def _rows(value: Any, *, doc_id: str, scope: str, owner: int | None) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(value, (list, tuple)) or not value:
        _fail("count_mismatch")
    try:
        digest = manifest_sha256(value)
        copies = [dict(row) for row in value]
        indices: list[int] = []
        chunk_ids: set[str] = set()
        for item in copies:
            if item["doc_id"] != doc_id or item["scope"] != scope or item["owner"] != owner:
                _fail("scope_mismatch")
            if item["chunk_id"] in chunk_ids:
                _fail("count_mismatch")
            chunk_ids.add(item["chunk_id"])
            indices.append(item["chunk_index"])
        if sorted(indices) != list(range(len(copies))):
            _fail("count_mismatch")
        return copies, digest
    except (TypeError, KeyError, AttributeError):
        _fail("types_invalid")


def _multiset(rows: Sequence[Mapping[str, Any]]) -> Counter[bytes]:
    return Counter(canonical_json_bytes(row) for row in rows)


def _clone_snapshot(snapshot: Any) -> IndexSnapshot:
    if not isinstance(snapshot, IndexSnapshot):
        _fail("types_invalid")
    try:
        return IndexSnapshot(
            target_index_id=snapshot.target_index_id,
            database_id=snapshot.database_id,
            schema_name=snapshot.schema_name,
            row_count=snapshot.row_count,
            rows=snapshot.rows,
            manifest_sha256=snapshot.manifest_sha256,
        )
    except (AttributeError, TypeError, ValueError):
        _fail("types_invalid")


def _preparation(value: Any) -> dict[str, Any]:
    prep = _exact_mapping(value, _PREPARATION_KEYS)
    if prep["schema_version"] != _PREPARATION_VERSION:
        _fail("version_unsupported")
    for field in (
        "source_sha256", "source_format", "import_namespace", "doc_id", "normalizer_version",
        "chunking_version", "doc_protocol", "chunk_protocol",
    ):
        _safe_ref(prep[field])
    _sha(prep["source_sha256"])
    if prep["source_format"] != _SOURCE_FORMAT:
        _fail("source_mismatch")
    frozen_versions = {
        "normalizer_version": _NORMALIZER_VERSION,
        "chunking_version": _CHUNKING_VERSION,
        "doc_protocol": _DOC_PROTOCOL,
        "chunk_protocol": _CHUNK_PROTOCOL,
    }
    if any(prep[field] != version for field, version in frozen_versions.items()):
        _fail("version_unsupported")
    _scope_owner(prep["scope"], prep["owner"])
    policy = _policy(prep["chunk_policy"])
    warnings = _warnings(prep["warnings"])
    return {
        "schema_version": _PREPARATION_VERSION,
        "source_sha256": prep["source_sha256"],
        "source_format": prep["source_format"],
        "import_namespace": prep["import_namespace"],
        "doc_id": prep["doc_id"],
        "scope": prep["scope"],
        "owner": prep["owner"],
        "normalizer_version": prep["normalizer_version"],
        "chunking_version": prep["chunking_version"],
        "doc_protocol": prep["doc_protocol"],
        "chunk_protocol": prep["chunk_protocol"],
        "chunk_policy": policy,
        "warnings": warnings,
    }


def _intent(value: Any) -> tuple[dict[str, Any], dict[str, Any], EmbeddingIdentity, dict[str, Any]]:
    intent = _exact_mapping(value, _INTENT_KEYS)
    if intent["schema_version"] != _INTENT_VERSION:
        _fail("version_unsupported")
    _uuid(intent["ingestion_run_id"])
    _utc(intent["created_at"])
    for field in ("database_id", "schema_name"):
        _string(intent[field])
    _safe_ref(intent["target_index_id"], "target_mismatch")
    _sha(intent["source_sha256"], "source_mismatch")
    _sha(intent["manifest_sha256"], "identity_mismatch")
    _sha(intent["embedding_fingerprint"], "identity_mismatch")
    _integer(intent["before_row_count"], minimum=0)
    if intent["before_row_count"] != 0:
        _fail("isolation_unproven")
    for field in ("resource_record_ref", "exclusivity_record_ref", "isolation_evidence_ref"):
        _safe_ref(intent[field], "isolation_unproven")
    if intent["exclusive_target"] is not True or intent["phase"] != "prepared":
        _fail("isolation_unproven")
    prep = _preparation(intent["preparation"])
    identity_obj, identity_config = _identity(intent["embedding_config"])
    return dict(intent), prep, identity_obj, identity_config


def _manifest(value: Any, *, run_id: str, target: str, doc_id: str, source_sha: str, fingerprint: str,
              scope: str, owner: int | None) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    manifest = _exact_mapping(value, _MANIFEST_KEYS)
    if manifest["schema_version"] != _MANIFEST_VERSION:
        _fail("version_unsupported")
    _uuid(manifest["ingestion_run_id"])
    _safe_ref(manifest["target_index_id"], "target_mismatch")
    _safe_ref(manifest["doc_id"])
    _sha(manifest["source_sha256"])
    _sha(manifest["embedding_fingerprint"])
    _sha(manifest["manifest_sha256"])
    if manifest["row_count"] == 0:
        _fail("count_mismatch")
    _integer(manifest["row_count"], minimum=1)
    if manifest["ingestion_run_id"] != run_id or manifest["target_index_id"] != target or manifest["doc_id"] != doc_id:
        _fail("target_mismatch")
    if manifest["source_sha256"] != source_sha:
        _fail("source_mismatch")
    if manifest["embedding_fingerprint"] != fingerprint:
        _fail("identity_mismatch")
    rows, actual_digest = _rows(manifest["rows"], doc_id=doc_id, scope=scope, owner=owner)
    if manifest["row_count"] != len(rows):
        _fail("count_mismatch")
    if manifest["manifest_sha256"] != actual_digest:
        _fail("identity_mismatch")
    return dict(manifest), rows, actual_digest


def _build_attestation(
    *, intent: Any, manifest: Any, result: Any, snapshot: Any, identity: Any, verified_at: Any
) -> dict[str, Any]:
    intent_value, prep, intent_identity, intent_config = _intent(intent)
    supplied_identity, supplied_config = _identity_argument(identity)
    if intent_config != supplied_config or intent_identity != supplied_identity:
        _fail("identity_mismatch")
    try:
        fingerprint = fingerprint_embedding(supplied_identity)
    except ValueError:
        _fail("identity_mismatch")
    if fingerprint != intent_value["embedding_fingerprint"]:
        _fail("identity_mismatch")
    if prep["source_sha256"] != intent_value["source_sha256"]:
        _fail("source_mismatch")
    if prep["scope"] not in {"global", "private"}:
        _fail("scope_mismatch")
    manifest_value, planned_rows, actual_manifest_sha = _manifest(
        manifest,
        run_id=intent_value["ingestion_run_id"],
        target=intent_value["target_index_id"],
        doc_id=prep["doc_id"],
        source_sha=intent_value["source_sha256"],
        fingerprint=fingerprint,
        scope=prep["scope"],
        owner=prep["owner"],
    )
    if intent_value["manifest_sha256"] != actual_manifest_sha:
        _fail("identity_mismatch")
    actual_snapshot = _clone_snapshot(snapshot)
    if actual_snapshot.target_index_id != intent_value["target_index_id"]:
        _fail("target_mismatch")
    if actual_snapshot.database_id != intent_value["database_id"] or actual_snapshot.schema_name != intent_value["schema_name"]:
        _fail("target_mismatch")
    if actual_snapshot.row_count <= 0 or actual_snapshot.row_count != manifest_value["row_count"]:
        _fail("count_mismatch")
    if actual_snapshot.manifest_sha256 != actual_manifest_sha:
        _fail("identity_mismatch")
    if _multiset(actual_snapshot.rows) != _multiset(planned_rows):
        _fail("identity_mismatch")
    if not isinstance(result, IngestResult):
        _fail("types_invalid")
    if result.status != "ok" or result.doc_id != prep["doc_id"]:
        _fail("count_mismatch")
    _integer(result.planned_chunk_count, minimum=1)
    _integer(result.written_chunk_count, minimum=1)
    if result.planned_chunk_count != actual_snapshot.row_count or result.written_chunk_count != actual_snapshot.row_count:
        _fail("count_mismatch")
    prep_warnings = prep["warnings"]
    result_warnings = _warnings(result.warnings)
    if result_warnings != prep_warnings:
        _fail("types_invalid")
    _utc(verified_at)
    output = {
        "schema_version": _ATTESTATION_VERSION,
        "contract_version": _CONTRACT_VERSION,
        "status": "ok",
        "ingestion_run_id": intent_value["ingestion_run_id"],
        "created_at": verified_at,
        "source_sha256": intent_value["source_sha256"],
        "source_format": prep["source_format"],
        "import_namespace": prep["import_namespace"],
        "doc_id": prep["doc_id"],
        "normalizer_version": prep["normalizer_version"],
        "chunking_version": prep["chunking_version"],
        "doc_protocol": prep["doc_protocol"],
        "chunk_protocol": prep["chunk_protocol"],
        "chunk_policy": dict(prep["chunk_policy"]),
        "planned_chunk_count": actual_snapshot.row_count,
        "written_chunk_count": actual_snapshot.row_count,
        "failure_count": 0,
        "backend": "pgvector",
        "provider": "PgVectorProvider",
        "dialect": "postgresql",
        "target_index_id": actual_snapshot.target_index_id,
        "scope": prep["scope"],
        "owner": prep["owner"],
        "embedding_config": intent_config,
        "embedding_fingerprint": fingerprint,
        "artifact_manifest_sha256": actual_snapshot.manifest_sha256,
        "isolation_evidence_ref": intent_value["isolation_evidence_ref"],
        "error_code": None,
        "safe_summary": "摄入已核验",
        "warnings": list(prep_warnings),
    }
    return output


def build_attestation(
    *,
    intent: dict[str, Any],
    manifest: dict[str, Any],
    result: IngestResult,
    snapshot: IndexSnapshot,
    identity: EmbeddingIdentity,
    verified_at: str,
) -> dict[str, Any]:
    """Build a complete success proof after cross-checking plan, result, and snapshot."""
    try:
        return _build_attestation(
            intent=intent, manifest=manifest, result=result, snapshot=snapshot,
            identity=identity, verified_at=verified_at,
        )
    except ValueError as exc:
        rule_id = str(exc)
        if _RULE_ID_RE.fullmatch(rule_id):
            raise ValueError(rule_id) from None
        raise ValueError("types_invalid") from None
    except Exception:
        raise ValueError("types_invalid") from None


def _validate_policy_value(value: Any, failures: list[str]) -> None:
    try:
        _policy(value)
    except ValueError as exc:
        failures.append(str(exc))


def _validate_proof_identity(value: Any, self_fingerprint: Any, expected: Any, failures: list[str]) -> None:
    try:
        parsed, config = _identity(value)
        calculated = fingerprint_embedding(parsed)
        _sha(self_fingerprint, "identity_mismatch")
        if calculated != self_fingerprint:
            failures.append("identity_mismatch")
        if calculated != expected.expected_embedding_fingerprint:
            failures.append("identity_mismatch")
        if config != to_json_dict(parsed):
            failures.append("identity_mismatch")
    except (AttributeError, TypeError, ValueError):
        failures.append("identity_mismatch")


def _validate_snapshot(snapshot: Any, failures: list[str]) -> IndexSnapshot | None:
    try:
        return _clone_snapshot(snapshot)
    except (TypeError, ValueError, AttributeError):
        failures.append("types_invalid")
        return None


def _validate_isolation(expected: Any, proof: Mapping[str, Any], snapshot: IndexSnapshot | None,
                        failures: list[str]) -> None:
    try:
        if not isinstance(expected, AttestationExpectation):
            failures.append("isolation_unproven")
            return
        evidence = expected.isolation_evidence
        if set(evidence) != {"mode", "target_index_id", "manifest_sha256", "row_count", "verified_at", "resource_record_ref"}:
            failures.append("isolation_unproven")
            return
        if evidence["mode"] != "isolated_db":
            failures.append("isolation_unproven")
        if evidence["target_index_id"] != expected.expected_target_index_id:
            failures.append("isolation_unproven")
        if evidence["target_index_id"] != proof.get("target_index_id"):
            failures.append("isolation_unproven")
        if evidence["manifest_sha256"] != expected.expected_manifest_sha256:
            failures.append("isolation_unproven")
        if evidence["manifest_sha256"] != proof.get("artifact_manifest_sha256"):
            failures.append("isolation_unproven")
        _integer(evidence["row_count"], minimum=1, rule_id="isolation_unproven")
        _utc(evidence["verified_at"], "isolation_unproven")
        if evidence["verified_at"] != proof.get("created_at"):
            failures.append("isolation_unproven")
        _safe_ref(evidence["resource_record_ref"], "isolation_unproven")
        if proof.get("planned_chunk_count") != evidence["row_count"]:
            failures.append("isolation_unproven")
        if snapshot is not None and evidence["row_count"] != snapshot.row_count:
            failures.append("isolation_unproven")
        _safe_ref(proof.get("isolation_evidence_ref"), "isolation_unproven")
    except (AttributeError, KeyError, TypeError, ValueError):
        failures.append("isolation_unproven")


def _validate_attestation(attestation: Any, *, expected: Any, snapshot: Any) -> ContractCheck:
    failures: list[str] = []
    if not isinstance(attestation, dict):
        return ContractCheck(False, ("types_invalid",))
    keys = set(attestation)
    if keys - _ATTESTATION_KEYS:
        failures.append("schema_extra")
    if _ATTESTATION_KEYS - keys:
        failures.append("schema_missing")
    actual_snapshot = _validate_snapshot(snapshot, failures)
    if not isinstance(expected, AttestationExpectation):
        failures.append("types_invalid")
    for field, fixed in (
        ("schema_version", _ATTESTATION_VERSION),
        ("contract_version", _CONTRACT_VERSION),
        ("status", "ok"),
    ):
        value = attestation.get(field)
        if not isinstance(value, str) or value != fixed:
            failures.append("version_unsupported")
    try:
        _uuid(attestation.get("ingestion_run_id"))
        _utc(attestation.get("created_at"))
    except ValueError:
        failures.append("types_invalid")
    try:
        _sha(attestation.get("source_sha256"), "source_mismatch")
        if expected is not None and attestation.get("source_sha256") != expected.expected_source_sha256:
            failures.append("source_mismatch")
    except (AttributeError, ValueError):
        failures.append("source_mismatch")
    for field in (
        "source_format", "import_namespace", "doc_id", "normalizer_version", "chunking_version",
        "doc_protocol", "chunk_protocol", "backend", "provider", "dialect", "target_index_id",
        "safe_summary",
    ):
        try:
            _safe_ref(attestation.get(field))
        except ValueError:
            failures.append("types_invalid")
    if attestation.get("backend") != "pgvector" or attestation.get("provider") != "PgVectorProvider" or attestation.get("dialect") != "postgresql":
        failures.append("version_unsupported")
    if attestation.get("safe_summary") != "摄入已核验":
        failures.append("types_invalid")
    if attestation.get("source_format") != _SOURCE_FORMAT:
        failures.append("source_mismatch")
    frozen_versions = {
        "normalizer_version": _NORMALIZER_VERSION,
        "chunking_version": _CHUNKING_VERSION,
        "doc_protocol": _DOC_PROTOCOL,
        "chunk_protocol": _CHUNK_PROTOCOL,
    }
    if any(attestation.get(field) != version for field, version in frozen_versions.items()):
        failures.append("version_unsupported")
    _validate_policy_value(attestation.get("chunk_policy"), failures)
    if expected is not None:
        target = attestation.get("target_index_id")
        if target != expected.expected_target_index_id or (actual_snapshot and target != actual_snapshot.target_index_id):
            failures.append("target_mismatch")
    if actual_snapshot is not None:
        if actual_snapshot.row_count <= 0:
            failures.append("count_mismatch")
        try:
            if manifest_sha256(actual_snapshot.rows) != actual_snapshot.manifest_sha256:
                failures.append("identity_mismatch")
        except (TypeError, ValueError):
            failures.append("identity_mismatch")
        if attestation.get("artifact_manifest_sha256") != actual_snapshot.manifest_sha256:
            failures.append("identity_mismatch")
    try:
        manifest_digest = _sha(attestation.get("artifact_manifest_sha256"), "identity_mismatch")
        if expected is not None and manifest_digest != expected.expected_manifest_sha256:
            failures.append("identity_mismatch")
    except ValueError:
        failures.append("identity_mismatch")
    _validate_proof_identity(
        attestation.get("embedding_config"), attestation.get("embedding_fingerprint"), expected, failures
    )
    for field in ("planned_chunk_count", "written_chunk_count", "failure_count"):
        try:
            _integer(attestation.get(field), minimum=0 if field == "failure_count" else 1, rule_id="count_mismatch")
        except ValueError:
            failures.append("count_mismatch")
    if attestation.get("failure_count") != 0 or attestation.get("planned_chunk_count") != attestation.get("written_chunk_count"):
        failures.append("count_mismatch")
    if actual_snapshot is not None and (
        attestation.get("planned_chunk_count") != actual_snapshot.row_count
        or attestation.get("written_chunk_count") != actual_snapshot.row_count
    ):
        failures.append("count_mismatch")
    try:
        _scope_owner(attestation.get("scope"), attestation.get("owner"))
        if expected is not None and (
            attestation.get("scope") != expected.expected_scope or attestation.get("owner") != expected.expected_owner
        ):
            failures.append("scope_mismatch")
        if actual_snapshot is not None:
            for row_value in actual_snapshot.rows:
                if row_value["scope"] != attestation.get("scope") or row_value["owner"] != attestation.get("owner"):
                    failures.append("scope_mismatch")
            _rows(actual_snapshot.rows, doc_id=attestation.get("doc_id"),
                  scope=attestation.get("scope"), owner=attestation.get("owner"))
    except (KeyError, TypeError, ValueError):
        failures.append("scope_mismatch")
    if attestation.get("error_code") is not None:
        failures.append("types_invalid")
    try:
        _warnings(attestation.get("warnings"))
    except ValueError:
        failures.append("types_invalid")
    _validate_isolation(expected, attestation, actual_snapshot, failures)
    return ContractCheck(not failures, tuple(failures))


def validate_attestation(
    attestation: dict[str, Any], *, expected: AttestationExpectation, snapshot: IndexSnapshot
) -> ContractCheck:
    """Validate proof against independent expectations and the supplied full snapshot."""
    try:
        return _validate_attestation(attestation, expected=expected, snapshot=snapshot)
    except Exception:
        return ContractCheck(False, ("types_invalid",))
