# T03 working-tree review package
BASE: 6324b9442b6f1671ccb4a19cdacb42bb91597187
No new commits; four tracked task files only.

diff --git a/app/agents/retriever.py b/app/agents/retriever.py
index 3896d06..cb93d78 100644
--- a/app/agents/retriever.py
+++ b/app/agents/retriever.py
@@ -3,51 +3,181 @@
 事件契约：
   source      = retriever
   subscriptions = [ActionRequested]（按 payload.target==retriever 过滤）
   emittable   = {RetrievedEvidence, RetrievalFailed}
 
 只做机械层：向量检索 + 原始 similarity score + retrieval_status。
 绝不评判"证据够不够好"（语义质量归 Critic 的 RAGQualityAssessed）。
 """
 
 import logging
+import math
 import time
 from collections import Counter
+from numbers import Real
 
 from app.agents.base import AgentBase
 from app.harness.enums import EventType, EventSource
 from app.harness.events import Event
 from app.harness.workspace_state import WorkspaceState
 from app.infrastructure.rag.coordinator import RAGCoordinator, VisibilityContext
 
 logger = logging.getLogger(__name__)
 
 LOW_SCORE_THRESHOLD = 0.3
 TOP_K_DEFAULT = 5
 TOP_K_MAX = 10
+EVALUATION_SCHEMA_VERSION = "retriever-evaluation-v1"
+JUDGE_METRIC_RANGES = {
+    "faithfulness": (0.0, 1.0),
+    "answer_relevancy": (-1.0, 1.0),
+    "context_precision": (0.0, 1.0),
+}
 
 # DEC-009（spec §G）：payload 只允许分类错误码 + 安全摘要；
 # str(exc)/SQL/连接串/堆栈只进内部日志。
 SAFE_SUMMARIES = {
     "backend_unavailable": "检索服务当前不可用",
     "db_error": "知识库服务暂时不可用",
     "embedding_failed": "知识索引服务暂时不可用",
     "provider_degraded": "部分知识来源不可用",
     "invalid_request": "当前请求无法检索知识",
     "timeout": "检索超时，请稍后重试",
 }
 
 
 def _safe_summary(error_code: str | None) -> str:
     return SAFE_SUMMARIES.get(error_code or "", "知识库服务暂时不可用")
 
 
+def _validate_judge_score(value, *, present: bool, minimum: float,
+                          maximum: float) -> dict:
+    if not present:
+        return {"value": None, "available": False, "safe_reason": "missing"}
+    if isinstance(value, bool) or not isinstance(value, Real):
+        return {"value": None, "available": False, "safe_reason": "non_numeric"}
+    try:
+        score = float(value)
+    except (OverflowError, ValueError):
+        return {"value": None, "available": False, "safe_reason": "non_finite"}
+    if not math.isfinite(score):
+        return {"value": None, "available": False, "safe_reason": "non_finite"}
+    if not minimum <= score <= maximum:
+        return {"value": None, "available": False, "safe_reason": "out_of_range"}
+    return {"value": score, "available": True, "safe_reason": None}
+
+
+def _collect_judge_scores(raw_scores, *, unavailable: bool) -> dict:
+    collected = {}
+    for name, (minimum, maximum) in JUDGE_METRIC_RANGES.items():
+        if unavailable:
+            collected[name] = {
+                "value": None, "available": False, "safe_reason": "unavailable",
+            }
+            continue
+        present = isinstance(raw_scores, dict) and name in raw_scores
+        values = raw_scores.get(name) if present else None
+        if isinstance(values, (list, tuple)):
+            if not values:
+                present = False
+                value = None
+            else:
+                value = values[0]
+        else:
+            value = values
+        collected[name] = _validate_judge_score(
+            value, present=present, minimum=minimum, maximum=maximum)
+    return collected
+
+
+def _new_evaluation_result(top_k, *, retrieval_status: str,
+                           error_code: str | None = None,
+                           sources_used: list[str] | None = None,
+                           attempted_providers: list[str] | None = None,
+                           failed_providers: list[str] | None = None,
+                           latency_ms: float | None = None,
+                           valid_for_quality: bool = False) -> dict:
+    judge_scores = {
+        name: {"value": None, "available": False, "safe_reason": "unavailable"}
+        for name in JUDGE_METRIC_RANGES
+    }
+    return {
+        "schema_version": EVALUATION_SCHEMA_VERSION,
+        "retrieval_status": retrieval_status,
+        "error_code": error_code,
+        "safe_summary": _safe_summary(error_code) if error_code else "",
+        "sources_used": sources_used or [],
+        "attempted_providers": attempted_providers or [],
+        "failed_providers": failed_providers or [],
+        "latency_ms": latency_ms,
+        "top_k": top_k,
+        "valid_for_quality": valid_for_quality,
+        "recall_at_k": None,
+        "recall_at_1": None,
+        "recall_at_3": None,
+        "recall_at_5": None,
+        "context_precision_proxy": None,
+        "redundancy": None,
+        "faithfulness": None,
+        "answer_relevancy": None,
+        "context_precision": None,
+        "judge_scores": judge_scores,
+        "judge_degraded": True,
+        "degraded": True,
+        "degraded_reason": None,
+    }
+
+
+def _compute_mechanical_metrics(retrieved_contents: list[str],
+                                golden_chunks: list[str], top_k: int) -> dict:
+    unique_gold = list(dict.fromkeys(golden_chunks))
+    returned = retrieved_contents[:top_k]
+
+    def recall(contents: list[str]) -> float | None:
+        if not unique_gold:
+            return None
+        matches = 0
+        for gold in unique_gold:
+            if any(gold in content or content in gold for content in contents):
+                matches += 1
+        return matches / len(unique_gold)
+
+    precision_proxy = None
+    if unique_gold:
+        relevant = sum(
+            any(gold in content or content in gold for gold in unique_gold)
+            for content in returned
+        )
+        precision_proxy = relevant / len(returned) if returned else 0.0
+
+    pairs = 0
+    similar = 0
+    for index, left_content in enumerate(returned):
+        left = Counter(left_content)
+        for right_content in returned[index + 1:]:
+            right = Counter(right_content)
+            intersection = sum((left & right).values())
+            union = sum((left | right).values())
+            pairs += 1
+            if union and intersection / union > 0.8:
+                similar += 1
+
+    return {
+        "recall_at_k": recall(returned),
+        "recall_at_1": recall(returned[:1]) if top_k >= 1 else None,
+        "recall_at_3": recall(returned[:3]) if top_k >= 3 else None,
+        "recall_at_5": recall(returned[:5]) if top_k >= 5 else None,
+        "context_precision_proxy": precision_proxy,
+        "redundancy": similar / pairs if pairs else 0.0,
+    }
+
+
 class RetrieverAgent(AgentBase):
     """知识检索 Agent（机械层，不自评语义质量）。"""
 
     source = EventSource.RETRIEVER
     subscriptions = [EventType.ACTION_REQUESTED]
     emittable_types = {EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}
 
     def __init__(self, coordinator: RAGCoordinator | None = None):
         self._coordinator = coordinator or RAGCoordinator()
 
@@ -192,170 +322,142 @@ class RetrieverAgent(AgentBase):
             payload["purpose"] = purpose
         if isinstance(retrieval_id, str) and retrieval_id:
             payload["retrieval_id"] = retrieval_id
 
         return [self.emit(EventType.RETRIEVED_EVIDENCE, ws,
                           payload=payload, parent_id=parent_id)]
 
     # --- 部件级评估接口（§5.2 RAG 三件套，供 Plan E 调用） ---
 
     def evaluate(self, test_case: dict) -> dict:
-        """部件级评估接口（§5.2 RAG 三件套 + recall@k）。
-
-        test_case 结构：
-          - query: str             检索查询
-          - golden_chunks: list[str] 人工标注的相关 chunk 内容
-          - golden_answer: str      期望答案（用于 faithfulness）
-          - top_k: int              检索数量（默认 5）
-
-        返回 6 个指标（初期启发式，后续可替换 ragas）。
-        """
-        query = test_case.get("query", "")
-        golden_chunks = test_case.get("golden_chunks", [])
-        golden_answer = test_case.get("golden_answer", "")
-        top_k = test_case.get("top_k", 5)
-
-        # 执行检索
-        t0 = time.time()
-        result = self._coordinator.search(query, sources=None, top_k=top_k)
-        latency_ms = (time.time() - t0) * 1000
-
-        retrieved_contents = [c.content for c in result.chunks]
-        combined = " ".join(retrieved_contents)
-
-        # --- recall@k：golden_chunks 中有多少被检索到 ---
-        if golden_chunks:
-            hit = sum(1 for g in golden_chunks
-                      if any(g in rc or rc in g for rc in retrieved_contents))
-            recall_at_k = hit / len(golden_chunks)
-        else:
-            recall_at_k = 1.0  # 无 golden_chunks 时无法评估，返回满分
-
-        # --- context_precision：检索结果中与 golden_chunks 相关的比例 ---
-        if retrieved_contents and golden_chunks:
-            relevant = sum(1 for rc in retrieved_contents
-                           if any(g in rc or rc in g for g in golden_chunks))
-            context_precision = relevant / len(retrieved_contents)
-        elif retrieved_contents:
-            # 无 golden_chunks：用 query 词重叠作为弱代理
-            query_tokens = set(query)
-            relevant = sum(1 for rc in retrieved_contents
-                           if any(t in rc for t in query_tokens))
-            context_precision = relevant / len(retrieved_contents)
+        """以一次 search 生成稳定的检索状态、机械 proxy 与 judge 结果。"""
+        raw_top_k = test_case.get("top_k", TOP_K_DEFAULT) if isinstance(test_case, dict) else None
+        top_k = raw_top_k if (isinstance(raw_top_k, int) and not isinstance(raw_top_k, bool)
+                              and 1 <= raw_top_k <= TOP_K_MAX) else None
+        query = test_case.get("query", "") if isinstance(test_case, dict) else None
+        golden_chunks = test_case.get("golden_chunks", []) if isinstance(test_case, dict) else None
+        golden_answer = test_case.get("golden_answer", "") if isinstance(test_case, dict) else None
+        valid_input = (
+            isinstance(query, str) and bool(query.strip())
+            and top_k is not None
+            and isinstance(golden_chunks, list)
+            and all(isinstance(chunk, str) for chunk in golden_chunks)
+            and isinstance(golden_answer, str)
+        )
+        if not valid_input:
+            result = _new_evaluation_result(
+                top_k, retrieval_status="invalid-request", error_code="invalid_request")
+            result["safe_summary"] = SAFE_SUMMARIES["invalid_request"]
+            result["degraded_reason"] = SAFE_SUMMARIES["invalid_request"]
+            return result
+
+        started = time.monotonic()
+        try:
+            search_result = self._coordinator.search(query, sources=None, top_k=top_k)
+        except TimeoutError:
+            code = "timeout"
+            result = _new_evaluation_result(
+                top_k, retrieval_status="failed", error_code=code)
+            result["safe_summary"] = SAFE_SUMMARIES[code]
+            result["degraded_reason"] = SAFE_SUMMARIES[code]
+            return result
+        except Exception:
+            code = "backend_unavailable"
+            result = _new_evaluation_result(
+                top_k, retrieval_status="failed", error_code=code)
+            result["safe_summary"] = SAFE_SUMMARIES[code]
+            result["degraded_reason"] = SAFE_SUMMARIES[code]
+            return result
+        elapsed = round(max(0.0, (time.monotonic() - started) * 1000), 3)
+        if not math.isfinite(elapsed):
+            elapsed = None
+
+        def provider_names(value):
+            return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
+
+        chunks = getattr(search_result, "chunks", None)
+        sources_used = provider_names(getattr(search_result, "sources_used", None))
+        attempted = provider_names(getattr(search_result, "attempted_providers", None))
+        failed = provider_names(getattr(search_result, "failed_providers", None))
+        outcome = getattr(search_result, "outcome", None)
+        raw_error_code = getattr(search_result, "error_code", None)
+        error_code = (raw_error_code if isinstance(raw_error_code, str)
+                      and raw_error_code in SAFE_SUMMARIES else None)
+
+        if outcome == "failed":
+            error_code = error_code or "backend_unavailable"
+            status = "invalid-request" if error_code == "invalid_request" else "failed"
+        elif outcome == "degraded":
+            status = "degraded"
+            error_code = error_code or "provider_degraded"
+        elif isinstance(outcome, str) and outcome in {"ok", "empty"} and isinstance(chunks, list):
+            status = "ok" if chunks else "empty"
+            error_code = None
         else:
-            context_precision = 0.0
-
-        # --- redundancy：检索结果中高度相似 chunk 对的比例（multiset Jaccard，
-        #   即按字符出现次数计算，避免重复字符被 set 折叠） ---
-        n = len(retrieved_contents)
-        if n >= 2:
-            similar_pairs = 0
-            for i in range(n):
-                for j in range(i + 1, n):
-                    ti = Counter(retrieved_contents[i])
-                    tj = Counter(retrieved_contents[j])
-                    inter = sum((ti & tj).values())
-                    union = sum((ti | tj).values())
-                    if union > 0 and inter / union > 0.8:
-                        similar_pairs += 1
-            total_pairs = n * (n - 1) / 2
-            redundancy = similar_pairs / total_pairs if total_pairs > 0 else 0.0
+            status = "failed"
+            error_code = "backend_unavailable"
+
+        result = _new_evaluation_result(
+            top_k, retrieval_status=status, error_code=error_code,
+            sources_used=sources_used, attempted_providers=attempted,
+            failed_providers=failed, latency_ms=elapsed,
+            valid_for_quality=status in {"ok", "empty"})
+        if status not in {"ok", "empty"}:
+            result["safe_summary"] = SAFE_SUMMARIES[error_code]
+            result["degraded_reason"] = SAFE_SUMMARIES[error_code]
+            return result
+
+        retrieved_contents = [getattr(chunk, "content", None) for chunk in chunks]
+        if not all(isinstance(content, str) for content in retrieved_contents):
+            result["retrieval_status"] = "failed"
+            result["error_code"] = "backend_unavailable"
+            result["safe_summary"] = SAFE_SUMMARIES["backend_unavailable"]
+            result["valid_for_quality"] = False
+            result["latency_ms"] = elapsed
+            result["degraded_reason"] = SAFE_SUMMARIES["backend_unavailable"]
+            return result
+
+        result.update(_compute_mechanical_metrics(retrieved_contents, golden_chunks, top_k))
+
+        if golden_answer:
+            try:
+                from ragas import evaluate as ragas_eval
+                from ragas.metrics import (
+                    faithfulness as m_faithfulness,
+                    answer_relevancy as m_answer_relevancy,
+                    context_precision as m_context_precision,
+                )
+                from datasets import Dataset
+                from app.eval.judge import build_judge
+
+                judge_handle = build_judge(target_agent_family="anthropic")
+                if judge_handle is None:
+                    judge_scores = _collect_judge_scores(None, unavailable=True)
+                else:
+                    eval_dataset = Dataset.from_dict({
+                        "user_input": [query],
+                        "response": [golden_answer],
+                        "retrieved_contexts": [retrieved_contents],
+                        "reference": [golden_answer],
+                    })
+                    ragas_result = ragas_eval(
+                        dataset=eval_dataset,
+                        metrics=[m_faithfulness, m_answer_relevancy, m_context_precision],
+                        llm=judge_handle["llm"],
+                        embeddings=judge_handle["embeddings"],
+                        raise_exceptions=False,
+                    )
+                    judge_scores = _collect_judge_scores(
+                        getattr(ragas_result, "_scores_dict", None), unavailable=False)
+            except Exception:
+                judge_scores = _collect_judge_scores(None, unavailable=True)
         else:
-            redundancy = 0.0
-
-        # --- RAGAS 评估三件套（faithfulness/answer_relevancy/context_precision） ---
-        if not golden_answer:
-            # 无 golden_answer 时 faithfulness/answer_relevancy 无意义，降级
-            return {
-                "recall_at_k": round(recall_at_k, 4),
-                "faithfulness": 0.0,
-                "answer_relevancy": 0.0,
-                "context_precision": round(context_precision, 4),  # 保留启发式
-                "latency_ms": round(latency_ms, 2),
-                "redundancy": round(redundancy, 4),
-                "degraded": True,
-                "degraded_reason": "无 golden_answer，无法评估 RAG 三件套",
-            }
-
-        try:
-            from ragas import evaluate as ragas_eval
-            from ragas.metrics import (
-                faithfulness as m_faithfulness,
-                answer_relevancy as m_answer_relevancy,
-                context_precision as m_context_precision,
-            )
-            from datasets import Dataset
-            from app.eval.judge import build_judge
-
-            # 构造 judge（复用 §5.1.1 不同族校验）
-            judge_handle = build_judge(target_agent_family="anthropic")
-
-            if judge_handle is None:
-                # 降级：judge 不可用（同族 / 无 key / 构造失败）
-                return {
-                    "recall_at_k": round(recall_at_k, 4),
-                    "faithfulness": 0.0,
-                    "answer_relevancy": 0.0,
-                    "context_precision": round(context_precision, 4),  # 保留启发式
-                    "latency_ms": round(latency_ms, 2),
-                    "redundancy": round(redundancy, 4),
-                    "degraded": True,
-                    "degraded_reason": "judge 不可用（同族或无 API key）",
-                }
-
-            # 包装为 RAGAS Dataset 格式（0.4.3 列名）
-            eval_dataset = Dataset.from_dict({
-                "user_input": [query],
-                "response": [golden_answer],
-                "retrieved_contexts": [retrieved_contents],
-                "reference": [golden_answer],  # context_precision 需要 reference
-            })
-
-            # 运行 RAGAS 评估（三指标）
-            ragas_result = ragas_eval(
-                dataset=eval_dataset,
-                metrics=[m_faithfulness, m_answer_relevancy, m_context_precision],
-                llm=judge_handle["llm"],
-                embeddings=judge_handle["embeddings"],
-                raise_exceptions=False,  # 单个失败不崩全局
-            )
-
-            # 提取分数（ragas_eval 返回 EvaluationResult，[key] → List[float]）
-            scores = ragas_result._scores_dict
-            ragas_faithfulness = float(scores["faithfulness"][0]) if "faithfulness" in scores else 0.0
-            ragas_answer_relevancy = float(scores["answer_relevancy"][0]) if "answer_relevancy" in scores else 0.0
-            ragas_context_precision = float(scores["context_precision"][0]) if "context_precision" in scores else context_precision
-
-            return {
-                "recall_at_k": round(recall_at_k, 4),
-                "faithfulness": round(ragas_faithfulness, 4),
-                "answer_relevancy": round(ragas_answer_relevancy, 4),
-                "context_precision": round(ragas_context_precision, 4),
-                "latency_ms": round(latency_ms, 2),
-                "redundancy": round(redundancy, 4),
-                "degraded": False,
-            }
-
-        except ImportError:
-            # RAGAS/datasets 未安装，降级到启发式
-            return {
-                "recall_at_k": round(recall_at_k, 4),
-                "faithfulness": 0.0,
-                "answer_relevancy": 0.0,
-                "context_precision": round(context_precision, 4),
-                "latency_ms": round(latency_ms, 2),
-                "redundancy": round(redundancy, 4),
-                "degraded": True,
-                "degraded_reason": "RAGAS 或 datasets 未安装",
-            }
-        except Exception as e:
-            # RAGAS 评估失败，降级
-            return {
-                "recall_at_k": round(recall_at_k, 4),
-                "faithfulness": 0.0,
-                "answer_relevancy": 0.0,
-                "context_precision": round(context_precision, 4),
-                "latency_ms": round(latency_ms, 2),
-                "redundancy": round(redundancy, 4),
-                "degraded": True,
-                "degraded_reason": f"RAGAS 评估失败: {str(e)}",
-            }
+            judge_scores = _collect_judge_scores(None, unavailable=True)
+
+        result["judge_scores"] = judge_scores
+        for name in JUDGE_METRIC_RANGES:
+            result[name] = judge_scores[name]["value"]
+        result["judge_degraded"] = any(not item["available"] for item in judge_scores.values())
+        result["degraded"] = result["judge_degraded"] or status not in {"ok", "empty"}
+        result["degraded_reason"] = (
+            "部分 judge 分数不可用" if result["judge_degraded"] else None)
+        return result
diff --git a/benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py b/benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py
index bba4d23..4591348 100644
--- a/benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py
+++ b/benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py
@@ -2,30 +2,61 @@
 
 本模块不抽取、切分、索引或写入数据库；它只将已验证 benchmark 资产转为
 ``RetrieverAgent.evaluate`` 的瞬态输入，并在调用前执行 DEC-010 准入检查。
 """
 
 from __future__ import annotations
 
 from dataclasses import dataclass
 from hashlib import sha256
 import json
+import math
 from pathlib import Path
+from numbers import Real
 from typing import Any, Callable
 
 import yaml
 
 from app.infrastructure.rag.pgvector_provider import PgVectorProvider
 
 PROXY_NAME = "paragraph-containment proxy"
 ENRICHMENT_NAME = "gold-answer/context enrichment"
 TOP_K = 5
+EXPECTED_COUNT = 20
+EVALUATION_SCHEMA_VERSION = "retriever-evaluation-v1"
+_EVALUATION_FIELDS = {
+    "schema_version", "retrieval_status", "error_code", "safe_summary",
+    "sources_used", "attempted_providers", "failed_providers", "latency_ms",
+    "top_k", "valid_for_quality", "recall_at_k", "recall_at_1", "recall_at_3",
+    "recall_at_5", "context_precision_proxy", "redundancy", "faithfulness",
+    "answer_relevancy", "context_precision", "judge_scores", "judge_degraded",
+    "degraded", "degraded_reason",
+}
+_MECHANICAL_FIELDS = (
+    "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
+    "context_precision_proxy", "redundancy",
+)
+_JUDGE_RANGES = {
+    "faithfulness": (0.0, 1.0),
+    "answer_relevancy": (-1.0, 1.0),
+    "context_precision": (0.0, 1.0),
+}
+_SAFE_SUMMARIES = {
+    "backend_unavailable": "检索服务当前不可用",
+    "db_error": "知识库服务暂时不可用",
+    "embedding_failed": "知识索引服务暂时不可用",
+    "provider_degraded": "部分知识来源不可用",
+    "invalid_request": "当前请求无法检索知识",
+    "timeout": "检索超时，请稍后重试",
+}
+_SAFE_JUDGE_REASONS = {"missing", "non_numeric", "non_finite", "out_of_range", "unavailable"}
+_ERROR_CODES = set(_SAFE_SUMMARIES)
 VALID_STATUSES = {
     "blocked:asset_invalid",
     "blocked:not_real_pgvector",
     "blocked:unattested_product_index",
     "infrastructure_inconclusive",
     "completed_judge_degraded",
     "completed",
 }
 _REQUIRED_ATTESTATION_FIELDS = {
     "ingestion_run_id", "source_sha256", "source_format", "doc_id",
@@ -92,49 +123,67 @@ def validate_assets(asset_dir: Path, source_path: Path | None = None) -> AssetBu
 
     corpus: dict[str, dict[str, Any]] = {}
     corpus_digest = sha256()
     with corpus_path.open("rb") as handle:
         for number, raw in enumerate(handle, start=1):
             corpus_digest.update(raw)
             try:
                 row = json.loads(raw)
             except json.JSONDecodeError as exc:
                 raise AssetValidationError(f"corpus 第 {number} 行不是 JSON") from exc
+            if not isinstance(row, dict):
+                raise AssetValidationError(f"corpus 第 {number} 行必须是 mapping")
             paragraph_id, text = row.get("paragraph_id"), row.get("text")
             if not isinstance(paragraph_id, str) or not paragraph_id or not isinstance(text, str):
                 raise AssetValidationError(f"corpus 第 {number} 行缺少 paragraph_id/text")
             if paragraph_id in corpus:
                 raise AssetValidationError(f"corpus paragraph_id 重复: {paragraph_id}")
             corpus[paragraph_id] = row
-    if len(corpus) != manifest.get("extraction", {}).get("paragraph_count"):
+    extraction = manifest.get("extraction")
+    if not isinstance(extraction, dict) or len(corpus) != extraction.get("paragraph_count"):
         raise AssetValidationError("corpus 段落数与 manifest 不一致")
 
     questions = questions_data.get("questions")
     if not isinstance(questions, list) or len(questions) != 20:
         raise AssetValidationError("题集必须恰有 20 题")
-    for case in questions:
+    seen_question_ids: set[str] = set()
+    for number, case in enumerate(questions, start=1):
+        if not isinstance(case, dict):
+            raise AssetValidationError(f"第 {number} 题必须是 mapping")
+        question_id = case.get("id")
+        if not isinstance(question_id, str) or not question_id.strip():
+            raise AssetValidationError(f"第 {number} 题缺少非空 id")
+        if question_id in seen_question_ids:
+            raise AssetValidationError(f"题目 id 重复: {question_id}")
+        seen_question_ids.add(question_id)
         if case.get("status") != "verified_v1":
-            continue
-        if not isinstance(case.get("question"), str) or not case["question"]:
+            raise AssetValidationError(f"题目必须是 verified_v1: {question_id}")
+        if not isinstance(case.get("question"), str) or not case["question"].strip():
             raise AssetValidationError(f"题目缺少 question: {case.get('id')}")
-        if not isinstance(case.get("gold_answer"), str) or not case["gold_answer"]:
+        if not isinstance(case.get("gold_answer"), str) or not case["gold_answer"].strip():
             raise AssetValidationError(f"已验证题目缺少 gold_answer: {case.get('id')}")
         evidence = case.get("gold_evidence")
         if not isinstance(evidence, list) or not evidence:
             raise AssetValidationError(f"已验证题目缺少 gold_evidence: {case.get('id')}")
         locator = case.get("source_locator")
         if not isinstance(locator, dict) or locator.get("page") is not None:
             raise AssetValidationError(f"source_locator.page 必须为 null: {case.get('id')}")
         locator_paragraphs = locator.get("paragraph")
         if isinstance(locator_paragraphs, str):
             locator_paragraphs = [locator_paragraphs]
+        if not isinstance(locator_paragraphs, list):
+            raise AssetValidationError(f"source_locator.paragraph 必须列出 evidence: {case.get('id')}")
+        if any(not isinstance(item, dict) for item in evidence):
+            raise AssetValidationError(f"gold_evidence 项必须是 mapping: {case.get('id')}")
         evidence_ids = [item.get("paragraph_id") for item in evidence]
+        if any(not isinstance(paragraph_id, str) or not paragraph_id for paragraph_id in evidence_ids):
+            raise AssetValidationError(f"gold_evidence 缺少 paragraph_id: {case.get('id')}")
         if locator_paragraphs != evidence_ids:
             raise AssetValidationError(f"source_locator.paragraph 与 gold_evidence 不一致: {case.get('id')}")
         for item in evidence:
             paragraph_id, excerpt = item.get("paragraph_id"), item.get("excerpt")
             if paragraph_id not in corpus:
                 raise AssetValidationError(f"未知 paragraph_id: {paragraph_id}")
             if not isinstance(excerpt, str) or excerpt not in corpus[paragraph_id]["text"]:
                 raise AssetValidationError(f"excerpt 不属于 paragraph: {paragraph_id}")
     return AssetBundle(manifest, questions, corpus, corpus_digest.hexdigest())
 
@@ -197,41 +246,243 @@ def validate_admission(agent: Any, settings_obj: Any, attestation: dict[str, Any
     return AdmissionResult(True)
 
 
 def run_baseline(agent: Any, settings_obj: Any, asset_dir: Path,
                  attestation: dict[str, Any] | None, corpus_isolation: dict[str, Any] | None,
                  source_path: Path | None = None,
                  dialect_getter: Callable[[PgVectorProvider], str] = _default_dialect) -> dict[str, Any]:
     """运行只读 baseline；每个 verified case 只调用一次 ``evaluate``。"""
     try:
         assets = validate_assets(asset_dir, source_path)
-    except (AssetValidationError, OSError, yaml.YAMLError) as exc:
-        return _envelope("blocked:asset_invalid", error=str(exc))
+    except Exception:
+        return _envelope(
+            "blocked:asset_invalid",
+            failures=[{"rule_id": "asset_validation"}],
+        )
     admission = validate_admission(agent, settings_obj, attestation, corpus_isolation,
                                    dialect_getter, assets.manifest["source"]["sha256"])
     if not admission.allowed:
         return _envelope(admission.status or "blocked:not_real_pgvector", failures=list(admission.failures))
 
-    results = []
-    try:
-        for case in assets.questions:
-            if case.get("status") != "verified_v1":
-                continue
+    results: list[dict[str, Any]] = []
+    failures: list[dict[str, str]] = []
+    attempted_count = 0
+    valid_count = 0
+    failed_count = 0
+    for case in assets.questions:
+        attempted_count += 1
+        case_id = case["id"]
+        try:
             metrics = agent.evaluate(to_evaluate_input(case, assets.corpus))
-            if not isinstance(metrics, dict):
-                raise TypeError("evaluate 未返回 metrics dict")
-            results.append({"case_id": case["id"], "metrics": metrics})
-        degraded = any(item["metrics"].get("degraded") for item in results)
-    except Exception as exc:
-        return _envelope("infrastructure_inconclusive", results=results, error=str(exc))
-    return _envelope("completed_judge_degraded" if degraded else "completed", results=results,
-                     asset_sha256={"source": assets.manifest["source"]["sha256"], "corpus": assets.corpus_sha256},
-                     attestation_id=attestation["ingestion_run_id"], corpus_isolation=corpus_isolation)
+        except TimeoutError:
+            metrics = _failed_attempt_metrics("timeout")
+            failures.append(_failure_record("evaluator_exception", case_id, "timeout"))
+            failed_count += 1
+            results.append({"case_id": case_id, "metrics": metrics})
+            break
+        except Exception:
+            metrics = _failed_attempt_metrics("backend_unavailable")
+            failures.append(_failure_record("evaluator_exception", case_id, "backend_unavailable"))
+            failed_count += 1
+            results.append({"case_id": case_id, "metrics": metrics})
+            break
+
+        if not _validate_evaluation_metrics(metrics):
+            metrics = _failed_attempt_metrics("invalid_request")
+            failures.append(_failure_record("evaluator_invalid_metrics", case_id, "invalid_request"))
+            failed_count += 1
+            results.append({"case_id": case_id, "metrics": metrics})
+            break
+
+        results.append({"case_id": case_id, "metrics": metrics})
+        if not metrics["valid_for_quality"]:
+            failures.append(_failure_record(
+                "retrieval_status", case_id,
+                metrics["error_code"] or "backend_unavailable",
+            ))
+            failed_count += 1
+            break
+        valid_count += 1
+
+    counts = {
+        "expected_count": EXPECTED_COUNT,
+        "attempted_count": attempted_count,
+        "valid_count": valid_count,
+        "failed_count": failed_count,
+        "not_run_count": EXPECTED_COUNT - attempted_count,
+        "results": results,
+        "failures": failures,
+    }
+    if failed_count:
+        return _envelope("infrastructure_inconclusive", **counts)
+
+    judge_degraded = any(item["metrics"]["judge_degraded"] for item in results)
+    return _envelope(
+        "completed_judge_degraded" if judge_degraded else "completed",
+        **counts,
+        asset_sha256={"source": assets.manifest["source"]["sha256"], "corpus": assets.corpus_sha256},
+        attestation_id=attestation["ingestion_run_id"], corpus_isolation=corpus_isolation,
+    )
+
+
+def _is_finite_number(value: Any, minimum: float, maximum: float) -> bool:
+    if isinstance(value, bool) or not isinstance(value, Real):
+        return False
+    try:
+        number = float(value)
+    except (OverflowError, ValueError):
+        return False
+    return math.isfinite(number) and minimum <= number <= maximum
+
+
+def _same_optional_number(left: Any, right: Any, minimum: float, maximum: float) -> bool:
+    if left is None or right is None:
+        return left is None and right is None
+    return (_is_finite_number(left, minimum, maximum)
+            and _is_finite_number(right, minimum, maximum)
+            and float(left) == float(right))
+
+
+def _validate_evaluation_metrics(metrics: Any) -> bool:
+    """Return false for malformed or adversarial evaluator values, never propagate them."""
+    try:
+        return _validate_evaluation_metrics_fields(metrics)
+    except Exception:
+        return False
+
+
+def _validate_evaluation_metrics_fields(metrics: Any) -> bool:
+    """Verify the complete D1 result, including all judge summary cross-fields."""
+    if not isinstance(metrics, dict) or set(metrics) != _EVALUATION_FIELDS:
+        return False
+    if metrics.get("schema_version") != EVALUATION_SCHEMA_VERSION:
+        return False
+
+    retrieval_status = metrics.get("retrieval_status")
+    if not isinstance(retrieval_status, str):
+        return False
+    if retrieval_status not in {"ok", "empty", "degraded", "failed", "invalid-request"}:
+        return False
+    healthy = retrieval_status in {"ok", "empty"}
+    error_code = metrics.get("error_code")
+    if error_code is not None and not isinstance(error_code, str):
+        return False
+    if healthy:
+        if error_code is not None or metrics.get("safe_summary") != "":
+            return False
+    elif error_code not in _ERROR_CODES or metrics.get("safe_summary") != _SAFE_SUMMARIES[error_code]:
+        return False
+    if retrieval_status == "invalid-request" and error_code != "invalid_request":
+        return False
+
+    for field in ("sources_used", "attempted_providers", "failed_providers"):
+        value = metrics.get(field)
+        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
+            return False
+    latency = metrics.get("latency_ms")
+    if latency is not None and not _is_finite_number(latency, 0.0, float("inf")):
+        return False
+    if type(metrics.get("top_k")) is not int or metrics["top_k"] != TOP_K:
+        return False
+    if type(metrics.get("valid_for_quality")) is not bool or metrics["valid_for_quality"] is not healthy:
+        return False
+
+    for field in _MECHANICAL_FIELDS:
+        value = metrics.get(field)
+        if healthy:
+            if not _is_finite_number(value, 0.0, 1.0):
+                return False
+        elif value is not None:
+            return False
+
+    judge_scores = metrics.get("judge_scores")
+    if not isinstance(judge_scores, dict) or set(judge_scores) != set(_JUDGE_RANGES):
+        return False
+    unavailable_reasons = []
+    for name, (minimum, maximum) in _JUDGE_RANGES.items():
+        score = judge_scores.get(name)
+        if not isinstance(score, dict) or set(score) != {"value", "available", "safe_reason"}:
+            return False
+        available = score.get("available")
+        value = score.get("value")
+        reason = score.get("safe_reason")
+        if type(available) is not bool:
+            return False
+        if available:
+            if reason is not None or not _is_finite_number(value, minimum, maximum):
+                return False
+        else:
+            if (value is not None or not isinstance(reason, str)
+                    or reason not in _SAFE_JUDGE_REASONS):
+                return False
+            unavailable_reasons.append(reason)
+        if not _same_optional_number(metrics.get(name), value, minimum, maximum):
+            return False
+
+    judge_degraded = bool(unavailable_reasons)
+    if type(metrics.get("judge_degraded")) is not bool or metrics["judge_degraded"] is not judge_degraded:
+        return False
+    if not healthy and any(
+        score["available"] is not False
+        or score["value"] is not None
+        or score["safe_reason"] != "unavailable"
+        for score in judge_scores.values()
+    ):
+        return False
+    expected_degraded = judge_degraded or not healthy
+    if type(metrics.get("degraded")) is not bool or metrics["degraded"] is not expected_degraded:
+        return False
+    expected_reason = (
+        "部分 judge 分数不可用" if healthy and judge_degraded else
+        _SAFE_SUMMARIES[error_code] if not healthy else None
+    )
+    if metrics.get("degraded_reason") != expected_reason:
+        return False
+    try:
+        json.dumps(metrics, ensure_ascii=False, allow_nan=False)
+    except (TypeError, ValueError, OverflowError):
+        return False
+    return True
+
+
+def _failed_attempt_metrics(error_code: str) -> dict[str, Any]:
+    retrieval_status = "invalid-request" if error_code == "invalid_request" else "failed"
+    judge_scores = {
+        name: {"value": None, "available": False, "safe_reason": "unavailable"}
+        for name in _JUDGE_RANGES
+    }
+    return {
+        "schema_version": EVALUATION_SCHEMA_VERSION,
+        "retrieval_status": retrieval_status,
+        "error_code": error_code,
+        "safe_summary": _SAFE_SUMMARIES[error_code],
+        "sources_used": [],
+        "attempted_providers": [],
+        "failed_providers": [],
+        "latency_ms": None,
+        "top_k": TOP_K,
+        "valid_for_quality": False,
+        **{field: None for field in _MECHANICAL_FIELDS},
+        "faithfulness": None,
+        "answer_relevancy": None,
+        "context_precision": None,
+        "judge_scores": judge_scores,
+        "judge_degraded": True,
+        "degraded": True,
+        "degraded_reason": "评测结果不可用",
+    }
+
+
+def _failure_record(rule_id: str, case_id: str, error_code: str) -> dict[str, str]:
+    return {"rule_id": rule_id, "case_id": case_id, "error_code": error_code}
 
 
 def _envelope(status: str, **payload: Any) -> dict[str, Any]:
     if status not in VALID_STATUSES:
         raise ValueError(f"未知 report status: {status}")
     return {"status": status, "evaluation_alignment": PROXY_NAME,
             "judge_enrichment": ENRICHMENT_NAME,
             "limitations": ["跨 chunk 切分或改写文本可能使 paragraph-containment proxy 误判。",
-                            "gold-answer/context enrichment 不代表在线 Tutor 质量。"], **payload}
+                            "gold-answer/context enrichment 不代表在线 Tutor 质量。"],
+            "expected_count": EXPECTED_COUNT, "attempted_count": 0, "valid_count": 0,
+            "failed_count": 0, "not_run_count": EXPECTED_COUNT, "results": [], "failures": [],
+            **payload}
diff --git a/tests/eval/test_rag_d.py b/tests/eval/test_rag_d.py
index 386a971..b7cd5e9 100644
--- a/tests/eval/test_rag_d.py
+++ b/tests/eval/test_rag_d.py
@@ -1,18 +1,18 @@
 from __future__ import annotations
 
 from hashlib import sha256
 import importlib.util
 import json
 from pathlib import Path
 import sys
-from types import SimpleNamespace
+from types import ModuleType, SimpleNamespace
 
 import pytest
 import yaml
 
 from app.infrastructure.rag.pgvector_provider import PgVectorProvider
 
 ASSET_DIR = Path(__file__).resolve().parents[2] / "benchmarks/rag/books/the-myth-of-sisyphus"
 MODULE_PATH = ASSET_DIR / "rag_d.py"
 SPEC = importlib.util.spec_from_file_location("rag_d_benchmark", MODULE_PATH)
 rag_d = importlib.util.module_from_spec(SPEC)
@@ -21,31 +21,89 @@ sys.modules[SPEC.name] = rag_d
 SPEC.loader.exec_module(rag_d)
 
 _SOURCE_BYTES = b"minimal test EPUB payload"
 _SOURCE_SHA256 = sha256(_SOURCE_BYTES).hexdigest()
 _PARAGRAPHS = {
     "paragraph-1": "第一段包含可验证摘录。",
     "paragraph-2": "第二段包含另一条可验证摘录。",
 }
 
 
+def _judge_score(value=0.8, *, available=True, safe_reason=None):
+    return {"value": value, "available": available, "safe_reason": safe_reason}
+
+
+def _evaluation_metrics(*, retrieval_status="ok", error_code=None,
+                        judge_values=(0.8, 0.7, 0.9), judge_available=None,
+                        top_k=5, valid_for_quality=None, degraded_reason=None):
+    judge_names = ("faithfulness", "answer_relevancy", "context_precision")
+    healthy = retrieval_status in {"ok", "empty"}
+    if judge_available is None:
+        judge_available = (True, True, True) if healthy else (False, False, False)
+    judge_scores = {
+        name: _judge_score(value if available else None, available=available,
+                           safe_reason=None if available else "unavailable")
+        for name, value, available in zip(judge_names, judge_values, judge_available)
+    }
+    judge_degraded = any(not item["available"] for item in judge_scores.values())
+    if valid_for_quality is None:
+        valid_for_quality = healthy
+    metric_values = {
+        "recall_at_k": 1.0 if healthy else None,
+        "recall_at_1": 1.0 if healthy else None,
+        "recall_at_3": 1.0 if healthy else None,
+        "recall_at_5": 1.0 if healthy else None,
+        "context_precision_proxy": 1.0 if healthy else None,
+        "redundancy": 0.0 if healthy else None,
+    }
+    return {
+        "schema_version": "retriever-evaluation-v1",
+        "retrieval_status": retrieval_status,
+        "error_code": error_code,
+        "safe_summary": "" if error_code is None else {
+            "backend_unavailable": "检索服务当前不可用",
+            "db_error": "知识库服务暂时不可用",
+            "embedding_failed": "知识索引服务暂时不可用",
+            "provider_degraded": "部分知识来源不可用",
+            "invalid_request": "当前请求无法检索知识",
+            "timeout": "检索超时，请稍后重试",
+        }[error_code],
+        "sources_used": ["vector"] if healthy else [],
+        "attempted_providers": ["vector"],
+        "failed_providers": ["vector"] if not healthy else [],
+        "latency_ms": 1.25 if healthy else None,
+        "top_k": top_k,
+        "valid_for_quality": valid_for_quality,
+        **metric_values,
+        **{name: judge_scores[name]["value"] for name in judge_names},
+        "judge_scores": judge_scores,
+        "judge_degraded": judge_degraded,
+        "degraded": judge_degraded or not healthy,
+        "degraded_reason": degraded_reason or (
+            "部分 judge 分数不可用" if judge_degraded else
+            "知识库服务暂时不可用" if not healthy else None
+        ),
+    }
+
+
 class FakeAgent:
-    def __init__(self, providers, metrics=None, fail_at=None):
+    def __init__(self, providers, metrics=None, fail_at=None, fail_exception=None):
         self._coordinator = SimpleNamespace(_providers=providers)
-        self.metrics = metrics or {"recall_at_k": 1.0, "degraded": False}
+        self.metrics = metrics if metrics is not None else _evaluation_metrics()
         self.fail_at = fail_at
+        self.fail_exception = fail_exception or RuntimeError("fake infrastructure unavailable")
         self.calls = 0
 
     def evaluate(self, test_case):
         self.calls += 1
         if self.calls == self.fail_at:
-            raise RuntimeError("fake infrastructure unavailable")
+            raise self.fail_exception
         assert set(test_case) == {"query", "golden_chunks", "golden_answer", "top_k"}
         return self.metrics
 
 
 def pg_provider():
     return object.__new__(PgVectorProvider)
 
 
 def write_assets(asset_dir: Path) -> Path:
     source_path = asset_dir / "source.epub"
@@ -79,82 +137,265 @@ def write_assets(asset_dir: Path) -> Path:
     }
     (asset_dir / "source-manifest.yaml").write_text(
         yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
     )
     (asset_dir / "questions.v1.yaml").write_text(
         yaml.safe_dump(questions_data, allow_unicode=True), encoding="utf-8"
     )
     return source_path
 
 
+def _write_questions(asset_dir: Path, questions):
+    questions_path = asset_dir / "questions.v1.yaml"
+    data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
+    data["questions"] = questions
+    questions_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
+
+
+def _assert_assets_blocked_before_evaluation(asset_dir: Path):
+    agent = admitted_agent()
+    report = rag_d.run_baseline(
+        agent, SimpleNamespace(rag_backend="pgvector"), asset_dir, attestation(),
+        {"mode": "isolated_db", "verified": True},
+        dialect_getter=lambda _: "postgresql",
+    )
+    assert report["status"] == "blocked:asset_invalid"
+    assert agent.calls == 0
+    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
+            report["failed_count"], report["not_run_count"], report["results"]) == (
+                20, 0, 0, 0, 20, [])
+
+
 @pytest.fixture
 def assets_dir(tmp_path):
     write_assets(tmp_path)
     return tmp_path
 
 
+@pytest.fixture(autouse=True)
+def disable_external_judge_by_default(monkeypatch):
+    """Runner tests must stay on synthetic admission, provider, and judge paths."""
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
+    pg_attempts = {"construct": 0, "connect": 0}
+    sdk_attempts = {"chat": 0, "openai": 0}
+
+    def forbid_pg_construct(*_args, **_kwargs):
+        pg_attempts["construct"] += 1
+        raise AssertionError("eval tests must not construct a real PG provider")
+
+    def forbid_pg_connect(*_args, **_kwargs):
+        pg_attempts["connect"] += 1
+        raise AssertionError("eval tests must not connect to a real PG provider")
+
+    def forbid_chat_sdk(*_args, **_kwargs):
+        sdk_attempts["chat"] += 1
+        raise AssertionError("eval tests must not construct a real chat SDK client")
+
+    def forbid_openai_sdk(*_args, **_kwargs):
+        sdk_attempts["openai"] += 1
+        raise AssertionError("eval tests must not construct a real OpenAI SDK client")
+
+    monkeypatch.setattr("app.infrastructure.rag.pgvector_provider.PgVectorProvider.__init__", forbid_pg_construct)
+    monkeypatch.setattr("app.infrastructure.rag.pgvector_provider.PgVectorProvider._get_conn", forbid_pg_connect)
+    import langchain_openai
+    import openai
+    monkeypatch.setattr(langchain_openai, "ChatOpenAI", forbid_chat_sdk)
+    monkeypatch.setattr(openai, "OpenAI", forbid_openai_sdk)
+    yield
+    assert pg_attempts == {"construct": 0, "connect": 0}
+    assert sdk_attempts == {"chat": 0, "openai": 0}
+
+
 def attestation():
     return {
         "ingestion_run_id": "run-1", "source_sha256": _SOURCE_SHA256,
         "source_format": "epub", "doc_id": "doc-1", "normalizer_version": "doc-norm-1",
         "chunking_version": "chunk-v1", "planned_chunk_count": 313, "written_chunk_count": 313,
         "backend": "pgvector", "dialect": "postgresql", "scope": "global", "owner": None,
     }
 
 
-def admitted_agent(metrics=None, fail_at=None):
-    return FakeAgent({"vector": pg_provider()}, metrics, fail_at)
+def admitted_agent(metrics=None, fail_at=None, fail_exception=None):
+    return FakeAgent({"vector": pg_provider()}, metrics, fail_at, fail_exception)
 
 
 def test_assets_validate_and_adapter_uses_full_paragraphs(assets_dir):
     assets = rag_d.validate_assets(assets_dir)
     case = assets.questions[0]
     mapped = rag_d.to_evaluate_input(case, assets.corpus)
 
     assert len(assets.questions) == 20
+    assert set(mapped) == {"query", "golden_chunks", "golden_answer", "top_k"}
     assert mapped["top_k"] == 5
     assert mapped["golden_chunks"] == [assets.corpus[case["gold_evidence"][0]["paragraph_id"]]["text"]]
     assert case["gold_evidence"][0]["excerpt"] != mapped["golden_chunks"][0]
 
 
+@pytest.mark.parametrize("count", [19, 21])
+def test_assets_contract_requires_exactly_twenty_cases(assets_dir, count):
+    questions_path = assets_dir / "questions.v1.yaml"
+    data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
+    if count < 20:
+        data["questions"].pop()
+    else:
+        data["questions"].append(dict(data["questions"][-1], id="question-21"))
+    questions_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
+
+    with pytest.raises(rag_d.AssetValidationError, match="20"):
+        rag_d.validate_assets(assets_dir)
+
+
+@pytest.mark.parametrize("draft_indexes", [[0], [19], list(range(20))])
+def test_assets_contract_rejects_every_draft_before_runner(assets_dir, draft_indexes):
+    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
+    for index in draft_indexes:
+        data["questions"][index]["status"] = "draft"
+    _write_questions(assets_dir, data["questions"])
+
+    with pytest.raises(rag_d.AssetValidationError, match="verified_v1"):
+        rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
+
+
+@pytest.mark.parametrize(
+    ("field", "value"),
+    [("question", None), ("question", ""), ("gold_answer", None),
+     ("gold_answer", ""), ("gold_evidence", [])],
+)
+def test_assets_contract_rejects_missing_gold_fields_before_runner(assets_dir, field, value):
+    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
+    data["questions"][0][field] = value
+    _write_questions(assets_dir, data["questions"])
+
+    with pytest.raises(rag_d.AssetValidationError, match=field):
+        rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
+
+
+@pytest.mark.parametrize("bad_id", [None, "", "   "])
+def test_assets_contract_rejects_missing_or_blank_ids_before_runner(assets_dir, bad_id):
+    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
+    data["questions"][0]["id"] = bad_id
+    _write_questions(assets_dir, data["questions"])
+
+    with pytest.raises(rag_d.AssetValidationError, match="id"):
+        rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
+
+
+def test_assets_contract_rejects_duplicate_ids_before_runner(assets_dir):
+    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
+    data["questions"][1]["id"] = data["questions"][0]["id"]
+    _write_questions(assets_dir, data["questions"])
+
+    with pytest.raises(rag_d.AssetValidationError, match="id"):
+        rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
+
+
+def test_assets_contract_rejects_non_mapping_case_before_runner(assets_dir):
+    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
+    data["questions"][0] = "not a mapping"
+    _write_questions(assets_dir, data["questions"])
+
+    with pytest.raises(rag_d.AssetValidationError, match="mapping"):
+        rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
+
+
+@pytest.mark.parametrize("field", ["question", "gold_answer"])
+def test_assets_contract_rejects_blank_question_or_answer_before_runner(assets_dir, field):
+    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
+    data["questions"][0][field] = "   "
+    _write_questions(assets_dir, data["questions"])
+
+    with pytest.raises(rag_d.AssetValidationError, match=field):
+        rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
+
+
 def test_validator_rejects_broken_excerpt(assets_dir):
     questions_path = assets_dir / "questions.v1.yaml"
     questions = questions_path.read_text(encoding="utf-8")
     questions_path.write_text(questions.replace("可验证摘录", "不存在的摘录", 1), encoding="utf-8")
 
     with pytest.raises(rag_d.AssetValidationError, match="excerpt"):
         rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
 
 
 def test_validator_rejects_corpus_version_or_locator_drift(assets_dir):
     questions_path = assets_dir / "questions.v1.yaml"
     questions = questions_path.read_text(encoding="utf-8")
     questions_path.write_text(questions.replace(_SOURCE_SHA256, "0" * 64, 1), encoding="utf-8")
     with pytest.raises(rag_d.AssetValidationError, match="corpus_version"):
         rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
 
     write_assets(assets_dir)
     questions = questions_path.read_text(encoding="utf-8")
     questions_path.write_text(questions.replace("- paragraph-1", "- missing-locator", 1), encoding="utf-8")
     with pytest.raises(rag_d.AssetValidationError, match="source_locator.paragraph"):
         rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
+
+
+def test_validator_rejects_source_bytes_drift_before_runner(assets_dir):
+    (assets_dir / "source.epub").write_bytes(b"changed EPUB payload")
+
+    with pytest.raises(rag_d.AssetValidationError, match="SHA-256"):
+        rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
+
+
+def test_assets_contract_rejects_non_mapping_corpus_row_before_runner(assets_dir):
+    corpus_path = assets_dir / "corpus.local.jsonl"
+    rows = corpus_path.read_text(encoding="utf-8").splitlines()
+    rows[0] = json.dumps(["not", "a", "mapping"])
+    corpus_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
+
+    with pytest.raises(rag_d.AssetValidationError, match="mapping"):
+        rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
 
 
 def test_runner_returns_asset_blocked_when_corpus_is_missing(tmp_path):
     source_path = write_assets(tmp_path)
     (tmp_path / "corpus.local.jsonl").unlink()
     report = rag_d.run_baseline(
         admitted_agent(), SimpleNamespace(rag_backend="pgvector"), tmp_path, attestation(),
         {"mode": "isolated_db", "verified": True}, source_path=source_path,
         dialect_getter=lambda _: "postgresql",
     )
     assert report["status"] == "blocked:asset_invalid"
+    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
+            report["failed_count"], report["not_run_count"]) == (20, 0, 0, 0, 20)
+
+
+def test_runner_does_not_expose_asset_oserror_text(assets_dir, monkeypatch):
+    secret = "private SQL URL postgres://credential"
+
+    def fail_validation(*_args, **_kwargs):
+        raise OSError(secret)
+
+    monkeypatch.setattr(rag_d, "validate_assets", fail_validation)
+
+    report = _run_report(admitted_agent(), assets_dir)
+
+    assert report["status"] == "blocked:asset_invalid"
+    assert "error" not in report
+    assert secret not in json.dumps(report, ensure_ascii=False)
+    assert report["failures"] == [{"rule_id": "asset_validation"}]
+    assert "error_code" not in report["failures"][0]
+    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
+            report["failed_count"], report["not_run_count"], report["results"]) == (
+                20, 0, 0, 0, 20, [])
 
 
 @pytest.mark.parametrize(
     ("settings_backend", "providers", "dialect", "expected_failure"),
     [
         ("fake", {"vector": pg_provider()}, "postgresql", "backend"),
         ("pgvector", {"vector": object()}, "postgresql", "provider"),
         ("pgvector", {"vector": pg_provider()}, "sqlite", "dialect"),
         ("pgvector", {"vector": pg_provider(), "ocr": object()}, "postgresql", "provider-set"),
     ],
@@ -190,43 +431,425 @@ def test_admission_blocks_missing_attestation_and_unverified_corpus(bad_attestat
 def test_admission_prioritizes_backend_truth_and_keeps_all_failed_checks():
     result = rag_d.validate_admission(
         FakeAgent({"vector": object()}), SimpleNamespace(rag_backend="fake"), None,
         None, lambda _: "sqlite",
     )
     assert result.status == "blocked:not_real_pgvector"
     assert result.failures == ("backend", "provider", "dialect", "attestation", "corpus-isolation")
 
 
 def test_runner_calls_each_case_once_and_reports_judge_degraded(assets_dir):
-    agent = admitted_agent({"recall_at_k": 0.5, "degraded": True})
+    agent = admitted_agent(_evaluation_metrics(judge_available=(False, True, True)))
     report = rag_d.run_baseline(
         agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
         {"mode": "isolated_db", "verified": True}, dialect_getter=lambda _: "postgresql",
     )
     assert report["status"] == "completed_judge_degraded"
     assert agent.calls == 20
     assert len(report["results"]) == 20
+    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
+            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
     assert report["evaluation_alignment"] == "paragraph-containment proxy"
     assert report["judge_enrichment"] == "gold-answer/context enrichment"
 
 
 def test_runner_classifies_evaluator_failure_without_second_run(assets_dir):
     agent = admitted_agent(fail_at=2)
     report = rag_d.run_baseline(
         agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
         {"mode": "provenance_filter", "verified": True}, dialect_getter=lambda _: "postgresql",
     )
     assert report["status"] == "infrastructure_inconclusive"
     assert agent.calls == 2
-    assert len(report["results"]) == 1
+    assert len(report["results"]) == 2
+    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
+            report["not_run_count"]) == (2, 1, 1, 18)
 
 
 def test_runner_classifies_invalid_metrics_without_second_run(assets_dir):
     agent = admitted_agent(metrics=None)
     agent.metrics = None
     report = rag_d.run_baseline(
         agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
         {"mode": "isolated_db", "verified": True}, dialect_getter=lambda _: "postgresql",
     )
     assert report["status"] == "infrastructure_inconclusive"
     assert agent.calls == 1
-    assert report["results"] == []
+    assert len(report["results"]) == 1
+    assert report["results"][0]["metrics"]["retrieval_status"] == "invalid-request"
+    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
+            report["not_run_count"]) == (1, 0, 1, 19)
+
+
+def _run_report(agent, assets_dir):
+    return rag_d.run_baseline(
+        agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
+        {"mode": "isolated_db", "verified": True}, dialect_getter=lambda _: "postgresql",
+    )
+
+
+@pytest.mark.parametrize("retrieval_status", ["ok", "empty"])
+def test_runner_contract_completes_twenty_healthy_cases_even_with_low_recall(assets_dir, retrieval_status):
+    metrics = _evaluation_metrics(retrieval_status=retrieval_status)
+    if retrieval_status == "ok":
+        metrics.update({key: 0.0 for key in (
+            "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
+            "context_precision_proxy", "redundancy",
+        )})
+    agent = admitted_agent(metrics)
+
+    report = _run_report(agent, assets_dir)
+
+    assert report["status"] == "completed"
+    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
+            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
+    assert [item["case_id"] for item in report["results"]] == [f"question-{n}" for n in range(1, 21)]
+    assert agent.calls == len(report["results"]) == 20
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+@pytest.mark.parametrize(
+    ("retrieval_status", "error_code"),
+    [("failed", "db_error"), ("degraded", "provider_degraded"),
+     ("invalid-request", "invalid_request")],
+)
+def test_runner_contract_stops_and_retains_first_unhealthy_attempt(
+    assets_dir, retrieval_status, error_code
+):
+    agent = admitted_agent(_evaluation_metrics(retrieval_status=retrieval_status, error_code=error_code))
+
+    report = _run_report(agent, assets_dir)
+
+    assert report["status"] == "infrastructure_inconclusive"
+    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
+            report["not_run_count"]) == (1, 0, 1, 19)
+    assert [item["case_id"] for item in report["results"]] == ["question-1"]
+    assert report["results"][0]["metrics"]["valid_for_quality"] is False
+    assert agent.calls == 1
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+@pytest.mark.parametrize(
+    ("fail_at", "counts", "failure_type", "error_code"),
+    [(1, (1, 0, 1, 19), RuntimeError, "backend_unavailable"),
+     (2, (2, 1, 1, 18), RuntimeError, "backend_unavailable"),
+     (20, (20, 19, 1, 0), RuntimeError, "backend_unavailable"),
+     (1, (1, 0, 1, 19), TimeoutError, "timeout")],
+)
+def test_runner_contract_synthesizes_and_keeps_exception_attempt(
+    assets_dir, fail_at, counts, failure_type, error_code
+):
+    agent = admitted_agent(fail_at=fail_at, fail_exception=failure_type("private failure detail"))
+
+    report = _run_report(agent, assets_dir)
+
+    attempted, valid, failed, not_run = counts
+    assert report["status"] == "infrastructure_inconclusive"
+    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
+            report["not_run_count"]) == counts
+    assert len(report["results"]) == attempted
+    assert [item["case_id"] for item in report["results"]] == [
+        f"question-{n}" for n in range(1, attempted + 1)
+    ]
+    failed_metrics = report["results"][-1]["metrics"]
+    assert failed_metrics["retrieval_status"] == "failed"
+    assert failed_metrics["error_code"] == error_code
+    assert failed_metrics["valid_for_quality"] is False
+    assert all(failed_metrics[key] is None for key in (
+        "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
+        "context_precision_proxy", "redundancy", "faithfulness", "answer_relevancy",
+        "context_precision",
+    ))
+    assert report["failures"][-1]["rule_id"] == "evaluator_exception"
+    assert report["failures"][-1]["case_id"] == f"question-{fail_at}"
+    assert report["failures"][-1]["error_code"] == error_code
+    assert "private failure detail" not in json.dumps(report, ensure_ascii=False)
+    assert agent.calls == attempted
+    assert (attempted, valid, failed, not_run) == (valid + failed, valid, failed, 20 - attempted)
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+@pytest.mark.parametrize(
+    "invalid_kind",
+    ["not_dict", "missing_schema", "missing_key", "bool_top_k", "nan", "unknown_code",
+     "status_unhashable", "code_unhashable", "reason_unhashable",
+     "failed_with_valid_judge", "degraded_with_valid_judge"],
+)
+def test_runner_contract_replaces_invalid_metrics_without_leaking_input(assets_dir, invalid_kind):
+    metrics = _evaluation_metrics()
+    if invalid_kind == "not_dict":
+        metrics = "private evaluator output"
+    elif invalid_kind == "missing_schema":
+        metrics.pop("schema_version")
+    elif invalid_kind == "missing_key":
+        metrics.pop("sources_used")
+    elif invalid_kind == "bool_top_k":
+        metrics["top_k"] = True
+    elif invalid_kind == "nan":
+        metrics["recall_at_k"] = float("nan")
+    elif invalid_kind == "unknown_code":
+        metrics["error_code"] = "private SQL connection string"
+    elif invalid_kind == "status_unhashable":
+        metrics["retrieval_status"] = []
+    elif invalid_kind == "code_unhashable":
+        metrics.update(_evaluation_metrics(retrieval_status="failed", error_code="db_error"))
+        metrics["error_code"] = []
+    elif invalid_kind == "reason_unhashable":
+        metrics = _evaluation_metrics(judge_available=(False, True, True))
+        metrics["judge_scores"]["faithfulness"]["safe_reason"] = []
+    elif invalid_kind in {"failed_with_valid_judge", "degraded_with_valid_judge"}:
+        status = "failed" if invalid_kind.startswith("failed") else "degraded"
+        error_code = "db_error" if status == "failed" else "provider_degraded"
+        metrics = _evaluation_metrics(retrieval_status=status, error_code=error_code)
+        for name, value in zip(("faithfulness", "answer_relevancy", "context_precision"), (0.8, 0.7, 0.9)):
+            metrics["judge_scores"][name] = _judge_score(value)
+            metrics[name] = value
+        metrics["judge_degraded"] = False
+    agent = admitted_agent(metrics)
+
+    report = _run_report(agent, assets_dir)
+
+    assert report["status"] == "infrastructure_inconclusive"
+    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
+            report["not_run_count"]) == (1, 0, 1, 19)
+    result_metrics = report["results"][0]["metrics"]
+    assert result_metrics["retrieval_status"] == "invalid-request"
+    assert result_metrics["error_code"] == "invalid_request"
+    assert result_metrics["valid_for_quality"] is False
+    assert result_metrics["safe_summary"] != "private evaluator output"
+    assert result_metrics["error_code"] != "private SQL connection string"
+    assert report["failures"] == [{
+        "rule_id": "evaluator_invalid_metrics", "case_id": "question-1",
+        "error_code": "invalid_request",
+    }]
+    assert agent.calls == 1
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+def _contradict_metrics(contradiction):
+    metrics = _evaluation_metrics()
+    if contradiction == "all_unavailable_but_not_degraded":
+        metrics = _evaluation_metrics(judge_available=(False, False, False))
+        metrics["judge_degraded"] = False
+        metrics["degraded"] = False
+    elif contradiction == "partial_unavailable_but_not_degraded":
+        metrics = _evaluation_metrics(judge_available=(False, True, True))
+        metrics["judge_degraded"] = False
+        metrics["degraded"] = False
+    elif contradiction == "all_available_but_judge_degraded":
+        metrics["judge_degraded"] = True
+        metrics["degraded"] = True
+    elif contradiction == "top_level_mismatch":
+        metrics["faithfulness"] = 0.2
+    elif contradiction == "top_level_null_mismatch":
+        metrics["context_precision"] = None
+    return metrics
+
+
+@pytest.mark.parametrize(
+    "contradiction",
+    ["all_unavailable_but_not_degraded", "partial_unavailable_but_not_degraded",
+     "all_available_but_judge_degraded", "top_level_mismatch", "top_level_null_mismatch"],
+)
+@pytest.mark.parametrize(("bad_at", "counts"), [(1, (1, 0, 1, 19)), (20, (20, 19, 1, 0))])
+def test_runner_contract_rejects_judge_cross_field_contradictions_at_first_or_last_case(
+    assets_dir, contradiction, bad_at, counts
+):
+    agent = admitted_agent()
+    valid_metrics = _evaluation_metrics()
+    invalid_metrics = _contradict_metrics(contradiction)
+
+    def evaluate(_test_case):
+        agent.calls += 1
+        return invalid_metrics if agent.calls == bad_at else valid_metrics
+
+    agent.evaluate = evaluate
+    report = _run_report(agent, assets_dir)
+
+    assert report["status"] == "infrastructure_inconclusive"
+    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
+            report["not_run_count"]) == counts
+    assert len(report["results"]) == bad_at
+    assert report["results"][-1]["case_id"] == f"question-{bad_at}"
+    failed_metrics = report["results"][-1]["metrics"]
+    assert failed_metrics["retrieval_status"] == "invalid-request"
+    assert all(failed_metrics[key] is None for key in (
+        "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
+        "context_precision_proxy", "redundancy", "faithfulness", "answer_relevancy",
+        "context_precision",
+    ))
+    assert report["failures"][-1]["rule_id"] == "evaluator_invalid_metrics"
+    assert agent.calls == bad_at
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+@pytest.mark.parametrize(
+    ("judge_values", "judge_available", "expected_status"),
+    [((0.0, -1.0, 0.0), (True, True, True), "completed"),
+     ((0.0, -0.5, 0.0), (False, True, True), "completed_judge_degraded")],
+)
+def test_runner_contract_accepts_legal_zero_negative_and_judge_degraded(
+    assets_dir, judge_values, judge_available, expected_status
+):
+    agent = admitted_agent(_evaluation_metrics(
+        judge_values=judge_values, judge_available=judge_available,
+    ))
+
+    report = _run_report(agent, assets_dir)
+
+    assert report["status"] == expected_status
+    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
+            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
+    assert report["results"][0]["metrics"]["faithfulness"] == (
+        judge_values[0] if judge_available[0] else None)
+    assert report["results"][0]["metrics"]["answer_relevancy"] == (
+        judge_values[1] if judge_available[1] else None)
+    assert agent.calls == 20
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+def _install_runner_judge(monkeypatch, scores):
+    ragas = ModuleType("ragas")
+    ragas.__path__ = []
+    ragas.evaluate = lambda **_: SimpleNamespace(_scores_dict=scores)
+    ragas_metrics = ModuleType("ragas.metrics")
+    ragas_metrics.faithfulness = object()
+    ragas_metrics.answer_relevancy = object()
+    ragas_metrics.context_precision = object()
+    datasets = ModuleType("datasets")
+
+    class Dataset:
+        @staticmethod
+        def from_dict(values):
+            return values
+
+    datasets.Dataset = Dataset
+    monkeypatch.setitem(sys.modules, "ragas", ragas)
+    monkeypatch.setitem(sys.modules, "ragas.metrics", ragas_metrics)
+    monkeypatch.setitem(sys.modules, "datasets", datasets)
+    monkeypatch.setattr(
+        "app.eval.judge.build_judge",
+        lambda **_: {"llm": object(), "embeddings": object()},
+    )
+
+
+def _real_evaluator_agent(mode):
+    from app.agents.retriever import RetrieverAgent
+    from app.infrastructure.rag.coordinator import Chunk, IndexProvider, RAGCoordinator
+
+    class ControlledVectorProvider(IndexProvider):
+        name = "vector"
+
+        def __init__(self):
+            self.calls = 0
+
+        def index(self, docs):
+            return len(docs)
+
+        def search(self, query, top_k=5, visibility=None):
+            self.calls += 1
+            if mode == "failed":
+                raise RuntimeError("private db connection secret")
+            if mode == "empty":
+                return []
+            return [Chunk(content="第一段包含可验证摘录。", score=0.9, source="vector")]
+
+        @property
+        def doc_count(self):
+            return 1
+
+    class FailingOCRProvider(IndexProvider):
+        name = "ocr"
+
+        def index(self, docs):
+            return len(docs)
+
+        def search(self, query, top_k=5, visibility=None):
+            raise RuntimeError("private OCR endpoint")
+
+        @property
+        def doc_count(self):
+            return 0
+
+    vector = ControlledVectorProvider()
+    coordinator = RAGCoordinator(vector_provider=vector)
+    if mode == "degraded":
+        coordinator.register_provider(FailingOCRProvider())
+    return RetrieverAgent(coordinator=coordinator), vector
+
+
+def _admit_controlled_real_evaluator(monkeypatch):
+    monkeypatch.setattr(rag_d, "validate_admission", lambda *_args, **_kwargs: rag_d.AdmissionResult(True))
+
+
+def test_runner_real_evaluator_stops_on_coordinator_captured_db_failure(assets_dir, monkeypatch):
+    _admit_controlled_real_evaluator(monkeypatch)
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
+    agent, vector = _real_evaluator_agent("failed")
+
+    report = _run_report(agent, assets_dir)
+
+    assert report["status"] == "infrastructure_inconclusive"
+    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
+            report["not_run_count"]) == (1, 0, 1, 19)
+    metrics = report["results"][0]["metrics"]
+    assert metrics["retrieval_status"] == "failed"
+    assert metrics["error_code"] == "db_error"
+    assert metrics["failed_providers"] == ["vector"]
+    assert metrics["valid_for_quality"] is False
+    assert vector.calls == 1
+    assert "private db connection secret" not in json.dumps(report, ensure_ascii=False)
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+def test_runner_real_evaluator_stops_on_coordinator_degraded_result(assets_dir, monkeypatch):
+    _admit_controlled_real_evaluator(monkeypatch)
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
+    agent, vector = _real_evaluator_agent("degraded")
+
+    report = _run_report(agent, assets_dir)
+
+    assert report["status"] == "infrastructure_inconclusive"
+    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
+            report["not_run_count"]) == (1, 0, 1, 19)
+    metrics = report["results"][0]["metrics"]
+    assert metrics["retrieval_status"] == "degraded"
+    assert metrics["error_code"] == "provider_degraded"
+    assert metrics["sources_used"] == ["vector"]
+    assert metrics["failed_providers"] == ["ocr"]
+    assert vector.calls == 1
+
+
+def test_runner_real_evaluator_completes_healthy_empty_with_judge_unavailable(assets_dir, monkeypatch):
+    _admit_controlled_real_evaluator(monkeypatch)
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
+    agent, vector = _real_evaluator_agent("empty")
+
+    report = _run_report(agent, assets_dir)
+
+    assert report["status"] == "completed_judge_degraded"
+    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
+            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
+    assert all(item["metrics"]["retrieval_status"] == "empty" for item in report["results"])
+    assert all(item["metrics"]["recall_at_k"] == 0.0 for item in report["results"])
+    assert all(item["metrics"]["judge_degraded"] is True for item in report["results"])
+    assert vector.calls == 20
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+def test_runner_real_evaluator_completes_with_controlled_judge_scores(assets_dir, monkeypatch):
+    _admit_controlled_real_evaluator(monkeypatch)
+    _install_runner_judge(monkeypatch, {
+        "faithfulness": [0.8], "answer_relevancy": [-0.2], "context_precision": [0.9],
+    })
+    agent, vector = _real_evaluator_agent("healthy")
+
+    report = _run_report(agent, assets_dir)
+
+    assert report["status"] == "completed"
+    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
+            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
+    assert all(item["metrics"]["retrieval_status"] == "ok" for item in report["results"])
+    assert all(item["metrics"]["faithfulness"] == 0.8 for item in report["results"])
+    assert all(item["metrics"]["answer_relevancy"] == -0.2 for item in report["results"])
+    assert vector.calls == 20
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
diff --git a/tests/unit/agents/test_retriever.py b/tests/unit/agents/test_retriever.py
index 4347ddf..cf6d384 100644
--- a/tests/unit/agents/test_retriever.py
+++ b/tests/unit/agents/test_retriever.py
@@ -1,28 +1,102 @@
+import json as _json
+
 import pytest
-from app.agents.retriever import RetrieverAgent, LOW_SCORE_THRESHOLD
+from app.agents.retriever import RetrieverAgent
 from app.agents.base import AgentBase
 from app.harness.enums import EventType, EventSource
 from app.harness.events import Event, check_ownership
 from app.harness.workspace_state import WorkspaceState
+from app.infrastructure.rag.coordinator import Chunk, IndexProvider, RAGCoordinator, SearchResult
+from app.infrastructure.rag.store import FakeRAGStore
 
 
 @pytest.fixture
 def ws():
     return WorkspaceState(session_id="s1", user_id=1)
 
 
 @pytest.fixture
 def agent():
     return RetrieverAgent()
 
 
+@pytest.fixture(autouse=True)
+def disable_external_judge_by_default(monkeypatch):
+    """Keep every default test path on explicit local retrieval and judge doubles."""
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
+    pg_attempts = {"construct": 0, "connect": 0}
+    sdk_attempts = {"chat": 0, "openai": 0}
+
+    def forbid_pg_construct(*_args, **_kwargs):
+        pg_attempts["construct"] += 1
+        raise AssertionError("unit tests must not construct a real PG provider")
+
+    def forbid_pg_connect(*_args, **_kwargs):
+        pg_attempts["connect"] += 1
+        raise AssertionError("unit tests must not connect to a real PG provider")
+
+    def forbid_chat_sdk(*_args, **_kwargs):
+        sdk_attempts["chat"] += 1
+        raise AssertionError("unit tests must not construct a real chat SDK client")
+
+    def forbid_openai_sdk(*_args, **_kwargs):
+        sdk_attempts["openai"] += 1
+        raise AssertionError("unit tests must not construct a real OpenAI SDK client")
+
+    monkeypatch.setattr("app.infrastructure.rag.pgvector_provider.PgVectorProvider.__init__", forbid_pg_construct)
+    monkeypatch.setattr("app.infrastructure.rag.pgvector_provider.PgVectorProvider._get_conn", forbid_pg_connect)
+    import langchain_openai
+    import openai
+    monkeypatch.setattr(langchain_openai, "ChatOpenAI", forbid_chat_sdk)
+    monkeypatch.setattr(openai, "OpenAI", forbid_openai_sdk)
+
+    def make_offline_coordinator():
+        store = FakeRAGStore()
+        return RAGCoordinator(store=store, vector_provider=_OfflineVectorProvider(store))
+
+    monkeypatch.setattr("app.agents.retriever.RAGCoordinator", make_offline_coordinator)
+    yield
+    assert pg_attempts == {"construct": 0, "connect": 0}
+    assert sdk_attempts == {"chat": 0, "openai": 0}
+
+
+class _OfflineVectorProvider(IndexProvider):
+    name = "vector"
+
+    def __init__(self, store):
+        self._store = store
+
+    def index(self, docs):
+        self._store.index(docs)
+        return len(docs)
+
+    def search(self, query, top_k=5, visibility=None):
+        return [
+            Chunk(content=item["content"], score=float(item.get("score", 0)),
+                  source="vector", metadata=item.get("metadata", {}))
+            for item in self._store.query(query, top_k, visibility=visibility)
+        ]
+
+    @property
+    def doc_count(self):
+        return self._store.doc_count
+
+
+def test_default_retriever_stays_offline_when_settings_select_pgvector(monkeypatch):
+    monkeypatch.setattr("app.core.config.settings.rag_backend", "pgvector")
+
+    agent = RetrieverAgent()
+
+    assert isinstance(agent._coordinator._providers["vector"], _OfflineVectorProvider)
+
+
 # --- 契约声明 ---
 
 def test_retriever_source_is_retriever(agent):
     assert agent.source == EventSource.RETRIEVER
 
 
 def test_retriever_subscribes_to_action_requested(agent):
     assert EventType.ACTION_REQUESTED in agent.subscriptions
 
 
@@ -110,27 +184,26 @@ def test_handle_low_score_with_mock_provider(ws):
     from app.infrastructure.rag.coordinator import IndexProvider, Chunk, RAGCoordinator
 
     class _LowScoreProvider(IndexProvider):
         name = "lowscore"
         def index(self, docs): pass
         def search(self, query, top_k=5):
             return [Chunk(content="low score chunk", score=0.1, source="lowscore")]
         @property
         def doc_count(self): return 1
 
-    coord = RAGCoordinator()
-    coord.register_provider(_LowScoreProvider())
+    coord = RAGCoordinator(vector_provider=_LowScoreProvider())
     agent = RetrieverAgent(coordinator=coord)
     ev = Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                session_id="s1", payload={"target": "retriever",
                                           "query": "anything",
-                                          "sources": ["lowscore"]})
+                                          "sources": ["vector"]})
     result = agent.handle(ev, ws)
     assert len(result) == 1
     assert result[0].type == EventType.RETRIEVED_EVIDENCE
     assert result[0].payload["retrieval_status"] == "ok"
     assert result[0].payload["quality"] == "low"
     assert len(result[0].payload["chunks"]) == 1
 
 
 # --- payload 传递 ---
 
@@ -243,21 +316,22 @@ def test_evaluate_context_precision():
     agent._coordinator.index_documents([
         {"content": "RAG 技术详解"},       # 相关
         {"content": "无关的天气报告"},      # 无关
         {"content": "RAG 应用场景"},       # 相关
     ])
     test_case = {
         "query": "RAG",
         "golden_chunks": ["RAG"],
     }
     metrics = agent.evaluate(test_case)
-    assert 0.0 <= metrics["context_precision"] <= 1.0
+    assert 0.0 <= metrics["context_precision_proxy"] <= 1.0
+    assert metrics["context_precision"] is None
 
 
 def test_evaluate_latency_ms_is_positive():
     agent = RetrieverAgent()
     agent._coordinator.index_documents([{"content": "测试"}])
     metrics = agent.evaluate({
         "query": "测试",
         "golden_chunks": [],
         "golden_answer": "",
     })
@@ -321,82 +395,64 @@ def test_evaluate_metric_bounds():
         {"content": "BERT 使用双向 Transformer 编码器"},
         {"content": "今天天气不错"},
     ])
     metrics = agent.evaluate({
         "query": "Transformer",
         "golden_chunks": ["BERT 使用双向 Transformer 编码器"],
         "golden_answer": "BERT 是双向 Transformer",
         "top_k": 3,
     })
     assert 0.0 <= metrics["recall_at_k"] <= 1.0
-    assert 0.0 <= metrics["context_precision"] <= 1.0
-    assert 0.0 <= metrics["faithfulness"] <= 1.0
-    assert 0.0 <= metrics["answer_relevancy"] <= 1.0
+    assert 0.0 <= metrics["context_precision_proxy"] <= 1.0
+    assert metrics["context_precision"] is None or 0.0 <= metrics["context_precision"] <= 1.0
+    assert metrics["faithfulness"] is None or 0.0 <= metrics["faithfulness"] <= 1.0
+    assert metrics["answer_relevancy"] is None or -1.0 <= metrics["answer_relevancy"] <= 1.0
     assert 0.0 <= metrics["redundancy"] <= 1.0
     assert metrics["latency_ms"] >= 0
 
 
 def test_evaluate_degraded_when_no_golden_answer():
     """无 golden_answer 时应降级（faithfulness/answer_relevancy 无意义）"""
     from unittest.mock import patch
 
     agent = RetrieverAgent()
     agent._coordinator.index_documents([{"content": "测试内容"}])
 
     # 无 golden_answer 时应在导入可选 RAGAS 依赖前降级。
     with patch("app.eval.judge.build_judge", return_value={"llm": "mock", "embeddings": "mock"}):
         metrics = agent.evaluate({
             "query": "测试",
             "golden_chunks": ["测试内容"],
             # 不传 golden_answer
         })
 
     assert metrics["degraded"] is True
-    assert "golden_answer" in metrics["degraded_reason"]
+    assert metrics["degraded_reason"] == "部分 judge 分数不可用"
     # 降级时仍应返回不依赖 LLM 的指标
     assert "recall_at_k" in metrics
     assert "redundancy" in metrics
     assert "latency_ms" in metrics
 
 
-def test_evaluate_ragas_happy_path_extraction():
+def test_evaluate_ragas_happy_path_extraction(monkeypatch):
     """happy-path：mock judge + ragas_eval，验证 import/Dataset/分数提取链路不崩。
 
     此前 32 测试全走降级分支，RAGAS 真实调用从未被执行，掩盖了
     metric import 类型错误与 EvaluationResult 提取接口错误两个 bug。
     本测试 mock 掉 build_judge 与 ragas_eval 本身，但保留真实的
     ragas.metrics import、Dataset 构造、_scores_dict 提取，覆盖该链路。
     """
-    from unittest.mock import patch, MagicMock
-    import pytest
-
-    pytest.importorskip("ragas")
-    pytest.importorskip("datasets")
-
-    agent = RetrieverAgent()
-    agent._coordinator.index_documents([{"content": "RAG 是检索增强生成"}])
-
-    fake_result = MagicMock()
-    fake_result._scores_dict = {
+    metrics = _evaluate_with_judge_scores(monkeypatch, {
         "faithfulness": [0.9],
         "answer_relevancy": [0.85],
         "context_precision": [0.8],
-    }
-
-    with patch("app.eval.judge.build_judge",
-               return_value={"llm": "mock_llm", "embeddings": "mock_emb"}), \
-         patch("ragas.evaluate", return_value=fake_result):
-        metrics = agent.evaluate({
-            "query": "RAG",
-            "golden_chunks": ["RAG 是检索增强生成"],
-            "golden_answer": "RAG 即检索增强生成",
-        })
+    })
 
     assert metrics["degraded"] is False
     assert metrics["faithfulness"] == 0.9
     assert metrics["answer_relevancy"] == 0.85
     assert metrics["context_precision"] == 0.8
 
 
 @pytest.mark.integration
 def test_evaluate_ragas_real_judge():
     """集成测试：真实 OpenAI judge 跑 RAGAS（需 OPENAI_API_KEY）。
@@ -415,25 +471,20 @@ def test_evaluate_ragas_real_judge():
         "golden_answer": "注意力机制核心是 QKV 三个矩阵",
     })
 
     assert metrics["degraded"] is False, f"不应降级：{metrics.get('degraded_reason')}"
     for k in ("faithfulness", "answer_relevancy", "context_precision"):
         assert 0.0 <= metrics[k] <= 1.0
 
 
 # ===== RAG-C Phase 2（C-10）：五态 + 入口校验 + 安全摘要 =====
 
-import json as _json
-
-from app.infrastructure.rag.coordinator import Chunk, SearchResult
-
-
 class _StubCoordinator:
     """可控 Coordinator 替身：记录调用，返回预设 SearchResult 或抛异常。"""
 
     def __init__(self, result=None, exc=None):
         self.result = result or SearchResult(
             chunks=[], total_found=0, sources_used=[], outcome="empty")
         self.exc = exc
         self.calls = []
 
     def search(self, query, sources=None, top_k=5, visibility=None):
@@ -442,20 +493,557 @@ class _StubCoordinator:
         if self.exc:
             raise self.exc
         return self.result
 
 
 def _retriever_event(payload):
     return Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                  session_id="s1", payload={"target": "retriever", **payload})
 
 
+_EVALUATION_KEYS = {
+    "schema_version", "retrieval_status", "error_code", "safe_summary",
+    "sources_used", "attempted_providers", "failed_providers", "latency_ms",
+    "top_k", "valid_for_quality", "recall_at_k", "recall_at_1",
+    "recall_at_3", "recall_at_5", "context_precision_proxy", "redundancy",
+    "faithfulness", "answer_relevancy", "context_precision", "judge_scores",
+    "judge_degraded", "degraded", "degraded_reason",
+}
+
+
+def _evaluation_search_result(outcome, *, chunks=None, error_code=None):
+    return SearchResult(
+        chunks=chunks or [], total_found=len(chunks or []),
+        sources_used=["vector"] if chunks else [], outcome=outcome,
+        attempted_providers=["vector", "archive"],
+        failed_providers=["archive"] if outcome == "degraded" else [],
+        error_code=error_code,
+    )
+
+
+def test_evaluate_contract_preserves_status_and_search_sources():
+    cases = [
+        ("ok", "ok", None, True),
+        ("empty", "empty", None, True),
+        ("degraded", "degraded", "provider_degraded", False),
+        ("failed", "failed", "db_error", False),
+        ("failed", "invalid-request", "invalid_request", False),
+    ]
+    for outcome, expected_status, error_code, valid in cases:
+        chunks = [Chunk(content="gold paragraph", score=0.9)] if outcome in {"ok", "degraded"} else []
+        stub = _StubCoordinator(result=_evaluation_search_result(
+            outcome, chunks=chunks, error_code=error_code))
+        metrics = RetrieverAgent(coordinator=stub).evaluate({
+            "query": "question", "golden_chunks": ["gold paragraph"],
+            "golden_answer": "answer", "top_k": 5,
+        })
+
+        assert set(metrics) == _EVALUATION_KEYS
+        assert metrics["schema_version"] == "retriever-evaluation-v1"
+        assert metrics["retrieval_status"] == expected_status
+        assert metrics["valid_for_quality"] is valid
+        assert metrics["sources_used"] == (["vector"] if chunks else [])
+        assert metrics["attempted_providers"] == ["vector", "archive"]
+        assert metrics["failed_providers"] == (["archive"] if outcome == "degraded" else [])
+        assert metrics["error_code"] == error_code
+        assert metrics["top_k"] == 5
+        assert len(stub.calls) == 1
+        assert _json.loads(_json.dumps(metrics, ensure_ascii=False, allow_nan=False)) == metrics
+
+
+@pytest.mark.parametrize(
+    ("exc", "expected_code"),
+    [(TimeoutError("private timeout text"), "timeout"),
+     (RuntimeError("private database text"), "backend_unavailable")],
+)
+def test_evaluate_contract_safely_classifies_search_exception(exc, expected_code, monkeypatch):
+    judge_calls = []
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: judge_calls.append(True))
+    stub = _StubCoordinator(exc=exc)
+    metrics = RetrieverAgent(coordinator=stub).evaluate({
+        "query": "question", "golden_chunks": ["gold"],
+        "golden_answer": "answer", "top_k": 5,
+    })
+
+    assert set(metrics) == _EVALUATION_KEYS
+    assert metrics["retrieval_status"] == "failed"
+    assert metrics["error_code"] == expected_code
+    assert metrics["latency_ms"] is None
+    assert metrics["sources_used"] == []
+    assert metrics["valid_for_quality"] is False
+    assert all(metrics[key] is None for key in (
+        "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
+        "context_precision_proxy", "redundancy", "faithfulness",
+        "answer_relevancy", "context_precision"))
+    assert judge_calls == []
+    dumped = _json.dumps(metrics, ensure_ascii=False, allow_nan=False)
+    assert "private timeout text" not in dumped
+    assert "private database text" not in dumped
+
+
+@pytest.mark.parametrize(
+    ("query", "top_k", "golden_chunks", "golden_answer", "expected_top_k"),
+    [("", 3, [], "answer", 3), ("question", True, [], "answer", None),
+     ("question", 0, [], "answer", None), ("question", 11, [], "answer", None),
+     ("question", "5", [], "answer", None),
+     ("question", 5, "not-a-list", "answer", 5),
+     ("question", 5, [], 12, 5)],
+)
+def test_evaluate_contract_rejects_invalid_inputs_before_search(
+    query, top_k, golden_chunks, golden_answer, expected_top_k,
+):
+    stub = _StubCoordinator()
+    metrics = RetrieverAgent(coordinator=stub).evaluate({
+        "query": query, "golden_chunks": golden_chunks,
+        "golden_answer": golden_answer, "top_k": top_k,
+    })
+
+    assert set(metrics) == _EVALUATION_KEYS
+    assert metrics["retrieval_status"] == "invalid-request"
+    assert metrics["error_code"] == "invalid_request"
+    assert metrics["top_k"] == expected_top_k
+    assert metrics["latency_ms"] is None
+    assert metrics["sources_used"] == []
+    assert metrics["valid_for_quality"] is False
+    assert metrics["judge_degraded"] is True
+    assert metrics["degraded"] is True
+    assert all(metrics[key] is None for key in (
+        "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
+        "context_precision_proxy", "redundancy", "faithfulness",
+        "answer_relevancy", "context_precision"))
+    assert stub.calls == []
+    _json.dumps(metrics, ensure_ascii=False, allow_nan=False)
+
+
+@pytest.mark.parametrize(
+    ("top_k", "recall_k", "recall_1", "recall_3", "recall_5", "proxy"),
+    [(1, 0.0, 0.0, None, None, 0.0),
+     (2, 0.0, 0.0, None, None, 0.0),
+     (3, 0.5, 0.0, 0.5, None, 1 / 3),
+     (5, 1.0, 0.0, 0.5, 1.0, 2 / 5),
+     (10, 1.0, 0.0, 0.5, 1.0, 2 / 5)],
+)
+def test_evaluate_proxy_derives_all_k_from_one_ordered_search(
+    top_k, recall_k, recall_1, recall_3, recall_5, proxy,
+):
+    contents = [
+        "first unrelated paragraph",
+        "second unrelated paragraph",
+        "gold alpha appears here",
+        "fourth unrelated paragraph",
+        "gold beta appears here",
+    ]
+    stub = _StubCoordinator(result=_evaluation_search_result(
+        "ok", chunks=[Chunk(content=text, score=1 - index / 10)
+                       for index, text in enumerate(contents)]))
+    metrics = RetrieverAgent(coordinator=stub).evaluate({
+        "query": "question",
+        "golden_chunks": ["gold alpha", "gold alpha", "gold beta"],
+        "golden_answer": "",
+        "top_k": top_k,
+    })
+
+    assert metrics["recall_at_k"] == recall_k
+    assert metrics["recall_at_1"] == recall_1
+    assert metrics["recall_at_3"] == recall_3
+    assert metrics["recall_at_5"] == recall_5
+    assert metrics["context_precision_proxy"] == pytest.approx(proxy)
+    assert metrics["context_precision"] is None
+    assert len(stub.calls) == 1
+    assert stub.calls[0]["top_k"] == top_k
+
+
+def test_evaluate_proxy_supports_containment_in_both_directions():
+    stub = _StubCoordinator(result=_evaluation_search_result(
+        "ok", chunks=[
+            Chunk(content="prefix and short phrase at the end", score=0.9),
+            Chunk(content="tiny", score=0.8),
+        ]))
+    metrics = RetrieverAgent(coordinator=stub).evaluate({
+        "query": "question",
+        "golden_chunks": ["short phrase", "a much longer tiny golden paragraph"],
+        "golden_answer": "",
+        "top_k": 2,
+    })
+
+    assert metrics["recall_at_k"] == 1.0
+    assert metrics["context_precision_proxy"] == 1.0
+    assert len(stub.calls) == 1
+
+
+def test_evaluate_proxy_has_zero_values_for_healthy_empty_and_null_without_gold():
+    empty_agent = RetrieverAgent(coordinator=_StubCoordinator(
+        result=_evaluation_search_result("empty")))
+    with_gold = empty_agent.evaluate({
+        "query": "question", "golden_chunks": ["gold"], "golden_answer": "",
+    })
+    without_gold = empty_agent.evaluate({
+        "query": "question", "golden_chunks": [], "golden_answer": "",
+    })
+
+    assert with_gold["retrieval_status"] == "empty"
+    assert with_gold["valid_for_quality"] is True
+    assert with_gold["recall_at_k"] == 0.0
+    assert with_gold["context_precision_proxy"] == 0.0
+    assert with_gold["redundancy"] == 0.0
+    assert without_gold["recall_at_k"] is None
+    assert without_gold["recall_at_1"] is None
+    assert without_gold["context_precision_proxy"] is None
+    assert len(empty_agent._coordinator.calls) == 2
+
+
+def test_evaluate_proxy_counts_highly_similar_nonduplicate_contents():
+    stub = _StubCoordinator(result=_evaluation_search_result(
+        "ok", chunks=[
+            Chunk(content="same paragraph same paragraph ending alpha", score=0.9),
+            Chunk(content="same paragraph same paragraph ending bravo", score=0.8),
+        ]))
+    metrics = RetrieverAgent(coordinator=stub).evaluate({
+        "query": "same paragraph", "golden_chunks": [], "golden_answer": "",
+    })
+
+    assert metrics["redundancy"] == 1.0
+    assert metrics["recall_at_k"] is None
+    assert len(stub.calls) == 1
+
+
+def test_evaluate_proxy_uses_real_coordinator_deduplication_for_duplicate_bodies():
+    from app.infrastructure.rag.coordinator import IndexProvider, RAGCoordinator
+
+    class DuplicateProvider(IndexProvider):
+        name = "vector"
+
+        def __init__(self):
+            self.calls = 0
+
+        def index(self, docs):
+            return len(docs)
+
+        def search(self, query, top_k=5, visibility=None):
+            self.calls += 1
+            return [
+                Chunk(content="same body", score=0.8),
+                Chunk(content="same body", score=0.9),
+                Chunk(content="other body", score=0.7),
+            ]
+
+        @property
+        def doc_count(self):
+            return 3
+
+    provider = DuplicateProvider()
+    agent = RetrieverAgent(coordinator=RAGCoordinator(vector_provider=provider))
+    metrics = agent.evaluate({
+        "query": "body", "golden_chunks": [], "golden_answer": "", "top_k": 5,
+    })
+
+    assert metrics["redundancy"] == 0.0
+    assert provider.calls == 1
+
+
+def _install_controlled_judge(monkeypatch, scores):
+    import sys
+    from types import ModuleType, SimpleNamespace
+
+    ragas = ModuleType("ragas")
+    ragas.__path__ = []
+    ragas.evaluate = lambda **_: SimpleNamespace(_scores_dict=scores)
+    ragas_metrics = ModuleType("ragas.metrics")
+    ragas_metrics.faithfulness = object()
+    ragas_metrics.answer_relevancy = object()
+    ragas_metrics.context_precision = object()
+    datasets = ModuleType("datasets")
+
+    class Dataset:
+        @staticmethod
+        def from_dict(values):
+            return values
+
+    datasets.Dataset = Dataset
+    monkeypatch.setitem(sys.modules, "ragas", ragas)
+    monkeypatch.setitem(sys.modules, "ragas.metrics", ragas_metrics)
+    monkeypatch.setitem(sys.modules, "datasets", datasets)
+    monkeypatch.setattr(
+        "app.eval.judge.build_judge",
+        lambda **_: {"llm": object(), "embeddings": object()},
+    )
+
+
+def _evaluate_with_judge_scores(monkeypatch, scores):
+    _install_controlled_judge(monkeypatch, scores)
+    stub = _StubCoordinator(result=_evaluation_search_result(
+        "ok", chunks=[Chunk(content="gold evidence", score=0.9)]))
+    metrics = RetrieverAgent(coordinator=stub).evaluate({
+        "query": "question", "golden_chunks": ["gold evidence"],
+        "golden_answer": "reference answer", "top_k": 5,
+    })
+    assert len(stub.calls) == 1
+    _json.dumps(metrics, ensure_ascii=False, allow_nan=False)
+    return metrics
+
+
+def test_evaluate_judge_contract_accepts_zero_boundaries_and_negative_relevancy(monkeypatch):
+    metrics = _evaluate_with_judge_scores(monkeypatch, {
+        "faithfulness": [0],
+        "answer_relevancy": [-1.0],
+        "context_precision": [1],
+    })
+
+    assert metrics["faithfulness"] == 0.0
+    assert metrics["answer_relevancy"] == -1.0
+    assert metrics["context_precision"] == 1.0
+    assert all(item["available"] for item in metrics["judge_scores"].values())
+    assert metrics["judge_degraded"] is False
+    assert metrics["degraded"] is False
+    assert metrics["context_precision_proxy"] == 1.0
+
+
+@pytest.mark.parametrize(
+    ("scores", "expected_reasons"),
+    [({}, {"faithfulness": "missing", "answer_relevancy": "missing",
+           "context_precision": "missing"}),
+     ({"faithfulness": [], "answer_relevancy": [], "context_precision": []},
+      {"faithfulness": "missing", "answer_relevancy": "missing",
+       "context_precision": "missing"}),
+     ({"faithfulness": [0.7], "answer_relevancy": [], "context_precision": [None]},
+      {"faithfulness": None, "answer_relevancy": "missing",
+       "context_precision": "non_numeric"})],
+)
+def test_evaluate_judge_contract_handles_missing_empty_and_partial_scores(
+    monkeypatch, scores, expected_reasons,
+):
+    metrics = _evaluate_with_judge_scores(monkeypatch, scores)
+
+    for name, reason in expected_reasons.items():
+        assert metrics["judge_scores"][name]["safe_reason"] == reason
+        assert metrics[name] == metrics["judge_scores"][name]["value"]
+    if scores.get("faithfulness"):
+        assert metrics["faithfulness"] == 0.7
+        assert metrics["context_precision_proxy"] == 1.0
+    assert metrics["judge_degraded"] is True
+    assert metrics["degraded"] is True
+
+
+@pytest.mark.parametrize(
+    ("metric", "bad_value", "expected_reason"),
+    [("faithfulness", True, "non_numeric"),
+     ("faithfulness", "0.5", "non_numeric"),
+     ("faithfulness", float("nan"), "non_finite"),
+     ("answer_relevancy", float("inf"), "non_finite"),
+     ("context_precision", float("-inf"), "non_finite"),
+     ("faithfulness", -0.01, "out_of_range"),
+     ("answer_relevancy", 1.01, "out_of_range"),
+     ("context_precision", 1.01, "out_of_range")],
+)
+def test_evaluate_judge_contract_rejects_bad_score_per_metric(
+    monkeypatch, metric, bad_value, expected_reason,
+):
+    scores = {"faithfulness": [0.6], "answer_relevancy": [0.2],
+              "context_precision": [0.8]}
+    scores[metric] = [bad_value]
+    metrics = _evaluate_with_judge_scores(monkeypatch, scores)
+
+    assert metrics[metric] is None
+    assert metrics["judge_scores"][metric] == {
+        "value": None, "available": False, "safe_reason": expected_reason,
+    }
+    assert metrics["judge_degraded"] is True
+    assert metrics["retrieval_status"] == "ok"
+    assert metrics["valid_for_quality"] is True
+    assert metrics["context_precision_proxy"] == 1.0
+
+
+def test_evaluate_judge_contract_does_not_call_judge_without_golden_answer(monkeypatch):
+    calls = []
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: calls.append(True))
+    stub = _StubCoordinator(result=_evaluation_search_result(
+        "ok", chunks=[Chunk(content="evidence", score=0.9)]))
+    metrics = RetrieverAgent(coordinator=stub).evaluate({
+        "query": "question", "golden_chunks": ["evidence"], "golden_answer": "",
+    })
+
+    assert calls == []
+    assert metrics["retrieval_status"] == "ok"
+    assert metrics["judge_scores"]["faithfulness"]["safe_reason"] == "unavailable"
+    assert metrics["context_precision_proxy"] == 1.0
+    _json.dumps(metrics, ensure_ascii=False, allow_nan=False)
+
+
+def test_evaluate_judge_contract_degrades_when_ragas_package_is_missing(monkeypatch):
+    import sys
+
+    monkeypatch.setitem(sys.modules, "ragas", None)
+    stub = _StubCoordinator(result=_evaluation_search_result(
+        "ok", chunks=[Chunk(content="evidence", score=0.9)]))
+    metrics = RetrieverAgent(coordinator=stub).evaluate({
+        "query": "question", "golden_chunks": ["evidence"],
+        "golden_answer": "answer",
+    })
+
+    assert metrics["retrieval_status"] == "ok"
+    assert metrics["valid_for_quality"] is True
+    assert metrics["context_precision_proxy"] == 1.0
+    assert all(item == {"value": None, "available": False, "safe_reason": "unavailable"}
+               for item in metrics["judge_scores"].values())
+    assert metrics["judge_degraded"] is True
+    assert metrics["degraded"] is True
+    _json.dumps(metrics, ensure_ascii=False, allow_nan=False)
+
+
+def test_evaluate_judge_contract_catches_unavailable_and_judge_exception(monkeypatch):
+    stub = _StubCoordinator(result=_evaluation_search_result(
+        "ok", chunks=[Chunk(content="evidence", score=0.9)]))
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
+    unavailable = RetrieverAgent(coordinator=stub).evaluate({
+        "query": "question", "golden_chunks": ["evidence"],
+        "golden_answer": "answer",
+    })
+    assert all(item["safe_reason"] == "unavailable"
+               for item in unavailable["judge_scores"].values())
+    assert unavailable["context_precision_proxy"] == 1.0
+
+    _install_controlled_judge(monkeypatch, {})
+    monkeypatch.setattr("app.eval.judge.build_judge",
+                        lambda **_: (_ for _ in ()).throw(RuntimeError("secret judge failure")))
+    failed = RetrieverAgent(coordinator=stub).evaluate({
+        "query": "question", "golden_chunks": ["evidence"],
+        "golden_answer": "answer",
+    })
+    assert failed["retrieval_status"] == "ok"
+    assert failed["valid_for_quality"] is True
+    assert failed["judge_degraded"] is True
+    assert failed["context_precision_proxy"] == 1.0
+    assert "secret judge failure" not in _json.dumps(failed, ensure_ascii=False)
+    assert len(stub.calls) == 2
+
+
+def _component_bench_agent(*, mode="healthy"):
+    from app.infrastructure.rag.coordinator import IndexProvider, RAGCoordinator
+
+    class ControlledProvider(IndexProvider):
+        name = "vector"
+
+        def __init__(self, should_fail=False):
+            self.calls = 0
+            self.should_fail = should_fail
+
+        def index(self, docs):
+            return len(docs)
+
+        def search(self, query, top_k=5, visibility=None):
+            self.calls += 1
+            if self.should_fail:
+                raise RuntimeError("private provider failure")
+            if mode == "empty":
+                return []
+            return [Chunk(content="gold evidence paragraph", score=0.9)]
+
+        @property
+        def doc_count(self):
+            return 1
+
+    class FailingOCRProvider(IndexProvider):
+        name = "ocr"
+
+        def index(self, docs):
+            return len(docs)
+
+        def search(self, query, top_k=5, visibility=None):
+            raise RuntimeError("private OCR failure")
+
+        @property
+        def doc_count(self):
+            return 0
+
+    provider = ControlledProvider(should_fail=mode == "failed")
+    coordinator = RAGCoordinator(vector_provider=provider)
+    if mode == "degraded":
+        coordinator.register_provider(FailingOCRProvider())
+    return RetrieverAgent(coordinator=coordinator), provider
+
+
+def test_evaluate_component_bench_contract_keeps_null_for_missing_gold(monkeypatch):
+    from app.eval.component_bench import ComponentBench
+    from app.eval.kernel import TestCase
+
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
+    agent, provider = _component_bench_agent()
+    case = TestCase(
+        name="missing-gold", component="retriever",
+        input={"query": "question", "golden_chunks": [], "golden_answer": "", "top_k": 5},
+        expected={"recall_at_k": 0.5},
+    )
+
+    result = ComponentBench({"retriever": agent}).run("retriever", [case])[0]
+
+    assert result.passed is False
+    assert result.metrics["recall_at_k"] is None
+    assert result.metrics["retrieval_status"] == "ok"
+    assert any("recall_at_k: 未返回" in error for error in result.errors)
+    assert provider.calls == 1
+
+
+@pytest.mark.parametrize(("mode", "expected_status"), [
+    ("failed", "failed"), ("degraded", "degraded"),
+])
+def test_evaluate_component_bench_contract_preserves_failed_and_degraded_status(
+    monkeypatch, mode, expected_status,
+):
+    from app.eval.component_bench import ComponentBench
+    from app.eval.kernel import TestCase
+
+    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
+    agent, provider = _component_bench_agent(mode=mode)
+    case = TestCase(
+        name=f"{mode}-retrieval", component="retriever",
+        input={"query": "question", "golden_chunks": ["gold evidence"],
+               "golden_answer": "answer", "top_k": 5},
+        expected={"recall_at_k": 0.5},
+    )
+
+    result = ComponentBench({"retriever": agent}).run("retriever", [case])[0]
+
+    assert result.passed is False
+    assert result.metrics["retrieval_status"] == expected_status
+    assert result.metrics["valid_for_quality"] is False
+    assert result.metrics["recall_at_k"] is None
+    assert result.metrics["sources_used"] == (["vector"] if mode == "degraded" else [])
+    assert any("recall_at_k: 未返回" in error for error in result.errors)
+    assert provider.calls == 1
+
+
+def test_evaluate_component_bench_contract_keeps_healthy_legacy_metrics(monkeypatch):
+    from app.eval.component_bench import ComponentBench
+    from app.eval.kernel import TestCase
+
+    _install_controlled_judge(monkeypatch, {
+        "faithfulness": [0.8], "answer_relevancy": [-0.2], "context_precision": [0.9],
+    })
+    agent, provider = _component_bench_agent()
+    case = TestCase(
+        name="healthy-gold", component="retriever",
+        input={"query": "question", "golden_chunks": ["gold evidence paragraph"],
+               "golden_answer": "answer", "top_k": 5},
+        expected={"recall_at_k": 1.0, "faithfulness": 0.8},
+    )
+
+    result = ComponentBench({"retriever": agent}).run("retriever", [case])[0]
+
+    assert result.passed is True
+    assert result.metrics["recall_at_k"] == 1.0
+    assert result.metrics["faithfulness"] == 0.8
+    assert result.metrics["answer_relevancy"] == -0.2
+    assert result.metrics["retrieval_status"] == "ok"
+    assert result.metrics["valid_for_quality"] is True
+    assert provider.calls == 1
+
+
 # --- invalid-request：入口拦截，不进入 provider ---
 
 def test_invalid_request_missing_query_skips_provider(ws):
     stub = _StubCoordinator()
     agent = RetrieverAgent(coordinator=stub)
     result = agent.handle(_retriever_event({"query": ""}), ws)
     assert result[0].type == EventType.RETRIEVAL_FAILED
     p = result[0].payload
     assert p["retrieval_status"] == "invalid-request"
     assert p["error_code"] == "invalid_request"
