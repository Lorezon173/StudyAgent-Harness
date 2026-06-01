from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, MasteryLevel
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.llm import LLMService


class CriticAgent(AgentBase):
    """文本语义评估（§2.1）。

    职能正交：只判文本语义层 —— mastery / confusion / contradiction /
    low_confidence / RAG 质量（#15 复述检查归本 Agent；#18 RAG 质量仅
    purpose=teaching 时评）。**不读图谱、不判前置缺失、不做路由决策**。
    单次 LLM 调用产出一份 JSON，含多观察字段，Critic 据此拆分多条 emit。
    """

    source = EventSource.CRITIC
    subscriptions = [EventType.USER_MESSAGE, EventType.RETRIEVED_EVIDENCE]
    emittable_types = {
        EventType.MASTERY_ASSESSED,
        EventType.CONFUSION_DETECTED,
        EventType.CONTRADICTION_DETECTED,
        EventType.LOW_CONFIDENCE_DETECTED,
        EventType.RAG_QUALITY_ASSESSED,
    }

    def __init__(self, llm: LLMService | None = None):
        self._llm = llm or LLMService()

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type == EventType.USER_MESSAGE:
            return self._assess_user_message(event, ws)
        if event.type == EventType.RETRIEVED_EVIDENCE:
            if event.payload.get("purpose") != "teaching":
                return []          # #18 成本优化：纯探索不评
            return self._assess_rag_quality(event, ws)
        return []

    def _assess_user_message(self, event: Event, ws: WorkspaceState) -> list[Event]:
        text = event.payload.get("text", "")
        result = self._llm.invoke_json(
            "你是融合式教学的 Critic，对用户回答做语义评估。"
            "输出 JSON：mastery_level(weak|partial|mastered)、mastery_score(0-100)、"
            "rationale、confusion(可选: {concept_a, concept_b})、"
            "contradiction(可选: {description})、low_confidence(可选: bool)。",
            f"主题：{ws.current_topic or ''}\n用户回答：{text}",
            session_id=ws.session_id, node="critic", intent="critic_assess",
        )
        events: list[Event] = []
        if "mastery_level" in result:
            events.append(self.emit(
                EventType.MASTERY_ASSESSED, ws,
                payload={
                    "level": result["mastery_level"],
                    "score": result.get("mastery_score"),
                    "rationale": result.get("rationale", ""),
                },
                parent_id=event.id))
        if isinstance(result.get("confusion"), dict):
            c = result["confusion"]
            events.append(self.emit(
                EventType.CONFUSION_DETECTED, ws,
                payload={
                    "concept_a": c.get("concept_a", ""),
                    "concept_b": c.get("concept_b", ""),
                },
                parent_id=event.id))
        if isinstance(result.get("contradiction"), dict):
            events.append(self.emit(
                EventType.CONTRADICTION_DETECTED, ws,
                payload={"description":
                         result["contradiction"].get("description", "")},
                parent_id=event.id))
        if result.get("low_confidence") is True:
            events.append(self.emit(
                EventType.LOW_CONFIDENCE_DETECTED, ws,
                payload={"signal": "user_self_uncertain"},
                parent_id=event.id))
        # 其余观察字段在后续 Task 落地（避免一次落地过大）
        return events

    def _assess_rag_quality(self, event: Event, ws: WorkspaceState) -> list[Event]:
        chunks = event.payload.get("chunks", [])
        result = self._llm.invoke_json(
            "你是融合式教学的 Critic，评估证据对当前教学是否相关、是否充分。"
            "输出 JSON：score(0-1)、relevance(0-1)、sufficiency(0-1)、rationale。",
            f"主题：{ws.current_topic or ''}\n证据条数：{len(chunks)}",
            session_id=ws.session_id, node="critic", intent="critic_rag_quality",
        )
        if "score" not in result:
            return []
        return [self.emit(
            EventType.RAG_QUALITY_ASSESSED, ws,
            payload={
                "score": result["score"],
                "relevance": result.get("relevance"),
                "sufficiency": result.get("sufficiency"),
                "rationale": result.get("rationale", ""),
            },
            parent_id=event.id)]

    def evaluate(self, test_case) -> dict:
        raise NotImplementedError("Plan E 实装 Critic 部件级评估（§5.2）")
