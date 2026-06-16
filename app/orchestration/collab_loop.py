import heapq
import itertools

from app.harness.events import Event, priority_of
from app.harness.enums import EventType, EventSource
from app.harness.eventbus import EventBus
from app.harness.workspace_state import WorkspaceState

MAX_TURNS = 50


class PriorityEventQueue:
    """优先级队列（§3.5.2）：priority 小先出；同 priority 按入队序 FIFO，
    保证确定性回放。观察类(10) < 默认(20) < Tick(100)，LoopExit(5) 最先。
    """

    def __init__(self):
        self._heap: list = []
        self._seq = itertools.count()

    def push(self, event: Event) -> None:
        heapq.heappush(self._heap, (priority_of(event.type), next(self._seq), event))

    def pop(self) -> Event:
        return heapq.heappop(self._heap)[2]

    def empty(self) -> bool:
        return not self._heap


def run_collab_loop(bus: EventBus, ws: WorkspaceState, seed_events: list[Event],
                    orchestrator=None, max_turns: int = MAX_TURNS) -> WorkspaceState:
    """单线程事件循环（§3.5.1）。

    seed_events：协作环种子，通常是 UserMessage（+ 新主题时的 TopicEntered）。
    orchestrator：可选，提供 on_event(event, ws) -> list[Event] 钩子做路由决策；
                  Plan 0 骨架可不传（Plan C 接入真正的 Orchestrator + 回合屏障）。
    """
    queue = PriorityEventQueue()

    def _publish_and_enqueue(ev: Event) -> None:
        bus.publish(ev)                 # §3.2 白名单校验 + 持久化
        ws.event_ids.append(ev.id)
        queue.push(ev)

    for ev in seed_events:
        _publish_and_enqueue(ev)

    turn = 0
    fused = False
    while not queue.empty():
        turn += 1
        if turn > max_turns and not fused:        # 死循环熔断（§9）
            fused = True
            _publish_and_enqueue(Event(
                type=EventType.LOOP_EXIT, source=EventSource.ORCHESTRATOR,
                session_id=ws.session_id, payload={"reason": "max_turns"}))

        event = queue.pop()
        if event.type == EventType.LOOP_EXIT:     # 唯一出环信号（§3.5.4）
            break

        for agent in bus.subscribers_of(event.type):
            for new_ev in agent.handle(event, ws):
                _publish_and_enqueue(new_ev)

        if orchestrator is not None:
            for new_ev in orchestrator.on_event(event, ws):
                _publish_and_enqueue(new_ev)

    # turn 是循环迭代次数：含「pop 到 LoopExit 即退出」的那一轮空转（熔断或正常
    # 出环时该轮未处理真实事件），故 turn_count 比真实处理回合数多 1。§5 评估
    # 协作指标若需「真实处理回合数」应取 turn_count - 1。
    ws.turn_count = turn
    return ws
