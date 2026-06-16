from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, MasteryLevel
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.llm import LLMService
from app.specs.loader import SpecLoader


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

    def __init__(self, llm: LLMService | None = None,
                 spec_loader: SpecLoader | None = None):
        self._llm = llm or LLMService()
        self._spec = spec_loader or SpecLoader()

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
            self._spec.compose("critic", "critic_assess"),
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
            self._spec.compose("critic", "critic_rag_quality"),
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

    def evaluate(self, test_case: dict) -> dict:
        """部件级评估（§5.2）：对给定用户文本做语义评估，返回标准化指标。

        test_case: {"user_text": str, "topic": str}
        返回: {"mastery_level": str, "mastery_score": int|None,
               "confusion_detected": bool, "contradiction_detected": bool,
               "low_confidence_detected": bool}
        """
        ws = WorkspaceState(session_id="__eval__", user_id="__eval__",
                            current_topic=test_case.get("topic", ""))
        fake_event = Event(
            type=EventType.USER_MESSAGE, source=EventSource.USER,
            session_id="__eval__",
            payload={"text": test_case.get("user_text", "")})
        produced = self._assess_user_message(fake_event, ws)
        result: dict = {
            "mastery_level": None,
            "mastery_score": None,
            "confusion_detected": False,
            "contradiction_detected": False,
            "low_confidence_detected": False,
        }
        for ev in produced:
            if ev.type == EventType.MASTERY_ASSESSED:
                result["mastery_level"] = ev.payload.get("level")
                result["mastery_score"] = ev.payload.get("score")
            elif ev.type == EventType.CONFUSION_DETECTED:
                result["confusion_detected"] = True
            elif ev.type == EventType.CONTRADICTION_DETECTED:
                result["contradiction_detected"] = True
            elif ev.type == EventType.LOW_CONFIDENCE_DETECTED:
                result["low_confidence_detected"] = True
        return result
