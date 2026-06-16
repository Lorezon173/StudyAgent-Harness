import pytest

from app.agents.conductor import ConductorAgent
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind
from app.harness.workspace_state import WorkspaceState


def _request(observations: list[dict]) -> Event:
    return Event(
        type=EventType.CONDUCTOR_REQUESTED, source=EventSource.ORCHESTRATOR,
        session_id="s1",
        payload={"observations": observations,
                 "reason": "rule fallthrough"},
    )


def test_conductor_contract():
    a = ConductorAgent()
    assert a.source == EventSource.CONDUCTOR
    assert a.subscriptions == [EventType.CONDUCTOR_REQUESTED]
    assert a.emittable_types == {EventType.CONDUCTOR_DECIDED}


def test_conductor_observation_enough_emits_action(mock_llm_invoke_json):
    mock_llm_invoke_json({"conductor_decide": {
        "action": "tutor_offer_analogy", "target": "tutor",
        "reason": "复述虽然偏，但前置 OK，类比破解最优",
        "observation_enough": True,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = ConductorAgent().handle(_request([
        {"type": "MasteryAssessed", "level": "partial"},
    ]), ws)
    assert len(out) == 1
    assert out[0].type == EventType.CONDUCTOR_DECIDED
    assert out[0].payload["action"] == str(ActionKind.TUTOR_OFFER_ANALOGY)
    assert out[0].payload["target"] == "tutor"


def test_conductor_cannot_emit_action_requested():
    # 越权防御（#16）：Conductor 不可直接 emit ActionRequested
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        ConductorAgent().emit(EventType.ACTION_REQUESTED, ws)


def test_conductor_cannot_emit_mastery_or_confusion():
    # 越权防御（#16）：Conductor 不能自产语义观察
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        ConductorAgent().emit(EventType.MASTERY_ASSESSED, ws)
    with pytest.raises(ValueError):
        ConductorAgent().emit(EventType.CONFUSION_DETECTED, ws)


def test_conductor_observation_insufficient_requests_critic(mock_llm_invoke_json):
    mock_llm_invoke_json({"conductor_decide": {
        "action": "request_observation",
        "target": "critic",
        "reason": "缺掌握度评估",
        "observation_enough": False,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = ConductorAgent().handle(_request([]), ws)
    assert len(out) == 1
    assert out[0].payload["action"] == str(ActionKind.REQUEST_OBSERVATION)
    assert out[0].payload["target"] == "critic"
    assert out[0].payload["observation_enough"] is False


def test_conductor_observation_insufficient_requests_curator(mock_llm_invoke_json):
    mock_llm_invoke_json({"conductor_decide": {
        "action": "request_observation",
        "target": "curator",
        "reason": "缺前置依赖结构观察",
        "observation_enough": False,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = ConductorAgent().handle(_request([
        {"type": "MasteryAssessed", "level": "weak"},
    ]), ws)
    assert out[0].payload["target"] == "curator"


def test_conductor_ignores_non_subscribed_event():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
               session_id="s1")
    assert ConductorAgent().handle(ev, ws) == []


def test_conductor_evaluate_empty_observations(mock_llm_invoke_json):
    mock_llm_invoke_json({"conductor_decide": {
        "action": "request_observation",
        "reason": "观察不足",
        "observation_enough": False,
        "target": "critic",
    }})
    conductor = ConductorAgent()
    result = conductor.evaluate({
        "observations": [],
        "current_mode": "Socratic",
    })
    assert result["action"] == "request_observation"
    assert result["observation_enough"] is False


def test_conductor_evaluate_with_observations(mock_llm_invoke_json):
    mock_llm_invoke_json({"conductor_decide": {
        "action": "tutor_offer_analogy",
        "reason": "混淆需要类比",
        "observation_enough": True,
    }})
    conductor = ConductorAgent()
    result = conductor.evaluate({
        "observations": [{"type": "ConfusionDetected"}],
        "current_mode": "Socratic",
    })
    assert result["action"] == "tutor_offer_analogy"
    assert result["observation_enough"] is True
