from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.llm import LLMService


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

    def __init__(self, llm: LLMService | None = None):
        self._llm = llm or LLMService()

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type != EventType.CONDUCTOR_REQUESTED:
            return []
        observations = event.payload.get("observations", [])
        result = self._llm.invoke_json(
            "你是融合式教学的 Conductor。只能基于已有观察事件做路由决策，"
            "禁止自产语义/结构观察。若观察不足，输出 "
            "action=request_observation + target=critic|curator。",
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

    def evaluate(self, test_case) -> dict:
        raise NotImplementedError("Plan E 实装 Conductor 部件级评估（§5.2）")
