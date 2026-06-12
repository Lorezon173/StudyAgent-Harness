from app.api._sse_projection import project_event
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


def _ev(t, source, payload):
    return Event(type=t, source=source, session_id="s", payload=payload)


def test_tutor_event_projected():
    out = project_event(_ev(EventType.TUTOR_ASKED, EventSource.TUTOR, {"content": "Q1"}))
    assert out["type"] == "agent_event"
    assert out["agent"] == "tutor"
    assert out["event"] == "TutorAsked"
    assert out["content"] == "Q1"


def test_mastery_assessed_carries_eval():
    out = project_event(_ev(EventType.MASTERY_ASSESSED, EventSource.CRITIC,
                            {"score": 80, "level": "good"}))
    assert out["agent"] == "critic"
    assert out["eval"]["score"] == 80
    assert out["eval"]["level"] == "good"


def test_control_event_filtered():
    assert project_event(_ev(EventType.ORCHESTRATOR_TICK, EventSource.ORCHESTRATOR, {})) is None
    assert project_event(_ev(EventType.USER_MESSAGE, EventSource.USER, {"text": "hi"})) is None
    assert project_event(_ev(EventType.LOOP_EXIT, EventSource.ORCHESTRATOR, {})) is None


def test_policy_transition_projected():
    out = project_event(_ev(EventType.POLICY_TRANSITION, EventSource.ORCHESTRATOR,
                            {"to": "feynman"}))
    assert out["event"] == "PolicyTransition"
    assert out["content"] == "feynman"
