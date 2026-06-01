import pytest

from app.agents.tutor import TutorAgent
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind
from app.harness.workspace_state import WorkspaceState


def _action(action: ActionKind, target: str = "tutor", **extra) -> Event:
    return Event(
        type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
        session_id="s1",
        payload={"action": str(action), "target": target, **extra},
    )


def test_tutor_contract_declaration():
    a = TutorAgent()
    assert a.source == EventSource.TUTOR
    assert EventType.ACTION_REQUESTED in a.subscriptions
    assert a.emittable_types == {
        EventType.TUTOR_ASKED,
        EventType.TUTOR_EXPLAINED,
        EventType.TUTOR_REQUESTED_RECAP,
        EventType.TUTOR_OFFERED_ANALOGY,
    }


def test_tutor_ignores_action_targeted_at_others():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    a = TutorAgent()
    out = a.handle(_action(ActionKind.RETRIEVER_SEARCH, target="retriever"), ws)
    assert out == []


def test_tutor_ask_emits_tutor_asked(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_ask": {"content": "为什么 LLM 需要外部资料？"}})
    ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="RAG")
    trigger = _action(ActionKind.TUTOR_ASK)
    out = TutorAgent().handle(trigger, ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_ASKED
    assert out[0].source == EventSource.TUTOR
    assert out[0].parent_id == trigger.id
    assert out[0].payload["content"] == "为什么 LLM 需要外部资料？"
    assert out[0].payload.get("kind") in (None, "ask")


def test_tutor_probe_prereq_emits_tutor_asked_with_kind(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_probe_prereq": {"content": "你之前接触过向量乘法吗？"}})
    ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="注意力机制")
    trigger = _action(ActionKind.TUTOR_PROBE_PREREQ, prereq_topic="向量乘法")
    out = TutorAgent().handle(trigger, ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_ASKED
    assert out[0].payload["kind"] == "probe_prereq"
    assert out[0].payload["prereq_topic"] == "向量乘法"


def test_tutor_explain_emits_tutor_explained(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_explain": {"content": "RAG = Retrieval-Augmented Generation..."}})
    ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="RAG")
    trigger = _action(ActionKind.TUTOR_EXPLAIN)
    out = TutorAgent().handle(trigger, ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_EXPLAINED
    assert out[0].payload["mode"] == "explain"


def test_tutor_re_explain_marks_repeat(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_re_explain": {"content": "换个角度："}})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = TutorAgent().handle(_action(ActionKind.TUTOR_RE_EXPLAIN), ws)
    assert out[0].type == EventType.TUTOR_EXPLAINED
    assert out[0].payload["mode"] == "re_explain"


def test_tutor_correct_for_contradiction(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_correct": {"content": "你刚才说的 X 不对，正确的是 Y"}})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = TutorAgent().handle(_action(ActionKind.TUTOR_CORRECT), ws)
    assert out[0].type == EventType.TUTOR_EXPLAINED
    assert out[0].payload["mode"] == "correct"
