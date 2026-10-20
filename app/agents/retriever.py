"""Retriever Agent（§2.1）—— 知识检索，只做机械层。

事件契约：
  source      = retriever
  subscriptions: ClassVar[list[EventType]] = [ActionRequested]（按 payload.target==retriever 过滤）
  emittable   = {RetrievedEvidence, RetrievalFailed}

只做机械层：向量检索 + 原始 similarity score + retrieval_status。
绝不评判"证据够不够好"（语义质量归 Critic 的 RAGQualityAssessed）。
"""

import logging
import time
from collections import Counter
from typing import ClassVar

from app.agents.base import AgentBase
from app.harness.enums import EventSource, EventType
from app.harness.events import Event
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.rag.coordinator import RAGCoordinator, VisibilityContext

logger = logging.getLogger(__name__)

LOW_SCORE_THRESHOLD = 0.3
TOP_K_DEFAULT = 5
TOP_K_MAX = 10

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


class RetrieverAgent(AgentBase):
    """知识检索 Agent（机械层，不自评语义质量）。"""

    source = EventSource.RETRIEVER
    subscriptions: ClassVar[list[EventType]] = [EventType.ACTION_REQUESTED]
    emittable_types: ClassVar[set[EventType]] = {EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}

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
        """部件级评估接口（§5.2 RAG 三件套 + recall@k）。

        test_case 结构：
          - query: str             检索查询
          - golden_chunks: list[str] 人工标注的相关 chunk 内容
          - golden_answer: str      期望答案（用于 faithfulness）
          - top_k: int              检索数量（默认 5）

        返回 6 个指标（初期启发式，后续可替换 ragas）。
        """
        query = test_case.get("query", "")
        golden_chunks = test_case.get("golden_chunks", [])
        golden_answer = test_case.get("golden_answer", "")
        top_k = test_case.get("top_k", 5)

        # 执行检索
        t0 = time.time()
        result = self._coordinator.search(query, sources=None, top_k=top_k)
        latency_ms = (time.time() - t0) * 1000

        retrieved_contents = [c.content for c in result.chunks]

        # --- recall@k：golden_chunks 中有多少被检索到 ---
        if golden_chunks:
            hit = sum(1 for g in golden_chunks
                      if any(g in rc or rc in g for rc in retrieved_contents))
            recall_at_k = hit / len(golden_chunks)
        else:
            recall_at_k = 1.0  # 无 golden_chunks 时无法评估，返回满分

        # --- context_precision：检索结果中与 golden_chunks 相关的比例 ---
        if retrieved_contents and golden_chunks:
            relevant = sum(1 for rc in retrieved_contents
                           if any(g in rc or rc in g for g in golden_chunks))
            context_precision = relevant / len(retrieved_contents)
        elif retrieved_contents:
            # 无 golden_chunks：用 query 词重叠作为弱代理
            query_tokens = set(query)
            relevant = sum(1 for rc in retrieved_contents
                           if any(t in rc for t in query_tokens))
            context_precision = relevant / len(retrieved_contents)
        else:
            context_precision = 0.0

        # --- redundancy：检索结果中高度相似 chunk 对的比例（multiset Jaccard，
        #   即按字符出现次数计算，避免重复字符被 set 折叠） ---
        n = len(retrieved_contents)
        if n >= 2:
            similar_pairs = 0
            for i in range(n):
                for j in range(i + 1, n):
                    ti = Counter(retrieved_contents[i])
                    tj = Counter(retrieved_contents[j])
                    inter = sum((ti & tj).values())
                    union = sum((ti | tj).values())
                    if union > 0 and inter / union > 0.8:
                        similar_pairs += 1
            total_pairs = n * (n - 1) / 2
            redundancy = similar_pairs / total_pairs if total_pairs > 0 else 0.0
        else:
            redundancy = 0.0

        # --- RAGAS 评估三件套（faithfulness/answer_relevancy/context_precision） ---
        if not golden_answer:
            # 无 golden_answer 时 faithfulness/answer_relevancy 无意义，降级
            return {
                "recall_at_k": round(recall_at_k, 4),
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "context_precision": round(context_precision, 4),  # 保留启发式
                "latency_ms": round(latency_ms, 2),
                "redundancy": round(redundancy, 4),
                "degraded": True,
                "degraded_reason": "无 golden_answer，无法评估 RAG 三件套",
            }

        try:
            from datasets import Dataset
            from ragas import evaluate as ragas_eval
            from ragas.metrics import (
                answer_relevancy as m_answer_relevancy,
            )
            from ragas.metrics import (
                context_precision as m_context_precision,
            )
            from ragas.metrics import (
                faithfulness as m_faithfulness,
            )

            from app.eval.judge import build_judge

            # 构造 judge（复用 §5.1.1 不同族校验）
            judge_handle = build_judge(target_agent_family="anthropic")

            if judge_handle is None:
                # 降级：judge 不可用（同族 / 无 key / 构造失败）
                return {
                    "recall_at_k": round(recall_at_k, 4),
                    "faithfulness": 0.0,
                    "answer_relevancy": 0.0,
                    "context_precision": round(context_precision, 4),  # 保留启发式
                    "latency_ms": round(latency_ms, 2),
                    "redundancy": round(redundancy, 4),
                    "degraded": True,
                    "degraded_reason": "judge 不可用（同族或无 API key）",
                }

            # 包装为 RAGAS Dataset 格式（0.4.3 列名）
            eval_dataset = Dataset.from_dict({
                "user_input": [query],
                "response": [golden_answer],
                "retrieved_contexts": [retrieved_contents],
                "reference": [golden_answer],  # context_precision 需要 reference
            })

            # 运行 RAGAS 评估（三指标）
            ragas_result = ragas_eval(
                dataset=eval_dataset,
                metrics=[m_faithfulness, m_answer_relevancy, m_context_precision],
                llm=judge_handle["llm"],
                embeddings=judge_handle["embeddings"],
                raise_exceptions=False,  # 单个失败不崩全局
            )

            # 提取分数（ragas_eval 返回 EvaluationResult，[key] → List[float]）
            scores = ragas_result._scores_dict
            ragas_faithfulness = float(scores["faithfulness"][0]) if "faithfulness" in scores else 0.0
            ragas_answer_relevancy = float(scores["answer_relevancy"][0]) if "answer_relevancy" in scores else 0.0
            ragas_context_precision = float(scores["context_precision"][0]) if "context_precision" in scores else context_precision

            return {
                "recall_at_k": round(recall_at_k, 4),
                "faithfulness": round(ragas_faithfulness, 4),
                "answer_relevancy": round(ragas_answer_relevancy, 4),
                "context_precision": round(ragas_context_precision, 4),
                "latency_ms": round(latency_ms, 2),
                "redundancy": round(redundancy, 4),
                "degraded": False,
            }

        except ImportError:
            # RAGAS/datasets 未安装，降级到启发式
            return {
                "recall_at_k": round(recall_at_k, 4),
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "context_precision": round(context_precision, 4),
                "latency_ms": round(latency_ms, 2),
                "redundancy": round(redundancy, 4),
                "degraded": True,
                "degraded_reason": "RAGAS 或 datasets 未安装",
            }
        except Exception as e:
            # RAGAS 评估失败，降级
            return {
                "recall_at_k": round(recall_at_k, 4),
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "context_precision": round(context_precision, 4),
                "latency_ms": round(latency_ms, 2),
                "redundancy": round(redundancy, 4),
                "degraded": True,
                "degraded_reason": f"RAGAS 评估失败: {e!s}",
            }
