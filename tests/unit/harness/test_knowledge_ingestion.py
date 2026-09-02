from pathlib import Path

import pytest

from app.harness.chunking_service import compute_doc_id
from app.harness.knowledge_ingestion import IngestResult, KnowledgeIngestionService
from app.infrastructure.rag.coordinator import IndexProvider, RAGCoordinator


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
