"""Retriever Agent（§2.1）—— 知识检索，只做机械层。

事件契约：
  source      = retriever
  subscriptions = [ActionRequested]（按 payload.target==retriever 过滤）
  emittable   = {RetrievedEvidence, RetrievalFailed}

只做机械层：向量检索 + 原始 similarity score + retrieval_status。
绝不评判"证据够不够好"（语义质量归 Critic 的 RAGQualityAssessed）。
"""

import logging
import math
import time
from collections import Counter
from numbers import Real

from app.agents.base import AgentBase
from app.harness.enums import EventType, EventSource
from app.harness.events import Event
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.rag.coordinator import RAGCoordinator, VisibilityContext

logger = logging.getLogger(__name__)

LOW_SCORE_THRESHOLD = 0.3
TOP_K_DEFAULT = 5
TOP_K_MAX = 10
EVALUATION_SCHEMA_VERSION = "retriever-evaluation-v1"
JUDGE_METRIC_RANGES = {
    "faithfulness": (0.0, 1.0),
    "answer_relevancy": (-1.0, 1.0),
    "context_precision": (0.0, 1.0),
}

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


def _validate_judge_score(value, *, present: bool, minimum: float,
                          maximum: float) -> dict:
    if not present:
        return {"value": None, "available": False, "safe_reason": "missing"}
    if isinstance(value, bool) or not isinstance(value, Real):
        return {"value": None, "available": False, "safe_reason": "non_numeric"}
    try:
        score = float(value)
    except (OverflowError, ValueError):
        return {"value": None, "available": False, "safe_reason": "non_finite"}
    if not math.isfinite(score):
        return {"value": None, "available": False, "safe_reason": "non_finite"}
    if not minimum <= score <= maximum:
        return {"value": None, "available": False, "safe_reason": "out_of_range"}
    return {"value": score, "available": True, "safe_reason": None}


def _collect_judge_scores(raw_scores, *, unavailable: bool) -> dict:
    collected = {}
    for name, (minimum, maximum) in JUDGE_METRIC_RANGES.items():
        if unavailable:
            collected[name] = {
                "value": None, "available": False, "safe_reason": "unavailable",
            }
            continue
        present = isinstance(raw_scores, dict) and name in raw_scores
        values = raw_scores.get(name) if present else None
        if isinstance(values, (list, tuple)):
            if not values:
                present = False
                value = None
            else:
                value = values[0]
        else:
            value = values
        collected[name] = _validate_judge_score(
            value, present=present, minimum=minimum, maximum=maximum)
    return collected


def _new_evaluation_result(top_k, *, retrieval_status: str,
                           error_code: str | None = None,
                           sources_used: list[str] | None = None,
                           attempted_providers: list[str] | None = None,
                           failed_providers: list[str] | None = None,
                           latency_ms: float | None = None,
                           valid_for_quality: bool = False) -> dict:
    judge_scores = {
        name: {"value": None, "available": False, "safe_reason": "unavailable"}
        for name in JUDGE_METRIC_RANGES
    }
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "retrieval_status": retrieval_status,
        "error_code": error_code,
        "safe_summary": _safe_summary(error_code) if error_code else "",
        "sources_used": sources_used or [],
        "attempted_providers": attempted_providers or [],
        "failed_providers": failed_providers or [],
        "latency_ms": latency_ms,
        "top_k": top_k,
        "valid_for_quality": valid_for_quality,
        "recall_at_k": None,
        "recall_at_1": None,
        "recall_at_3": None,
        "recall_at_5": None,
        "context_precision_proxy": None,
        "redundancy": None,
        "faithfulness": None,
        "answer_relevancy": None,
        "context_precision": None,
        "judge_scores": judge_scores,
        "judge_degraded": True,
        "degraded": True,
        "degraded_reason": None,
    }


def _compute_mechanical_metrics(retrieved_contents: list[str],
                                golden_chunks: list[str], top_k: int) -> dict:
    unique_gold = list(dict.fromkeys(golden_chunks))
    returned = retrieved_contents[:top_k]

    def recall(contents: list[str]) -> float | None:
        if not unique_gold:
            return None
        matches = 0
        for gold in unique_gold:
            if any(gold in content or content in gold for content in contents):
                matches += 1
        return matches / len(unique_gold)

    precision_proxy = None
    if unique_gold:
        relevant = sum(
            any(gold in content or content in gold for gold in unique_gold)
            for content in returned
        )
        precision_proxy = relevant / len(returned) if returned else 0.0

    pairs = 0
    similar = 0
    for index, left_content in enumerate(returned):
        left = Counter(left_content)
        for right_content in returned[index + 1:]:
            right = Counter(right_content)
            intersection = sum((left & right).values())
            union = sum((left | right).values())
            pairs += 1
            if union and intersection / union > 0.8:
                similar += 1

    return {
        "recall_at_k": recall(returned),
        "recall_at_1": recall(returned[:1]) if top_k >= 1 else None,
        "recall_at_3": recall(returned[:3]) if top_k >= 3 else None,
        "recall_at_5": recall(returned[:5]) if top_k >= 5 else None,
        "context_precision_proxy": precision_proxy,
        "redundancy": similar / pairs if pairs else 0.0,
    }


class RetrieverAgent(AgentBase):
    """知识检索 Agent（机械层，不自评语义质量）。"""

    source = EventSource.RETRIEVER
    subscriptions = [EventType.ACTION_REQUESTED]
    emittable_types = {EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}

    def __init__(self, coordinator: RAGCoordinator | None = None):
        self._coordinator = coordinator or RAGCoordinator()

    # --- AgentBase 契约 ---

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """处理 ActionRequested(target=retriever)，委托 RAGCoordinator 检索。

        RAG-C Phase 2（C-10）：入口校验（DEC-008 invalid-request）在调用
        provider 之前完成；异常/失败 payload 只含分类错误码 + 安全摘要。
        """
        payload = event.payload or {}

        # 过滤：只处理 target=retriever 的请求
        if payload.get("target") != EventSource.RETRIEVER.value:
            return []

        query = payload.get("query")
        top_k = payload.get("top_k", TOP_K_DEFAULT)
        sources = payload.get("sources", None)
        purpose = payload.get("purpose", None)
        retrieval_id = payload.get("retrieval_id")
        visibility_payload = payload.get("visibility")

        if self._is_invalid_request(query, top_k, visibility_payload,
                                    retrieval_id, payload.get("user_id"), ws):
            return [self._emit_failure(
                ws, parent_id=event.id, retrieval_status="invalid-request",
                error_code="invalid_request", query=query,
                retrieval_id=retrieval_id)]

        visibility = None
        if visibility_payload is not None:
            visibility = VisibilityContext(user_id=visibility_payload["user_id"])

        try:
            return self._do_retrieve_and_emit(
                query=query, top_k=top_k, sources=sources,
                purpose=purpose, parent_id=event.id, ws=ws,
                visibility=visibility, retrieval_id=retrieval_id,
            )
        except Exception as exc:
            # DEC-009：完整异常只进内部日志；对外只有分类码 + 安全摘要
            logger.exception("retrieval failed unexpectedly")
            error_code = "timeout" if isinstance(exc, TimeoutError) else "db_error"
            return [self._emit_failure(
                ws, parent_id=event.id, retrieval_status="failed",
                error_code=error_code, query=query, retrieval_id=retrieval_id)]

    @staticmethod
    def _is_invalid_request(query, top_k, visibility_payload,
                            retrieval_id, user_id, ws: WorkspaceState) -> bool:
        """入口契约校验：返回 True 表示 invalid-request（不进入 provider）。

        非受限请求（无 visibility）只要求 query/top_k 合法，保持旧路径；
        受限请求必须把 payload 与 visibility 身份绑定到可信会话用户，且带
        retrieval_id（DEC-001/003），不能由 action payload 冒充其他用户。
        """
        if not isinstance(query, str) or not query.strip():
            return True
        if isinstance(top_k, bool) or not isinstance(top_k, int) \
                or not (1 <= top_k <= TOP_K_MAX):
            return True
        if visibility_payload is None:
            return False
        if not isinstance(visibility_payload, dict):
            return True
        vis_uid = visibility_payload.get("user_id")
        if isinstance(vis_uid, bool) or not isinstance(vis_uid, int):
            return True
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            return True
        if user_id != ws.user_id or vis_uid != ws.user_id:
            return True
        return not (isinstance(retrieval_id, str) and retrieval_id.strip())

    def _emit_failure(self, ws: WorkspaceState, *, parent_id: str | None,
                      retrieval_status: str, error_code: str | None,
                      query, retrieval_id) -> Event:
        """构造安全的 RetrievalFailed（DEC-009：无 str(exc)/SQL/堆栈）。"""
        payload = {
            "retrieval_status": retrieval_status,
            "error_code": error_code,
            "safe_summary": _safe_summary(error_code),
            "query": query if isinstance(query, str) else "",
        }
        if isinstance(retrieval_id, str) and retrieval_id:
            payload["retrieval_id"] = retrieval_id
        return self.emit(EventType.RETRIEVAL_FAILED, ws,
                         payload=payload, parent_id=parent_id)

    # --- 检索 + 机械判定 ---

    def _do_retrieve_and_emit(self, *, query: str, top_k: int,
                              sources: list[str] | None, purpose: str | None,
                              parent_id: str, ws: WorkspaceState,
                              visibility: VisibilityContext | None = None,
                              retrieval_id: str | None = None) -> list[Event]:
        """执行检索并按纯机械指标判定 retrieval_status（DEC-008 五态）。"""
        t0 = time.time()
        result = self._coordinator.search(query, sources=sources, top_k=top_k,
                                          visibility=visibility)
        latency_ms = (time.time() - t0) * 1000

        # 全部 provider 失败 → RetrievalFailed（DEC-008/009）
        if result.outcome == "failed":
            return [self._emit_failure(
                ws, parent_id=parent_id, retrieval_status="failed",
                error_code=result.error_code or "db_error",
                query=query, retrieval_id=retrieval_id)]

        chunks = result.chunks
        scores = [c.score for c in chunks]
        max_score = max(scores) if scores else 0.0

        # 机械判定 retrieval_status（§3.6 + DEC-008）：
        # low_score 不再是独立状态，降为 ok 的 quality=low 子标记
        if result.outcome == "degraded":
            retrieval_status = "degraded"
        elif not chunks:
            retrieval_status = "empty"
        else:
            retrieval_status = "ok"

        payload = {
            "chunks": [{"content": c.content, "score": c.score,
                        "source": c.source, "metadata": c.metadata}
                       for c in chunks],
            "scores": scores,
            "retrieval_status": retrieval_status,
            "sources_used": result.sources_used,
            "query": query,
            "latency_ms": latency_ms,
        }
        if chunks and max_score < LOW_SCORE_THRESHOLD:
            payload["quality"] = "low"
        if retrieval_status == "degraded":
            payload["error_code"] = result.error_code or "provider_degraded"
            payload["safe_summary"] = _safe_summary(payload["error_code"])
            payload["provider_failures"] = list(result.failed_providers)
        if purpose:
            payload["purpose"] = purpose
        if isinstance(retrieval_id, str) and retrieval_id:
            payload["retrieval_id"] = retrieval_id

        return [self.emit(EventType.RETRIEVED_EVIDENCE, ws,
                          payload=payload, parent_id=parent_id)]

    # --- 部件级评估接口（§5.2 RAG 三件套，供 Plan E 调用） ---

    def evaluate(self, test_case: dict) -> dict:
        """以一次 search 生成稳定的检索状态、机械 proxy 与 judge 结果。"""
        raw_top_k = test_case.get("top_k", TOP_K_DEFAULT) if isinstance(test_case, dict) else None
        top_k = raw_top_k if (isinstance(raw_top_k, int) and not isinstance(raw_top_k, bool)
                              and 1 <= raw_top_k <= TOP_K_MAX) else None
        query = test_case.get("query", "") if isinstance(test_case, dict) else None
        golden_chunks = test_case.get("golden_chunks", []) if isinstance(test_case, dict) else None
        golden_answer = test_case.get("golden_answer", "") if isinstance(test_case, dict) else None
        valid_input = (
            isinstance(query, str) and bool(query.strip())
            and top_k is not None
            and isinstance(golden_chunks, list)
            and all(isinstance(chunk, str) and bool(chunk.strip()) for chunk in golden_chunks)
            and isinstance(golden_answer, str)
        )
        if not valid_input:
            result = _new_evaluation_result(
                top_k, retrieval_status="invalid-request", error_code="invalid_request")
            result["safe_summary"] = SAFE_SUMMARIES["invalid_request"]
            result["degraded_reason"] = SAFE_SUMMARIES["invalid_request"]
            return result

        started = time.monotonic()
        try:
            search_result = self._coordinator.search(query, sources=None, top_k=top_k)
        except TimeoutError:
            code = "timeout"
            result = _new_evaluation_result(
                top_k, retrieval_status="failed", error_code=code)
            result["safe_summary"] = SAFE_SUMMARIES[code]
            result["degraded_reason"] = SAFE_SUMMARIES[code]
            return result
        except Exception:
            code = "backend_unavailable"
            result = _new_evaluation_result(
                top_k, retrieval_status="failed", error_code=code)
            result["safe_summary"] = SAFE_SUMMARIES[code]
            result["degraded_reason"] = SAFE_SUMMARIES[code]
            return result
        elapsed = round(max(0.0, (time.monotonic() - started) * 1000), 3)
        if not math.isfinite(elapsed):
            elapsed = None

        def provider_names(value):
            return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []

        chunks = getattr(search_result, "chunks", None)
        sources_used = provider_names(getattr(search_result, "sources_used", None))
        attempted = provider_names(getattr(search_result, "attempted_providers", None))
        failed = provider_names(getattr(search_result, "failed_providers", None))
        outcome = getattr(search_result, "outcome", None)
        raw_error_code = getattr(search_result, "error_code", None)
        error_code = (raw_error_code if isinstance(raw_error_code, str)
                      and raw_error_code in SAFE_SUMMARIES else None)

        if outcome == "failed":
            error_code = error_code or "backend_unavailable"
            status = "invalid-request" if error_code == "invalid_request" else "failed"
        elif outcome == "degraded":
            status = "degraded"
            error_code = error_code or "provider_degraded"
        elif isinstance(outcome, str) and outcome in {"ok", "empty"} and isinstance(chunks, list):
            status = "ok" if chunks else "empty"
            error_code = None
        else:
            status = "failed"
            error_code = "backend_unavailable"

        result = _new_evaluation_result(
            top_k, retrieval_status=status, error_code=error_code,
            sources_used=sources_used, attempted_providers=attempted,
            failed_providers=failed, latency_ms=elapsed,
            valid_for_quality=status in {"ok", "empty"})
        if status not in {"ok", "empty"}:
            result["safe_summary"] = SAFE_SUMMARIES[error_code]
            result["degraded_reason"] = SAFE_SUMMARIES[error_code]
            return result

        retrieved_contents = [getattr(chunk, "content", None) for chunk in chunks]
        if not all(isinstance(content, str) for content in retrieved_contents):
            result["retrieval_status"] = "failed"
            result["error_code"] = "backend_unavailable"
            result["safe_summary"] = SAFE_SUMMARIES["backend_unavailable"]
            result["valid_for_quality"] = False
            result["latency_ms"] = elapsed
            result["degraded_reason"] = SAFE_SUMMARIES["backend_unavailable"]
            return result

        result.update(_compute_mechanical_metrics(retrieved_contents, golden_chunks, top_k))

        if golden_answer:
            try:
                from ragas import evaluate as ragas_eval
                from ragas.metrics import (
                    faithfulness as m_faithfulness,
                    answer_relevancy as m_answer_relevancy,
                    context_precision as m_context_precision,
                )
                from datasets import Dataset
                from app.eval.judge import build_judge

                judge_handle = build_judge(target_agent_family="anthropic")
                if judge_handle is None:
                    judge_scores = _collect_judge_scores(None, unavailable=True)
                else:
                    eval_dataset = Dataset.from_dict({
                        "user_input": [query],
                        "response": [golden_answer],
                        "retrieved_contexts": [retrieved_contents],
                        "reference": [golden_answer],
                    })
                    ragas_result = ragas_eval(
                        dataset=eval_dataset,
                        metrics=[m_faithfulness, m_answer_relevancy, m_context_precision],
                        llm=judge_handle["llm"],
                        embeddings=judge_handle["embeddings"],
                        raise_exceptions=False,
                    )
                    judge_scores = _collect_judge_scores(
                        getattr(ragas_result, "_scores_dict", None), unavailable=False)
            except Exception:
                judge_scores = _collect_judge_scores(None, unavailable=True)
        else:
            judge_scores = _collect_judge_scores(None, unavailable=True)

        result["judge_scores"] = judge_scores
        for name in JUDGE_METRIC_RANGES:
            result[name] = judge_scores[name]["value"]
        result["judge_degraded"] = any(not item["available"] for item in judge_scores.values())
        result["degraded"] = result["judge_degraded"] or status not in {"ok", "empty"}
        result["degraded_reason"] = (
            "部分 judge 分数不可用" if result["judge_degraded"] else None)
        return result
