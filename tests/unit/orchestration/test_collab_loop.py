import os
import tempfile

from app.orchestration.collab_loop import run_collab_loop, PriorityEventQueue
from app.harness.eventbus import EventBus
from app.infrastructure.storage.event_store import EventStore
from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState
from app.agents.base import AgentBase


def _bus():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = EventStore(db_path=path)
    store.init()
    return EventBus(store=store), store, path


class _AskOnce(AgentBase):
    source = EventSource.TUTOR
    subscriptions = [EventType.USER_MESSAGE]
    emittable_types = {EventType.TUTOR_ASKED}

    def handle(self, event, ws):
        return [self.emit(EventType.TUTOR_ASKED, ws, payload={"q": "why"})]


class _LoopForever(AgentBase):
    source = EventSource.TUTOR
    subscriptions = [EventType.USER_MESSAGE, EventType.TUTOR_ASKED]
    emittable_types = {EventType.TUTOR_ASKED}

    def handle(self, event, ws):
        return [self.emit(EventType.TUTOR_ASKED, ws)]


class _StubOrchestrator:
    def __init__(self):
        self.seen = []

    def on_event(self, event, ws):
        self.seen.append(event.type)
        if event.type == EventType.USER_MESSAGE:
            return [Event(type=EventType.LOOP_EXIT, source=EventSource.ORCHESTRATOR,
                          session_id=ws.session_id, payload={"reason": "done"})]
        return []


def test_priority_queue_observation_before_default():
    q = PriorityEventQueue()
    tutor = Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR, session_id="s")
    mastery = Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC, session_id="s")
    q.push(tutor)
    q.push(mastery)
    assert q.pop().type == EventType.MASTERY_ASSESSED   # 观察类先出（回合屏障基础）
    assert q.pop().type == EventType.TUTOR_ASKED


def test_priority_queue_same_priority_fifo():
    q = PriorityEventQueue()
    a = Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR, session_id="s", id="a")
    b = Event(type=EventType.TUTOR_EXPLAINED, source=EventSource.TUTOR, session_id="s", id="b")
    q.push(a)
    q.push(b)
    assert q.pop().id == "a"        # 同优先级 FIFO（确定性回放）
    assert q.pop().id == "b"


def test_loop_runs_until_queue_empty():
    bus, store, path = _bus()
    try:
        bus.subscribe(_AskOnce(), [EventType.USER_MESSAGE])
        ws = WorkspaceState(session_id="s1", user_id="u1")
        seed = Event(type=EventType.USER_MESSAGE, source=EventSource.USER, session_id="s1")
        run_collab_loop(bus, ws, [seed])
        types = [e.type for e in bus.replay("s1")]
        assert EventType.USER_MESSAGE in types
        assert EventType.TUTOR_ASKED in types
    finally:
        store.close()
        os.unlink(path)


def test_max_turns_fuse_stops_infinite_loop():
    bus, store, path = _bus()
    try:
        bus.subscribe(_LoopForever(), [EventType.USER_MESSAGE, EventType.TUTOR_ASKED])
        ws = WorkspaceState(session_id="s1", user_id="u1")
        seed = Event(type=EventType.USER_MESSAGE, source=EventSource.USER, session_id="s1")
        run_collab_loop(bus, ws, [seed], max_turns=5)
        assert ws.turn_count >= 5
        assert any(e.type == EventType.LOOP_EXIT for e in bus.replay("s1"))  # 熔断注入
    finally:
        store.close()
        os.unlink(path)


def test_dual_seed_both_persisted():
    bus, store, path = _bus()
    try:
        ws = WorkspaceState(session_id="s1", user_id="u1")
        seeds = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER, session_id="s1"),
            Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                  session_id="s1", payload={"topic": "RAG"}),
        ]
        run_collab_loop(bus, ws, seeds)
        types = {e.type for e in bus.replay("s1")}
        assert EventType.USER_MESSAGE in types
        assert EventType.TOPIC_ENTERED in types       # 双种子（§3.5.1）
    finally:
        store.close()
        os.unlink(path)


def test_orchestrator_hook_invoked_and_can_exit():
    bus, store, path = _bus()
    try:
        orch = _StubOrchestrator()
        ws = WorkspaceState(session_id="s1", user_id="u1")
        seed = Event(type=EventType.USER_MESSAGE, source=EventSource.USER, session_id="s1")
        run_collab_loop(bus, ws, [seed], orchestrator=orch)
        assert EventType.USER_MESSAGE in orch.seen
        assert any(e.type == EventType.LOOP_EXIT for e in bus.replay("s1"))
    finally:
        store.close()
        os.unlink(path)


def test_priority_queue_tick_is_last():
    # OrchestratorTick 最低优先级（回合屏障基础：观察处理完才决策，§3.5.3）
    q = PriorityEventQueue()
    q.push(Event(type=EventType.ORCHESTRATOR_TICK, source=EventSource.ORCHESTRATOR, session_id="s"))
    q.push(Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR, session_id="s"))
    q.push(Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC, session_id="s"))
    assert q.pop().type == EventType.MASTERY_ASSESSED   # 观察类先
    assert q.pop().type == EventType.TUTOR_ASKED         # 默认次
    assert q.pop().type == EventType.ORCHESTRATOR_TICK   # Tick 最后（屏障）


def test_loop_exit_preempts_queued_events():
    # 熔断安全性基础：LoopExit 优先级最高，即使队列已堆积大量普通/观察事件，
    # 注入的 LoopExit 也会被立即 pop（保证熔断即时终止，不必等队列耗尽）。
    q = PriorityEventQueue()
    for _ in range(5):
        q.push(Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR, session_id="s"))
        q.push(Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC, session_id="s"))
    q.push(Event(type=EventType.LOOP_EXIT, source=EventSource.ORCHESTRATOR, session_id="s"))
    assert q.pop().type == EventType.LOOP_EXIT   # 穿透所有已排队事件
