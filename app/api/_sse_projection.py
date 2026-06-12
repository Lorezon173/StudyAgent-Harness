from app.harness.events import Event
from app.harness.enums import EventType

# 语义事件白名单（15 个）→ content 提取方式
_TUTOR = (EventType.TUTOR_ASKED, EventType.TUTOR_EXPLAINED,
          EventType.TUTOR_REQUESTED_RECAP, EventType.TUTOR_OFFERED_ANALOGY)
_CRITIC_EVAL = (EventType.MASTERY_ASSESSED, EventType.CONFUSION_DETECTED,
                EventType.CONTRADICTION_DETECTED, EventType.LOW_CONFIDENCE_DETECTED,
                EventType.RAG_QUALITY_ASSESSED)
_CURATOR = (EventType.GRAPH_NODE_STRENGTHENED, EventType.GRAPH_PREREQ_WEAK_DETECTED)
_RETRIEVER = (EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED)

_WHITELIST = set(_TUTOR) | set(_CRITIC_EVAL) | set(_CURATOR) | set(_RETRIEVER) | {
    EventType.CONDUCTOR_DECIDED, EventType.POLICY_TRANSITION,
}


def project_event(ev: Event) -> dict | None:
    """语义事件 → 前端友好 SSE payload；控制信号返回 None（生成器跳过）。"""
    if ev.type not in _WHITELIST:
        return None

    p = ev.payload or dict()
    out = {
        "type": "agent_event",
        "agent": str(ev.source),
        "event": str(ev.type),
        "content": "",
    }

    if ev.type in _TUTOR:
        out["content"] = p.get("content", "")
    elif ev.type in _CRITIC_EVAL:
        out["content"] = p.get("rationale", "") or p.get("content", "")
        out["eval"] = {k: p[k] for k in ("score", "level", "basis") if k in p}
    elif ev.type in _CURATOR:
        out["content"] = p.get("topic_id", "")
        out["eval"] = {k: p[k] for k in ("mastery", "prereq_topic_id") if k in p}
    elif ev.type in _RETRIEVER:
        out["content"] = p.get("summary", "") or str(p.get("count", ""))
    elif ev.type == EventType.POLICY_TRANSITION:
        out["content"] = p.get("to", "")
    elif ev.type == EventType.CONDUCTOR_DECIDED:
        out["content"] = p.get("decision", "") or p.get("action", "")

    return out
