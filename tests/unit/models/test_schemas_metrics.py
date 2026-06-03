from app.models.schemas import ChatResponse


def test_chat_response_backward_compatible_minimal():
    """老栈构造方式（仅 reply/session_id/mastery_score）仍合法，新字段默认 None。"""
    r = ChatResponse(reply="hi", session_id="s1", mastery_score=70)
    assert r.reply == "hi"
    assert r.session_id == "s1"
    assert r.mastery_score == 70
    assert r.turn_count is None
    assert r.mode_path is None
    assert r.cost_est_usd is None
    assert r.stack is None


def test_chat_response_accepts_new_metric_fields():
    """新栈可填充全部对齐指标字段。"""
    r = ChatResponse(
        reply="问题？", session_id="s2", mastery_score=55,
        turn_count=11, mode_path=["Socratic", "Feynman"],
        cost_est_usd=0.0123, stack="new",
    )
    assert r.turn_count == 11
    assert r.mode_path == ["Socratic", "Feynman"]
    assert r.cost_est_usd == 0.0123
    assert r.stack == "new"


def test_chat_response_stack_legacy_label():
    """老栈出口标识 stack="legacy" 合法（与新栈 "new" 对称）。"""
    r = ChatResponse(reply="x", session_id="s3", stack="legacy")
    assert r.stack == "legacy"
