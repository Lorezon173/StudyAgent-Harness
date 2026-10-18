from __future__ import annotations

import builtins
import copy
import hashlib
import io
import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from app.core.config import settings
from app.harness.knowledge_ingestion import IngestResult
from app.infrastructure.rag.contracts import (
    AttestationExpectation,
    EmbeddingIdentity,
    IndexSnapshot,
    canonical_json_bytes,
    manifest_sha256,
)
from app.infrastructure.rag.embedding import EmbeddingService
from app.infrastructure.rag.embedding_identity import fingerprint_embedding, to_json_dict
from app.infrastructure.rag.pgvector_provider import PgVectorProvider
from app.harness.ingestion_attestation import build_attestation, validate_attestation


RUN_ID = "00000000-0000-4000-8000-000000000004"
VERIFIED_AT = "2026-10-16T00:00:00Z"
SOURCE_SHA = "1a89e8c34a455cfadab9c5730f68a2669a3ac1db4f8b490065353e261f2cb6e8"
IDENTITY_SHA = "005a79e156e97b05af18abadbadeda7c40bab8418a0152e7f36ee08b19aa798a"
ROW_SHA = "77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a"
MANIFEST_SHA = "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
TARGET = "rag-t04-fixture"
WARNING = "chunk_index=0 超过 embedding 安全阈值（hard_limit），已整块保留（atomic 不切裂）"


@pytest.fixture(autouse=True)
def offline_pgvector_boundary(monkeypatch):
    calls = {"sdk_factory": 0, "embeddings_create": 0, "embed_one": 0, "embed_many": 0,
             "sync_engine": 0, "async_engine": 0, "provider_connection": 0}

    def trap(name):
        def fail(*args, **kwargs):
            calls[name] += 1
            raise AssertionError(f"offline boundary: {name}")
        return fail

    def sdk_factory(*, api_key, base_url):
        calls["sdk_factory"] += 1
        return SimpleNamespace(base_url=base_url, embeddings=SimpleNamespace(create=trap("embeddings_create")))

    monkeypatch.setattr(settings, "rag_backend", "pgvector")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=sdk_factory))
    monkeypatch.setattr(EmbeddingService, "embed_one", trap("embed_one"))
    monkeypatch.setattr(EmbeddingService, "embed_many", trap("embed_many"))
    import sqlalchemy
    import sqlalchemy.ext.asyncio
    monkeypatch.setattr(sqlalchemy, "create_engine", trap("sync_engine"))
    monkeypatch.setattr(sqlalchemy.ext.asyncio, "create_async_engine", trap("async_engine"))
    monkeypatch.setattr(PgVectorProvider, "_get_conn", trap("provider_connection"))
    yield calls
    assert calls["embeddings_create"] == 0
    assert calls["embed_one"] == 0
    assert calls["embed_many"] == 0
    assert calls["sync_engine"] == 0
    assert calls["async_engine"] == 0
    assert calls["provider_connection"] == 0


def identity(*, model="model-a", service_id="svc-public", deployment_id=None,
             model_version=None, parameters=None):
    return EmbeddingIdentity(
        schema_version="embedding-identity-v1", service_id=service_id,
        deployment_id=deployment_id, model=model, dimension=2,
        parameters=parameters or {"dimensions": "service_default", "encoding_format": "service_default"},
        model_version=model_version,
        version_binding="pinned" if model_version is not None else "alias_unpinned",
    )


def row(*, scope="global", owner=None, chunk_id="chunk-0", chunk_index=0, doc_id="doc-fixture"):
    return {
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "content_sha256": ROW_SHA,
        "doc_id": doc_id,
        "owner": owner,
        "scope": scope,
        "source_locator": {"paragraph": chunk_index},
    }


def bundle(*, scope="global", owner=None, warnings=None, use_fixed_digest=True, identity_parameters=None):
    warnings = [] if warnings is None else list(warnings)
    rows = [row(scope=scope, owner=owner)]
    row_digest = MANIFEST_SHA if use_fixed_digest and scope == "global" and owner is None and rows[0] == row() else manifest_sha256(rows)
    config = identity(parameters=identity_parameters)
    identity_fingerprint = fingerprint_embedding(config)
    prep = {
        "schema_version": "prepared-ingestion-v1",
        "source_sha256": SOURCE_SHA,
        "source_format": "epub",
        "import_namespace": "fixture-book",
        "doc_id": "doc-fixture",
        "scope": scope,
        "owner": owner,
        "normalizer_version": "doc-norm-1",
        "chunking_version": "chunk-policy-1",
        "doc_protocol": "doc-v1",
        "chunk_protocol": "chunk-v1",
        "chunk_policy": {"chunk_size": 500, "chunk_overlap": 50, "hard_limit": 8192},
        "warnings": warnings,
    }
    intent = {
        "schema_version": "ingestion-intent-v1",
        "ingestion_run_id": RUN_ID,
        "created_at": "2026-10-15T23:00:00Z",
        "target_index_id": TARGET,
        "database_id": "rag_fixture",
        "schema_name": "public",
        "source_sha256": SOURCE_SHA,
        "manifest_sha256": row_digest,
        "embedding_fingerprint": identity_fingerprint,
        "embedding_config": to_json_dict(config),
        "preparation": prep,
        "before_row_count": 0,
        "resource_record_ref": "fixture/resources/t04",
        "exclusivity_record_ref": "fixture/leases/t04",
        "isolation_evidence_ref": "fixture/run-t04/isolation-evidence.json",
        "exclusive_target": True,
        "phase": "prepared",
    }
    manifest = {
        "schema_version": "ingestion-manifest-v1",
        "ingestion_run_id": RUN_ID,
        "target_index_id": TARGET,
        "doc_id": "doc-fixture",
        "source_sha256": SOURCE_SHA,
        "embedding_fingerprint": identity_fingerprint,
        "rows": rows,
        "row_count": 1,
        "manifest_sha256": row_digest,
    }
    snapshot = IndexSnapshot(
        target_index_id=TARGET,
        database_id="rag_fixture",
        schema_name="public",
        row_count=1,
        rows=rows,
        manifest_sha256=row_digest,
    )
    result = IngestResult(
        status="ok", doc_id="doc-fixture", planned_chunk_count=1,
        written_chunk_count=1, warnings=warnings,
    )
    isolation = {
        "mode": "isolated_db",
        "target_index_id": TARGET,
        "manifest_sha256": row_digest,
        "row_count": 1,
        "verified_at": VERIFIED_AT,
        "resource_record_ref": "fixture/resources/t04",
    }
    expected = AttestationExpectation(
        expected_source_sha256=SOURCE_SHA,
        expected_target_index_id=TARGET,
        expected_embedding_fingerprint=identity_fingerprint,
        expected_manifest_sha256=row_digest,
        expected_scope=scope,
        expected_owner=owner,
        isolation_evidence=isolation,
    )
    return {"intent": intent, "manifest": manifest, "result": result, "snapshot": snapshot,
            "identity": config, "verified_at": VERIFIED_AT, "expected": expected, "isolation": isolation}


def build(bundle_value):
    return build_attestation(
        intent=bundle_value["intent"], manifest=bundle_value["manifest"],
        result=bundle_value["result"], snapshot=bundle_value["snapshot"],
        identity=bundle_value["identity"], verified_at=bundle_value["verified_at"],
    )


def test_build_and_validate_return_exact_success_contract_using_new_verification_time():
    values = bundle()
    intent_before = copy.deepcopy(values["intent"])
    manifest_before = copy.deepcopy(values["manifest"])
    result_warnings_before = list(values["result"].warnings)
    attestation = build(values)

    assert set(attestation) == {
        "schema_version", "contract_version", "status", "ingestion_run_id", "created_at",
        "source_sha256", "source_format", "import_namespace", "doc_id", "normalizer_version",
        "chunking_version", "doc_protocol", "chunk_protocol", "chunk_policy", "planned_chunk_count",
        "written_chunk_count", "failure_count", "backend", "provider", "dialect", "target_index_id",
        "scope", "owner", "embedding_config", "embedding_fingerprint", "artifact_manifest_sha256",
        "isolation_evidence_ref", "error_code", "safe_summary", "warnings",
    }
    assert attestation["schema_version"] == "ingestion-attestation-v1"
    assert attestation["contract_version"] == "rag-mvp-contracts-v1.0.1"
    assert attestation["status"] == "ok"
    assert attestation["ingestion_run_id"] == RUN_ID
    assert attestation["created_at"] == VERIFIED_AT
    assert attestation["created_at"] != values["intent"]["created_at"]
    assert attestation["chunking_version"] == "chunk-policy-1"
    assert attestation["chunk_protocol"] == "chunk-v1"
    assert attestation["backend"] == "pgvector"
    assert attestation["provider"] == "PgVectorProvider"
    assert attestation["dialect"] == "postgresql"
    assert attestation["embedding_fingerprint"] == IDENTITY_SHA
    assert attestation["artifact_manifest_sha256"] == MANIFEST_SHA
    assert validate_attestation(attestation, expected=values["expected"], snapshot=values["snapshot"]).allowed
    assert values["intent"] == intent_before
    assert values["manifest"] == manifest_before
    assert values["result"].warnings == result_warnings_before
    assert build(values) == attestation


def test_build_preserves_unfixed_namespace_but_rejects_unfrozen_preparation_versions():
    values = bundle()
    preparation = values["intent"]["preparation"]
    preparation["import_namespace"] = "other-book"

    proof = build(values)

    assert proof["import_namespace"] == "other-book"
    assert validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed


@pytest.mark.parametrize(("field", "bad_value"), [
    ("source_format", "pdf"),
    ("normalizer_version", "other-normalizer"),
    ("chunking_version", "other-chunk-policy"),
    ("doc_protocol", "doc-v2"),
    ("chunk_protocol", "chunk-v2"),
])
def test_build_rejects_preparation_values_outside_frozen_b1(field, bad_value):
    values = bundle()
    values["intent"]["preparation"][field] = bad_value

    with pytest.raises(ValueError) as exc:
        build(values)

    assert re_safe_rule_id(str(exc.value))


@pytest.mark.parametrize("encoding_format", ["float", "base64"])
def test_build_and_validate_accept_supported_explicit_encoding_formats(encoding_format):
    values = bundle(identity_parameters={"dimensions": "service_default", "encoding_format": encoding_format})

    proof = build(values)

    assert proof["embedding_config"]["parameters"]["encoding_format"] == encoding_format
    assert validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed


def test_build_and_validate_reject_secret_like_encoding_format_without_echoing_it():
    values = bundle()
    unsafe_config = dict(values["intent"]["embedding_config"])
    unsafe_parameters = dict(unsafe_config["parameters"])
    unsafe_parameters["encoding_format"] = "api_key=FAKE_SECRET"
    unsafe_config["parameters"] = unsafe_parameters
    unsafe_digest = hashlib.sha256(canonical_json_bytes(unsafe_config)).hexdigest()
    values["intent"]["embedding_config"] = unsafe_config
    values["intent"]["embedding_fingerprint"] = unsafe_digest
    values["manifest"]["embedding_fingerprint"] = unsafe_digest
    object.__setattr__(values["identity"], "parameters", unsafe_parameters)
    with pytest.raises(ValueError) as exc:
        build(values)
    assert "FAKE_SECRET" not in str(exc.value)

    values = bundle()
    proof = build(values)
    unsafe_config = dict(proof["embedding_config"])
    unsafe_parameters = dict(unsafe_config["parameters"])
    unsafe_parameters["encoding_format"] = "https://user:FAKE_SECRET@example.test"
    unsafe_config["parameters"] = unsafe_parameters
    unsafe_digest = hashlib.sha256(canonical_json_bytes(unsafe_config)).hexdigest()
    proof["embedding_config"] = unsafe_config
    proof["embedding_fingerprint"] = unsafe_digest
    expected = AttestationExpectation(
        expected_source_sha256=values["expected"].expected_source_sha256,
        expected_target_index_id=values["expected"].expected_target_index_id,
        expected_embedding_fingerprint=unsafe_digest,
        expected_manifest_sha256=values["expected"].expected_manifest_sha256,
        expected_scope=values["expected"].expected_scope,
        expected_owner=values["expected"].expected_owner,
        isolation_evidence=values["isolation"],
    )
    checked = validate_attestation(proof, expected=expected, snapshot=values["snapshot"])

    assert not checked.allowed
    assert "identity_mismatch" in checked.failures
    assert "FAKE_SECRET" not in repr(checked)


def test_build_rejects_secret_like_target_even_when_all_target_sources_agree():
    values = bundle()
    unsafe_target = "https://user:FAKE_SECRET@example.invalid/rag"
    values["intent"]["target_index_id"] = unsafe_target
    values["manifest"]["target_index_id"] = unsafe_target
    object.__setattr__(values["snapshot"], "target_index_id", unsafe_target)

    with pytest.raises(ValueError) as exc:
        build(values)

    assert re_safe_rule_id(str(exc.value))
    assert "FAKE_SECRET" not in str(exc.value)


def test_private_owner_and_known_oversized_warning_are_valid_success_cases():
    private = bundle(scope="private", owner=7, use_fixed_digest=False)
    proof = build(private)
    assert proof["scope"] == "private"
    assert proof["owner"] == 7
    assert validate_attestation(proof, expected=private["expected"], snapshot=private["snapshot"]).allowed

    oversized = bundle(warnings=[WARNING])
    warning_proof = build(oversized)
    assert warning_proof["warnings"] == [WARNING]
    assert validate_attestation(warning_proof, expected=oversized["expected"], snapshot=oversized["snapshot"]).allowed


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_intent_field", "extra_intent_field", "intent_version", "before_row_count",
        "exclusive_target", "missing_lock_ref", "missing_isolation_ref", "preparation_version",
        "preparation_extra", "policy_size_zero", "policy_overlap_equal_size", "policy_hard_limit_small",
        "policy_boolean", "manifest_version", "manifest_extra", "manifest_run_id", "manifest_target",
        "manifest_doc", "manifest_source", "manifest_identity", "manifest_count_zero", "manifest_digest",
        "row_order", "row_duplicate", "identity_model", "identity_fingerprint", "identity_dimension",
        "snapshot_target", "snapshot_database", "snapshot_schema", "result_failed", "result_doc",
        "result_planned_zero", "result_written_mismatch", "result_boolean_count", "warnings_mismatch",
        "warning_secret", "verified_at_missing", "verified_at_invalid", "verified_at_non_utc",
    ],
)
def test_build_rejects_each_single_field_contract_violation(mutation):
    values = bundle()
    if mutation == "missing_intent_field":
        del values["intent"]["phase"]
    elif mutation == "extra_intent_field":
        values["intent"]["unexpected"] = "x"
    elif mutation == "intent_version":
        values["intent"]["schema_version"] = "ingestion-intent-v0"
    elif mutation == "before_row_count":
        values["intent"]["before_row_count"] = 1
    elif mutation == "exclusive_target":
        values["intent"]["exclusive_target"] = False
    elif mutation == "missing_lock_ref":
        values["intent"]["exclusivity_record_ref"] = ""
    elif mutation == "missing_isolation_ref":
        values["intent"]["isolation_evidence_ref"] = None
    elif mutation == "preparation_version":
        values["intent"]["preparation"]["schema_version"] = "prepared-ingestion-v0"
    elif mutation == "preparation_extra":
        values["intent"]["preparation"]["extra"] = True
    elif mutation == "policy_size_zero":
        values["intent"]["preparation"]["chunk_policy"]["chunk_size"] = 0
    elif mutation == "policy_overlap_equal_size":
        values["intent"]["preparation"]["chunk_policy"]["chunk_overlap"] = 500
    elif mutation == "policy_hard_limit_small":
        values["intent"]["preparation"]["chunk_policy"]["hard_limit"] = 499
    elif mutation == "policy_boolean":
        values["intent"]["preparation"]["chunk_policy"]["chunk_size"] = True
    elif mutation == "manifest_version":
        values["manifest"]["schema_version"] = "ingestion-manifest-v0"
    elif mutation == "manifest_extra":
        values["manifest"]["extra"] = 1
    elif mutation == "manifest_run_id":
        values["manifest"]["ingestion_run_id"] = "run-1"
    elif mutation == "manifest_target":
        values["manifest"]["target_index_id"] = "other-target"
    elif mutation == "manifest_doc":
        values["manifest"]["doc_id"] = "other-doc"
    elif mutation == "manifest_source":
        values["manifest"]["source_sha256"] = "0" * 64
    elif mutation == "manifest_identity":
        values["manifest"]["embedding_fingerprint"] = "0" * 64
    elif mutation == "manifest_count_zero":
        values["manifest"]["row_count"] = 0
    elif mutation == "manifest_digest":
        values["manifest"]["manifest_sha256"] = "0" * 64
    elif mutation == "row_order":
        values["manifest"]["rows"] = [{**values["manifest"]["rows"][0], "chunk_index": 1}]
    elif mutation == "row_duplicate":
        values["manifest"]["rows"] = [values["manifest"]["rows"][0], values["manifest"]["rows"][0]]
        values["manifest"]["row_count"] = 2
    elif mutation == "identity_model":
        values["identity"] = identity(model="model-b")
    elif mutation == "identity_fingerprint":
        values["intent"]["embedding_fingerprint"] = "0" * 64
    elif mutation == "identity_dimension":
        values["identity"] = identity()
        object.__setattr__(values["identity"], "dimension", 3)
    elif mutation == "snapshot_target":
        values["snapshot"] = IndexSnapshot(
            target_index_id="other-target", database_id="rag_fixture", schema_name="public", row_count=1,
            rows=[row()], manifest_sha256=MANIFEST_SHA,
        )
    elif mutation == "snapshot_database":
        values["snapshot"] = IndexSnapshot(
            target_index_id=TARGET, database_id="other-db", schema_name="public", row_count=1,
            rows=[row()], manifest_sha256=MANIFEST_SHA,
        )
    elif mutation == "snapshot_schema":
        values["snapshot"] = IndexSnapshot(
            target_index_id=TARGET, database_id="rag_fixture", schema_name="other-schema", row_count=1,
            rows=[row()], manifest_sha256=MANIFEST_SHA,
        )
    elif mutation == "result_failed":
        values["result"] = IngestResult(status="db_error", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=1)
    elif mutation == "result_doc":
        values["result"] = IngestResult(status="ok", doc_id="other-doc", planned_chunk_count=1, written_chunk_count=1)
    elif mutation == "result_planned_zero":
        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=0, written_chunk_count=0)
    elif mutation == "result_written_mismatch":
        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=2)
    elif mutation == "result_boolean_count":
        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=True, written_chunk_count=True)
    elif mutation == "warnings_mismatch":
        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=1, warnings=[WARNING])
    elif mutation == "warning_secret":
        values["intent"]["preparation"]["warnings"] = ["api_key=FAKE_SECRET"]
        values["result"] = IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=1, warnings=["api_key=FAKE_SECRET"])
    elif mutation == "verified_at_missing":
        values["verified_at"] = None
    elif mutation == "verified_at_invalid":
        values["verified_at"] = "yesterday"
    elif mutation == "verified_at_non_utc":
        values["verified_at"] = "2026-10-16T09:00:00+09:00"

    with pytest.raises(ValueError) as exc:
        build(values)
    assert re_safe_rule_id(str(exc.value))
    assert "FAKE_SECRET" not in str(exc.value)


def re_safe_rule_id(value):
    import re
    return re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) is not None


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("source_sha256", "0" * 64), ("source_format", "pdf"),
        ("doc_id", "other-doc"),
        ("normalizer_version", "other-normalizer"), ("chunking_version", "other-chunk-policy"),
        ("doc_protocol", "chunk-v1"), ("chunk_protocol", "doc-v1"), ("target_index_id", "other-target"),
        ("scope", "private"), ("owner", 7), ("planned_chunk_count", 0),
        ("written_chunk_count", 0), ("failure_count", 1), ("backend", "fake"),
        ("provider", "OtherProvider"), ("dialect", "sqlite"),
        ("artifact_manifest_sha256", "0" * 64), ("isolation_evidence_ref", ""),
        ("error_code", "db_error"), ("safe_summary", "api_key=FAKE_SECRET"),
    ],
)
def test_validator_rejects_individual_proof_field_mismatches(field, bad_value):
    values = bundle()
    proof = build(values)
    proof[field] = bad_value

    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
    assert checked.allowed is False
    assert checked.failures
    assert all(re_safe_rule_id(rule) for rule in checked.failures)
    assert "FAKE_SECRET" not in repr(checked)


@pytest.mark.parametrize("key", [
    "schema_version", "contract_version", "status", "ingestion_run_id", "created_at", "source_sha256",
    "source_format", "import_namespace", "doc_id", "normalizer_version", "chunking_version",
    "doc_protocol", "chunk_protocol", "chunk_policy", "planned_chunk_count", "written_chunk_count",
    "failure_count", "backend", "provider", "dialect", "target_index_id", "scope", "owner",
    "embedding_config", "embedding_fingerprint", "artifact_manifest_sha256", "isolation_evidence_ref",
    "error_code", "safe_summary", "warnings",
])
def test_validator_rejects_each_missing_top_level_field(key):
    values = bundle()
    proof = build(values)
    del proof[key]

    check = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
    assert not check.allowed
    assert "schema_missing" in check.failures


@pytest.mark.parametrize("extra", ["unexpected", "verified", "provenance_filter"])
def test_validator_rejects_legacy_or_unfrozen_extra_fields(extra):
    values = bundle()
    proof = build(values)
    proof[extra] = True

    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
    assert not checked.allowed
    assert "schema_extra" in checked.failures


@pytest.mark.parametrize("field", [
    "schema_version", "contract_version", "status", "ingestion_run_id", "created_at", "source_sha256",
    "source_format", "import_namespace", "doc_id", "normalizer_version", "chunking_version",
    "doc_protocol", "chunk_protocol", "chunk_policy", "planned_chunk_count", "written_chunk_count",
    "failure_count", "backend", "provider", "dialect", "target_index_id", "scope", "embedding_config",
    "embedding_fingerprint", "artifact_manifest_sha256", "isolation_evidence_ref", "safe_summary", "warnings",
])
def test_validator_rejects_null_in_every_non_nullable_top_level_field(field):
    values = bundle()
    proof = build(values)
    proof[field] = None

    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
    assert not checked.allowed
    assert checked.failures


@pytest.mark.parametrize(
    "policy",
    [
        {"chunk_size": 0, "chunk_overlap": 0, "hard_limit": 8192},
        {"chunk_size": 500, "chunk_overlap": -1, "hard_limit": 8192},
        {"chunk_size": 500, "chunk_overlap": 500, "hard_limit": 8192},
        {"chunk_size": 500, "chunk_overlap": 50, "hard_limit": 499},
        {"chunk_size": True, "chunk_overlap": 50, "hard_limit": 8192},
        {"chunk_size": 500, "chunk_overlap": False, "hard_limit": 8192},
        {"chunk_size": 500, "chunk_overlap": 50, "hard_limit": True},
        {"chunk_size": 500, "chunk_overlap": 50, "hard_limit": 8192, "extra": 1},
    ],
)
def test_validator_rejects_invalid_or_extra_policy_fields(policy):
    values = bundle()
    proof = build(values)
    proof["chunk_policy"] = policy

    assert not validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed


def test_validator_accepts_zero_overlap_and_rejects_identity_that_is_self_consistent_but_not_expected():
    values = bundle()
    proof = build(values)
    proof["chunk_policy"]["chunk_overlap"] = 0
    assert validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed

    changed = identity(model="same-dimension-other-model")
    proof["embedding_config"] = to_json_dict(changed)
    proof["embedding_fingerprint"] = fingerprint_embedding(changed)
    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
    assert not checked.allowed
    assert "identity_mismatch" in checked.failures


@pytest.mark.parametrize("changed", [
    {"model": "model-b"}, {"service_id": "svc-other"}, {"deployment_id": "deploy-b"},
    {"parameters": {"dimensions": 3, "encoding_format": "service_default"}},
    {"model_version": "release/v2", "version_binding": "pinned"},
])
def test_validator_rejects_all_semantic_identity_changes_even_with_recomputed_fingerprint(changed):
    values = bundle()
    proof = build(values)
    config = to_json_dict(values["identity"])
    config.update(changed)
    altered = identity(
        model=config["model"], service_id=config["service_id"], deployment_id=config["deployment_id"],
        model_version=config["model_version"], parameters=config["parameters"],
    )
    proof["embedding_config"] = to_json_dict(altered)
    proof["embedding_fingerprint"] = fingerprint_embedding(altered)

    check = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
    assert not check.allowed
    assert "identity_mismatch" in check.failures


@pytest.mark.parametrize("bad_value", [True, 1.0, -1, None, "1"])
def test_validator_rejects_boolean_float_negative_or_null_counts(bad_value):
    values = bundle()
    proof = build(values)
    proof["planned_chunk_count"] = bad_value

    assert not validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed


@pytest.mark.parametrize("owner", [None, 0, -1, True, 1.5, "7"])
def test_validator_rejects_private_scope_without_a_positive_non_boolean_owner(owner):
    values = bundle()
    proof = build(values)
    proof["scope"] = "private"
    proof["owner"] = owner

    assert not validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed


def test_validator_rejects_global_scope_with_owner_and_expected_context_drift():
    values = bundle()
    proof = build(values)
    proof["owner"] = 7
    assert not validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed

    for field, value in (
        ("expected_source_sha256", "0" * 64),
        ("expected_target_index_id", "other-target"),
        ("expected_embedding_fingerprint", "0" * 64),
        ("expected_manifest_sha256", "0" * 64),
        ("expected_scope", "private"),
    ):
        isolation = dict(values["isolation"])
        if field == "expected_target_index_id":
            isolation["target_index_id"] = value
        elif field == "expected_manifest_sha256":
            isolation["manifest_sha256"] = value
        drifted = AttestationExpectation(
            expected_source_sha256=value if field == "expected_source_sha256" else values["expected"].expected_source_sha256,
            expected_target_index_id=value if field == "expected_target_index_id" else values["expected"].expected_target_index_id,
            expected_embedding_fingerprint=value if field == "expected_embedding_fingerprint" else values["expected"].expected_embedding_fingerprint,
            expected_manifest_sha256=value if field == "expected_manifest_sha256" else values["expected"].expected_manifest_sha256,
            expected_scope=value if field == "expected_scope" else values["expected"].expected_scope,
            expected_owner=7 if field == "expected_scope" else values["expected"].expected_owner,
            isolation_evidence=isolation,
        )
        proof = build(values)
        assert not validate_attestation(proof, expected=drifted, snapshot=values["snapshot"]).allowed


@pytest.mark.parametrize("isolation", [
    {"verified": True},
    {"mode": "provenance_filter", "target_index_id": TARGET, "manifest_sha256": MANIFEST_SHA,
     "row_count": 1, "verified_at": VERIFIED_AT, "resource_record_ref": "fixture/resources/t04"},
    {"mode": "isolated_db", "target_index_id": "other-target", "manifest_sha256": MANIFEST_SHA,
     "row_count": 1, "verified_at": VERIFIED_AT, "resource_record_ref": "fixture/resources/t04"},
    {"mode": "isolated_db", "target_index_id": TARGET, "manifest_sha256": "0" * 64,
     "row_count": 1, "verified_at": VERIFIED_AT, "resource_record_ref": "fixture/resources/t04"},
    {"mode": "isolated_db", "target_index_id": TARGET, "manifest_sha256": MANIFEST_SHA,
     "row_count": 0, "verified_at": VERIFIED_AT, "resource_record_ref": "fixture/resources/t04"},
    {"mode": "isolated_db", "target_index_id": TARGET, "manifest_sha256": MANIFEST_SHA,
     "row_count": 1, "verified_at": "yesterday", "resource_record_ref": "fixture/resources/t04"},
    {"mode": "isolated_db", "target_index_id": TARGET, "manifest_sha256": MANIFEST_SHA,
     "row_count": 1, "verified_at": VERIFIED_AT, "resource_record_ref": ""},
])
def test_expectation_rejects_incomplete_or_untrusted_isolation_evidence(isolation):
    with pytest.raises(ValueError):
        AttestationExpectation(
            expected_source_sha256=SOURCE_SHA, expected_target_index_id=TARGET,
            expected_embedding_fingerprint=IDENTITY_SHA, expected_manifest_sha256=MANIFEST_SHA,
            expected_scope="global", expected_owner=None, isolation_evidence=isolation,
        )


def test_build_and_validate_are_pure_repeatable_and_do_not_mutate_inputs(monkeypatch, offline_pgvector_boundary):
    values = bundle()
    opened = {"count": 0}

    def trap_open(*args, **kwargs):
        opened["count"] += 1
        raise AssertionError("file IO is forbidden")

    monkeypatch.setattr(builtins, "open", trap_open)
    monkeypatch.setattr(io, "open", trap_open)
    monkeypatch.setattr(Path, "open", trap_open)
    monkeypatch.setattr(Path, "read_text", trap_open)
    monkeypatch.setattr(Path, "read_bytes", trap_open)
    proof = build(values)
    first = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])
    second = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])

    assert first == second
    assert first.allowed
    assert opened["count"] == 0
    assert offline_pgvector_boundary["embeddings_create"] == 0


def test_validator_rejects_self_consistent_attestation_for_different_snapshot():
    values = bundle()
    proof = build(values)
    other_row = {**row(), "doc_id": "other-doc"}
    other_snapshot = IndexSnapshot(
        target_index_id=TARGET, database_id="rag_fixture", schema_name="public", row_count=1,
        rows=[other_row], manifest_sha256=manifest_sha256([other_row]),
    )

    checked = validate_attestation(proof, expected=values["expected"], snapshot=other_snapshot)
    assert not checked.allowed
    assert "identity_mismatch" in checked.failures or "count_mismatch" in checked.failures


def test_multiple_failures_are_deduplicated_in_stable_contract_order_and_never_echo_secrets():
    values = bundle()
    proof = build(values)
    proof["unexpected"] = "FAKE_SECRET"
    proof["source_sha256"] = "invalid"
    proof["target_index_id"] = "other-target"
    proof["planned_chunk_count"] = True
    proof["scope"] = "unknown"
    proof["embedding_fingerprint"] = "0" * 64
    proof["isolation_evidence_ref"] = ""
    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])

    assert not checked.allowed
    assert checked.failures == tuple(dict.fromkeys(checked.failures))
    assert all(re_safe_rule_id(rule) for rule in checked.failures)
    assert "FAKE_SECRET" not in repr(checked)


def test_validator_rejects_non_dict_outer_mapping_but_accepts_nested_contract_mappings():
    values = bundle()
    proof = build(values)
    checked = validate_attestation(MappingProxyType(proof), expected=values["expected"], snapshot=values["snapshot"])

    assert not checked.allowed
    assert checked.failures == ("types_invalid",)

    proof["chunk_policy"] = MappingProxyType(dict(proof["chunk_policy"]))
    assert validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed


def test_validator_requires_isolation_and_attestation_verification_times_to_match():
    values = bundle()
    proof = build(values)
    proof["created_at"] = "2026-10-16T00:00:01Z"

    checked = validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"])

    assert not checked.allowed
    assert "isolation_unproven" in checked.failures
