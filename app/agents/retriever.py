"""Retriever Agent（§2.1）—— 知识检索，只做机械层。

事件契约：
  source      = retriever
  subscriptions = [ActionRequested]（按 payload.target==retriever 过滤）
  emittable   = {RetrievedEvidence, RetrievalFailed}

只做机械层：向量检索 + 原始 similarity score + retrieval_status。
绝不评判"证据够不够好"（语义质量归 Critic 的 RAGQualityAssessed）。
"""

import time

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
