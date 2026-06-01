import os
import tempfile

import pytest

from app.harness.eventbus import EventBus
from app.infrastructure.storage.event_store import EventStore
from app.harness.events import Event, EmitViolationError
from app.harness.enums import EventType, EventSource


def _make_bus() -> tuple[EventBus, EventStore, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = EventStore(db_path=path)
    store.init()
    return EventBus(store=store), store, path


def test_publish_legal_event_persists():
    bus, store, path = _make_bus()
    try:
        ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="s1", payload={"text": "hi"})
        bus.publish(ev)
        assert len(bus.replay("s1")) == 1
    finally:
        store.close()
        os.unlink(path)


def test_publish_violation_raises_and_not_persisted():
    bus, store, path = _make_bus()
    try:
        bad = Event(type=EventType.CONFUSION_DETECTED, source=EventSource.TUTOR,
                    session_id="s1")
        with pytest.raises(EmitViolationError):
            bus.publish(bad)
        assert bus.replay("s1") == []      # 越权事件不落库
    finally:
        store.close()
        os.unlink(path)


def test_subscribe_and_subscribers_of():
    bus, store, path = _make_bus()
    try:
        agent_a, agent_b = object(), object()
        bus.subscribe(agent_a, [EventType.USER_MESSAGE, EventType.TUTOR_ASKED])
        bus.subscribe(agent_b, [EventType.USER_MESSAGE])
        subs = bus.subscribers_of(EventType.USER_MESSAGE)
        assert agent_a in subs and agent_b in subs
        assert bus.subscribers_of(EventType.TUTOR_ASKED) == [agent_a]
        assert bus.subscribers_of(EventType.LOOP_EXIT) == []
    finally:
        store.close()
        os.unlink(path)


def test_replay_without_store_returns_empty():
    bus = EventBus(store=None)
    assert bus.replay("s1") == []
