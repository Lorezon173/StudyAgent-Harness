# T02 round 1 scoped fix diff
Original reviewed working-tree snapshot versus current files.
--- before/app/harness/knowledge_ingestion.py
+++ after/app/harness/knowledge_ingestion.py
@@ -150,22 +150,21 @@
             object.__setattr__(self, name, _freeze_json(getattr(self, name)))
         if (
             not isinstance(self.warnings, tuple)
             or any(not isinstance(warning, str) for warning in self.warnings)
             or self.warnings != _safe_warnings(self.documents)
         ):
             raise ValueError("prepared warnings 无效")
 
     def to_intent_metadata(self) -> dict[str, Any]:
         """返回不含正文、且与快照相互隔离的 JSON 元数据副本。"""
-        if self.warnings != _safe_warnings(self.documents):
-            raise ValueError("prepared warnings 无效")
+        KnowledgeIngestionService._validate_prepared(self)
         keys = (
             "schema_version", "source_sha256", "source_format", "import_namespace",
             "doc_id", "scope", "owner", "normalizer_version", "chunking_version",
             "doc_protocol", "chunk_protocol", "chunk_policy", "warnings",
         )
         result = {key: _thaw_json(getattr(self, key)) for key in keys}
         result["warnings"] = list(result["warnings"])
         return result
 
 
--- before/tests/unit/harness/test_knowledge_ingestion.py
+++ after/tests/unit/harness/test_knowledge_ingestion.py
@@ -46,66 +46,98 @@
     }
 
 
 def test_ingestion_fixture_forces_fake_backend_when_pgvector_is_configured():
     coordinator = RAGCoordinator()
 
     assert coordinator.get_provider("vector") is not None
     assert coordinator.get_provider("vector").__class__.__name__ == "_VectorStoreProvider"
 
 
-def test_prepared_ingestion_constructor_freezes_snapshot_and_intent():
-    source_doc = {
-        "content": "private body sentinel",
-        "doc_id": "doc-fixture",
-        "metadata": {"source_locator": {"positions": [0]}},
-    }
-    source_manifest = {
-        "schema_version": "prepared-manifest-v1",
-        "doc_id": "doc-fixture",
-        "rows": [{"source_locator": {"positions": [0]}}],
-        "row_count": 1,
-        "manifest_sha256": "digest",
-    }
-    prepared = knowledge_ingestion.PreparedIngestion(
-        schema_version="prepared-ingestion-v1",
-        source_sha256="source-digest",
-        source_format="txt",
-        import_namespace="course-1",
-        doc_id="doc-fixture",
-        scope="global",
-        owner=None,
-        normalizer_version="doc-norm-1",
-        chunking_version="chunk-policy-1",
-        doc_protocol="doc-v1",
-        chunk_protocol="chunk-v1",
-        chunk_policy={"chunk_size": 10, "chunk_overlap": 0, "hard_limit": 10},
-        documents=[source_doc],
-        manifest=source_manifest,
-        warnings=[],
-    )
-
-    source_doc["metadata"]["source_locator"]["positions"].append(1)
-    source_manifest["rows"][0]["source_locator"]["positions"].append(1)
+def test_prepared_ingestion_constructor_freezes_snapshot_and_intent(tmp_path, monkeypatch):
+    source_docs = []
+
+    def docs_factory(context):
+        docs = _fixture_docs(context, contents=("private body sentinel", "second body"))
+        source_docs.extend(docs)
+        return docs
+
+    source, _, _, _, service = _make_test_service(
+        tmp_path, monkeypatch, docs_factory=docs_factory
+    )
+    base = service.prepare_file(str(source), import_namespace="course-1")
+    constructor_inputs = _prepared_kwargs(base)
+    constructor_inputs["chunk_policy"]["chunk_size"] = 10
+    constructor_inputs["chunk_policy"]["chunk_overlap"] = 0
+    source_manifest = constructor_inputs["manifest"]
+    prepared = knowledge_ingestion.PreparedIngestion(**constructor_inputs)
+
+    constructor_inputs["documents"][0]["metadata"]["source_locator"]["paragraph"] = 99
+    constructor_inputs["documents"][0]["metadata"]["element_types"].append("mutated")
+    source_manifest["rows"][0]["source_locator"]["paragraph"] = 99
     intent = prepared.to_intent_metadata()
     intent["chunk_policy"]["chunk_size"] = 20
 
-    assert prepared.documents[0]["metadata"]["source_locator"]["positions"] == (0,)
-    assert prepared.manifest["rows"][0]["source_locator"]["positions"] == (0,)
+    assert prepared.documents[0]["content"] == "private body sentinel"
+    assert prepared.documents[0]["metadata"]["source_locator"]["paragraph"] == 0
+    assert prepared.documents[0]["metadata"]["element_types"] == ("paragraph",)
+    assert prepared.manifest["rows"][0]["source_locator"]["paragraph"] == 0
     assert prepared.chunk_policy["chunk_size"] == 10
     assert set(intent) == {
         "schema_version", "source_sha256", "source_format", "import_namespace",
         "doc_id", "scope", "owner", "normalizer_version", "chunking_version",
         "doc_protocol", "chunk_protocol", "chunk_policy", "warnings",
     }
     assert "documents" not in intent
-    assert "private body sentinel" not in json.dumps(intent)
+    assert "private body sentinel" not in json.dumps({
+        "manifest": _thaw(prepared.manifest), "intent": intent,
+        "warnings": list(prepared.warnings),
+    })
+
+
+@pytest.mark.parametrize("corruption", ["owner", "schema", "policy", "manifest_digest"])
+def test_to_intent_metadata_rejects_invalid_direct_snapshot(
+    tmp_path, monkeypatch, corruption
+):
+    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)
+    base = service.prepare_file(str(source), import_namespace="course-1")
+    values = _prepared_kwargs(base)
+    if corruption == "owner":
+        values["owner"] = True
+    elif corruption == "schema":
+        values["schema_version"] = "unknown-schema"
+    elif corruption == "policy":
+        values["chunk_policy"]["chunk_size"] = True
+    else:
+        values["manifest"]["manifest_sha256"] = "0" * 64
+    direct = knowledge_ingestion.PreparedIngestion(**values)
+
+    with pytest.raises(ValueError):
+        direct.to_intent_metadata()
+
+    assert provider.calls == 0
+
+
+def test_private_intent_metadata_is_valid_and_deeply_isolated(tmp_path, monkeypatch):
+    source, _, _, _, service = _make_test_service(tmp_path, monkeypatch)
+    prepared = service.prepare_file(
+        str(source), import_namespace="course-1", scope="private", user_id=7
+    )
+
+    intent = prepared.to_intent_metadata()
+    intent["chunk_policy"]["hard_limit"] = 10
+    intent["warnings"].append("caller edit")
+
+    assert intent["owner"] == 7
+    assert prepared.owner == 7
+    assert prepared.chunk_policy["hard_limit"] == 8192
+    assert prepared.warnings == ()
 
 
 @pytest.mark.parametrize(
     "unsafe_warning",
     ["api_key=FAKE_SECRET", "RuntimeError: upstream returned private body sentinel"],
 )
 def test_prepared_ingestion_rejects_untrusted_warnings_before_intent_export(
     unsafe_warning,
 ):
     with pytest.raises(ValueError):
