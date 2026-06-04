from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.llm import LLMService


class TutorAgent(AgentBase):
    """生成教学内容（§2.1）。

    职能正交：只生成（讲解 / 提问 / 类比 / 发起复述），不评判（复述质量归
    Critic，§2.4 / #15）。subscriptions 含 ActionRequested，内部按
    payload.action 分派；payload.target != 'tutor' 的事件被忽略（多 Agent 并存
    时由 Orchestrator 用 target 定向，§4 接口冻结清单 #8）。
    """

    source = EventSource.TUTOR
    subscriptions = [EventType.ACTION_REQUESTED]
    emittable_types = {
        EventType.TUTOR_ASKED,
        EventType.TUTOR_EXPLAINED,
        EventType.TUTOR_REQUESTED_RECAP,
        EventType.TUTOR_OFFERED_ANALOGY,
    }

    def __init__(self, llm: LLMService | None = None):
        self._llm = llm or LLMService()

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type != EventType.ACTION_REQUESTED:
            return []
        if event.payload.get("target") != str(EventSource.TUTOR):
            return []
        action = event.payload.get("action")
        if action == str(ActionKind.TUTOR_ASK):
            return self._ask(event, ws, intent="tutor_ask", kind="ask")
        if action == str(ActionKind.TUTOR_PROBE_PREREQ):
            return self._ask(event, ws, intent="tutor_probe_prereq",
                             kind="probe_prereq",
                             extra={"prereq_topic": event.payload.get("prereq_topic")})
        if action == str(ActionKind.TUTOR_EXPLAIN):
            return self._explain(event, ws, intent="tutor_explain", mode="explain")
        if action == str(ActionKind.TUTOR_RE_EXPLAIN):
            return self._explain(event, ws, intent="tutor_re_explain", mode="re_explain")
        if action == str(ActionKind.TUTOR_CORRECT):
            return self._explain(event, ws, intent="tutor_correct", mode="correct")
        if action == str(ActionKind.TUTOR_REQUEST_RECAP):
            result = self._llm.invoke_json(
                "你是融合式教学的 Tutor，切入费曼模式让用户复述。",
                f"主题：{ws.current_topic or ''}",
                session_id=ws.session_id, node="tutor",
                intent="tutor_request_recap",
            )
            return [self.emit(EventType.TUTOR_REQUESTED_RECAP, ws,
                              payload={"content": result.get("content", "")},
                              parent_id=event.id)]
        if action == str(ActionKind.TUTOR_OFFER_ANALOGY):
            result = self._llm.invoke_json(
                "你是融合式教学的 Tutor，给出类比破除概念混淆。",
                f"主题：{ws.current_topic or ''}",
                session_id=ws.session_id, node="tutor",
                intent="tutor_offer_analogy",
            )
            payload = {"content": result.get("content", "")}
            if "analogy_target" in result:
                payload["analogy_target"] = result["analogy_target"]
            return [self.emit(EventType.TUTOR_OFFERED_ANALOGY, ws,
                              payload=payload, parent_id=event.id)]
        return []

    def _ask(self, trigger: Event, ws: WorkspaceState, intent: str,
             kind: str, extra: dict | None = None) -> list[Event]:
        result = self._llm.invoke_json(
            "你是融合式教学的 Tutor，在 Socratic 模式下抛出引导问题。",
            f"主题：{ws.current_topic or ''}",
            session_id=ws.session_id, node="tutor", intent=intent,
        )
        payload = {"content": result.get("content", ""), "kind": kind}
        if extra:
            payload.update({k: v for k, v in extra.items() if v is not None})
        return [self.emit(EventType.TUTOR_ASKED, ws, payload=payload,
                          parent_id=trigger.id)]

    def _explain(self, trigger: Event, ws: WorkspaceState, intent: str,
                 mode: str) -> list[Event]:
        result = self._llm.invoke_json(
            "你是融合式教学的 Tutor，根据模式给出讲解。",
            f"主题：{ws.current_topic or ''}\n模式：{mode}",
            session_id=ws.session_id, node="tutor", intent=intent,
        )
        return [self.emit(EventType.TUTOR_EXPLAINED, ws,
                          payload={"content": result.get("content", ""),
                                   "mode": mode},
                          parent_id=trigger.id)]

    def evaluate(self, test_case: dict) -> dict:
        """部件级评估（§5.2）：生成教学内容并计算质量指标。

        test_case: {"topic": str, "action": str, "golden_response"?: str}
        返回: {"explanation_completeness": float, "response_length": int}
        """
        from collections import Counter

        topic = test_case.get("topic", "")
        action = test_case.get("action", "tutor_explain")
        golden = test_case.get("golden_response", "")

        ws = WorkspaceState(session_id="__eval__", user_id="__eval__",
                            current_topic=topic)
        trigger = Event(
            type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
            session_id="__eval__",
            payload={"action": action, "target": str(EventSource.TUTOR)})
        produced = self.handle(trigger, ws)

        content = ""
        for ev in produced:
            content = ev.payload.get("content", "")
            if content:
                break

        response_length = len(content)
        if golden and content:
            gc = Counter(golden)
            cc = Counter(content)
            intersection = sum((gc & cc).values())
            union = sum((gc | cc).values())
            completeness = intersection / union if union else 0.0
        elif content:
            completeness = min(response_length / 50, 1.0)
        else:
            completeness = 0.0

        return {
            "explanation_completeness": round(completeness, 4),
            "response_length": response_length,
        }
