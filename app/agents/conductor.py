from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.llm import LLMService
from app.specs.loader import SpecLoader


class ConductorAgent(AgentBase):
    """LLM 决策兜底（§2.3 / #16）。

    硬约束：
      - 只能在已有观察事件之上做路由决策，**不自产语义/结构观察**
      - emit 集合仅 ConductorDecided（不直接发 ActionRequested，由
        Orchestrator 转译）
      - 观察不足时 emit ConductorDecided(action=REQUEST_OBSERVATION, target=critic|curator)
        让专业 Agent 先看，下轮可能命中规则
    """

    source = EventSource.CONDUCTOR
    subscriptions = [EventType.CONDUCTOR_REQUESTED]
    emittable_types = {EventType.CONDUCTOR_DECIDED}

    def __init__(self, llm: LLMService | None = None,
                 spec_loader: SpecLoader | None = None):
        self._llm = llm or LLMService()
        self._spec = spec_loader or SpecLoader()

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type != EventType.CONDUCTOR_REQUESTED:
            return []
        observations = event.payload.get("observations", [])
        result = self._llm.invoke_json(
            self._spec.compose("conductor", "conductor_decide"),
            f"观察集：{observations}\n当前模式：{ws.current_mode}",
            session_id=ws.session_id, node="conductor",
            intent="conductor_decide",
        )
        payload = {
            "action": result.get("action", str(ActionKind.LOOP_EXIT)),
            "reason": result.get("reason", ""),
            "observation_enough": bool(result.get("observation_enough", False)),
        }
        if "target" in result:
            payload["target"] = result["target"]
        return [self.emit(EventType.CONDUCTOR_DECIDED, ws,
                          payload=payload, parent_id=event.id)]

    def evaluate(self, test_case: dict) -> dict:
        """部件级评估（§5.2）：给定观察集做决策，返回决策结果指标。

        test_case: {"observations": list[dict], "current_mode": str}
        返回: {"action": str, "observation_enough": bool, "reason": str}
        """
        ws = WorkspaceState(
            session_id="__eval__", user_id="__eval__",
            current_mode=test_case.get("current_mode", "Socratic"))
        trigger = Event(
            type=EventType.CONDUCTOR_REQUESTED, source=EventSource.ORCHESTRATOR,
            session_id="__eval__",
            payload={
                "observations": test_case.get("observations", []),
                "reason": "evaluate",
            })
        produced = self.handle(trigger, ws)
        if not produced:
            return {"action": "", "observation_enough": False, "reason": "no output"}
        ev = produced[0]
        return {
            "action": ev.payload.get("action", ""),
            "observation_enough": ev.payload.get("observation_enough", False),
            "reason": ev.payload.get("reason", ""),
        }
