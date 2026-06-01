import time
from app.harness.events import Event, new_event_id, EVENT_PRIORITY
from app.harness.enums import EventType, EventSource


def test_new_event_id_is_time_sortable():
    a = new_event_id(1000.0)
    b = new_event_id(2000.0)
    assert a < b                       # 字典序 == 时序
    assert len(a) == 25                # 13 位 ms + 12 位随机


def test_new_event_id_unique_same_ms():
    ids = {new_event_id(1000.0) for _ in range(100)}
    assert len(ids) == 100             # 同毫秒也唯一


def test_event_auto_id_and_ts():
    ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
               session_id="s1", payload={"text": "hi"})
    assert ev.id != ""                 # __post_init__ 自动生成
    assert ev.ts > 0
    assert ev.payload == {"text": "hi"}
    assert ev.parent_id is None
    assert ev.metadata == {}


def test_event_explicit_id_preserved():
    ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
               session_id="s1", id="fixed-id", ts=123.0)
    assert ev.id == "fixed-id"
    assert ev.ts == 123.0


def test_event_priority_observation_before_default():
    assert EVENT_PRIORITY[EventType.MASTERY_ASSESSED] < EVENT_PRIORITY.get(
        EventType.TUTOR_ASKED, 20)


def test_event_priority_tick_is_lowest():
    tick = EVENT_PRIORITY[EventType.ORCHESTRATOR_TICK]
    assert tick > EVENT_PRIORITY[EventType.MASTERY_ASSESSED]
    assert tick > EVENT_PRIORITY.get(EventType.ACTION_REQUESTED, 20)


def test_loop_exit_is_high_priority():
    assert EVENT_PRIORITY[EventType.LOOP_EXIT] < EVENT_PRIORITY[EventType.MASTERY_ASSESSED]
