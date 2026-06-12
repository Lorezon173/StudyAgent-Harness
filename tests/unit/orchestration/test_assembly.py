from app.orchestration.assembly import (
    extract_reply, extract_mastery_score, extract_mode_path,
)
from app.orchestration.assembly import run_new_agent_session, NewStackResult
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


def test_run_new_agent_session_partial_drives_socratic_to_feynman(mock_llm_invoke_json):
    """端到端：partial → Orchestrator 切 Feynman → Tutor 发 recap；
    队列自然耗尽结束。验证 reply/mastery/mode_path/turn_count 提取。"""
    mock_llm_invoke_json({
        "tutor_ask": {"content": "你怎么理解 RAG？"},
        "critic_assess": {"mastery_level": "partial", "mastery_score": 55,
                          "rationale": "基础有，细节缺"},
        "tutor_request_recap": {"content": "请用你的话复述 RAG"},
    })
    result = run_new_agent_session(
        session_id="asm-1", user_id="u1", user_message="帮我理解 RAG")

    assert isinstance(result, NewStackResult)
    # 最后一个 Tutor 事件是 recap（partial 触发 Socratic→Feynman→request_recap）
    assert result.reply == "请用你的话复述 RAG"
    assert result.mastery_score == 55
    assert result.turn_count > 0
    assert result.mode_path[0] == "Socratic"
    assert "Feynman" in result.mode_path


def test_run_new_agent_session_no_observation_still_replies(mock_llm_invoke_json):
    """Critic 无观察（{}）时，注入的 tutor_ask 种子仍保证有首条引导问题。"""
    mock_llm_invoke_json({
        "tutor_ask": {"content": "开场引导问题"},
        "critic_assess": {},
    })
    result = run_new_agent_session(
        session_id="asm-2", user_id="u2", user_message="随便聊聊")
    assert result.reply == "开场引导问题"
    assert result.mastery_score is None
    assert result.mode_path == ["Socratic"]


def test_run_new_agent_session_no_emit_violation(mock_llm_invoke_json):
    """装配跑完不应抛 EmitViolationError（职能正交 #14 全局不变量）。"""
    from app.harness.events import EmitViolationError
    mock_llm_invoke_json({
        "tutor_ask": {"content": "Q"},
        "critic_assess": {"mastery_level": "mastered", "mastery_score": 95},
        "conductor_decide": {"action": "loop_exit", "reason": "done"},
    })
    try:
        result = run_new_agent_session(
            session_id="asm-3", user_id="u3", user_message="我已经懂了")
    except EmitViolationError as e:
        raise AssertionError(f"出现越权 emit：{e}")
    assert result.reply  # 有回复
    # mastered 经 Conductor 决策走到 loop_exit 末态（spec §4.3）
    assert result.mastery_score == 95
    assert any(e.type == EventType.LOOP_EXIT for e in result.events)


def test_run_new_agent_session_invokes_on_event(mock_llm_invoke_json):
    mock_llm_invoke_json({})
    seen = []
    result = run_new_agent_session(
        "sess-onev", "u-onev", "什么是二分查找",
        on_event=lambda ev: seen.append(ev.type),
    )
    assert isinstance(result, NewStackResult)
    assert len(seen) >= 1  # 回调被逐事件调用


def test_run_new_agent_session_accepts_external_graph(mock_llm_invoke_json):
    mock_llm_invoke_json({})
    from app.harness.mastery_graph import MasteryGraph
    from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore
    graph = MasteryGraph(user_id="u-ext", store=MasteryGraphStore(db_path=":memory:"))
    result = run_new_agent_session(
        "sess-ext", "u-ext", "二分查找", graph=graph,
    )
    assert isinstance(result, NewStackResult)
