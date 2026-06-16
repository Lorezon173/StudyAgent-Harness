from collections import defaultdict

from app.harness.events import Event, check_ownership
from app.harness.enums import EventType
from app.infrastructure.storage.event_store import EventStore


class EventBus:
    """发布/订阅 + 白名单校验 + 持久化（§3.1/§3.2）。

    publish 是唯一的写入口：先校验所有权（越权抛 EmitViolationError，事件不落库），
    再持久化到 EventStore。分发（按 type 找订阅者并调用 handle）由协作环（§3.5）
    用 subscribers_of 驱动，EventBus 本身不调用 Agent —— 保持单线程循环对控制流的
    完全掌控。
    """

    def __init__(self, store: EventStore | None = None):
        self._subscribers: dict[EventType, list] = defaultdict(list)
        self._store = store

    def subscribe(self, agent, event_types: list[EventType]) -> None:
        for et in event_types:
            self._subscribers[et].append(agent)

    def subscribers_of(self, event_type: EventType) -> list:
        return list(self._subscribers.get(event_type, []))

    def publish(self, event: Event) -> None:
        check_ownership(event)                 # §3.2 越权抛错（在持久化之前）
        if self._store is not None:
            self._store.append(event)

    def replay(self, session_id: str) -> list[Event]:
        if self._store is None:
            return []
        return self._store.replay(session_id)
