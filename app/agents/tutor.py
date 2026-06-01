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

    def evaluate(self, test_case) -> dict:
        raise NotImplementedError("Plan E 实装 Tutor 部件级评估（§5.2）")
