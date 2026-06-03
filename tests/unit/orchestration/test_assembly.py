from app.orchestration.assembly import (
    extract_reply, extract_mastery_score, extract_mode_path,
)
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


def _ev(t, payload, source=EventSource.TUTOR):
    return Event(type=t, source=source, session_id="s", payload=payload)


def test_extract_reply_takes_last_tutor_content():
    events = [
        _ev(EventType.TUTOR_ASKED, {"content": "Q1"}),
        _ev(EventType.TUTOR_REQUESTED_RECAP, {"content": "请复述"}),
    ]
    assert extract_reply(events) == "请复述"


def test_extract_reply_covers_all_tutor_types():
    for t in (EventType.TUTOR_ASKED, EventType.TUTOR_EXPLAINED,
              EventType.TUTOR_REQUESTED_RECAP, EventType.TUTOR_OFFERED_ANALOGY):
        assert extract_reply([_ev(t, {"content": "C"})]) == "C"


def test_extract_reply_empty_when_no_tutor_event():
    events = [_ev(EventType.MASTERY_ASSESSED, {"score": 80},
                  source=EventSource.CRITIC)]
    assert extract_reply(events) == ""


def test_extract_mastery_score_takes_last():
    events = [
        _ev(EventType.MASTERY_ASSESSED, {"score": 40}, source=EventSource.CRITIC),
        _ev(EventType.MASTERY_ASSESSED, {"score": 90}, source=EventSource.CRITIC),
    ]
    assert extract_mastery_score(events) == 90


def test_extract_mastery_score_none_when_absent_or_null():
    assert extract_mastery_score([_ev(EventType.TUTOR_ASKED, {"content": "x"})]) is None
    events = [_ev(EventType.MASTERY_ASSESSED, {"score": None},
                  source=EventSource.CRITIC)]
    assert extract_mastery_score(events) is None


def test_extract_mode_path_starts_socratic_and_follows_transitions():
    events = [
        _ev(EventType.POLICY_TRANSITION, {"from": "Socratic", "to": "Feynman"},
            source=EventSource.ORCHESTRATOR),
        _ev(EventType.POLICY_TRANSITION, {"from": "Feynman", "to": "Analogy"},
            source=EventSource.ORCHESTRATOR),
    ]
    assert extract_mode_path(events) == ["Socratic", "Feynman", "Analogy"]


def test_extract_mode_path_default_socratic_when_no_transition():
    assert extract_mode_path([]) == ["Socratic"]
