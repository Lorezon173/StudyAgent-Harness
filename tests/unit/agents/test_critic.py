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


def test_critic_emits_confusion_when_present(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "partial",
        "confusion": {"concept_a": "retrieval", "concept_b": "augment"},
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("先搜，再给 LLM 处理"), ws)
    confusion = [e for e in out if e.type == EventType.CONFUSION_DETECTED]
    assert len(confusion) == 1
    assert confusion[0].payload["concept_a"] == "retrieval"
    assert confusion[0].payload["concept_b"] == "augment"


def test_critic_emits_contradiction_when_present(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "weak",
        "contradiction": {"description": "前后说 RAG 是又是微调又是检索"},
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("反复矛盾"), ws)
    assert any(e.type == EventType.CONTRADICTION_DETECTED for e in out)


def test_critic_emits_low_confidence(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "partial",
        "low_confidence": True,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("可能…大概…"), ws)
    assert any(e.type == EventType.LOW_CONFIDENCE_DETECTED for e in out)


def test_critic_emits_all_observations_in_single_handle(mock_llm_invoke_json):
    # 一次 handle 同时 emit 多观察（回合屏障的输入条件）
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "partial",
        "confusion": {"concept_a": "A", "concept_b": "B"},
        "low_confidence": True,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("x"), ws)
    types = {e.type for e in out}
    assert types == {
        EventType.MASTERY_ASSESSED,
        EventType.CONFUSION_DETECTED,
        EventType.LOW_CONFIDENCE_DETECTED,
    }


def test_critic_emits_rag_quality_for_teaching_purpose(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_rag_quality": {
        "score": 0.42, "relevance": 0.5, "sufficiency": 0.3,
        "rationale": "证据偏离主题",
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="RAG")
    ev = Event(type=EventType.RETRIEVED_EVIDENCE, source=EventSource.RETRIEVER,
               session_id="s1",
               payload={"chunks": [{"text": "..."}], "purpose": "teaching"})
    out = CriticAgent().handle(ev, ws)
    assert len(out) == 1
    assert out[0].type == EventType.RAG_QUALITY_ASSESSED
    assert out[0].payload["score"] == 0.42
    assert out[0].parent_id == ev.id


def test_critic_cannot_emit_tutor_event():
    # 越权防御（#14）
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        CriticAgent().emit(EventType.TUTOR_ASKED, ws)


def test_critic_cannot_emit_graph_prereq_weak():
    # 越权防御：结构层归 Curator（#15 切分）
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        CriticAgent().emit(EventType.GRAPH_PREREQ_WEAK_DETECTED, ws)


def test_critic_evaluate_returns_mastery_level(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "partial",
        "mastery_score": 55,
        "rationale": "基本概念正确但不完整",
    }})
    critic = CriticAgent()
    result = critic.evaluate({"user_text": "RAG是检索增强生成", "topic": "RAG"})
    assert result["mastery_level"] == "partial"
    assert result["mastery_score"] == 55
    assert result["confusion_detected"] is False
    assert result["contradiction_detected"] is False


def test_critic_evaluate_detects_confusion(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "weak",
        "mastery_score": 30,
        "rationale": "混淆概念",
        "confusion": {"concept_a": "retrieval", "concept_b": "fine-tuning"},
    }})
    critic = CriticAgent()
    result = critic.evaluate({"user_text": "RAG就是微调", "topic": "RAG"})
    assert result["mastery_level"] == "weak"
    assert result["confusion_detected"] is True
