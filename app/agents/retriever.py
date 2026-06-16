"""Retriever Agent（§2.1）—— 知识检索，只做机械层。

事件契约：
  source      = retriever
  subscriptions = [ActionRequested]（按 payload.target==retriever 过滤）
  emittable   = {RetrievedEvidence, RetrievalFailed}

只做机械层：向量检索 + 原始 similarity score + retrieval_status。
绝不评判"证据够不够好"（语义质量归 Critic 的 RAGQualityAssessed）。
"""

import time
from collections import Counter

from app.agents.base import AgentBase
from app.harness.enums import EventType, EventSource
from app.harness.events import Event
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.rag.coordinator import RAGCoordinator

LOW_SCORE_THRESHOLD = 0.3


class RetrieverAgent(AgentBase):
    """知识检索 Agent（机械层，不自评语义质量）。"""

    source = EventSource.RETRIEVER
    subscriptions = [EventType.ACTION_REQUESTED]
    emittable_types = {EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED}

    def __init__(self, coordinator: RAGCoordinator | None = None):
        self._coordinator = coordinator or RAGCoordinator()

    # --- AgentBase 契约 ---

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """处理 ActionRequested(target=retriever)，委托 RAGCoordinator 检索。"""
        payload = event.payload or {}

        # 过滤：只处理 target=retriever 的请求
        if payload.get("target") != EventSource.RETRIEVER.value:
            return []

        query = payload.get("query", "")
        top_k = payload.get("top_k", 5)
        sources = payload.get("sources", None)
        purpose = payload.get("purpose", None)

        try:
            return self._do_retrieve_and_emit(
                query=query, top_k=top_k, sources=sources,
                purpose=purpose, parent_id=event.id, ws=ws,
            )
        except Exception as exc:
            return [self.emit(
                EventType.RETRIEVAL_FAILED, ws,
                payload={
                    "reason": str(exc),
                    "retrieval_status": "timeout",
                    "query": query,
                },
                parent_id=event.id,
            )]

    # --- 检索 + 机械判定 ---

    def _do_retrieve_and_emit(self, *, query: str, top_k: int,
                              sources: list[str] | None, purpose: str | None,
                              parent_id: str, ws: WorkspaceState) -> list[Event]:
        """执行检索并按纯机械指标判定 retrieval_status。"""
        t0 = time.time()
        result = self._coordinator.search(query, sources=sources, top_k=top_k)
        latency_ms = (time.time() - t0) * 1000

        chunks = result.chunks
        scores = [c.score for c in chunks]
        max_score = max(scores) if scores else 0.0

        # 机械判定 retrieval_status（§3.6）
        if not chunks:
            retrieval_status = "empty"
        elif max_score < LOW_SCORE_THRESHOLD:
            retrieval_status = "low_score"
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
        if purpose:
            payload["purpose"] = purpose

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
        combined = " ".join(retrieved_contents)

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

        # --- faithfulness：检索内容与 golden_answer 的字符 Jaccard 相似度 ---
        if golden_answer and combined:
            answer_tokens = set(golden_answer)
            retrieved_tokens = set(combined)
            intersection = answer_tokens & retrieved_tokens
            union = answer_tokens | retrieved_tokens
            faithfulness = len(intersection) / len(union) if union else 0.0
        elif combined and query:
            query_tokens = set(query)
            retrieved_tokens = set(combined)
            intersection = query_tokens & retrieved_tokens
            union = query_tokens | retrieved_tokens
            faithfulness = len(intersection) / len(union) if union else 0.0
        else:
            faithfulness = 0.0

        # --- answer_relevancy：检索内容与 query 的字符 Jaccard 相似度 ---
        if combined and query:
            query_tokens = set(query)
            retrieved_tokens = set(combined)
            intersection = query_tokens & retrieved_tokens
            union = query_tokens | retrieved_tokens
            answer_relevancy = len(intersection) / len(union) if union else 0.0
        else:
            answer_relevancy = 0.0

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

        return {
            "faithfulness": round(faithfulness, 4),
            "answer_relevancy": round(answer_relevancy, 4),
            "context_precision": round(context_precision, 4),
            "recall_at_k": round(recall_at_k, 4),
            "latency_ms": round(latency_ms, 2),
            "redundancy": round(redundancy, 4),
        }
