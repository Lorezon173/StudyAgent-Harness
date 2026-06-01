import pytest

from app.agents.critic import CriticAgent
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, MasteryLevel
from app.harness.workspace_state import WorkspaceState


def _user_msg(text: str) -> Event:
    return Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                 session_id="s1", payload={"text": text})


def test_critic_contract_declaration():
    a = CriticAgent()
    assert a.source == EventSource.CRITIC
    assert EventType.USER_MESSAGE in a.subscriptions
    assert EventType.RETRIEVED_EVIDENCE in a.subscriptions
    assert a.emittable_types == {
        EventType.MASTERY_ASSESSED,
        EventType.CONFUSION_DETECTED,
        EventType.CONTRADICTION_DETECTED,
        EventType.LOW_CONFIDENCE_DETECTED,
        EventType.RAG_QUALITY_ASSESSED,
    }


def test_critic_emits_mastery_assessed_on_user_message(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "partial",
        "mastery_score": 65,
        "rationale": "基本概念掌握，细节不足",
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("我觉得 RAG 应该是先搜再答"), ws)
    types = [e.type for e in out]
    assert EventType.MASTERY_ASSESSED in types
    mastery = next(e for e in out if e.type == EventType.MASTERY_ASSESSED)
    assert mastery.source == EventSource.CRITIC
    assert mastery.payload["level"] == str(MasteryLevel.PARTIAL)
    assert mastery.payload["score"] == 65


def test_critic_handles_missing_optional_fields(mock_llm_invoke_json):
    # LLM 仅返回最小集合
    mock_llm_invoke_json({"critic_assess": {"mastery_level": "weak"}})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("不懂"), ws)
    assert any(e.type == EventType.MASTERY_ASSESSED for e in out)
    assert all(e.type != EventType.CONFUSION_DETECTED for e in out)
    assert all(e.type != EventType.CONTRADICTION_DETECTED for e in out)


def test_critic_ignores_evidence_without_purpose_teaching(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_rag_quality": {"score": 0.4}})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    ev = Event(type=EventType.RETRIEVED_EVIDENCE, source=EventSource.RETRIEVER,
               session_id="s1", payload={"chunks": [], "purpose": "exploration"})
    out = CriticAgent().handle(ev, ws)
    assert out == []   # 纯探索检索跳过（#18 成本优化）
