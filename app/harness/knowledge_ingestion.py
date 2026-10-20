"""新增通用文档 Gate 0 的薄摄入编排。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.harness.chunking_service import ChunkingContext, ChunkingService, ChunkPolicy
from app.infrastructure.rag.coordinator import RAGCoordinator
from app.infrastructure.rag.extractors.base import get_extractor


@dataclass(frozen=True)
class IngestResult:
    status: str
    doc_id: str | None = None
    planned_chunk_count: int = 0
    written_chunk_count: int = 0
    warnings: list[str] = field(default_factory=list)


class KnowledgeIngestionService:
    """extract → adapt → chunk → index 的薄编排；不接管 OCR/Code 专用路径。"""

    def __init__(
        self,
        coordinator: RAGCoordinator,
        chunker: ChunkingService | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._chunker = chunker or ChunkingService()

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
        if not import_namespace:
            raise ValueError("import_namespace 不得为空")
        if scope == "global" and user_id is not None:
            raise ValueError("global 摄入必须使用 user_id=None")
        if scope == "private" and user_id is None:
            raise ValueError("private 摄入必须提供 user_id")
        if scope not in {"global", "private"}:
            raise ValueError("scope 仅支持 global 或 private")
        extractor = get_extractor(file_path)
        if extractor is None:
            return IngestResult(status="unsupported")
        text = extractor.extract(file_path)
        if not text:
            return IngestResult(status="extraction_empty")
        context = ChunkingContext(
            import_namespace=import_namespace,
            source_format=Path(file_path).suffix.lower().lstrip("."),
            scope=scope,
            user_id=user_id,
            source_locator={"file_path": file_path},
            chunking_spec_version=chunking_spec_version,
        )
        docs = self._chunker.chunk_text(text, context, policy)
        if not docs:
            return IngestResult(status="extraction_empty")
        warnings = [
            f"chunk_index={doc['metadata']['chunk_index']} 超过 embedding 安全阈值"
            "（hard_limit），已整块保留（atomic 不切裂）"
            for doc in docs
            if doc["metadata"].get("oversized_hard_limit")
        ]
        for doc in docs:
            metadata = doc["metadata"]
            if doc["doc_id"] != metadata["doc_id"] or not metadata["chunk_id"]:
                raise ValueError("ChunkDocument provenance 校验失败")
            json.dumps(metadata)
        written = self._coordinator.index_documents(docs, source="vector")
        if written != len(docs):
            # B3-06：不得仅以 planned 推断 written；未确认时返回明确非成功状态。
            warnings.append(f"provider 写入未确认：written={written}")
            return IngestResult(
                status="index_unconfirmed",
                doc_id=docs[0]["doc_id"],
                planned_chunk_count=len(docs),
                written_chunk_count=written or 0,
                warnings=warnings,
            )
        return IngestResult(
            status="ok",
            doc_id=docs[0]["doc_id"],
            planned_chunk_count=len(docs),
            written_chunk_count=written,
            warnings=warnings,
        )
