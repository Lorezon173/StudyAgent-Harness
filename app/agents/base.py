from abc import ABC, abstractmethod

from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState


class AgentBase(ABC):
    """所有 Agent 的统一契约（§2.2）。

    子类必须声明三个类属性：
      source           —— 该 Agent 的事件来源身份（EventSource）
      subscriptions    —— 订阅的事件类型（协作环据此分发）
      emittable_types  —— 允许 emit 的事件类型集合（声明即契约，§2.2）

    约束：Agent 不直接互相调用、不直接写 DB/LLM（经 Harness 接口）、不写
    WorkspaceState。emit 出的事件先过本地 emittable_types 校验，最终所有权
    由 EventBus.publish 的 check_ownership 把关（§3.2）。
    """

    source: EventSource
    subscriptions: list[EventType]
    emittable_types: set[EventType]

    @abstractmethod
    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """处理一个订阅到的事件，返回产出的新事件（可为空列表）。"""
        ...

    def emit(self, type: EventType, ws: WorkspaceState,
             payload: dict | None = None,
             parent_id: str | None = None) -> Event:
        """构造一个带本 Agent source 身份的事件。

        本地校验 type ∈ emittable_types（声明即契约），越界抛 ValueError。
        """
        if type not in self.emittable_types:
            raise ValueError(
                f"{self.source} 未声明可 emit {type}（不在 emittable_types）")
        return Event(type=type, source=self.source, session_id=ws.session_id,
                     payload=payload or {}, parent_id=parent_id)

    def evaluate(self, test_case) -> dict:
        """部件级评估接口（§5.2）。Plan E / Wave 1 各 Agent 自行实现。"""
        raise NotImplementedError(
            f"{type(self).__name__} 尚未实现 evaluate（见 §5.2）")
