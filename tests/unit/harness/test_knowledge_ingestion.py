import hashlib
import json
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.harness.chunking_service import ChunkPolicy, compute_doc_id
import app.harness.knowledge_ingestion as knowledge_ingestion
from app.harness.knowledge_ingestion import IngestResult, KnowledgeIngestionService
from app.infrastructure.rag.coordinator import IndexProvider, RAGCoordinator
from app.infrastructure.rag.embedding import EmbeddingService
from app.infrastructure.rag.pgvector_provider import PgVectorProvider


@pytest.fixture(autouse=True)
def isolate_ingestion_tests(monkeypatch):
    """Pin this module to fake RAG and fail immediately on service access."""
    from app.core.config import settings

    trap_calls = {"pgvector_init": 0, "pgvector_connection": 0, "embedding": 0, "sdk": 0}

    def fail_on_call(counter):
        def fail(*args, **kwargs):
            trap_calls[counter] += 1
            raise AssertionError("offline ingestion test reached a forbidden service")
        return fail

    # Simulate a machine configured for pgvector, then pin the test module to fake.
    monkeypatch.setattr(settings, "rag_backend", "pgvector")
    monkeypatch.setattr(settings, "rag_backend", "fake")
    monkeypatch.setattr(PgVectorProvider, "__init__", fail_on_call("pgvector_init"))
    monkeypatch.setattr(PgVectorProvider, "_get_conn", fail_on_call("pgvector_connection"))
    monkeypatch.setattr(EmbeddingService, "embed_one", fail_on_call("embedding"))
    monkeypatch.setattr(EmbeddingService, "embed_many", fail_on_call("embedding"))
    monkeypatch.setattr("openai.OpenAI", fail_on_call("sdk"))

    yield trap_calls

    assert trap_calls == {
        "pgvector_init": 0,
        "pgvector_connection": 0,
        "embedding": 0,
        "sdk": 0,
    }


def test_ingestion_fixture_forces_fake_backend_when_pgvector_is_configured():
    coordinator = RAGCoordinator()

    assert coordinator.get_provider("vector") is not None
    assert coordinator.get_provider("vector").__class__.__name__ == "_VectorStoreProvider"


def test_prepared_ingestion_constructor_freezes_snapshot_and_intent(tmp_path, monkeypatch):
    source_docs = []

    def docs_factory(context):
        docs = _fixture_docs(context, contents=("private body sentinel", "second body"))
        source_docs.extend(docs)
        return docs

    source, _, _, _, service = _make_test_service(
        tmp_path, monkeypatch, docs_factory=docs_factory
    )
    base = service.prepare_file(str(source), import_namespace="course-1")
    constructor_inputs = _prepared_kwargs(base)
    constructor_inputs["chunk_policy"]["chunk_size"] = 10
    constructor_inputs["chunk_policy"]["chunk_overlap"] = 0
    source_manifest = constructor_inputs["manifest"]
    prepared = knowledge_ingestion.PreparedIngestion(**constructor_inputs)

    constructor_inputs["documents"][0]["metadata"]["source_locator"]["paragraph"] = 99
    constructor_inputs["documents"][0]["metadata"]["element_types"].append("mutated")
    source_manifest["rows"][0]["source_locator"]["paragraph"] = 99
    intent = prepared.to_intent_metadata()
    intent["chunk_policy"]["chunk_size"] = 20

    assert prepared.documents[0]["content"] == "private body sentinel"
    assert prepared.documents[0]["metadata"]["source_locator"]["paragraph"] == 0
    assert prepared.documents[0]["metadata"]["element_types"] == ("paragraph",)
    assert prepared.manifest["rows"][0]["source_locator"]["paragraph"] == 0
    assert prepared.chunk_policy["chunk_size"] == 10
    assert set(intent) == {
        "schema_version", "source_sha256", "source_format", "import_namespace",
        "doc_id", "scope", "owner", "normalizer_version", "chunking_version",
        "doc_protocol", "chunk_protocol", "chunk_policy", "warnings",
    }
    assert "documents" not in intent
    assert "private body sentinel" not in json.dumps({
        "manifest": _thaw(prepared.manifest), "intent": intent,
        "warnings": list(prepared.warnings),
    })


@pytest.mark.parametrize("corruption", ["owner", "schema", "policy", "manifest_digest"])
def test_to_intent_metadata_rejects_invalid_direct_snapshot(
    tmp_path, monkeypatch, corruption
):
    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)
    base = service.prepare_file(str(source), import_namespace="course-1")
    values = _prepared_kwargs(base)
    if corruption == "owner":
        values["owner"] = True
    elif corruption == "schema":
        values["schema_version"] = "unknown-schema"
    elif corruption == "policy":
        values["chunk_policy"]["chunk_size"] = True
    else:
        values["manifest"]["manifest_sha256"] = "0" * 64
    direct = knowledge_ingestion.PreparedIngestion(**values)

    with pytest.raises(ValueError):
        direct.to_intent_metadata()

    assert provider.calls == 0


def test_private_intent_metadata_is_valid_and_deeply_isolated(tmp_path, monkeypatch):
    source, _, _, _, service = _make_test_service(tmp_path, monkeypatch)
    prepared = service.prepare_file(
        str(source), import_namespace="course-1", scope="private", user_id=7
    )

    intent = prepared.to_intent_metadata()
    intent["chunk_policy"]["hard_limit"] = 10
    intent["warnings"].append("caller edit")

    assert intent["owner"] == 7
    assert prepared.owner == 7
    assert prepared.chunk_policy["hard_limit"] == 8192
    assert prepared.warnings == ()


@pytest.mark.parametrize(
    "unsafe_warning",
    ["api_key=FAKE_SECRET", "RuntimeError: upstream returned private body sentinel"],
)
def test_prepared_ingestion_rejects_untrusted_warnings_before_intent_export(
    unsafe_warning,
):
    with pytest.raises(ValueError):
        knowledge_ingestion.PreparedIngestion(
            schema_version="prepared-ingestion-v1",
            source_sha256="source-digest",
            source_format="txt",
            import_namespace="course-1",
            doc_id="doc-fixture",
            scope="global",
            owner=None,
            normalizer_version="doc-norm-1",
            chunking_version="chunk-policy-1",
            doc_protocol="doc-v1",
            chunk_protocol="chunk-v1",
            chunk_policy={"chunk_size": 10, "chunk_overlap": 0, "hard_limit": 10},
            documents=[{
                "content": "fixture content",
                "metadata": {"oversized_hard_limit": False},
            }],
            manifest={},
            warnings=[unsafe_warning],
        )


class _UnconfirmedVectorProvider(IndexProvider):
    """index 返回 None（无法确认写入）的 vector provider（B3-06 对抗）。"""

    name = "vector"

    def index(self, docs):
        return None

    def search(self, query, top_k=5, visibility=None):
        return []

    @property
    def doc_count(self):
        return 0


_AUTO_COUNT = object()


class _RecordingVectorProvider(IndexProvider):
    name = "vector"

    def __init__(self, result=_AUTO_COUNT, mutator=None):
        self.result = result
        self.mutator = mutator
        self.calls = 0
        self.docs = None

    def index(self, docs):
        self.calls += 1
        self.docs = docs
        if self.mutator is not None:
            self.mutator(docs)
        return len(docs) if self.result is _AUTO_COUNT else self.result

    def search(self, query, top_k=5, visibility=None):
        return []

    @property
    def doc_count(self):
        return 0


class _FakeExtractor:
    def __init__(self, result, after_extract=None):
        self.result = result
        self.after_extract = after_extract
        self.calls = 0

    def extract(self, file_path):
        self.calls += 1
        if self.after_extract is not None:
            self.after_extract(file_path)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _FixedChunker:
    def __init__(self, docs_factory):
        self.docs_factory = docs_factory
        self.calls = 0
        self.last_text = None

    def chunk_text(self, text, context, policy=None):
        self.calls += 1
        self.last_text = text
        return self.docs_factory(context)


def _fixture_docs(context, contents=("first chunk", "second chunk")):
    doc_id = "doc-fixture"
    docs = []
    for index, content in enumerate(contents):
        docs.append({
            "content": content,
            "doc_id": doc_id,
            "source": "vector",
            "scope": context.scope,
            "user_id": context.user_id,
            "metadata": {
                "doc_id": doc_id,
                "chunk_id": f"chunk-{index}",
                "chunk_index": index,
                "normalizer_version": "doc-norm-1",
                "chunking_spec_version": context.chunking_spec_version,
                "source_format": context.source_format,
                "source_locator": {"paragraph": index},
                "element_types": ["paragraph"],
            },
        })
    return docs


def _thaw(value):
    if hasattr(value, "items"):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _prepared_kwargs(prepared):
    return {item.name: _thaw(getattr(prepared, item.name)) for item in fields(prepared)}


def _make_test_service(
    tmp_path,
    monkeypatch,
    *,
    text="first chunk\n\nsecond chunk",
    docs_factory=_fixture_docs,
    provider_result=_AUTO_COUNT,
    after_extract=None,
):
    source = tmp_path / "lesson.txt"
    source.write_bytes(b"source bytes")
    extractor = _FakeExtractor(text, after_extract=after_extract)
    monkeypatch.setattr(knowledge_ingestion, "get_extractor", lambda path: extractor)
    chunker = _FixedChunker(docs_factory)
    provider = _RecordingVectorProvider(result=provider_result)
    service = KnowledgeIngestionService(
        RAGCoordinator(vector_provider=provider), chunker=chunker
    )
    return source, extractor, chunker, provider, service


class _OversizedStubChunker:
    """产出带 oversized_hard_limit 标记 docs 的 chunker 桩（B3-04 上浮测试）。"""

    def chunk_text(self, text, context, policy=None):
        doc_id, _ = compute_doc_id(context.import_namespace, text)
        return [{
            "content": text,
            "doc_id": doc_id,
            "source": "vector",
            "scope": context.scope,
            "user_id": context.user_id,
            "metadata": {
                "doc_id": doc_id,
                "chunk_id": "chunk-oversized",
                "chunk_index": 0,
                "chunking_spec_version": context.chunking_spec_version,
                "normalizer_version": "doc-norm-1",
                "source_format": context.source_format,
                "source_locator": {},
                "oversized_hard_limit": True,
            },
        }]


def test_ingest_file_indexes_chunk_documents(tmp_path: Path):
    source = tmp_path / "lesson.txt"
    source.write_text("第一段知识。\n\n第二段知识。", encoding="utf-8")
    coordinator = RAGCoordinator()
    result = KnowledgeIngestionService(coordinator).ingest_file(
        str(source), import_namespace="course-1"
    )

    assert result.status == "ok"
    assert result.planned_chunk_count == result.written_chunk_count == 1
    chunk = coordinator.search("第一段", sources=["vector"]).chunks[0]
    assert chunk.metadata["doc_id"] == result.doc_id
    assert chunk.metadata["chunk_id"]


def test_ingest_file_rejects_empty_namespace(tmp_path: Path):
    source = tmp_path / "lesson.txt"
    source.write_text("知识", encoding="utf-8")

    with pytest.raises(ValueError, match="import_namespace"):
        KnowledgeIngestionService(RAGCoordinator()).ingest_file(
            str(source), import_namespace=""
        )


def test_ingest_file_reports_unsupported(tmp_path: Path):
    source = tmp_path / "lesson.unknown"
    source.write_text("知识", encoding="utf-8")

    result = KnowledgeIngestionService(RAGCoordinator()).ingest_file(
        str(source), import_namespace="course-1"
    )
    assert result.status == "unsupported"


@pytest.mark.parametrize(
    ("scope", "user_id", "message"),
    [
        ("private", None, "private"),
        ("global", 1, "global"),
        ("shared", None, "scope"),
    ],
)
def test_ingest_file_rejects_noncanonical_scope_owner(
    tmp_path: Path, scope: str, user_id: int | None, message: str
):
    source = tmp_path / "lesson.txt"
    source.write_text("知识", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        KnowledgeIngestionService(RAGCoordinator()).ingest_file(
            str(source),
            import_namespace="course-1",
            scope=scope,
            user_id=user_id,
        )


# ===== B3-06：写入确认，provider 无法确认时不报成功 =====


def test_ingest_reports_unconfirmed_when_provider_returns_none(tmp_path: Path):
    source = tmp_path / "lesson.txt"
    source.write_text("第一段知识。\n\n第二段知识。", encoding="utf-8")
    coordinator = RAGCoordinator(vector_provider=_UnconfirmedVectorProvider())

    result = KnowledgeIngestionService(coordinator).ingest_file(
        str(source), import_namespace="course-1"
    )

    assert isinstance(result, IngestResult)
    assert result.status == "index_unconfirmed"
    assert result.planned_chunk_count == 1
    assert result.written_chunk_count == 0
    assert any("未确认" in warning for warning in result.warnings)


def test_ingest_confirms_written_count_from_provider(tmp_path: Path):
    source = tmp_path / "lesson.txt"
    source.write_text("第一段知识。\n\n第二段知识。", encoding="utf-8")
    coordinator = RAGCoordinator()

    result = KnowledgeIngestionService(coordinator).ingest_file(
        str(source), import_namespace="course-1"
    )

    assert result.status == "ok"
    assert result.planned_chunk_count == result.written_chunk_count == 1
    assert result.warnings == []


def test_ingest_file_does_not_treat_boolean_as_confirmed_integer(tmp_path: Path):
    source = tmp_path / "lesson.txt"
    source.write_text("第一段知识。", encoding="utf-8")
    provider = _RecordingVectorProvider(result=True)
    coordinator = RAGCoordinator(vector_provider=provider)

    result = KnowledgeIngestionService(coordinator).ingest_file(
        str(source), import_namespace="course-1"
    )

    assert result.status == "index_unconfirmed"
    assert result.planned_chunk_count == 1
    assert result.written_chunk_count == 0
    assert "写入未确认，计数0不代表已确认零写入" in result.warnings


# ===== B3-04：超 hard_limit 的 atomic 块以 warning 上浮（不切裂）=====


def test_ingest_surfaces_oversized_hard_limit_warning(tmp_path: Path):
    source = tmp_path / "table.txt"
    source.write_text("超长表格内容", encoding="utf-8")
    coordinator = RAGCoordinator()
    service = KnowledgeIngestionService(coordinator, chunker=_OversizedStubChunker())

    result = service.ingest_file(str(source), import_namespace="course-1")

    assert result.status == "ok"
    assert len(result.warnings) == 1
    assert "hard_limit" in result.warnings[0]
    assert result.written_chunk_count == 1


def test_prepare_file_has_no_index_side_effect(tmp_path, monkeypatch):
    source, extractor, chunker, provider, service = _make_test_service(
        tmp_path, monkeypatch
    )

    prepared = service.prepare_file(str(source), import_namespace="course-1")

    assert isinstance(prepared, knowledge_ingestion.PreparedIngestion)
    assert provider.calls == 0
    assert extractor.calls == 1
    assert chunker.calls == 1


def test_prepare_file_extracts_and_chunks_once(tmp_path, monkeypatch):
    source, extractor, chunker, provider, service = _make_test_service(
        tmp_path, monkeypatch
    )

    prepared = service.prepare_file(str(source), import_namespace="course-1")

    assert prepared.doc_id == "doc-fixture"
    assert len(prepared.documents) == 2
    assert extractor.calls == 1
    assert chunker.calls == 1
    assert provider.calls == 0


def test_prepare_file_rejects_source_change(tmp_path, monkeypatch):
    def change_source(file_path):
        Path(file_path).write_bytes(b"changed source bytes")

    source, _, chunker, provider, service = _make_test_service(
        tmp_path, monkeypatch, after_extract=change_source
    )

    with pytest.raises(knowledge_ingestion.IngestionPreparationError) as raised:
        service.prepare_file(str(source), import_namespace="course-1")

    assert raised.value.status == "invalid_request"
    assert raised.value.safe_summary == "摄入参数无效"
    assert chunker.calls == 1
    assert provider.calls == 0


def test_prepare_snapshot_is_deeply_immutable_and_isolated(tmp_path, monkeypatch):
    source_docs = []

    def docs_factory(context):
        docs = _fixture_docs(context)
        source_docs.extend(docs)
        return docs

    source, _, _, _, service = _make_test_service(
        tmp_path, monkeypatch, docs_factory=docs_factory
    )
    prepared = service.prepare_file(str(source), import_namespace="course-1")
    original_locator = _thaw(prepared.documents[0]["metadata"]["source_locator"])

    source_docs[0]["content"] = "mutated after preparation"
    source_docs[0]["metadata"]["source_locator"]["paragraph"] = 99

    assert prepared.documents[0]["content"] == "first chunk"
    assert _thaw(prepared.documents[0]["metadata"]["source_locator"]) == original_locator
    with pytest.raises(TypeError):
        prepared.documents[0]["metadata"]["source_locator"]["paragraph"] = 3
    with pytest.raises(TypeError):
        prepared.manifest["rows"][0]["source_locator"]["paragraph"] = 3
    with pytest.raises(TypeError):
        prepared.chunk_policy["chunk_size"] = 1

    intent = prepared.to_intent_metadata()
    intent["chunk_policy"]["chunk_size"] = 1
    intent["warnings"].append("changed")
    assert prepared.chunk_policy["chunk_size"] == 500
    assert prepared.warnings == ()


def test_prepared_manifest_matches_canonical_rows(tmp_path, monkeypatch):
    def fixed_docs(context):
        return [{
            "content": "fixture content",
            "doc_id": "doc-fixture",
            "source": "vector",
            "scope": context.scope,
            "user_id": context.user_id,
            "metadata": {
                "doc_id": "doc-fixture",
                "chunk_id": "chunk-0",
                "chunk_index": 0,
                "normalizer_version": "doc-norm-1",
                "chunking_spec_version": context.chunking_spec_version,
                "source_format": context.source_format,
                "source_locator": {"paragraph": 0},
            },
        }]

    source, _, _, _, service = _make_test_service(
        tmp_path, monkeypatch, docs_factory=fixed_docs
    )
    prepared = service.prepare_file(str(source), import_namespace="course-1")
    expected_row = {
        "doc_id": "doc-fixture",
        "chunk_id": "chunk-0",
        "content_sha256": "77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a",
        "chunk_index": 0,
        "scope": "global",
        "owner": None,
        "source_locator": {"paragraph": 0},
    }

    assert hashlib.sha256(b"fixture content").hexdigest() == (
        "77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a"
    )
    assert _thaw(prepared.manifest["rows"]) == [expected_row]
    assert prepared.manifest["manifest_sha256"] == (
        "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
    )

    def canonical(value):
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def oracle(rows):
        ordered = sorted(rows, key=canonical)
        return hashlib.sha256(canonical(ordered)).hexdigest()

    def reordered_docs(context):
        docs = _fixture_docs(context, contents=("中文内容甲", "中文内容乙"))
        docs[0]["metadata"]["chunk_id"] = "z-row"
        docs[0]["metadata"]["source_locator"] = {"z": "中文", "a": {"n": 1}}
        docs[1]["metadata"]["chunk_id"] = "a-row"
        docs[1]["metadata"]["source_locator"] = {"a": {"n": 2}, "z": "文本"}
        return docs

    source2, _, _, _, service2 = _make_test_service(
        tmp_path, monkeypatch, docs_factory=reordered_docs
    )
    prepared2 = service2.prepare_file(str(source2), import_namespace="course-1")
    rows = _thaw(prepared2.manifest["rows"])
    canonical_rows = [canonical(row) for row in rows]
    assert [row["chunk_index"] for row in rows] == [0, 1]
    assert canonical_rows != sorted(canonical_rows)
    assert prepared2.manifest["manifest_sha256"] == oracle(rows)
    assert oracle(rows) == oracle(list(reversed(rows)))
    duplicated = [rows[0], rows[1], rows[0]]
    assert knowledge_ingestion._manifest_sha256(duplicated) == oracle(duplicated)
    assert oracle(duplicated) != oracle(rows)

    intent = prepared2.to_intent_metadata()
    expected_keys = {
        "schema_version", "source_sha256", "source_format", "import_namespace",
        "doc_id", "scope", "owner", "normalizer_version", "chunking_version",
        "doc_protocol", "chunk_protocol", "chunk_policy", "warnings",
    }
    assert set(intent) == expected_keys
    serialized = json.dumps(
        {"manifest": _thaw(prepared2.manifest), "intent": intent,
         "warnings": list(prepared2.warnings)},
        ensure_ascii=False,
    )
    assert "中文内容甲" not in serialized
    assert "中文内容乙" not in serialized


@pytest.mark.parametrize(
    "corruption",
    [
        "manifest_digest", "source_digest", "identity", "chunk_index",
        "duplicate_chunk_id", "scope_owner", "version", "locator", "content",
        "row_owner_bool", "chunk_index_bool", "locator_bool", "locator_float",
        "warnings_api_key", "warnings_exception",
    ],
)
def test_ingest_prepared_rejects_inconsistent_snapshot(
    tmp_path, monkeypatch, corruption
):
    scope = "private" if corruption == "row_owner_bool" else "global"
    user_id = 1 if scope == "private" else None

    def numeric_locator_docs(context):
        docs = _fixture_docs(context)
        for doc in docs:
            doc["metadata"]["source_locator"] = {"paragraph": 1}
        return docs

    docs_factory = (
        numeric_locator_docs
        if corruption in {"locator_bool", "locator_float"}
        else _fixture_docs
    )
    source, _, _, provider, service = _make_test_service(
        tmp_path, monkeypatch, docs_factory=docs_factory
    )
    prepared = service.prepare_file(
        str(source), import_namespace="course-1", scope=scope, user_id=user_id
    )
    values = _prepared_kwargs(prepared)
    docs = values["documents"]
    manifest = values["manifest"]

    if corruption == "manifest_digest":
        manifest["manifest_sha256"] = "0" * 64
    elif corruption == "source_digest":
        values["source_sha256"] = "invalid"
    elif corruption == "identity":
        values["doc_id"] = "different-doc"
    elif corruption == "chunk_index":
        docs[0]["metadata"]["chunk_index"] = 1
    elif corruption == "duplicate_chunk_id":
        docs[1]["metadata"]["chunk_id"] = docs[0]["metadata"]["chunk_id"]
    elif corruption == "scope_owner":
        values["scope"] = "private"
        values["owner"] = 9
    elif corruption == "version":
        values["chunking_version"] = "different-policy"
    elif corruption == "locator":
        docs[0]["metadata"]["source_locator"] = {0: "not a JSON object key"}
    elif corruption == "warnings":
        values["warnings"] = ["private body sentinel"]
    elif corruption == "row_owner_bool":
        manifest["rows"][0]["owner"] = True
    elif corruption == "chunk_index_bool":
        manifest["rows"][0]["chunk_index"] = False
    elif corruption == "locator_bool":
        manifest["rows"][0]["source_locator"]["paragraph"] = True
    elif corruption == "locator_float":
        manifest["rows"][0]["source_locator"]["paragraph"] = 1.0
    elif corruption == "warnings_api_key":
        values["warnings"] = ["api_key=FAKE_SECRET"]
    elif corruption == "warnings_exception":
        values["warnings"] = ["RuntimeError: upstream returned private body sentinel"]
    else:
        docs[0]["content"] = "changed content"

    values["documents"] = docs
    values["manifest"] = manifest
    with pytest.raises(ValueError):
        corrupted = knowledge_ingestion.PreparedIngestion(**values)
        service.ingest_prepared(corrupted)

    assert provider.calls == 0


def test_ingest_file_delegates_once(tmp_path, monkeypatch):
    source, _, _, _, service = _make_test_service(tmp_path, monkeypatch)
    prepared = SimpleNamespace()
    expected_result = IngestResult(status="ok")
    calls = {"prepare": 0, "ingest": 0}

    def prepare(*args, **kwargs):
        calls["prepare"] += 1
        return prepared

    def ingest(value):
        calls["ingest"] += 1
        assert value is prepared
        return expected_result

    monkeypatch.setattr(service, "prepare_file", prepare, raising=False)
    monkeypatch.setattr(service, "ingest_prepared", ingest, raising=False)

    result = service.ingest_file(str(source), import_namespace="course-1")

    assert result is expected_result
    assert calls == {"prepare": 1, "ingest": 1}


@pytest.mark.parametrize(
    ("provider_result", "expected_status", "expected_written"),
    [
        (None, "index_unconfirmed", 0),
        (True, "index_unconfirmed", 0),
        (False, "index_unconfirmed", 0),
        (1.0, "index_unconfirmed", 0),
        (-1, "index_unconfirmed", 0),
        (0, "index_unconfirmed", 0),
        (1, "index_unconfirmed", 1),
        (3, "index_unconfirmed", 0),
        (2, "ok", 2),
    ],
)
def test_ingest_prepared_requires_confirmed_integer_count(
    tmp_path, monkeypatch, provider_result, expected_status, expected_written
):
    source, _, _, provider, service = _make_test_service(
        tmp_path, monkeypatch, provider_result=provider_result
    )
    prepared = service.prepare_file(str(source), import_namespace="course-1")

    result = service.ingest_prepared(prepared)

    assert result.status == expected_status
    assert result.planned_chunk_count == 2
    assert result.written_chunk_count == expected_written
    assert provider.calls == 1
    if expected_status == "index_unconfirmed":
        assert "写入未确认，计数0不代表已确认零写入" in result.warnings


def test_ingest_prepared_does_not_reextract(tmp_path, monkeypatch):
    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)
    prepared = service.prepare_file(str(source), import_namespace="course-1")

    def unexpected_extraction(path):
        raise AssertionError("ingest_prepared must consume the prepared snapshot")

    monkeypatch.setattr(knowledge_ingestion, "get_extractor", unexpected_extraction)

    result = service.ingest_prepared(prepared)

    assert result.status == "ok"
    assert provider.calls == 1


def test_ingest_prepared_provider_mutation_does_not_change_snapshot(tmp_path, monkeypatch):
    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)
    prepared = service.prepare_file(str(source), import_namespace="course-1")
    original_doc = _thaw(prepared.documents[0])

    def mutate_provider_docs(docs):
        docs[0]["content"] = "provider mutation"
        docs[0]["metadata"]["source_locator"]["paragraph"] = 99

    provider.mutator = mutate_provider_docs
    result = service.ingest_prepared(prepared)

    assert result.status == "ok"
    assert _thaw(prepared.documents[0]) == original_doc


@pytest.mark.parametrize(
    ("scope", "user_id"),
    [
        ("private", 0), ("private", -1), ("private", True),
        ("private", 1.5), ("private", "1"), ("global", False),
    ],
)
def test_prepare_file_rejects_invalid_owner(tmp_path, monkeypatch, scope, user_id):
    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        service.prepare_file(
            str(source), import_namespace="course-1", scope=scope, user_id=user_id
        )

    assert provider.calls == 0


def test_prepare_file_rejects_boolean_private_chunk_owner(tmp_path, monkeypatch):
    def boolean_owner_docs(context):
        docs = _fixture_docs(context)
        for doc in docs:
            doc["user_id"] = True
        return docs

    source, _, _, provider, service = _make_test_service(
        tmp_path, monkeypatch, docs_factory=boolean_owner_docs
    )

    with pytest.raises(ValueError):
        service.prepare_file(
            str(source), import_namespace="course-1", scope="private", user_id=1
        )

    assert provider.calls == 0


@pytest.mark.parametrize(
    "policy",
    [
        ChunkPolicy(chunk_size=True, chunk_overlap=0, hard_limit=8192),
        ChunkPolicy(chunk_size=2.5, chunk_overlap=0, hard_limit=8192),
        ChunkPolicy(chunk_size=10, chunk_overlap=0.5, hard_limit=8192),
        ChunkPolicy(chunk_size=1, chunk_overlap=0, hard_limit=True),
    ],
)
def test_prepare_file_rejects_non_integer_policy_fields(tmp_path, monkeypatch, policy):
    source, _, _, _, service = _make_test_service(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        service.prepare_file(str(source), import_namespace="course-1", policy=policy)


def test_prepare_file_accepts_zero_overlap(tmp_path, monkeypatch):
    policy = ChunkPolicy(chunk_size=10, chunk_overlap=0, hard_limit=10)
    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)

    prepared = service.prepare_file(
        str(source), import_namespace="course-1", policy=policy
    )

    assert prepared.chunk_policy == {
        "chunk_size": 10, "chunk_overlap": 0, "hard_limit": 10
    }
    assert provider.calls == 0


@pytest.mark.parametrize(
    ("file_path", "extractor", "namespace", "status", "summary"),
    [
        ("lesson.unknown", None, "course-1", "unsupported", "不支持的文档格式"),
        ("lesson.txt", _FakeExtractor(""), "course-1", "extraction_empty", "未提取到可用文本"),
        ("lesson.txt", _FakeExtractor("text"), "", "invalid_request", "摄入参数无效"),
    ],
)
def test_preparation_error_has_exact_safe_status_and_summary(
    tmp_path, monkeypatch, file_path, extractor, namespace, status, summary
):
    source = tmp_path / file_path
    source.write_bytes(b"source bytes")
    monkeypatch.setattr(knowledge_ingestion, "get_extractor", lambda path: extractor)
    provider = _RecordingVectorProvider()
    service = KnowledgeIngestionService(
        RAGCoordinator(vector_provider=provider), chunker=_FixedChunker(_fixture_docs)
    )

    with pytest.raises(knowledge_ingestion.IngestionPreparationError) as raised:
        service.prepare_file(str(source), import_namespace=namespace)

    assert raised.value.status == status
    assert raised.value.safe_summary == summary
    assert provider.calls == 0


def test_ingest_file_maps_preparation_errors_and_preserves_unknown_errors(
    tmp_path, monkeypatch
):
    source, _, _, provider, service = _make_test_service(
        tmp_path, monkeypatch, text=""
    )
    result = service.ingest_file(str(source), import_namespace="course-1")
    assert result.status == "extraction_empty"
    assert provider.calls == 0

    unknown = RuntimeError("extractor internal failure")
    extractor = _FakeExtractor(unknown)
    monkeypatch.setattr(knowledge_ingestion, "get_extractor", lambda path: extractor)
    with pytest.raises(RuntimeError) as raised:
        service.ingest_file(str(source), import_namespace="course-1")
    assert raised.value is unknown
    assert provider.calls == 0
