import os
import tempfile

from app.infrastructure.storage.event_store import EventStore
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


def _make_store() -> tuple[EventStore, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = EventStore(db_path=path)
    store.init()
    return store, path


def test_append_and_replay_roundtrip():
    store, path = _make_store()
    try:
        ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="s1", payload={"text": "hi"})
        store.append(ev)
        got = store.replay("s1")
        assert len(got) == 1
        assert got[0].id == ev.id
        assert got[0].type == EventType.USER_MESSAGE
        assert got[0].source == EventSource.USER
        assert got[0].payload == {"text": "hi"}
    finally:
        store.close()
        os.unlink(path)


def test_replay_is_total_order_by_id():
    store, path = _make_store()
    try:
        # 故意乱序 append，但 id 时序递增（ts 递增）
        e2 = Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR,
                   session_id="s1", ts=2000.0)
        e1 = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="s1", ts=1000.0)
        store.append(e2)
        store.append(e1)
        got = store.replay("s1")
        assert [e.ts for e in got] == [1000.0, 2000.0]   # 回放按 id(时序) 升序
    finally:
        store.close()
        os.unlink(path)


def test_replay_filters_by_session():
    store, path = _make_store()
    try:
        store.append(Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                           session_id="s1"))
        store.append(Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                           session_id="s2"))
        assert len(store.replay("s1")) == 1
        assert len(store.replay("s2")) == 1
        assert store.replay("nope") == []
    finally:
        store.close()
        os.unlink(path)


def test_append_preserves_parent_id_and_metadata():
    store, path = _make_store()
    try:
        ev = Event(type=EventType.CONFUSION_DETECTED, source=EventSource.CRITIC,
                   session_id="s1", parent_id="p1", metadata={"cost": 0.01})
        store.append(ev)
        got = store.replay("s1")[0]
        assert got.parent_id == "p1"
        assert got.metadata == {"cost": 0.01}
    finally:
        store.close()
        os.unlink(path)
