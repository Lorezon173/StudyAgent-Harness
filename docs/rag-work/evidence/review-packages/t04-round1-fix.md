# T04 round 1 scoped fix diff
Compare original review package snapshot with current working tree.
--- before/app/infrastructure/rag/contracts.py
+++ after/app/infrastructure/rag/contracts.py
@@ -30,20 +30,21 @@
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
+_ENCODING_FORMATS = frozenset({"service_default", "float", "base64"})
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
@@ -283,22 +284,22 @@
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
-        if encoding_format != "service_default":
-            _nonempty_string(encoding_format)
+        if not isinstance(encoding_format, str) or encoding_format not in _ENCODING_FORMATS:
+            _fail("types_invalid")
         frozen = _freeze_json(self.parameters)
         if any(isinstance(value, Mapping) or isinstance(value, tuple) for value in frozen.values()):
             _fail("types_invalid")
         object.__setattr__(self, "parameters", frozen)
 
 
 @dataclass(frozen=True)
 class IndexSnapshot:
     target_index_id: str
     database_id: str
--- before/app/harness/ingestion_attestation.py
+++ after/app/harness/ingestion_attestation.py
@@ -18,20 +18,25 @@
     manifest_sha256,
 )
 from app.infrastructure.rag.embedding_identity import fingerprint_embedding, to_json_dict
 
 
 _CONTRACT_VERSION = "rag-mvp-contracts-v1.0.1"
 _ATTESTATION_VERSION = "ingestion-attestation-v1"
 _INTENT_VERSION = "ingestion-intent-v1"
 _MANIFEST_VERSION = "ingestion-manifest-v1"
 _PREPARATION_VERSION = "prepared-ingestion-v1"
+_SOURCE_FORMAT = "epub"
+_NORMALIZER_VERSION = "doc-norm-1"
+_CHUNKING_VERSION = "chunk-policy-1"
+_DOC_PROTOCOL = "doc-v1"
+_CHUNK_PROTOCOL = "chunk-v1"
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
@@ -235,20 +240,30 @@
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
+    if prep["source_format"] != _SOURCE_FORMAT:
+        _fail("source_mismatch")
+    frozen_versions = {
+        "normalizer_version": _NORMALIZER_VERSION,
+        "chunking_version": _CHUNKING_VERSION,
+        "doc_protocol": _DOC_PROTOCOL,
+        "chunk_protocol": _CHUNK_PROTOCOL,
+    }
+    if any(prep[field] != version for field, version in frozen_versions.items()):
+        _fail("version_unsupported")
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
@@ -527,23 +542,29 @@
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
-    if attestation.get("doc_protocol") != "doc-v1" or attestation.get("chunk_protocol") != "chunk-v1":
-        failures.append("version_unsupported")
-    if attestation.get("chunking_version") == attestation.get("chunk_protocol"):
+    if attestation.get("source_format") != _SOURCE_FORMAT:
+        failures.append("source_mismatch")
+    frozen_versions = {
+        "normalizer_version": _NORMALIZER_VERSION,
+        "chunking_version": _CHUNKING_VERSION,
+        "doc_protocol": _DOC_PROTOCOL,
+        "chunk_protocol": _CHUNK_PROTOCOL,
+    }
+    if any(attestation.get(field) != version for field, version in frozen_versions.items()):
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
--- before/tests/unit/infrastructure/test_rag_contracts.py
+++ after/tests/unit/infrastructure/test_rag_contracts.py
@@ -157,20 +157,41 @@
         with pytest.raises(ValueError):
             EmbeddingIdentity(**{**IDENTITY, "model_version": unsafe_field, "version_binding": "pinned"})
     public_variant = EmbeddingIdentity(
         **{**IDENTITY, "model": "vendor/embedding-v2", "model_version": "snapshot/release-v2",
            "version_binding": "pinned"}
     )
     assert public_variant.model == "vendor/embedding-v2"
     assert public_variant.model_version == "snapshot/release-v2"
 
 
+@pytest.mark.parametrize("encoding_format", ["float", "base64"])
+def test_embedding_identity_accepts_supported_explicit_encoding_formats(encoding_format):
+    identity = EmbeddingIdentity(
+        **{**IDENTITY, "parameters": {"dimensions": "service_default", "encoding_format": encoding_format}}
+    )
+
+    assert identity.parameters["encoding_format"] == encoding_format
+
+
+@pytest.mark.parametrize("encoding_format", [
+    "api_key=FAKE_SECRET", "https://user:FAKE_SECRET@example.test", "base64\napi_key=x", "json", "",
+])
+def test_embedding_identity_rejects_unsafe_or_unsupported_encoding_formats(encoding_format):
+    with pytest.raises(ValueError) as exc:
+        EmbeddingIdentity(
+            **{**IDENTITY, "parameters": {"dimensions": "service_default", "encoding_format": encoding_format}}
+        )
+
+    assert "FAKE_SECRET" not in str(exc.value)
+
+
 def test_index_snapshot_copies_complete_rows_and_recomputes_duplicate_preserving_digest():
     original = [deepcopy(ROW)]
     snapshot = IndexSnapshot(
         target_index_id="rag-t04-fixture", database_id="rag_fixture", schema_name="public",
         row_count=1, rows=original, manifest_sha256="7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176",
     )
     original[0]["source_locator"]["paragraph"] = 99
 
     assert snapshot.rows[0]["source_locator"]["paragraph"] == 0
     assert snapshot.manifest_sha256 == "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
--- before/tests/unit/infrastructure/test_embedding_identity.py
+++ after/tests/unit/infrastructure/test_embedding_identity.py
@@ -151,20 +151,41 @@
     }
     assert exported["parameters"] == {
         "dimensions": "service_default", "encoding_format": "service_default"
     }
     exported["parameters"]["dimensions"] = 99
     assert identity.parameters["dimensions"] == "service_default"
     with pytest.raises(ValueError):
         to_json_dict(binding())
 
 
+@pytest.mark.parametrize("encoding_format", ["float", "base64"])
+def test_explicit_encoding_format_survives_json_export_and_fingerprint(encoding_format):
+    identity = EmbeddingIdentity(
+        service_id="svc-public", deployment_id=None, model="model-a", dimension=2,
+        parameters={"dimensions": "service_default", "encoding_format": encoding_format},
+        model_version=None, version_binding="alias_unpinned",
+    )
+
+    exported = to_json_dict(identity)
+
+    assert exported["parameters"]["encoding_format"] == encoding_format
+    assert fingerprint_embedding(identity)
+    object.__setattr__(identity, "parameters", {"dimensions": "service_default", "encoding_format": "api_key=FAKE_SECRET"})
+    with pytest.raises(ValueError) as json_error:
+        to_json_dict(identity)
+    with pytest.raises(ValueError) as fingerprint_error:
+        fingerprint_embedding(identity)
+    assert "FAKE_SECRET" not in str(json_error.value)
+    assert "FAKE_SECRET" not in str(fingerprint_error.value)
+
+
 def test_endpoint_binding_is_strict_and_error_does_not_disclose_url_or_credentials():
     endpoint = "https://user:FAKE_SECRET@embedding.example.test/v1/"
     service = EmbeddingService(model="model-a", api_key="FAKE_API_KEY_DO_NOT_LEAK", base_url=endpoint)
 
     identity = describe_embedding(service, binding(endpoint))
     assert identity.model == "model-a"
     with pytest.raises(ValueError) as exc:
         describe_embedding(service, binding(endpoint.rstrip("/")))
     message = str(exc.value)
     assert "endpoint_mismatch" in message
--- before/tests/unit/harness/test_ingestion_attestation.py
+++ after/tests/unit/harness/test_ingestion_attestation.py
@@ -1,27 +1,29 @@
 from __future__ import annotations
 
 import builtins
 import copy
+import hashlib
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
+    canonical_json_bytes,
     manifest_sha256,
 )
 from app.infrastructure.rag.embedding import EmbeddingService
 from app.infrastructure.rag.embedding_identity import fingerprint_embedding, to_json_dict
 from app.infrastructure.rag.pgvector_provider import PgVectorProvider
 from app.harness.ingestion_attestation import build_attestation, validate_attestation
 
 
 RUN_ID = "00000000-0000-4000-8000-000000000004"
 VERIFIED_AT = "2026-10-16T00:00:00Z"
@@ -82,25 +84,26 @@
         "chunk_id": chunk_id,
         "chunk_index": chunk_index,
         "content_sha256": ROW_SHA,
         "doc_id": doc_id,
         "owner": owner,
         "scope": scope,
         "source_locator": {"paragraph": chunk_index},
     }
 
 
-def bundle(*, scope="global", owner=None, warnings=None, use_fixed_digest=True):
+def bundle(*, scope="global", owner=None, warnings=None, use_fixed_digest=True, identity_parameters=None):
     warnings = [] if warnings is None else list(warnings)
     rows = [row(scope=scope, owner=owner)]
     row_digest = MANIFEST_SHA if use_fixed_digest and scope == "global" and owner is None and rows[0] == row() else manifest_sha256(rows)
-    config = identity()
+    config = identity(parameters=identity_parameters)
+    identity_fingerprint = fingerprint_embedding(config)
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
@@ -111,37 +114,37 @@
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
-        "embedding_fingerprint": IDENTITY_SHA,
+        "embedding_fingerprint": identity_fingerprint,
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
-        "embedding_fingerprint": IDENTITY_SHA,
+        "embedding_fingerprint": identity_fingerprint,
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
@@ -155,21 +158,21 @@
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
-        expected_embedding_fingerprint=IDENTITY_SHA,
+        expected_embedding_fingerprint=identity_fingerprint,
         expected_manifest_sha256=row_digest,
         expected_scope=scope,
         expected_owner=owner,
         isolation_evidence=isolation,
     )
     return {"intent": intent, "manifest": manifest, "result": result, "snapshot": snapshot,
             "identity": config, "verified_at": VERIFIED_AT, "expected": expected, "isolation": isolation}
 
 
 def build(bundle_value):
@@ -208,33 +211,96 @@
     assert attestation["dialect"] == "postgresql"
     assert attestation["embedding_fingerprint"] == IDENTITY_SHA
     assert attestation["artifact_manifest_sha256"] == MANIFEST_SHA
     assert validate_attestation(attestation, expected=values["expected"], snapshot=values["snapshot"]).allowed
     assert values["intent"] == intent_before
     assert values["manifest"] == manifest_before
     assert values["result"].warnings == result_warnings_before
     assert build(values) == attestation
 
 
-def test_build_copies_preparation_fields_without_claiming_independent_validation():
+def test_build_preserves_unfixed_namespace_but_rejects_unfrozen_preparation_versions():
     values = bundle()
     preparation = values["intent"]["preparation"]
-    preparation["source_format"] = "pdf"
     preparation["import_namespace"] = "other-book"
-    preparation["normalizer_version"] = "other-normalizer"
-
-    proof = build(values)
-
-    assert proof["source_format"] == "pdf"
+
+    proof = build(values)
+
     assert proof["import_namespace"] == "other-book"
-    assert proof["normalizer_version"] == "other-normalizer"
     assert validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed
+
+
+@pytest.mark.parametrize(("field", "bad_value"), [
+    ("source_format", "pdf"),
+    ("normalizer_version", "other-normalizer"),
+    ("chunking_version", "other-chunk-policy"),
+    ("doc_protocol", "doc-v2"),
+    ("chunk_protocol", "chunk-v2"),
+])
+def test_build_rejects_preparation_values_outside_frozen_b1(field, bad_value):
+    values = bundle()
+    values["intent"]["preparation"][field] = bad_value
+
+    with pytest.raises(ValueError) as exc:
+        build(values)
+
+    assert re_safe_rule_id(str(exc.value))
+
+
+@pytest.mark.parametrize("encoding_format", ["float", "base64"])
+def test_build_and_validate_accept_supported_explicit_encoding_formats(encoding_format):
+    values = bundle(identity_parameters={"dimensions": "service_default", "encoding_format": encoding_format})
+
+    proof = build(values)
+
+    assert proof["embedding_config"]["parameters"]["encoding_format"] == encoding_format
+    assert validate_attestation(proof, expected=values["expected"], snapshot=values["snapshot"]).allowed
+
+
+def test_build_and_validate_reject_secret_like_encoding_format_without_echoing_it():
+    values = bundle()
+    unsafe_config = dict(values["intent"]["embedding_config"])
+    unsafe_parameters = dict(unsafe_config["parameters"])
+    unsafe_parameters["encoding_format"] = "api_key=FAKE_SECRET"
+    unsafe_config["parameters"] = unsafe_parameters
+    unsafe_digest = hashlib.sha256(canonical_json_bytes(unsafe_config)).hexdigest()
+    values["intent"]["embedding_config"] = unsafe_config
+    values["intent"]["embedding_fingerprint"] = unsafe_digest
+    values["manifest"]["embedding_fingerprint"] = unsafe_digest
+    object.__setattr__(values["identity"], "parameters", unsafe_parameters)
+    with pytest.raises(ValueError) as exc:
+        build(values)
+    assert "FAKE_SECRET" not in str(exc.value)
+
+    values = bundle()
+    proof = build(values)
+    unsafe_config = dict(proof["embedding_config"])
+    unsafe_parameters = dict(unsafe_config["parameters"])
+    unsafe_parameters["encoding_format"] = "https://user:FAKE_SECRET@example.test"
+    unsafe_config["parameters"] = unsafe_parameters
+    unsafe_digest = hashlib.sha256(canonical_json_bytes(unsafe_config)).hexdigest()
+    proof["embedding_config"] = unsafe_config
+    proof["embedding_fingerprint"] = unsafe_digest
+    expected = AttestationExpectation(
+        expected_source_sha256=values["expected"].expected_source_sha256,
+        expected_target_index_id=values["expected"].expected_target_index_id,
+        expected_embedding_fingerprint=unsafe_digest,
+        expected_manifest_sha256=values["expected"].expected_manifest_sha256,
+        expected_scope=values["expected"].expected_scope,
+        expected_owner=values["expected"].expected_owner,
+        isolation_evidence=values["isolation"],
+    )
+    checked = validate_attestation(proof, expected=expected, snapshot=values["snapshot"])
+
+    assert not checked.allowed
+    assert "identity_mismatch" in checked.failures
+    assert "FAKE_SECRET" not in repr(checked)
 
 
 def test_build_rejects_secret_like_target_even_when_all_target_sources_agree():
     values = bundle()
     unsafe_target = "https://user:FAKE_SECRET@example.invalid/rag"
     values["intent"]["target_index_id"] = unsafe_target
     values["manifest"]["target_index_id"] = unsafe_target
     object.__setattr__(values["snapshot"], "target_index_id", unsafe_target)
 
     with pytest.raises(ValueError) as exc:
@@ -373,24 +439,24 @@
 
 
 def re_safe_rule_id(value):
     import re
     return re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) is not None
 
 
 @pytest.mark.parametrize(
     ("field", "bad_value"),
     [
-        ("source_sha256", "0" * 64),
+        ("source_sha256", "0" * 64), ("source_format", "pdf"),
         ("doc_id", "other-doc"),
-        ("chunking_version", "chunk-v1"), ("doc_protocol", "chunk-v1"),
-        ("chunk_protocol", "doc-v1"), ("target_index_id", "other-target"),
+        ("normalizer_version", "other-normalizer"), ("chunking_version", "other-chunk-policy"),
+        ("doc_protocol", "chunk-v1"), ("chunk_protocol", "doc-v1"), ("target_index_id", "other-target"),
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
