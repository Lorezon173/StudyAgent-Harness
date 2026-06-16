import pytest

from app.agents.base import AgentBase
from app.harness.events import Event, check_ownership
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState


class _EchoTutor(AgentBase):
    source = EventSource.TUTOR
    subscriptions = [EventType.USER_MESSAGE]
    emittable_types = {EventType.TUTOR_ASKED}

    def handle(self, event, ws):
        return [self.emit(EventType.TUTOR_ASKED, ws, payload={"q": "why?"},
                          parent_id=event.id)]


def test_handle_emits_event_with_own_source():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    trigger = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                    session_id="s1")
    out = _EchoTutor().handle(trigger, ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_ASKED
    assert out[0].source == EventSource.TUTOR
    assert out[0].session_id == "s1"
    assert out[0].parent_id == trigger.id        # 因果链


def test_emit_undeclared_type_raises():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    agent = _EchoTutor()
    with pytest.raises(ValueError):
        agent.emit(EventType.CONFUSION_DETECTED, ws)   # 未在 emittable_types


def test_emitted_event_passes_bus_ownership():
    # AgentBase.emit 出的事件应天然通过 §3.2 全局白名单
    ws = WorkspaceState(session_id="s1", user_id="u1")
    ev = _EchoTutor().emit(EventType.TUTOR_ASKED, ws)
    check_ownership(ev)                              # 不抛错


def test_evaluate_default_not_implemented():
    with pytest.raises(NotImplementedError):
        _EchoTutor().evaluate(test_case={})
