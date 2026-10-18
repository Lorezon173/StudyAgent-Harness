from __future__ import annotations

import builtins
import hashlib
import io
import sys
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.core.config import settings
from app.harness.knowledge_ingestion import IngestResult
from app.infrastructure.rag.embedding import EmbeddingService
from app.infrastructure.rag.pgvector_provider import PgVectorProvider
from app.infrastructure.rag.contracts import (
    AttestationExpectation,
    ContractCheck,
    EmbeddingBinding,
    EmbeddingIdentity,
    IndexSnapshot,
    RAGRequestContext,
    RunRecord,
    canonical_json_bytes,
    manifest_sha256,
)


ROW = {
    "chunk_id": "chunk-0",
    "chunk_index": 0,
    "content_sha256": "77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a",
    "doc_id": "doc-fixture",
    "owner": None,
    "scope": "global",
    "source_locator": {"paragraph": 0},
}
IDENTITY = {
    "schema_version": "embedding-identity-v1",
    "service_id": "svc-public",
    "deployment_id": None,
    "model": "model-a",
    "dimension": 2,
    "parameters": {"dimensions": "service_default", "encoding_format": "service_default"},
    "model_version": None,
    "version_binding": "alias_unpinned",
}


@pytest.fixture(autouse=True)
def offline_pgvector_boundary(monkeypatch):
    """Make accidental network/database use fail, even under pgvector settings."""
    calls = {"sdk_factory": 0, "embeddings_create": 0, "embed_one": 0, "embed_many": 0,
             "sync_engine": 0, "async_engine": 0, "provider_connection": 0}

    def trap(name):
        def fail(*args, **kwargs):
            calls[name] += 1
            raise AssertionError(f"offline boundary: {name}")
        return fail

    def sdk_factory(*args, **kwargs):
        calls["sdk_factory"] += 1
        return SimpleNamespace(embeddings=SimpleNamespace(create=trap("embeddings_create")))

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
    assert not any(calls.values())


def test_contract_check_freezes_failures_and_uses_contract_category_order():
    check = ContractCheck(
        allowed=False,
        failures=("target_mismatch", "schema_missing", "count_mismatch", "schema_missing", "identity_mismatch"),
    )

    assert check.allowed is False
    assert check.failures == ("schema_missing", "target_mismatch", "identity_mismatch", "count_mismatch")
    assert isinstance(check.failures, tuple)
    with pytest.raises((AttributeError, TypeError)):
        check.failures += ("types_invalid",)
    with pytest.raises(ValueError):
        ContractCheck(allowed=True, failures=("schema_missing",))
    with pytest.raises(ValueError):
        ContractCheck(allowed=False, failures=())
    with pytest.raises(ValueError):
        ContractCheck(allowed=1, failures=())
    with pytest.raises(ValueError):
        ContractCheck(allowed=False, failures=("secret-token-should-not-be-a-rule",))


def test_embedding_binding_keeps_endpoint_out_of_repr_and_rejects_secret_like_ids():
    binding = EmbeddingBinding(
        service_id="svc-public",
        deployment_id="deploy-a",
        model_version=None,
        expected_endpoint="https://user:secret@example.test/v1/",
    )

    assert "svc-public" in repr(binding)
    assert "example.test" not in repr(binding)
    assert "secret" not in repr(binding)
    assert binding.deployment_id == "deploy-a"
    assert binding.model_version is None
    for unsafe in ("https://service.test", "user:password", "with space", "", "x@y"):
        with pytest.raises(ValueError):
            EmbeddingBinding(service_id=unsafe, deployment_id=None, model_version=None,
                            expected_endpoint="https://service.test")
    for unsafe_version in ("https://user:fake-secret@example.test/v1", "api_key=fake-secret", "token: fake-secret", "v1\napi_key=x"):
        with pytest.raises(ValueError):
            EmbeddingBinding(service_id="svc-public", deployment_id=None, model_version=unsafe_version,
                            expected_endpoint="https://service.test")


def test_embedding_identity_freezes_nested_parameters_and_has_exact_versioned_fields():
    source = {"dimensions": "service_default", "encoding_format": "service_default"}
    identity = EmbeddingIdentity(**{**IDENTITY, "parameters": source})
    source["dimensions"] = 99

    assert identity.schema_version == "embedding-identity-v1"
    assert dict(identity.parameters) == {
        "dimensions": "service_default", "encoding_format": "service_default"
    }
    with pytest.raises(TypeError):
        identity.parameters["encoding_format"] = "base64"
    with pytest.raises(ValueError):
        EmbeddingIdentity(**{**IDENTITY, "schema_version": "embedding-identity-v2"})
    for bad_dimension in (0, -1, True, 2.0, None):
        with pytest.raises(ValueError):
            EmbeddingIdentity(**{**IDENTITY, "dimension": bad_dimension})
    for bad_parameters in (
        {"dimensions": "service_default"},
        {"dimensions": "service_default", "encoding_format": "service_default", "extra": 1},
        {"dimensions": float("nan"), "encoding_format": "service_default"},
        {"dimensions": {"secret": "x"}, "encoding_format": "service_default"},
    ):
        with pytest.raises(ValueError):
            EmbeddingIdentity(**{**IDENTITY, "parameters": bad_parameters})
    with pytest.raises(ValueError):
        EmbeddingIdentity(**{**IDENTITY, "model_version": "v1"})
    with pytest.raises(ValueError):
        EmbeddingIdentity(**{**IDENTITY, "version_binding": "pinned"})
    with pytest.raises(ValueError):
        EmbeddingIdentity(**{**IDENTITY, "deployment_id": ""})
    for unsafe_field in ("https://user:fake-secret@example.test/v1", "api_key=fake-secret", "token: fake-secret", "v1\npassword=x"):
        with pytest.raises(ValueError):
            EmbeddingIdentity(**{**IDENTITY, "model": unsafe_field})
        with pytest.raises(ValueError):
            EmbeddingIdentity(**{**IDENTITY, "model_version": unsafe_field, "version_binding": "pinned"})
    public_variant = EmbeddingIdentity(
        **{**IDENTITY, "model": "vendor/embedding-v2", "model_version": "snapshot/release-v2",
           "version_binding": "pinned"}
    )
    assert public_variant.model == "vendor/embedding-v2"
    assert public_variant.model_version == "snapshot/release-v2"


@pytest.mark.parametrize("encoding_format", ["float", "base64"])
def test_embedding_identity_accepts_supported_explicit_encoding_formats(encoding_format):
    identity = EmbeddingIdentity(
        **{**IDENTITY, "parameters": {"dimensions": "service_default", "encoding_format": encoding_format}}
    )

    assert identity.parameters["encoding_format"] == encoding_format


@pytest.mark.parametrize("encoding_format", [
    "api_key=FAKE_SECRET", "https://user:FAKE_SECRET@example.test", "base64\napi_key=x", "json", "",
])
def test_embedding_identity_rejects_unsafe_or_unsupported_encoding_formats(encoding_format):
    with pytest.raises(ValueError) as exc:
        EmbeddingIdentity(
            **{**IDENTITY, "parameters": {"dimensions": "service_default", "encoding_format": encoding_format}}
        )

    assert "FAKE_SECRET" not in str(exc.value)


def test_index_snapshot_copies_complete_rows_and_recomputes_duplicate_preserving_digest():
    original = [deepcopy(ROW)]
    snapshot = IndexSnapshot(
        target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
        row_count=1, rows=original, manifest_sha256="7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176",
    )
    original[0]["source_locator"]["paragraph"] = 99

    assert snapshot.rows[0]["source_locator"]["paragraph"] == 0
    assert snapshot.manifest_sha256 == "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
    assert isinstance(snapshot.rows, tuple)
    with pytest.raises(TypeError):
        snapshot.rows[0]["doc_id"] = "changed"
    assert manifest_sha256([ROW, ROW]) != manifest_sha256([ROW])
    assert manifest_sha256([ROW, {**ROW, "chunk_id": "chunk-1", "chunk_index": 1}]) == manifest_sha256(
        [{**ROW, "chunk_id": "chunk-1", "chunk_index": 1}, ROW]
    )
    with pytest.raises(ValueError):
        IndexSnapshot(target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
                      row_count=2, rows=[ROW], manifest_sha256="7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176")
    with pytest.raises(ValueError):
        IndexSnapshot(target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
                      row_count=True, rows=[ROW], manifest_sha256="7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176")
    with pytest.raises(ValueError):
        IndexSnapshot(target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
                      row_count=1, rows=[{**ROW, "owner": False}], manifest_sha256="0" * 64)
    with pytest.raises(ValueError):
        IndexSnapshot(target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
                      row_count=0, rows=[], manifest_sha256="not-a-sha")
    with pytest.raises(ValueError):
        IndexSnapshot(target_index_id="https://user:FAKE_SECRET@example.test/rag", database_id="rag_fixture",
                      schema_name="public", row_count=1, rows=[ROW],
                      manifest_sha256="7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176")


def test_attestation_expectation_deep_freezes_isolation_evidence():
    isolation = {
        "mode": "isolated_db", "target_index_id": "rag-t04-fixture",
        "manifest_sha256": "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176",
        "row_count": 1, "verified_at": "2026-10-16T00:00:00Z",
        "resource_record_ref": "fixture/resources/t04",
    }
    expected = AttestationExpectation(
        expected_source_sha256="1a89e8c34a455cfadab9c5730f68a2669a3ac1db4f8b490065353e261f2cb6e8",
        expected_target_index_id="rag-t04-fixture",
        expected_embedding_fingerprint="005a79e156e97b05af18abadbadeda7c40bab8418a0152e7f36ee08b19aa798a",
        expected_manifest_sha256=isolation["manifest_sha256"], expected_scope="global", expected_owner=None,
        isolation_evidence=isolation,
    )
    isolation["row_count"] = 0

    assert expected.isolation_evidence["row_count"] == 1
    with pytest.raises(TypeError):
        expected.isolation_evidence["row_count"] = 0
    with pytest.raises(ValueError, match="^target_mismatch$"):
        AttestationExpectation(
            expected_source_sha256=expected.expected_source_sha256,
            expected_target_index_id="https://user:FAKE_SECRET@example.test/rag",
            expected_embedding_fingerprint=expected.expected_embedding_fingerprint,
            expected_manifest_sha256=expected.expected_manifest_sha256,
            expected_scope="global", expected_owner=None,
            isolation_evidence=expected.isolation_evidence,
        )
    for bad_owner in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            AttestationExpectation(
                expected_source_sha256="1a89e8c34a455cfadab9c5730f68a2669a3ac1db4f8b490065353e261f2cb6e8",
                expected_target_index_id="rag-t04-fixture", expected_embedding_fingerprint="0" * 64,
                expected_manifest_sha256="0" * 64, expected_scope="private", expected_owner=bad_owner,
                isolation_evidence=expected.isolation_evidence,
            )


def test_request_context_is_immutable_and_attempt_is_exactly_one():
    context = RAGRequestContext(retrieval_id="retrieval-1", attempt=1, trace_id=None, session_id="session-1")

    assert context.retrieval_id == "retrieval-1"
    assert context.trace_id is None
    for attempt in (0, 2, True, 1.0, None):
        with pytest.raises(ValueError):
            RAGRequestContext(retrieval_id="retrieval-1", attempt=attempt)
    for retrieval_id in ("", None, 3):
        with pytest.raises(ValueError):
            RAGRequestContext(retrieval_id=retrieval_id)


@pytest.mark.parametrize(
    ("phase", "summary"),
    [
        ("prepared", "\u6444\u5165\u8ba1\u5212\u5df2\u51c6\u5907"),
        ("committed_unattested", "\u5199\u5165\u5f85\u8bc1\u660e"),
        ("completed", "\u6444\u5165\u5df2\u6838\u9a8c"),
        ("failed", "\u6444\u5165\u672a\u5b8c\u6210"),
        ("inconclusive", "\u6444\u5165\u72b6\u6001\u5f85\u6838\u9a8c"),
    ],
)
def test_run_record_summary_and_failure_ids_follow_frozen_phase_contract(phase, summary):
    kwargs = {"schema_version": "ingestion-run-v1", "ingestion_run_id": "00000000-0000-4000-8000-000000000004",
              "phase": phase, "error_code": None, "safe_summary": summary,
              "failures": ("z_rule", "a_rule", "z_rule"), "attestation_path": "proof.json" if phase == "completed" else None}
    record = RunRecord(**kwargs)

    assert record.failures == ("a_rule", "z_rule")
    assert record.safe_summary == summary
    with pytest.raises(ValueError):
        RunRecord(**{**kwargs, "phase": "unknown"})
    with pytest.raises(ValueError):
        RunRecord(**{**kwargs, "safe_summary": "raw error text"})
    with pytest.raises(ValueError):
        RunRecord(**{**kwargs, "attestation_path": "proof.json" if phase != "completed" else None})
    with pytest.raises(ValueError):
        RunRecord(**{**kwargs, "error_code": "new_public_code"})


def test_run_record_rejects_invalid_uuid_error_text_and_non_string_failures():
    base = {"schema_version": "ingestion-run-v1", "ingestion_run_id": "00000000-0000-4000-8000-000000000004",
            "phase": "failed", "error_code": "db_error", "safe_summary": "\u6444\u5165\u672a\u5b8c\u6210", "failures": (),
            "attestation_path": None}
    for bad_uuid in ("run-1", "", None):
        with pytest.raises(ValueError):
            RunRecord(**{**base, "ingestion_run_id": bad_uuid})
    for failures in (("traceback with secret",), (1,), ("bad rule",)):
        with pytest.raises(ValueError):
            RunRecord(**{**base, "failures": failures})
    with pytest.raises(ValueError):
        RunRecord(**{**base, "schema_version": "ingestion-run-v2"})


def test_canonical_json_fixed_vectors_use_unicode_utf8_and_no_extra_whitespace():
    value = {"z": None, "a": "甲"}
    encoded = canonical_json_bytes(value)

    assert encoded == '{"a":"甲","z":null}'.encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == "815d7d75761381ceee22ca5c208ba165a97158ae816d7e968c885f41f1605634"
    assert canonical_json_bytes({"a": "甲", "z": None}) == encoded
    assert canonical_json_bytes("é") != canonical_json_bytes("e\u0301")
    assert hashlib.sha256(canonical_json_bytes(IDENTITY)).hexdigest() == "005a79e156e97b05af18abadbadeda7c40bab8418a0152e7f36ee08b19aa798a"
    assert hashlib.sha256(canonical_json_bytes([ROW])).hexdigest() == "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"


@pytest.mark.parametrize(
    "bad_value",
    [
        {1: "non-string key"},
        {"x": float("nan")},
        {"x": float("inf")},
        {"x": -float("inf")},
        {"x": object()},
        {"x": {"unsafe": object()}},
    ],
)
def test_canonical_json_rejects_values_outside_strict_json(bad_value):
    with pytest.raises(ValueError) as exc:
        canonical_json_bytes(bad_value)
    assert "object at" not in str(exc.value)
    assert "nan" not in str(exc.value).lower()


def test_manifest_digest_validates_full_row_schema_without_losing_duplicates():
    expected = "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"

    assert manifest_sha256([ROW]) == expected
    assert manifest_sha256([ROW, ROW]) != expected
    with pytest.raises(ValueError):
        manifest_sha256([{**ROW, "extra": True}])
    with pytest.raises(ValueError):
        manifest_sha256([{**ROW, "chunk_index": True}])


def test_shared_contract_types_do_not_touch_sdk_database_embedding_methods_or_files(
    offline_pgvector_boundary, monkeypatch
):
    def trap_open(*args, **kwargs):
        raise AssertionError("file IO is forbidden")

    monkeypatch.setattr(builtins, "open", trap_open)
    monkeypatch.setattr(io, "open", trap_open)
    monkeypatch.setattr(Path, "open", trap_open)
    monkeypatch.setattr(Path, "read_text", trap_open)
    monkeypatch.setattr(Path, "read_bytes", trap_open)

    assert settings.rag_backend == "pgvector"
    assert IngestResult(status="ok", doc_id="doc-fixture", planned_chunk_count=1, written_chunk_count=1).status == "ok"
    assert manifest_sha256([ROW]) == "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
    assert not any(offline_pgvector_boundary.values())
