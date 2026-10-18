# T02 working-tree review package
BASE: 6324b9442b6f1671ccb4a19cdacb42bb91597187
No new commits; six tracked task files. Snapshot after ingestion 62-pass report; implementer finishing lint/integration evidence.

diff --git a/app/harness/knowledge_ingestion.py b/app/harness/knowledge_ingestion.py
index 3620249..bd20c0c 100644
--- a/app/harness/knowledge_ingestion.py
+++ b/app/harness/knowledge_ingestion.py
@@ -1,98 +1,531 @@
 """新增通用文档 Gate 0 的薄摄入编排。"""
 
 from __future__ import annotations
 
 import json
+import hashlib
+import math
+from collections.abc import Mapping
 from dataclasses import dataclass, field
+from types import MappingProxyType
 from pathlib import Path
 from typing import Any
 
-from app.harness.chunking_service import ChunkingContext, ChunkingService, ChunkPolicy
+from app.harness.chunking_service import (
+    CHUNK_PROTOCOL,
+    DOC_PROTOCOL,
+    NORMALIZER_VERSION,
+    ChunkingContext,
+    ChunkingService,
+    ChunkPolicy,
+)
 from app.infrastructure.rag.coordinator import RAGCoordinator
 from app.infrastructure.rag.extractors.base import get_extractor
 
 
 @dataclass(frozen=True)
 class IngestResult:
     status: str
     doc_id: str | None = None
     planned_chunk_count: int = 0
     written_chunk_count: int = 0
     warnings: list[str] = field(default_factory=list)
 
 
+_PREPARATION_SUMMARIES = {
+    "unsupported": "不支持的文档格式",
+    "extraction_empty": "未提取到可用文本",
+    "invalid_request": "摄入参数无效",
+}
+
+
+class IngestionPreparationError(ValueError):
+    """仅携带冻结状态与安全摘要的准备阶段错误。"""
+
+    def __init__(self, status: str, field_name: str | None = None) -> None:
+        if status not in _PREPARATION_SUMMARIES:
+            raise ValueError("未知的准备阶段错误状态")
+        self.status = status
+        self.safe_summary = _PREPARATION_SUMMARIES[status]
+        # 只允许内部固定字段名帮助兼容旧调用方，不接纳路径、正文或错误原文。
+        safe_fields = {
+            "import_namespace", "scope", "user_id", "chunking_spec_version", "policy",
+            "global", "private",
+        }
+        suffix = f" ({field_name})" if field_name in safe_fields else ""
+        super().__init__(f"{self.safe_summary}{suffix}")
+
+
+def _freeze_json(value: Any) -> Any:
+    """递归复制 JSON 值并冻结映射、数组；拒绝非 JSON 与非有限数。"""
+    if isinstance(value, Mapping):
+        if any(not isinstance(key, str) for key in value):
+            raise ValueError("JSON 对象键必须为字符串")
+        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
+    if isinstance(value, (list, tuple)):
+        return tuple(_freeze_json(item) for item in value)
+    if value is None or isinstance(value, (str, bool, int)):
+        return value
+    if isinstance(value, float) and math.isfinite(value):
+        return value
+    raise ValueError("值必须是严格 JSON 数据")
+
+
+def _thaw_json(value: Any) -> Any:
+    """将冻结 JSON 值递归复制为彼此隔离的普通 dict/list。"""
+    if isinstance(value, Mapping):
+        return {key: _thaw_json(item) for key, item in value.items()}
+    if isinstance(value, tuple):
+        return [_thaw_json(item) for item in value]
+    return value
+
+
+def _canonical_json(value: Any) -> bytes:
+    """序列化冻结契约规定的规范 JSON 字节。"""
+    return json.dumps(
+        _thaw_json(value),
+        sort_keys=True,
+        ensure_ascii=False,
+        separators=(",", ":"),
+        allow_nan=False,
+    ).encode("utf-8")
+
+
+def _manifest_sha256(rows: list[dict[str, Any]] | tuple[Any, ...]) -> str:
+    """按完整规范行字节排序，保留重复行后计算 prepared-manifest 摘要。"""
+    ordered_rows = [json.loads(row_bytes) for row_bytes in sorted(
+        _canonical_json(row) for row in rows
+    )]
+    return hashlib.sha256(_canonical_json(ordered_rows)).hexdigest()
+
+
+def _safe_warnings(documents: Any) -> tuple[str, ...]:
+    """仅从合法的 oversized 标记生成固定、无正文的产品 warning。"""
+    if not isinstance(documents, (list, tuple)):
+        raise ValueError("prepared warnings 无效")
+    warnings = []
+    for doc in documents:
+        if not isinstance(doc, Mapping) or not isinstance(doc.get("metadata"), Mapping):
+            raise ValueError("prepared warnings 无效")
+        metadata = doc["metadata"]
+        if "oversized_hard_limit" not in metadata:
+            continue
+        oversized = metadata["oversized_hard_limit"]
+        if not isinstance(oversized, bool):
+            raise ValueError("prepared warnings 无效")
+        if not oversized:
+            continue
+        chunk_index = metadata.get("chunk_index")
+        if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
+            raise ValueError("prepared warnings 无效")
+        warnings.append(
+            f"chunk_index={chunk_index} 超过 embedding 安全阈值"
+            "（hard_limit），已整块保留（atomic 不切裂）"
+        )
+    return tuple(warnings)
+
+
+@dataclass(frozen=True)
+class PreparedIngestion:
+    """不含运行绑定的摄入快照；所有可变输入在构造时深复制并冻结。"""
+
+    schema_version: str
+    source_sha256: str
+    source_format: str
+    import_namespace: str
+    doc_id: str
+    scope: str
+    owner: int | None
+    normalizer_version: str
+    chunking_version: str
+    doc_protocol: str
+    chunk_protocol: str
+    chunk_policy: Mapping[str, int]
+    documents: tuple[Mapping[str, Any], ...]
+    manifest: Mapping[str, Any]
+    warnings: tuple[str, ...]
+
+    def __post_init__(self) -> None:
+        for name in ("owner", "chunk_policy", "documents", "manifest", "warnings"):
+            object.__setattr__(self, name, _freeze_json(getattr(self, name)))
+        if (
+            not isinstance(self.warnings, tuple)
+            or any(not isinstance(warning, str) for warning in self.warnings)
+            or self.warnings != _safe_warnings(self.documents)
+        ):
+            raise ValueError("prepared warnings 无效")
+
+    def to_intent_metadata(self) -> dict[str, Any]:
+        """返回不含正文、且与快照相互隔离的 JSON 元数据副本。"""
+        if self.warnings != _safe_warnings(self.documents):
+            raise ValueError("prepared warnings 无效")
+        keys = (
+            "schema_version", "source_sha256", "source_format", "import_namespace",
+            "doc_id", "scope", "owner", "normalizer_version", "chunking_version",
+            "doc_protocol", "chunk_protocol", "chunk_policy", "warnings",
+        )
+        result = {key: _thaw_json(getattr(self, key)) for key in keys}
+        result["warnings"] = list(result["warnings"])
+        return result
+
+
 class KnowledgeIngestionService:
     """extract → adapt → chunk → index 的薄编排；不接管 OCR/Code 专用路径。"""
 
     def __init__(
         self,
         coordinator: RAGCoordinator,
         chunker: ChunkingService | None = None,
     ) -> None:
         self._coordinator = coordinator
         self._chunker = chunker or ChunkingService()
 
-    def ingest_file(
+    @staticmethod
+    def _warnings_for_documents(documents: list[dict[str, Any]]) -> list[str]:
+        return list(_safe_warnings(documents))
+
+    def prepare_file(
         self,
         file_path: str,
         *,
         import_namespace: str,
         scope: str = "global",
         user_id: int | None = None,
         chunking_spec_version: str = "chunk-policy-1",
         policy: ChunkPolicy | None = None,
-    ) -> IngestResult:
-        if not import_namespace:
-            raise ValueError("import_namespace 不得为空")
-        if scope == "global" and user_id is not None:
-            raise ValueError("global 摄入必须使用 user_id=None")
-        if scope == "private" and user_id is None:
-            raise ValueError("private 摄入必须提供 user_id")
-        if scope not in {"global", "private"}:
-            raise ValueError("scope 仅支持 global 或 private")
+    ) -> PreparedIngestion:
+        """提取并切块一次，交付不可变快照；本阶段不做 embedding 或写入。"""
+        if not isinstance(file_path, str) or not file_path:
+            raise IngestionPreparationError("invalid_request")
+        if not isinstance(import_namespace, str) or not import_namespace:
+            raise IngestionPreparationError("invalid_request", "import_namespace")
+        if not isinstance(chunking_spec_version, str) or not chunking_spec_version:
+            raise IngestionPreparationError("invalid_request", "chunking_spec_version")
+        if scope == "global":
+            if user_id is not None:
+                raise IngestionPreparationError("invalid_request", "global")
+            owner = None
+        elif scope == "private":
+            if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
+                raise IngestionPreparationError("invalid_request", "private")
+            owner = user_id
+        else:
+            raise IngestionPreparationError("invalid_request", "scope")
+
+        active_policy = policy if policy is not None else ChunkPolicy()
+        if not isinstance(active_policy, ChunkPolicy):
+            raise IngestionPreparationError("invalid_request", "policy")
+        policy_values = {
+            "chunk_size": active_policy.chunk_size,
+            "chunk_overlap": active_policy.chunk_overlap,
+            "hard_limit": active_policy.hard_limit,
+        }
+        if any(
+            isinstance(value, bool) or not isinstance(value, int)
+            for value in policy_values.values()
+        ):
+            raise IngestionPreparationError("invalid_request", "policy")
+        chunk_size = policy_values["chunk_size"]
+        overlap = policy_values["chunk_overlap"]
+        hard_limit = policy_values["hard_limit"]
+        if chunk_size <= 0 or not 0 <= overlap < chunk_size or hard_limit < chunk_size:
+            raise IngestionPreparationError("invalid_request", "policy")
+
+        source_path = Path(file_path)
+        source_format = source_path.suffix.lower().lstrip(".")
         extractor = get_extractor(file_path)
         if extractor is None:
-            return IngestResult(status="unsupported")
+            raise IngestionPreparationError("unsupported")
+
+        source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
         text = extractor.extract(file_path)
-        if not text:
-            return IngestResult(status="extraction_empty")
         context = ChunkingContext(
             import_namespace=import_namespace,
-            source_format=Path(file_path).suffix.lower().lstrip("."),
+            source_format=source_format,
             scope=scope,
             user_id=user_id,
             source_locator={"file_path": file_path},
             chunking_spec_version=chunking_spec_version,
         )
-        docs = self._chunker.chunk_text(text, context, policy)
-        if not docs:
-            return IngestResult(status="extraction_empty")
-        warnings = [
-            f"chunk_index={doc['metadata']['chunk_index']} 超过 embedding 安全阈值"
-            "（hard_limit），已整块保留（atomic 不切裂）"
-            for doc in docs
-            if doc["metadata"].get("oversized_hard_limit")
-        ]
-        for doc in docs:
-            metadata = doc["metadata"]
-            if doc["doc_id"] != metadata["doc_id"] or not metadata["chunk_id"]:
+        documents = (
+            self._chunker.chunk_text(text, context, active_policy)
+            if isinstance(text, str) and text
+            else []
+        )
+        if hashlib.sha256(source_path.read_bytes()).hexdigest() != source_sha256:
+            raise IngestionPreparationError("invalid_request")
+        if not text:
+            raise IngestionPreparationError("extraction_empty")
+        if not isinstance(text, str):
+            raise IngestionPreparationError("invalid_request")
+        if not documents:
+            raise IngestionPreparationError("extraction_empty")
+
+        rows = self._build_manifest_rows(
+            documents,
+            doc_id=documents[0].get("doc_id"),
+            scope=scope,
+            owner=owner,
+            source_format=source_format,
+            chunking_spec_version=chunking_spec_version,
+        )
+        doc_id = rows[0]["doc_id"]
+        manifest = {
+            "schema_version": "prepared-manifest-v1",
+            "doc_id": doc_id,
+            "rows": rows,
+            "row_count": len(rows),
+            "manifest_sha256": _manifest_sha256(rows),
+        }
+        warnings = self._warnings_for_documents(documents)
+        return PreparedIngestion(
+            schema_version="prepared-ingestion-v1",
+            source_sha256=source_sha256,
+            source_format=source_format,
+            import_namespace=import_namespace,
+            doc_id=doc_id,
+            scope=scope,
+            owner=owner,
+            normalizer_version=NORMALIZER_VERSION,
+            chunking_version=chunking_spec_version,
+            doc_protocol=DOC_PROTOCOL,
+            chunk_protocol=CHUNK_PROTOCOL,
+            chunk_policy=policy_values,
+            documents=documents,
+            manifest=manifest,
+            warnings=warnings,
+        )
+
+    @staticmethod
+    def _build_manifest_rows(
+        documents: list[dict[str, Any]],
+        *,
+        doc_id: Any,
+        scope: str,
+        owner: int | None,
+        source_format: str,
+        chunking_spec_version: str,
+    ) -> list[dict[str, Any]]:
+        if not isinstance(doc_id, str) or not doc_id or not documents:
+            raise ValueError("ChunkDocument 身份或数量无效")
+        if scope == "global":
+            if owner is not None:
+                raise ValueError("ChunkDocument owner 与 scope 不一致")
+        elif scope == "private":
+            if isinstance(owner, bool) or not isinstance(owner, int) or owner <= 0:
+                raise ValueError("ChunkDocument owner 与 scope 不一致")
+        else:
+            raise ValueError("ChunkDocument scope 无效")
+        rows: list[dict[str, Any]] = []
+        seen_chunk_ids: set[str] = set()
+        for expected_index, doc in enumerate(documents):
+            if not isinstance(doc, Mapping):
+                raise ValueError("ChunkDocument 格式无效")
+            metadata = doc.get("metadata")
+            if not isinstance(metadata, Mapping):
+                raise ValueError("ChunkDocument metadata 无效")
+            chunk_index = metadata.get("chunk_index")
+            chunk_id = metadata.get("chunk_id")
+            content = doc.get("content")
+            document_owner = doc.get("user_id")
+            source_locator = metadata.get("source_locator")
+            if scope == "global":
+                owner_matches = document_owner is None
+            else:
+                owner_matches = (
+                    not isinstance(document_owner, bool)
+                    and isinstance(document_owner, int)
+                    and document_owner > 0
+                    and document_owner == owner
+                )
+            if (
+                doc.get("doc_id") != doc_id
+                or doc.get("source") != "vector"
+                or metadata.get("doc_id") != doc_id
+                or doc.get("scope") != scope
+                or not owner_matches
+                or isinstance(chunk_index, bool)
+                or not isinstance(chunk_index, int)
+                or chunk_index != expected_index
+                or not isinstance(chunk_id, str)
+                or not chunk_id
+                or chunk_id in seen_chunk_ids
+                or metadata.get("normalizer_version") != NORMALIZER_VERSION
+                or metadata.get("chunking_spec_version") != chunking_spec_version
+                or metadata.get("source_format") != source_format
+                or not isinstance(content, str)
+                or not content
+                or not isinstance(source_locator, Mapping)
+            ):
                 raise ValueError("ChunkDocument provenance 校验失败")
-            json.dumps(metadata)
+            try:
+                _canonical_json(source_locator)
+            except (TypeError, ValueError, OverflowError) as exc:
+                raise ValueError("ChunkDocument source_locator 不是严格 JSON 对象") from exc
+            seen_chunk_ids.add(chunk_id)
+            rows.append({
+                "doc_id": doc_id,
+                "chunk_id": chunk_id,
+                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
+                "chunk_index": chunk_index,
+                "scope": scope,
+                "owner": owner,
+                "source_locator": _thaw_json(source_locator),
+            })
+        return rows
+
+    @staticmethod
+    def _validate_prepared(prepared: PreparedIngestion) -> list[dict[str, Any]]:
+        """重新验证快照身份、docs 与无正文 manifest 的逐行一致性。"""
+        if not isinstance(prepared, PreparedIngestion):
+            raise ValueError("prepared 类型无效")
+        if (
+            prepared.schema_version != "prepared-ingestion-v1"
+            or not isinstance(prepared.source_sha256, str)
+            or len(prepared.source_sha256) != 64
+            or any(char not in "0123456789abcdef" for char in prepared.source_sha256)
+            or not isinstance(prepared.source_format, str)
+            or not prepared.source_format
+            or not isinstance(prepared.import_namespace, str)
+            or not prepared.import_namespace
+            or not isinstance(prepared.doc_id, str)
+            or not prepared.doc_id
+            or prepared.normalizer_version != NORMALIZER_VERSION
+            or prepared.doc_protocol != DOC_PROTOCOL
+            or prepared.chunk_protocol != CHUNK_PROTOCOL
+            or not isinstance(prepared.chunking_version, str)
+            or not prepared.chunking_version
+        ):
+            raise ValueError("prepared 身份或版本无效")
+        if prepared.scope == "global":
+            if prepared.owner is not None:
+                raise ValueError("prepared owner 与 scope 不一致")
+        elif prepared.scope == "private":
+            if (
+                isinstance(prepared.owner, bool)
+                or not isinstance(prepared.owner, int)
+                or prepared.owner <= 0
+            ):
+                raise ValueError("prepared owner 与 scope 不一致")
+        else:
+            raise ValueError("prepared scope 无效")
+
+        policy = prepared.chunk_policy
+        if not isinstance(policy, Mapping) or set(policy) != {
+            "chunk_size", "chunk_overlap", "hard_limit"
+        }:
+            raise ValueError("prepared chunk_policy 无效")
+        policy_values = [policy[key] for key in ("chunk_size", "chunk_overlap", "hard_limit")]
+        if any(isinstance(value, bool) or not isinstance(value, int) for value in policy_values):
+            raise ValueError("prepared chunk_policy 无效")
+        chunk_size, overlap, hard_limit = policy_values
+        if chunk_size <= 0 or not 0 <= overlap < chunk_size or hard_limit < chunk_size:
+            raise ValueError("prepared chunk_policy 无效")
+
+        if not isinstance(prepared.documents, tuple) or not prepared.documents:
+            raise ValueError("prepared documents 无效")
+        docs = [_thaw_json(doc) for doc in prepared.documents]
+        rows = KnowledgeIngestionService._build_manifest_rows(
+            docs,
+            doc_id=prepared.doc_id,
+            scope=prepared.scope,
+            owner=prepared.owner,
+            source_format=prepared.source_format,
+            chunking_spec_version=prepared.chunking_version,
+        )
+        if not isinstance(prepared.manifest, Mapping) or set(prepared.manifest) != {
+            "schema_version", "doc_id", "rows", "row_count", "manifest_sha256"
+        }:
+            raise ValueError("prepared manifest 无效")
+        manifest = _thaw_json(prepared.manifest)
+        actual_rows = manifest.get("rows")
+        row_keys = {
+            "doc_id", "chunk_id", "content_sha256", "chunk_index",
+            "scope", "owner", "source_locator",
+        }
+        if not isinstance(actual_rows, list) or any(
+            not isinstance(row, Mapping) or set(row) != row_keys for row in actual_rows
+        ):
+            raise ValueError("prepared manifest rows 无效")
+        try:
+            actual_row_bytes = tuple(_canonical_json(row) for row in actual_rows)
+            expected_row_bytes = tuple(_canonical_json(row) for row in rows)
+            actual_manifest_digest = _manifest_sha256(actual_rows)
+            expected_manifest_digest = _manifest_sha256(rows)
+        except (TypeError, ValueError, OverflowError) as exc:
+            raise ValueError("prepared manifest rows 无效") from exc
+        row_count = manifest.get("row_count")
+        if (
+            manifest.get("schema_version") != "prepared-manifest-v1"
+            or manifest.get("doc_id") != prepared.doc_id
+            or actual_row_bytes != expected_row_bytes
+            or isinstance(row_count, bool)
+            or not isinstance(row_count, int)
+            or row_count != len(actual_rows)
+            or actual_manifest_digest != manifest.get("manifest_sha256")
+            or actual_manifest_digest != expected_manifest_digest
+        ):
+            raise ValueError("prepared manifest 与 documents 不一致")
+        if not isinstance(prepared.warnings, tuple) or any(
+            not isinstance(warning, str) for warning in prepared.warnings
+        ):
+            raise ValueError("prepared warnings 无效")
+        if _safe_warnings(docs) != prepared.warnings:
+            raise ValueError("prepared warnings 与 documents 不一致")
+        return docs
+
+    def ingest_prepared(self, prepared: PreparedIngestion) -> IngestResult:
+        """校验准备快照后恰好 index 一次；不重新提取或切块。"""
+        docs = self._validate_prepared(prepared)
+        planned = len(docs)
         written = self._coordinator.index_documents(docs, source="vector")
-        if written != len(docs):
-            # B3-06：不得仅以 planned 推断 written；未确认时返回明确非成功状态。
-            warnings.append(f"provider 写入未确认：written={written}")
+        warnings = list(prepared.warnings)
+        if isinstance(written, int) and not isinstance(written, bool) and written == planned:
             return IngestResult(
-                status="index_unconfirmed",
-                doc_id=docs[0]["doc_id"],
-                planned_chunk_count=len(docs),
-                written_chunk_count=written or 0,
+                status="ok",
+                doc_id=prepared.doc_id,
+                planned_chunk_count=planned,
+                written_chunk_count=written,
                 warnings=warnings,
             )
+
+        confirmed_count = (
+            written
+            if isinstance(written, int)
+            and not isinstance(written, bool)
+            and 0 <= written <= planned
+            else 0
+        )
+        warnings.append("写入未确认，计数0不代表已确认零写入")
         return IngestResult(
-            status="ok",
-            doc_id=docs[0]["doc_id"],
-            planned_chunk_count=len(docs),
-            written_chunk_count=written,
+            status="index_unconfirmed",
+            doc_id=prepared.doc_id,
+            planned_chunk_count=planned,
+            written_chunk_count=confirmed_count,
             warnings=warnings,
         )
+
+    def ingest_file(
+        self,
+        file_path: str,
+        *,
+        import_namespace: str,
+        scope: str = "global",
+        user_id: int | None = None,
+        chunking_spec_version: str = "chunk-policy-1",
+        policy: ChunkPolicy | None = None,
+    ) -> IngestResult:
+        try:
+            prepared = self.prepare_file(
+                file_path,
+                import_namespace=import_namespace,
+                scope=scope,
+                user_id=user_id,
+                chunking_spec_version=chunking_spec_version,
+                policy=policy,
+            )
+        except IngestionPreparationError as exc:
+            if exc.status in {"unsupported", "extraction_empty"}:
+                return IngestResult(status=exc.status)
+            raise
+        return self.ingest_prepared(prepared)
diff --git a/app/infrastructure/rag/embedding.py b/app/infrastructure/rag/embedding.py
index 6c28335..0fcadaf 100644
--- a/app/infrastructure/rag/embedding.py
+++ b/app/infrastructure/rag/embedding.py
@@ -21,26 +21,30 @@ class EmbeddingService:
         """初始化 embedding 服务。
 
         Args:
             model: embedding 模型名（空则从 settings.embedding_model 读取）
             api_key: OpenAI API key（空则从 settings.openai_api_key 读取）
             base_url: OpenAI base URL（空则从 settings.openai_base_url 读取）
         """
         self.model = model or settings.embedding_model
         self.api_key = api_key or settings.openai_api_key
         self.base_url = base_url or settings.openai_base_url
+        dimension = settings.embedding_dim
+        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
+            raise ValueError("embedding_dim 必须为正整数")
+        self._dim = dimension
         self._client = None
 
     @property
     def dim(self) -> int:
-        """返回当前模型的向量维度。"""
-        return settings.embedding_dim
+        """返回实例创建时绑定的向量维度。"""
+        return self._dim
 
     @property
     def client(self):
         """懒加载 OpenAI embedding client（直接用 OpenAI SDK，避免 langchain 预分词问题）。"""
         if self._client is None:
             from openai import OpenAI
             self._client = OpenAI(
                 api_key=self.api_key,
                 base_url=self.base_url or None,
             )
@@ -71,29 +75,54 @@ class EmbeddingService:
         if not texts:
             return []
         # 过滤空文本，保持索引对应关系
         non_empty_indices = [i for i, t in enumerate(texts) if t]
         non_empty_texts = [texts[i] for i in non_empty_indices]
 
         if not non_empty_texts:
             return [[0.0] * self.dim] * len(texts)
 
         # 分批调用 API（方舟限制：单次最多 10 条）
-        BATCH_SIZE = 10
+        batch_size = 10
         all_embeddings = []
-        for i in range(0, len(non_empty_texts), BATCH_SIZE):
-            batch = non_empty_texts[i:i + BATCH_SIZE]
+        for i in range(0, len(non_empty_texts), batch_size):
+            batch = non_empty_texts[i:i + batch_size]
             response = self.client.embeddings.create(
                 model=self.model,
                 input=batch,
             )
-            all_embeddings.extend([item.embedding for item in response.data])
+            data = getattr(response, "data", None)
+            if not isinstance(data, (list, tuple)) or len(data) != len(batch):
+                raise ValueError("embedding 响应数量不匹配")
+
+            ordered_embeddings = [None] * len(batch)
+            seen_indices = set()
+            for item in data:
+                index = getattr(item, "index", None)
+                if (
+                    isinstance(index, bool)
+                    or not isinstance(index, int)
+                    or index < 0
+                    or index >= len(batch)
+                    or index in seen_indices
+                ):
+                    raise ValueError("embedding 响应索引无效")
+                try:
+                    embedding = item.embedding
+                except AttributeError as exc:
+                    raise ValueError("embedding 响应条目无效") from exc
+                ordered_embeddings[index] = embedding
+                seen_indices.add(index)
+
+            if len(seen_indices) != len(batch):
+                raise ValueError("embedding 响应索引不完整")
+            all_embeddings.extend(ordered_embeddings)
 
         # 将结果映射回原始索引位置
         result = []
         embed_idx = 0
         for i, text in enumerate(texts):
             if text:
                 result.append(all_embeddings[embed_idx])
                 embed_idx += 1
             else:
                 result.append([0.0] * self.dim)
diff --git a/app/infrastructure/rag/pgvector_provider.py b/app/infrastructure/rag/pgvector_provider.py
index 8cecdac..f59b640 100644
--- a/app/infrastructure/rag/pgvector_provider.py
+++ b/app/infrastructure/rag/pgvector_provider.py
@@ -6,20 +6,23 @@
   - doc_count: 已索引文档数
 
 关键设计点：
   1. sync/async 边界：IndexProvider.search 是同步方法，但 PG 访问是 async。
      解决方案：向量表用同步 psycopg 连接（不与业务 async_session 混用）。
   2. score 校准：pgvector <=> 返回距离（越小越近），需转成"越大越相关"的 score。
      采用 score = 1 / (1 + distance)，使其落在 (0, 1] 区间。
 """
 
 import json
+import math
+from numbers import Number
+
 from sqlalchemy import text
 from app.infrastructure.rag.coordinator import IndexProvider, Chunk
 from app.infrastructure.rag.embedding import EmbeddingService
 from app.core.config import settings
 
 
 def _sql_or_metadata(sql_value, metadata: dict, key: str):
     """读侧 identity 归一：SQL 顶层值是权威来源（B3-05）。
 
     legacy 行 SQL 列为 NULL/空串时，回退保留 metadata 中合法的
@@ -74,30 +77,62 @@ class PgVectorProvider(IndexProvider):
 
         Args:
             docs: 文档列表，每个 doc 含 {"content": str, "metadata": dict, ...}
 
         Returns:
             写入确认条数（commit 成功即确认）；空列表返回 0。
         """
         if not docs:
             return 0
 
-        # 批量 embed
+        dimension = self._embedding.dim
+        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
+            raise ValueError("embedding dimension 必须为正整数")
+
+        # 批量 embed，并在打开数据库连接前校验整个向量批次。
         contents = [d.get("content", "") for d in docs]
         embeddings = self._embedding.embed_many(contents)
+        current_dimension = self._embedding.dim
+        if (
+            isinstance(current_dimension, bool)
+            or not isinstance(current_dimension, int)
+            or current_dimension != dimension
+        ):
+            raise ValueError("embedding dimension 在批次中发生变化")
+        if not isinstance(embeddings, (list, tuple)) or len(embeddings) != len(docs):
+            raise ValueError("embedding 数量与文档数量不匹配")
+
+        validated_embeddings = []
+        for embedding in embeddings:
+            if not isinstance(embedding, (list, tuple)) or len(embedding) != dimension:
+                raise ValueError("embedding dimension 与配置不匹配")
+            validated = []
+            for value in embedding:
+                if isinstance(value, bool) or not isinstance(value, Number):
+                    raise ValueError("embedding 必须由有限数值组成")
+                try:
+                    numeric_value = float(value)
+                except (OverflowError, TypeError, ValueError) as exc:
+                    raise ValueError("embedding 必须由有限数值组成") from exc
+                if not math.isfinite(numeric_value):
+                    raise ValueError("embedding 必须由有限数值组成")
+                validated.append(numeric_value)
+            validated_embeddings.append(validated)
 
-        # 写入向量表
+        # 写入向量表。仅在所有 embedding 校验通过后才获取连接。
         conn = self._get_conn()
         dialect = conn.dialect.name
 
+        written_count = 0
         try:
-            for doc, emb in zip(docs, embeddings):
+            for index, doc in enumerate(docs):
+                emb = validated_embeddings[index]
                 content = doc.get("content", "")
                 metadata = doc.get("metadata", {})
                 doc_id = doc.get("doc_id") or metadata.get("doc_id", "")
                 chunk_id = doc.get("chunk_id") or metadata.get("chunk_id")
                 source = doc.get("source", "vector")
                 scope = doc.get("scope", "global")
                 user_id = doc.get("user_id", None)
 
                 if dialect == "postgresql":
                     # PostgreSQL: embedding 存为 pgvector 的 vector 类型
@@ -116,25 +151,30 @@ class PgVectorProvider(IndexProvider):
                     # SQLite: embedding 存为 JSON 字符串
                     conn.execute(
                         text("""
                         INSERT INTO vector_chunks (user_id, scope, content, embedding, source, doc_id, chunk_id, metadata_json)
                         VALUES (:user_id, :scope, :content, :embedding, :source, :doc_id, :chunk_id, :metadata_json)
                         """),
                         {"user_id": user_id, "scope": scope, "content": content,
                          "embedding": json.dumps(emb), "source": source, "doc_id": doc_id,
                          "chunk_id": chunk_id, "metadata_json": json.dumps(metadata)}
                     )
+                written_count += 1
             conn.commit()
         except Exception:
-            conn.rollback()
+            try:
+                conn.rollback()
+            except Exception:
+                # Rollback cannot establish the outcome and must not mask the cause.
+                pass
             raise
-        return len(docs)
+        return written_count
 
     def search(self, query: str, top_k: int = 5, visibility=None) -> list[Chunk]:
         """检索：embed query + 近邻查询 + 转 Chunk。
 
         Args:
             query: 查询文本
             top_k: 返回前 k 个最相关 chunk
             visibility: 受限检索可见性上下文（DEC-001）；None 保持旧全量行为。
                 PG/SQLite 分支执行同一授权谓词，且先于排序/LIMIT。
 
diff --git a/tests/unit/harness/test_knowledge_ingestion.py b/tests/unit/harness/test_knowledge_ingestion.py
index 31be878..5fef0d5 100644
--- a/tests/unit/harness/test_knowledge_ingestion.py
+++ b/tests/unit/harness/test_knowledge_ingestion.py
@@ -1,51 +1,287 @@
+import hashlib
+import json
+from dataclasses import fields
 from pathlib import Path
+from types import SimpleNamespace
 
 import pytest
 
-from app.harness.chunking_service import compute_doc_id
+from app.harness.chunking_service import ChunkPolicy, compute_doc_id
+import app.harness.knowledge_ingestion as knowledge_ingestion
 from app.harness.knowledge_ingestion import IngestResult, KnowledgeIngestionService
 from app.infrastructure.rag.coordinator import IndexProvider, RAGCoordinator
+from app.infrastructure.rag.embedding import EmbeddingService
+from app.infrastructure.rag.pgvector_provider import PgVectorProvider
+
+
+@pytest.fixture(autouse=True)
+def isolate_ingestion_tests(monkeypatch):
+    """Pin this module to fake RAG and fail immediately on service access."""
+    from app.core.config import settings
+
+    trap_calls = {"pgvector_init": 0, "pgvector_connection": 0, "embedding": 0, "sdk": 0}
+
+    def fail_on_call(counter):
+        def fail(*args, **kwargs):
+            trap_calls[counter] += 1
+            raise AssertionError("offline ingestion test reached a forbidden service")
+        return fail
+
+    # Simulate a machine configured for pgvector, then pin the test module to fake.
+    monkeypatch.setattr(settings, "rag_backend", "pgvector")
+    monkeypatch.setattr(settings, "rag_backend", "fake")
+    monkeypatch.setattr(PgVectorProvider, "__init__", fail_on_call("pgvector_init"))
+    monkeypatch.setattr(PgVectorProvider, "_get_conn", fail_on_call("pgvector_connection"))
+    monkeypatch.setattr(EmbeddingService, "embed_one", fail_on_call("embedding"))
+    monkeypatch.setattr(EmbeddingService, "embed_many", fail_on_call("embedding"))
+    monkeypatch.setattr("openai.OpenAI", fail_on_call("sdk"))
+
+    yield trap_calls
+
+    assert trap_calls == {
+        "pgvector_init": 0,
+        "pgvector_connection": 0,
+        "embedding": 0,
+        "sdk": 0,
+    }
+
+
+def test_ingestion_fixture_forces_fake_backend_when_pgvector_is_configured():
+    coordinator = RAGCoordinator()
+
+    assert coordinator.get_provider("vector") is not None
+    assert coordinator.get_provider("vector").__class__.__name__ == "_VectorStoreProvider"
+
+
+def test_prepared_ingestion_constructor_freezes_snapshot_and_intent():
+    source_doc = {
+        "content": "private body sentinel",
+        "doc_id": "doc-fixture",
+        "metadata": {"source_locator": {"positions": [0]}},
+    }
+    source_manifest = {
+        "schema_version": "prepared-manifest-v1",
+        "doc_id": "doc-fixture",
+        "rows": [{"source_locator": {"positions": [0]}}],
+        "row_count": 1,
+        "manifest_sha256": "digest",
+    }
+    prepared = knowledge_ingestion.PreparedIngestion(
+        schema_version="prepared-ingestion-v1",
+        source_sha256="source-digest",
+        source_format="txt",
+        import_namespace="course-1",
+        doc_id="doc-fixture",
+        scope="global",
+        owner=None,
+        normalizer_version="doc-norm-1",
+        chunking_version="chunk-policy-1",
+        doc_protocol="doc-v1",
+        chunk_protocol="chunk-v1",
+        chunk_policy={"chunk_size": 10, "chunk_overlap": 0, "hard_limit": 10},
+        documents=[source_doc],
+        manifest=source_manifest,
+        warnings=[],
+    )
+
+    source_doc["metadata"]["source_locator"]["positions"].append(1)
+    source_manifest["rows"][0]["source_locator"]["positions"].append(1)
+    intent = prepared.to_intent_metadata()
+    intent["chunk_policy"]["chunk_size"] = 20
+
+    assert prepared.documents[0]["metadata"]["source_locator"]["positions"] == (0,)
+    assert prepared.manifest["rows"][0]["source_locator"]["positions"] == (0,)
+    assert prepared.chunk_policy["chunk_size"] == 10
+    assert set(intent) == {
+        "schema_version", "source_sha256", "source_format", "import_namespace",
+        "doc_id", "scope", "owner", "normalizer_version", "chunking_version",
+        "doc_protocol", "chunk_protocol", "chunk_policy", "warnings",
+    }
+    assert "documents" not in intent
+    assert "private body sentinel" not in json.dumps(intent)
+
+
+@pytest.mark.parametrize(
+    "unsafe_warning",
+    ["api_key=FAKE_SECRET", "RuntimeError: upstream returned private body sentinel"],
+)
+def test_prepared_ingestion_rejects_untrusted_warnings_before_intent_export(
+    unsafe_warning,
+):
+    with pytest.raises(ValueError):
+        knowledge_ingestion.PreparedIngestion(
+            schema_version="prepared-ingestion-v1",
+            source_sha256="source-digest",
+            source_format="txt",
+            import_namespace="course-1",
+            doc_id="doc-fixture",
+            scope="global",
+            owner=None,
+            normalizer_version="doc-norm-1",
+            chunking_version="chunk-policy-1",
+            doc_protocol="doc-v1",
+            chunk_protocol="chunk-v1",
+            chunk_policy={"chunk_size": 10, "chunk_overlap": 0, "hard_limit": 10},
+            documents=[{
+                "content": "fixture content",
+                "metadata": {"oversized_hard_limit": False},
+            }],
+            manifest={},
+            warnings=[unsafe_warning],
+        )
 
 
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
 
 
+_AUTO_COUNT = object()
+
+
+class _RecordingVectorProvider(IndexProvider):
+    name = "vector"
+
+    def __init__(self, result=_AUTO_COUNT, mutator=None):
+        self.result = result
+        self.mutator = mutator
+        self.calls = 0
+        self.docs = None
+
+    def index(self, docs):
+        self.calls += 1
+        self.docs = docs
+        if self.mutator is not None:
+            self.mutator(docs)
+        return len(docs) if self.result is _AUTO_COUNT else self.result
+
+    def search(self, query, top_k=5, visibility=None):
+        return []
+
+    @property
+    def doc_count(self):
+        return 0
+
+
+class _FakeExtractor:
+    def __init__(self, result, after_extract=None):
+        self.result = result
+        self.after_extract = after_extract
+        self.calls = 0
+
+    def extract(self, file_path):
+        self.calls += 1
+        if self.after_extract is not None:
+            self.after_extract(file_path)
+        if isinstance(self.result, Exception):
+            raise self.result
+        return self.result
+
+
+class _FixedChunker:
+    def __init__(self, docs_factory):
+        self.docs_factory = docs_factory
+        self.calls = 0
+        self.last_text = None
+
+    def chunk_text(self, text, context, policy=None):
+        self.calls += 1
+        self.last_text = text
+        return self.docs_factory(context)
+
+
+def _fixture_docs(context, contents=("first chunk", "second chunk")):
+    doc_id = "doc-fixture"
+    docs = []
+    for index, content in enumerate(contents):
+        docs.append({
+            "content": content,
+            "doc_id": doc_id,
+            "source": "vector",
+            "scope": context.scope,
+            "user_id": context.user_id,
+            "metadata": {
+                "doc_id": doc_id,
+                "chunk_id": f"chunk-{index}",
+                "chunk_index": index,
+                "normalizer_version": "doc-norm-1",
+                "chunking_spec_version": context.chunking_spec_version,
+                "source_format": context.source_format,
+                "source_locator": {"paragraph": index},
+                "element_types": ["paragraph"],
+            },
+        })
+    return docs
+
+
+def _thaw(value):
+    if hasattr(value, "items"):
+        return {key: _thaw(item) for key, item in value.items()}
+    if isinstance(value, (list, tuple)):
+        return [_thaw(item) for item in value]
+    return value
+
+
+def _prepared_kwargs(prepared):
+    return {item.name: _thaw(getattr(prepared, item.name)) for item in fields(prepared)}
+
+
+def _make_test_service(
+    tmp_path,
+    monkeypatch,
+    *,
+    text="first chunk\n\nsecond chunk",
+    docs_factory=_fixture_docs,
+    provider_result=_AUTO_COUNT,
+    after_extract=None,
+):
+    source = tmp_path / "lesson.txt"
+    source.write_bytes(b"source bytes")
+    extractor = _FakeExtractor(text, after_extract=after_extract)
+    monkeypatch.setattr(knowledge_ingestion, "get_extractor", lambda path: extractor)
+    chunker = _FixedChunker(docs_factory)
+    provider = _RecordingVectorProvider(result=provider_result)
+    service = KnowledgeIngestionService(
+        RAGCoordinator(vector_provider=provider), chunker=chunker
+    )
+    return source, extractor, chunker, provider, service
+
+
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
+                "normalizer_version": "doc-norm-1",
                 "source_format": context.source_format,
                 "source_locator": {},
                 "oversized_hard_limit": True,
             },
         }]
 
 
 def test_ingest_file_indexes_chunk_documents(tmp_path: Path):
     source = tmp_path / "lesson.txt"
     source.write_text("第一段知识。\n\n第二段知识。", encoding="utf-8")
@@ -130,25 +366,489 @@ def test_ingest_confirms_written_count_from_provider(tmp_path: Path):
 
     result = KnowledgeIngestionService(coordinator).ingest_file(
         str(source), import_namespace="course-1"
     )
 
     assert result.status == "ok"
     assert result.planned_chunk_count == result.written_chunk_count == 1
     assert result.warnings == []
 
 
+def test_ingest_file_does_not_treat_boolean_as_confirmed_integer(tmp_path: Path):
+    source = tmp_path / "lesson.txt"
+    source.write_text("第一段知识。", encoding="utf-8")
+    provider = _RecordingVectorProvider(result=True)
+    coordinator = RAGCoordinator(vector_provider=provider)
+
+    result = KnowledgeIngestionService(coordinator).ingest_file(
+        str(source), import_namespace="course-1"
+    )
+
+    assert result.status == "index_unconfirmed"
+    assert result.planned_chunk_count == 1
+    assert result.written_chunk_count == 0
+    assert "写入未确认，计数0不代表已确认零写入" in result.warnings
+
+
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
+
+
+def test_prepare_file_has_no_index_side_effect(tmp_path, monkeypatch):
+    source, extractor, chunker, provider, service = _make_test_service(
+        tmp_path, monkeypatch
+    )
+
+    prepared = service.prepare_file(str(source), import_namespace="course-1")
+
+    assert isinstance(prepared, knowledge_ingestion.PreparedIngestion)
+    assert provider.calls == 0
+    assert extractor.calls == 1
+    assert chunker.calls == 1
+
+
+def test_prepare_file_extracts_and_chunks_once(tmp_path, monkeypatch):
+    source, extractor, chunker, provider, service = _make_test_service(
+        tmp_path, monkeypatch
+    )
+
+    prepared = service.prepare_file(str(source), import_namespace="course-1")
+
+    assert prepared.doc_id == "doc-fixture"
+    assert len(prepared.documents) == 2
+    assert extractor.calls == 1
+    assert chunker.calls == 1
+    assert provider.calls == 0
+
+
+def test_prepare_file_rejects_source_change(tmp_path, monkeypatch):
+    def change_source(file_path):
+        Path(file_path).write_bytes(b"changed source bytes")
+
+    source, _, chunker, provider, service = _make_test_service(
+        tmp_path, monkeypatch, after_extract=change_source
+    )
+
+    with pytest.raises(knowledge_ingestion.IngestionPreparationError) as raised:
+        service.prepare_file(str(source), import_namespace="course-1")
+
+    assert raised.value.status == "invalid_request"
+    assert raised.value.safe_summary == "摄入参数无效"
+    assert chunker.calls == 1
+    assert provider.calls == 0
+
+
+def test_prepare_snapshot_is_deeply_immutable_and_isolated(tmp_path, monkeypatch):
+    source_docs = []
+
+    def docs_factory(context):
+        docs = _fixture_docs(context)
+        source_docs.extend(docs)
+        return docs
+
+    source, _, _, _, service = _make_test_service(
+        tmp_path, monkeypatch, docs_factory=docs_factory
+    )
+    prepared = service.prepare_file(str(source), import_namespace="course-1")
+    original_locator = _thaw(prepared.documents[0]["metadata"]["source_locator"])
+
+    source_docs[0]["content"] = "mutated after preparation"
+    source_docs[0]["metadata"]["source_locator"]["paragraph"] = 99
+
+    assert prepared.documents[0]["content"] == "first chunk"
+    assert _thaw(prepared.documents[0]["metadata"]["source_locator"]) == original_locator
+    with pytest.raises(TypeError):
+        prepared.documents[0]["metadata"]["source_locator"]["paragraph"] = 3
+    with pytest.raises(TypeError):
+        prepared.manifest["rows"][0]["source_locator"]["paragraph"] = 3
+    with pytest.raises(TypeError):
+        prepared.chunk_policy["chunk_size"] = 1
+
+    intent = prepared.to_intent_metadata()
+    intent["chunk_policy"]["chunk_size"] = 1
+    intent["warnings"].append("changed")
+    assert prepared.chunk_policy["chunk_size"] == 500
+    assert prepared.warnings == ()
+
+
+def test_prepared_manifest_matches_canonical_rows(tmp_path, monkeypatch):
+    def fixed_docs(context):
+        return [{
+            "content": "fixture content",
+            "doc_id": "doc-fixture",
+            "source": "vector",
+            "scope": context.scope,
+            "user_id": context.user_id,
+            "metadata": {
+                "doc_id": "doc-fixture",
+                "chunk_id": "chunk-0",
+                "chunk_index": 0,
+                "normalizer_version": "doc-norm-1",
+                "chunking_spec_version": context.chunking_spec_version,
+                "source_format": context.source_format,
+                "source_locator": {"paragraph": 0},
+            },
+        }]
+
+    source, _, _, _, service = _make_test_service(
+        tmp_path, monkeypatch, docs_factory=fixed_docs
+    )
+    prepared = service.prepare_file(str(source), import_namespace="course-1")
+    expected_row = {
+        "doc_id": "doc-fixture",
+        "chunk_id": "chunk-0",
+        "content_sha256": "77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a",
+        "chunk_index": 0,
+        "scope": "global",
+        "owner": None,
+        "source_locator": {"paragraph": 0},
+    }
+
+    assert hashlib.sha256(b"fixture content").hexdigest() == (
+        "77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a"
+    )
+    assert _thaw(prepared.manifest["rows"]) == [expected_row]
+    assert prepared.manifest["manifest_sha256"] == (
+        "7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176"
+    )
+
+    def canonical(value):
+        return json.dumps(
+            value,
+            sort_keys=True,
+            ensure_ascii=False,
+            separators=(",", ":"),
+            allow_nan=False,
+        ).encode("utf-8")
+
+    def oracle(rows):
+        ordered = sorted(rows, key=canonical)
+        return hashlib.sha256(canonical(ordered)).hexdigest()
+
+    def reordered_docs(context):
+        docs = _fixture_docs(context, contents=("中文内容甲", "中文内容乙"))
+        docs[0]["metadata"]["chunk_id"] = "z-row"
+        docs[0]["metadata"]["source_locator"] = {"z": "中文", "a": {"n": 1}}
+        docs[1]["metadata"]["chunk_id"] = "a-row"
+        docs[1]["metadata"]["source_locator"] = {"a": {"n": 2}, "z": "文本"}
+        return docs
+
+    source2, _, _, _, service2 = _make_test_service(
+        tmp_path, monkeypatch, docs_factory=reordered_docs
+    )
+    prepared2 = service2.prepare_file(str(source2), import_namespace="course-1")
+    rows = _thaw(prepared2.manifest["rows"])
+    canonical_rows = [canonical(row) for row in rows]
+    assert [row["chunk_index"] for row in rows] == [0, 1]
+    assert canonical_rows != sorted(canonical_rows)
+    assert prepared2.manifest["manifest_sha256"] == oracle(rows)
+    assert oracle(rows) == oracle(list(reversed(rows)))
+    duplicated = [rows[0], rows[1], rows[0]]
+    assert knowledge_ingestion._manifest_sha256(duplicated) == oracle(duplicated)
+    assert oracle(duplicated) != oracle(rows)
+
+    intent = prepared2.to_intent_metadata()
+    expected_keys = {
+        "schema_version", "source_sha256", "source_format", "import_namespace",
+        "doc_id", "scope", "owner", "normalizer_version", "chunking_version",
+        "doc_protocol", "chunk_protocol", "chunk_policy", "warnings",
+    }
+    assert set(intent) == expected_keys
+    serialized = json.dumps(
+        {"manifest": _thaw(prepared2.manifest), "intent": intent,
+         "warnings": list(prepared2.warnings)},
+        ensure_ascii=False,
+    )
+    assert "中文内容甲" not in serialized
+    assert "中文内容乙" not in serialized
+
+
+@pytest.mark.parametrize(
+    "corruption",
+    [
+        "manifest_digest", "source_digest", "identity", "chunk_index",
+        "duplicate_chunk_id", "scope_owner", "version", "locator", "content",
+        "row_owner_bool", "chunk_index_bool", "locator_bool", "locator_float",
+        "warnings_api_key", "warnings_exception",
+    ],
+)
+def test_ingest_prepared_rejects_inconsistent_snapshot(
+    tmp_path, monkeypatch, corruption
+):
+    scope = "private" if corruption == "row_owner_bool" else "global"
+    user_id = 1 if scope == "private" else None
+
+    def numeric_locator_docs(context):
+        docs = _fixture_docs(context)
+        for doc in docs:
+            doc["metadata"]["source_locator"] = {"paragraph": 1}
+        return docs
+
+    docs_factory = (
+        numeric_locator_docs
+        if corruption in {"locator_bool", "locator_float"}
+        else _fixture_docs
+    )
+    source, _, _, provider, service = _make_test_service(
+        tmp_path, monkeypatch, docs_factory=docs_factory
+    )
+    prepared = service.prepare_file(
+        str(source), import_namespace="course-1", scope=scope, user_id=user_id
+    )
+    values = _prepared_kwargs(prepared)
+    docs = values["documents"]
+    manifest = values["manifest"]
+
+    if corruption == "manifest_digest":
+        manifest["manifest_sha256"] = "0" * 64
+    elif corruption == "source_digest":
+        values["source_sha256"] = "invalid"
+    elif corruption == "identity":
+        values["doc_id"] = "different-doc"
+    elif corruption == "chunk_index":
+        docs[0]["metadata"]["chunk_index"] = 1
+    elif corruption == "duplicate_chunk_id":
+        docs[1]["metadata"]["chunk_id"] = docs[0]["metadata"]["chunk_id"]
+    elif corruption == "scope_owner":
+        values["scope"] = "private"
+        values["owner"] = 9
+    elif corruption == "version":
+        values["chunking_version"] = "different-policy"
+    elif corruption == "locator":
+        docs[0]["metadata"]["source_locator"] = {0: "not a JSON object key"}
+    elif corruption == "warnings":
+        values["warnings"] = ["private body sentinel"]
+    elif corruption == "row_owner_bool":
+        manifest["rows"][0]["owner"] = True
+    elif corruption == "chunk_index_bool":
+        manifest["rows"][0]["chunk_index"] = False
+    elif corruption == "locator_bool":
+        manifest["rows"][0]["source_locator"]["paragraph"] = True
+    elif corruption == "locator_float":
+        manifest["rows"][0]["source_locator"]["paragraph"] = 1.0
+    elif corruption == "warnings_api_key":
+        values["warnings"] = ["api_key=FAKE_SECRET"]
+    elif corruption == "warnings_exception":
+        values["warnings"] = ["RuntimeError: upstream returned private body sentinel"]
+    else:
+        docs[0]["content"] = "changed content"
+
+    values["documents"] = docs
+    values["manifest"] = manifest
+    with pytest.raises(ValueError):
+        corrupted = knowledge_ingestion.PreparedIngestion(**values)
+        service.ingest_prepared(corrupted)
+
+    assert provider.calls == 0
+
+
+def test_ingest_file_delegates_once(tmp_path, monkeypatch):
+    source, _, _, _, service = _make_test_service(tmp_path, monkeypatch)
+    prepared = SimpleNamespace()
+    expected_result = IngestResult(status="ok")
+    calls = {"prepare": 0, "ingest": 0}
+
+    def prepare(*args, **kwargs):
+        calls["prepare"] += 1
+        return prepared
+
+    def ingest(value):
+        calls["ingest"] += 1
+        assert value is prepared
+        return expected_result
+
+    monkeypatch.setattr(service, "prepare_file", prepare, raising=False)
+    monkeypatch.setattr(service, "ingest_prepared", ingest, raising=False)
+
+    result = service.ingest_file(str(source), import_namespace="course-1")
+
+    assert result is expected_result
+    assert calls == {"prepare": 1, "ingest": 1}
+
+
+@pytest.mark.parametrize(
+    ("provider_result", "expected_status", "expected_written"),
+    [
+        (None, "index_unconfirmed", 0),
+        (True, "index_unconfirmed", 0),
+        (False, "index_unconfirmed", 0),
+        (1.0, "index_unconfirmed", 0),
+        (-1, "index_unconfirmed", 0),
+        (0, "index_unconfirmed", 0),
+        (1, "index_unconfirmed", 1),
+        (3, "index_unconfirmed", 0),
+        (2, "ok", 2),
+    ],
+)
+def test_ingest_prepared_requires_confirmed_integer_count(
+    tmp_path, monkeypatch, provider_result, expected_status, expected_written
+):
+    source, _, _, provider, service = _make_test_service(
+        tmp_path, monkeypatch, provider_result=provider_result
+    )
+    prepared = service.prepare_file(str(source), import_namespace="course-1")
+
+    result = service.ingest_prepared(prepared)
+
+    assert result.status == expected_status
+    assert result.planned_chunk_count == 2
+    assert result.written_chunk_count == expected_written
+    assert provider.calls == 1
+    if expected_status == "index_unconfirmed":
+        assert "写入未确认，计数0不代表已确认零写入" in result.warnings
+
+
+def test_ingest_prepared_does_not_reextract(tmp_path, monkeypatch):
+    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)
+    prepared = service.prepare_file(str(source), import_namespace="course-1")
+
+    def unexpected_extraction(path):
+        raise AssertionError("ingest_prepared must consume the prepared snapshot")
+
+    monkeypatch.setattr(knowledge_ingestion, "get_extractor", unexpected_extraction)
+
+    result = service.ingest_prepared(prepared)
+
+    assert result.status == "ok"
+    assert provider.calls == 1
+
+
+def test_ingest_prepared_provider_mutation_does_not_change_snapshot(tmp_path, monkeypatch):
+    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)
+    prepared = service.prepare_file(str(source), import_namespace="course-1")
+    original_doc = _thaw(prepared.documents[0])
+
+    def mutate_provider_docs(docs):
+        docs[0]["content"] = "provider mutation"
+        docs[0]["metadata"]["source_locator"]["paragraph"] = 99
+
+    provider.mutator = mutate_provider_docs
+    result = service.ingest_prepared(prepared)
+
+    assert result.status == "ok"
+    assert _thaw(prepared.documents[0]) == original_doc
+
+
+@pytest.mark.parametrize(
+    ("scope", "user_id"),
+    [
+        ("private", 0), ("private", -1), ("private", True),
+        ("private", 1.5), ("private", "1"), ("global", False),
+    ],
+)
+def test_prepare_file_rejects_invalid_owner(tmp_path, monkeypatch, scope, user_id):
+    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)
+
+    with pytest.raises(ValueError):
+        service.prepare_file(
+            str(source), import_namespace="course-1", scope=scope, user_id=user_id
+        )
+
+    assert provider.calls == 0
+
+
+def test_prepare_file_rejects_boolean_private_chunk_owner(tmp_path, monkeypatch):
+    def boolean_owner_docs(context):
+        docs = _fixture_docs(context)
+        for doc in docs:
+            doc["user_id"] = True
+        return docs
+
+    source, _, _, provider, service = _make_test_service(
+        tmp_path, monkeypatch, docs_factory=boolean_owner_docs
+    )
+
+    with pytest.raises(ValueError):
+        service.prepare_file(
+            str(source), import_namespace="course-1", scope="private", user_id=1
+        )
+
+    assert provider.calls == 0
+
+
+@pytest.mark.parametrize(
+    "policy",
+    [
+        ChunkPolicy(chunk_size=True, chunk_overlap=0, hard_limit=8192),
+        ChunkPolicy(chunk_size=2.5, chunk_overlap=0, hard_limit=8192),
+        ChunkPolicy(chunk_size=10, chunk_overlap=0.5, hard_limit=8192),
+        ChunkPolicy(chunk_size=1, chunk_overlap=0, hard_limit=True),
+    ],
+)
+def test_prepare_file_rejects_non_integer_policy_fields(tmp_path, monkeypatch, policy):
+    source, _, _, _, service = _make_test_service(tmp_path, monkeypatch)
+
+    with pytest.raises(ValueError):
+        service.prepare_file(str(source), import_namespace="course-1", policy=policy)
+
+
+def test_prepare_file_accepts_zero_overlap(tmp_path, monkeypatch):
+    policy = ChunkPolicy(chunk_size=10, chunk_overlap=0, hard_limit=10)
+    source, _, _, provider, service = _make_test_service(tmp_path, monkeypatch)
+
+    prepared = service.prepare_file(
+        str(source), import_namespace="course-1", policy=policy
+    )
+
+    assert prepared.chunk_policy == {
+        "chunk_size": 10, "chunk_overlap": 0, "hard_limit": 10
+    }
+    assert provider.calls == 0
+
+
+@pytest.mark.parametrize(
+    ("file_path", "extractor", "namespace", "status", "summary"),
+    [
+        ("lesson.unknown", None, "course-1", "unsupported", "不支持的文档格式"),
+        ("lesson.txt", _FakeExtractor(""), "course-1", "extraction_empty", "未提取到可用文本"),
+        ("lesson.txt", _FakeExtractor("text"), "", "invalid_request", "摄入参数无效"),
+    ],
+)
+def test_preparation_error_has_exact_safe_status_and_summary(
+    tmp_path, monkeypatch, file_path, extractor, namespace, status, summary
+):
+    source = tmp_path / file_path
+    source.write_bytes(b"source bytes")
+    monkeypatch.setattr(knowledge_ingestion, "get_extractor", lambda path: extractor)
+    provider = _RecordingVectorProvider()
+    service = KnowledgeIngestionService(
+        RAGCoordinator(vector_provider=provider), chunker=_FixedChunker(_fixture_docs)
+    )
+
+    with pytest.raises(knowledge_ingestion.IngestionPreparationError) as raised:
+        service.prepare_file(str(source), import_namespace=namespace)
+
+    assert raised.value.status == status
+    assert raised.value.safe_summary == summary
+    assert provider.calls == 0
+
+
+def test_ingest_file_maps_preparation_errors_and_preserves_unknown_errors(
+    tmp_path, monkeypatch
+):
+    source, _, _, provider, service = _make_test_service(
+        tmp_path, monkeypatch, text=""
+    )
+    result = service.ingest_file(str(source), import_namespace="course-1")
+    assert result.status == "extraction_empty"
+    assert provider.calls == 0
+
+    unknown = RuntimeError("extractor internal failure")
+    extractor = _FakeExtractor(unknown)
+    monkeypatch.setattr(knowledge_ingestion, "get_extractor", lambda path: extractor)
+    with pytest.raises(RuntimeError) as raised:
+        service.ingest_file(str(source), import_namespace="course-1")
+    assert raised.value is unknown
+    assert provider.calls == 0
diff --git a/tests/unit/infrastructure/test_embedding.py b/tests/unit/infrastructure/test_embedding.py
index c712eae..08f3196 100644
--- a/tests/unit/infrastructure/test_embedding.py
+++ b/tests/unit/infrastructure/test_embedding.py
@@ -1,42 +1,63 @@
 """EmbeddingService 单元测试（阶段 A）。
 
 Mock 标注说明：
 - 所有外部 API 调用（openai.OpenAI.embeddings.create）均已 mock
 - Mock 标注：[MOCK:阶段A]
 - Mock 出处：openai.OpenAI.embeddings.create
 - 切除方式：用户配置真实 API key 后，运行集成测试（test_pgvector_real.py）验证真实 API 调用
 """
 
 from dataclasses import dataclass
+from types import SimpleNamespace
 from typing import Any
 
 import pytest
 from app.infrastructure.rag.embedding import EmbeddingService
 
 
+@pytest.fixture(autouse=True)
+def block_openai_client_by_default(monkeypatch):
+    """Require SDK tests to install their own in-memory OpenAI substitute."""
+    def fail_openai_factory(*args, **kwargs):
+        raise AssertionError("offline embedding test attempted to construct an OpenAI client")
+
+    monkeypatch.setattr("openai.OpenAI", fail_openai_factory)
+
+
 # [MOCK:阶段A] 假 OpenAI embeddings.create 响应对象
 @dataclass
 class FakeEmbeddingItem:
     embedding: list[float]
-    index: int = 0
+    index: int
     object: str = "embedding"
 
 
 @dataclass
 class FakeEmbeddingResponse:
     data: list[FakeEmbeddingItem]
     model: str = "fake-model"
     object: str = "list"
     usage: dict[str, Any] | None = None
 
 
+def _install_fake_response(monkeypatch, response_factory):
+    class FakeOpenAI:
+        def __init__(self, **kwargs):
+            self.embeddings = self
+
+        def create(self, model, input, **kwargs):
+            return response_factory(model, input, **kwargs)
+
+    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
+
+
 def test_embedding_service_defaults():
     """验证默认配置从 settings 读取。"""
     service = EmbeddingService()
     assert service.model == "doubao-embedding-vision"
     assert service.dim == 2048
 
 
 def test_embedding_service_custom_config():
     """验证可传入自定义配置。"""
     service = EmbeddingService(
@@ -58,21 +79,24 @@ def test_embed_one_returns_correct_dimension(monkeypatch):
     fake_embedding = [0.1] * 2048
 
     class FakeOpenAI:
         def __init__(self, **kwargs):
             pass
 
         class _embeddings:
             @staticmethod
             def create(model, input, **kwargs):
                 return FakeEmbeddingResponse(
-                    data=[FakeEmbeddingItem(embedding=fake_embedding) for _ in input]
+                    data=[
+                        FakeEmbeddingItem(embedding=fake_embedding, index=i)
+                        for i, _ in enumerate(input)
+                    ]
                 )
 
         embeddings = _embeddings()
 
     monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
 
     service = EmbeddingService()
     result = service.embed_one("测试文本")
 
     assert len(result) == 2048
@@ -230,10 +254,115 @@ def test_settings_fallback(monkeypatch):
     try:
         service = EmbeddingService()  # 不传参数
         assert service.api_key == "settings-key"
         assert service.base_url == "https://settings.com"
         assert service.model == "settings-model"
     finally:
         # [MOCK:阶段A] 恢复原始 settings
         config.settings.openai_api_key = original_api_key
         config.settings.openai_base_url = original_base_url
         config.settings.embedding_model = original_model
+
+
+def test_dimension_is_bound_per_instance(monkeypatch):
+    from app.core.config import settings
+
+    monkeypatch.setattr(settings, "embedding_dim", 2048)
+    existing = EmbeddingService()
+    monkeypatch.setattr(settings, "embedding_dim", 3)
+    new = EmbeddingService()
+
+    assert existing.dim == 2048
+    assert new.dim == 3
+
+
+@pytest.mark.parametrize("invalid_dim", [0, -1, True, 1.5, "3", None])
+def test_embedding_service_rejects_invalid_dimension(monkeypatch, invalid_dim):
+    from app.core.config import settings
+
+    monkeypatch.setattr(settings, "embedding_dim", invalid_dim)
+
+    with pytest.raises(ValueError):
+        EmbeddingService()
+
+
+@pytest.mark.parametrize("response_count", [1, 3])
+def test_embed_many_rejects_batch_cardinality_mismatch(monkeypatch, response_count):
+    vector = [0.25] * 2048
+
+    def response_factory(model, input, **kwargs):
+        return FakeEmbeddingResponse(
+            data=[FakeEmbeddingItem(vector, index=i) for i in range(response_count)]
+        )
+
+    _install_fake_response(monkeypatch, response_factory)
+
+    with pytest.raises(ValueError):
+        EmbeddingService().embed_many(["first", "second"])
+
+
+def test_embed_many_orders_batch_by_response_index(monkeypatch):
+    first = [0.1] * 2048
+    second = [0.2] * 2048
+
+    def response_factory(model, input, **kwargs):
+        return FakeEmbeddingResponse(data=[
+            FakeEmbeddingItem(second, index=1),
+            FakeEmbeddingItem(first, index=0),
+        ])
+
+    _install_fake_response(monkeypatch, response_factory)
+
+    assert EmbeddingService().embed_many(["first", "second"]) == [first, second]
+
+
+@pytest.mark.parametrize(
+    "case",
+    ["missing", "duplicate", "negative", "out_of_range", "bool", "string"],
+)
+def test_embed_many_rejects_invalid_response_index(monkeypatch, case):
+    vector = [0.3] * 2048
+    if case == "missing":
+        items = [SimpleNamespace(embedding=vector), SimpleNamespace(embedding=vector)]
+    elif case == "duplicate":
+        items = [FakeEmbeddingItem(vector, index=0), FakeEmbeddingItem(vector, index=0)]
+    elif case == "negative":
+        items = [FakeEmbeddingItem(vector, index=-1), FakeEmbeddingItem(vector, index=1)]
+    elif case == "out_of_range":
+        items = [FakeEmbeddingItem(vector, index=2), FakeEmbeddingItem(vector, index=0)]
+    elif case == "bool":
+        items = [FakeEmbeddingItem(vector, index=True), FakeEmbeddingItem(vector, index=0)]
+    else:
+        items = [FakeEmbeddingItem(vector, index="0"), FakeEmbeddingItem(vector, index=1)]
+
+    _install_fake_response(
+        monkeypatch,
+        lambda model, input, **kwargs: FakeEmbeddingResponse(data=items),
+    )
+
+    with pytest.raises(ValueError):
+        EmbeddingService().embed_many(["first", "second"])
+
+
+def test_embed_many_validates_each_batch_and_restores_empty_positions(monkeypatch):
+    inputs = ["a", "", "b", "c", "", "d", "e", "f", "g", "", "h", "i", "j", "k"]
+    batch_inputs = []
+
+    def response_factory(model, input, **kwargs):
+        batch_inputs.append(list(input))
+        return FakeEmbeddingResponse(data=[
+            FakeEmbeddingItem([float(ord(value))] * 2048, index=i)
+            for i, value in enumerate(input)
+        ])
+
+    _install_fake_response(monkeypatch, response_factory)
+
+    result = EmbeddingService().embed_many(inputs)
+
+    assert [len(batch) for batch in batch_inputs] == [10, 1]
+    non_empty_values = {value for value in inputs if value}
+    for index, value in enumerate(inputs):
+        if value:
+            assert result[index] == [float(ord(value))] * 2048
+        else:
+            assert result[index] == [0.0] * 2048
+    assert len(non_empty_values) == 11
diff --git a/tests/unit/infrastructure/test_pgvector_provider.py b/tests/unit/infrastructure/test_pgvector_provider.py
index 6a5a5f2..fe6f9dc 100644
--- a/tests/unit/infrastructure/test_pgvector_provider.py
+++ b/tests/unit/infrastructure/test_pgvector_provider.py
@@ -2,27 +2,49 @@
 
 Mock 标注说明：
 - EmbeddingService 已 mock（返回固定向量）
 - 使用内存 sqlite 数据库（sqlite:///:memory:）测试降级分支
 - Mock 标注：[MOCK:阶段A]
 - Mock 出处：EmbeddingService.embed_one / embed_many
 - 切除方式：运行集成测试（test_pgvector_real.py）验证真实 PG + pgvector 行为
 """
 
 import json
+from math import inf, nan
+from types import SimpleNamespace
+
 import pytest
 from sqlalchemy import text
 from app.infrastructure.rag.pgvector_provider import PgVectorProvider
 from app.infrastructure.rag.embedding import EmbeddingService
 from app.infrastructure.rag.coordinator import Chunk
 
 
+@pytest.fixture(autouse=True)
+def isolate_pgvector_tests(monkeypatch):
+    """Allow only in-memory SQLite and block every SDK construction by default."""
+    import sqlalchemy
+
+    original_create_engine = sqlalchemy.create_engine
+
+    def guarded_create_engine(url, *args, **kwargs):
+        if str(url) != "sqlite:///:memory:":
+            raise AssertionError("unit tests may create only an in-memory SQLite engine")
+        return original_create_engine(url, *args, **kwargs)
+
+    def fail_openai_factory(*args, **kwargs):
+        raise AssertionError("offline provider test attempted to construct an OpenAI client")
+
+    monkeypatch.setattr(sqlalchemy, "create_engine", guarded_create_engine)
+    monkeypatch.setattr("openai.OpenAI", fail_openai_factory)
+
+
 class FakeEmbeddingService:
     """[MOCK:阶段A] 假 embedding 服务，返回固定向量用于测试。"""
 
     def __init__(self, dim=2048):
         self._dim = dim
 
     @property
     def dim(self):
         return self._dim
 
@@ -30,20 +52,63 @@ class FakeEmbeddingService:
         """返回固定向量（用文本长度作为首元素以区分）。"""
         if not text:
             return [0.0] * self._dim
         return [float(len(text))] + [0.1] * (self._dim - 1)
 
     def embed_many(self, texts: list[str]) -> list[list[float]]:
         """批量返回固定向量。"""
         return [self.embed_one(t) for t in texts]
 
 
+class _SuppliedEmbeddingService:
+    def __init__(self, vectors, dim=2, dimension_after_embed=None):
+        self._dim = dim
+        self._dimension_after_embed = dimension_after_embed
+        self.vectors = vectors
+        self.calls = 0
+
+    @property
+    def dim(self):
+        return self._dim
+
+    def embed_many(self, texts):
+        self.calls += 1
+        if self._dimension_after_embed is not None:
+            self._dim = self._dimension_after_embed
+        return self.vectors
+
+
+class _RecordingConnection:
+    dialect = SimpleNamespace(name="sqlite")
+
+    def __init__(self):
+        self.execute_calls = []
+        self.commit_calls = 0
+        self.rollback_calls = 0
+
+    def execute(self, statement, parameters=None):
+        self.execute_calls.append((statement, parameters))
+
+    def commit(self):
+        self.commit_calls += 1
+
+    def rollback(self):
+        self.rollback_calls += 1
+
+
+def _recording_provider(embedding_service, monkeypatch):
+    provider = PgVectorProvider(embedding_service=embedding_service, db_url="sqlite:///:memory:")
+    connection = _RecordingConnection()
+    monkeypatch.setattr(provider, "_get_conn", lambda: connection)
+    return provider, connection
+
+
 @pytest.fixture
 def sqlite_provider():
     """提供基于内存 sqlite 的 PgVectorProvider（测试降级分支）。
 
     [MOCK:阶段A] 使用 FakeEmbeddingService
     """
     fake_embedding = FakeEmbeddingService()
     provider = PgVectorProvider(
         embedding_service=fake_embedding,
         db_url="sqlite:///:memory:"
@@ -66,20 +131,287 @@ def sqlite_provider():
     """))
     conn.commit()
 
     yield provider
 
     # 清理
     if provider._conn:
         provider._conn.close()
 
 
+@pytest.mark.parametrize(
+    "vectors",
+    [
+        [[0.1, 0.2]],
+        [[0.1, 0.2], [0.1, 0.2], [0.1, 0.2]],
+        [[], [0.1, 0.2]],
+        [[0.1], [0.1, 0.2]],
+        [[True, 0.2], [0.1, 0.2]],
+        [["0.1", 0.2], [0.1, 0.2]],
+        [[nan, 0.2], [0.1, 0.2]],
+        [[inf, 0.2], [0.1, 0.2]],
+        [[-inf, 0.2], [0.1, 0.2]],
+    ],
+    ids=[
+        "short-batch", "long-batch", "zero-dimension", "wrong-dimension",
+        "bool-value", "non-numeric-value", "nan-value", "positive-infinity",
+        "negative-infinity",
+    ],
+)
+def test_index_rejects_invalid_embedding_batch_before_insert(monkeypatch, vectors):
+    service = _SuppliedEmbeddingService(vectors)
+    provider, connection = _recording_provider(service, monkeypatch)
+
+    with pytest.raises(ValueError):
+        provider.index([{"content": "first"}, {"content": "second"}])
+
+    assert connection.execute_calls == []
+    assert connection.commit_calls == 0
+
+
+def test_index_rejects_embedding_dimension_drift_before_insert(monkeypatch):
+    service = _SuppliedEmbeddingService(
+        [[0.1, 0.2], [0.3, 0.4]], dimension_after_embed=3
+    )
+    provider, connection = _recording_provider(service, monkeypatch)
+
+    with pytest.raises(ValueError):
+        provider.index([{"content": "first"}, {"content": "second"}])
+
+    assert connection.execute_calls == []
+    assert connection.commit_calls == 0
+
+
+def test_index_empty_batch_does_not_embed_or_connect(monkeypatch):
+    service = _SuppliedEmbeddingService([])
+    provider, connection = _recording_provider(service, monkeypatch)
+
+    assert provider.index([]) == 0
+    assert service.calls == 0
+    assert connection.execute_calls == []
+    assert connection.commit_calls == 0
+
+
+@pytest.mark.parametrize("malformation", ["duplicate", "missing", "out_of_range"])
+def test_index_rejects_invalid_sdk_response_indexes_before_connect(
+    monkeypatch, malformation
+):
+    from app.core.config import settings
+
+    monkeypatch.setattr(settings, "embedding_dim", 2)
+    vector = [0.1, 0.2]
+
+    def response_items(batch):
+        if malformation == "duplicate":
+            return [SimpleNamespace(index=0, embedding=vector), SimpleNamespace(index=0, embedding=vector)]
+        if malformation == "missing":
+            return [SimpleNamespace(embedding=vector), SimpleNamespace(index=1, embedding=vector)]
+        return [SimpleNamespace(index=2, embedding=vector), SimpleNamespace(index=0, embedding=vector)]
+
+    class FakeOpenAI:
+        def __init__(self, **kwargs):
+            self.embeddings = self
+
+        def create(self, model, input, **kwargs):
+            return SimpleNamespace(data=response_items(input))
+
+    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
+    service = EmbeddingService()
+    provider = PgVectorProvider(embedding_service=service, db_url="sqlite:///:memory:")
+    connection_calls = []
+
+    def forbidden_connection():
+        connection_calls.append(True)
+        raise AssertionError("invalid embedding response reached the database")
+
+    monkeypatch.setattr(provider, "_get_conn", forbidden_connection)
+
+    with pytest.raises(ValueError):
+        provider.index([{"content": "first"}, {"content": "second"}])
+
+    assert connection_calls == []
+
+
+def test_index_rejects_invalid_second_sdk_batch_before_connect(monkeypatch):
+    from app.core.config import settings
+
+    monkeypatch.setattr(settings, "embedding_dim", 2)
+    calls = []
+
+    class FakeOpenAI:
+        def __init__(self, **kwargs):
+            self.embeddings = self
+
+        def create(self, model, input, **kwargs):
+            calls.append(list(input))
+            if len(calls) == 1:
+                data = [
+                    SimpleNamespace(index=i, embedding=[0.1, 0.2])
+                    for i in range(len(input))
+                ]
+            else:
+                data = [SimpleNamespace(index=1, embedding=[0.1, 0.2])]
+            return SimpleNamespace(data=data)
+
+    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
+    provider = PgVectorProvider(
+        embedding_service=EmbeddingService(), db_url="sqlite:///:memory:"
+    )
+    connection_calls = []
+    monkeypatch.setattr(provider, "_get_conn", lambda: connection_calls.append(True))
+
+    with pytest.raises(ValueError):
+        provider.index([{"content": str(i)} for i in range(11)])
+
+    assert [len(batch) for batch in calls] == [10, 1]
+    assert connection_calls == []
+
+
+def test_index_rolls_back_insert_failure(sqlite_provider, monkeypatch):
+    real_connection = sqlite_provider._get_conn()
+    failure = RuntimeError("second insert failed")
+
+    class FailingConnection:
+        dialect = real_connection.dialect
+
+        def __init__(self):
+            self.execute_calls = 0
+            self.commit_calls = 0
+            self.rollback_calls = 0
+
+        def execute(self, statement, parameters=None):
+            self.execute_calls += 1
+            if self.execute_calls == 2:
+                raise failure
+            return real_connection.execute(statement, parameters)
+
+        def commit(self):
+            self.commit_calls += 1
+            return real_connection.commit()
+
+        def rollback(self):
+            self.rollback_calls += 1
+            return real_connection.rollback()
+
+    connection = FailingConnection()
+    monkeypatch.setattr(sqlite_provider, "_get_conn", lambda: connection)
+
+    with pytest.raises(RuntimeError, match="second insert failed"):
+        sqlite_provider.index([{"content": "first"}, {"content": "second"}])
+
+    assert connection.execute_calls == 2
+    assert connection.commit_calls == 0
+    assert connection.rollback_calls == 1
+    assert real_connection.execute(text("SELECT COUNT(*) FROM vector_chunks")).scalar() == 0
+
+
+def test_index_propagates_commit_failure(sqlite_provider, monkeypatch):
+    real_connection = sqlite_provider._get_conn()
+    failure = RuntimeError("commit failed")
+
+    class CommitFailingConnection:
+        dialect = real_connection.dialect
+
+        def __init__(self):
+            self.execute_calls = 0
+            self.commit_calls = 0
+            self.rollback_calls = 0
+
+        def execute(self, statement, parameters=None):
+            self.execute_calls += 1
+            return real_connection.execute(statement, parameters)
+
+        def commit(self):
+            self.commit_calls += 1
+            raise failure
+
+        def rollback(self):
+            self.rollback_calls += 1
+            return real_connection.rollback()
+
+    connection = CommitFailingConnection()
+    monkeypatch.setattr(sqlite_provider, "_get_conn", lambda: connection)
+
+    with pytest.raises(RuntimeError) as raised:
+        sqlite_provider.index([{"content": "first"}])
+
+    assert raised.value is failure
+    assert connection.execute_calls == 1
+    assert connection.commit_calls == 1
+    assert connection.rollback_calls == 1
+    assert real_connection.execute(text("SELECT COUNT(*) FROM vector_chunks")).scalar() == 0
+
+
+def test_index_preserves_primary_error_when_rollback_fails(monkeypatch):
+    primary_error = RuntimeError("insert failed")
+    rollback_error = RuntimeError("rollback failed")
+
+    class RollbackFailingConnection:
+        dialect = SimpleNamespace(name="sqlite")
+
+        def execute(self, statement, parameters=None):
+            raise primary_error
+
+        def commit(self):
+            raise AssertionError("failed insert must not commit")
+
+        def rollback(self):
+            raise rollback_error
+
+    provider = PgVectorProvider(
+        embedding_service=FakeEmbeddingService(dim=2), db_url="sqlite:///:memory:"
+    )
+    monkeypatch.setattr(provider, "_get_conn", lambda: RollbackFailingConnection())
+
+    with pytest.raises(RuntimeError) as raised:
+        provider.index([{"content": "first"}])
+
+    assert raised.value is primary_error
+
+
+def test_index_does_not_retry_after_commit_ack_loss(sqlite_provider, monkeypatch):
+    real_connection = sqlite_provider._get_conn()
+    ack_loss = RuntimeError("commit acknowledgement lost")
+
+    class CommitAckLossConnection:
+        dialect = real_connection.dialect
+
+        def __init__(self):
+            self.execute_calls = 0
+            self.commit_calls = 0
+            self.rollback_calls = 0
+
+        def execute(self, statement, parameters=None):
+            self.execute_calls += 1
+            return real_connection.execute(statement, parameters)
+
+        def commit(self):
+            self.commit_calls += 1
+            real_connection.commit()
+            raise ack_loss
+
+        def rollback(self):
+            self.rollback_calls += 1
+            return real_connection.rollback()
+
+    connection = CommitAckLossConnection()
+    monkeypatch.setattr(sqlite_provider, "_get_conn", lambda: connection)
+
+    with pytest.raises(RuntimeError) as raised:
+        sqlite_provider.index([{"content": "first"}])
+
+    assert raised.value is ack_loss
+    assert connection.execute_calls == 1
+    assert connection.commit_calls == 1
+    assert real_connection.execute(text("SELECT COUNT(*) FROM vector_chunks")).scalar() == 1
+
+
 def test_provider_name():
     """验证 provider name 为 'vector'。"""
     provider = PgVectorProvider(embedding_service=FakeEmbeddingService())
     assert provider.name == "vector"
 
 
 def test_make_sync_db_url_postgresql():
     """验证 async URL 转同步 URL（PostgreSQL）。"""
     async_url = "postgresql+asyncpg://user:pass@localhost/db"
     sync_url = PgVectorProvider._make_sync_db_url(async_url)
@@ -125,28 +457,28 @@ def test_index_single_doc(sqlite_provider):
     assert metadata == {"source": "book"}
 
 
 def test_index_multiple_docs(sqlite_provider):
     """验证能批量写入多个文档。"""
     docs = [
         {"content": "文本1", "doc_id": "doc1"},
         {"content": "文本2", "doc_id": "doc2"},
         {"content": "文本3", "doc_id": "doc3"},
     ]
-    sqlite_provider.index(docs)
+    assert sqlite_provider.index(docs) == 3
 
     assert sqlite_provider.doc_count == 3
 
 
 def test_index_empty_list(sqlite_provider):
     """验证空列表不报错。"""
-    sqlite_provider.index([])
+    assert sqlite_provider.index([]) == 0
     assert sqlite_provider.doc_count == 0
 
 
 def test_index_with_scope_and_user_id(sqlite_provider):
     """验证 scope 和 user_id 字段正确写入。"""
     docs = [{
         "content": "私有知识",
         "scope": "personal",
         "user_id": 42
     }]
