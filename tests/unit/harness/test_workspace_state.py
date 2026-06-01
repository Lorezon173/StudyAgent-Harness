from app.harness.workspace_state import WorkspaceState
from app.harness.enums import TeachingMode


def test_workspace_state_defaults():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    assert ws.session_id == "s1"
    assert ws.user_id == "u1"
    assert ws.current_topic is None
    assert ws.current_mode == TeachingMode.SOCRATIC   # 默认进苏格拉底
    assert ws.turn_count == 0
    assert ws.event_ids == []
    assert ws.evidence_pool == []
    assert ws.critic_state == {}
    assert ws.profile_snapshot == {}


def test_workspace_state_independent_mutables():
    # 两个实例的可变默认字段不共享（dataclass field(default_factory)）
    a = WorkspaceState(session_id="s1", user_id="u1")
    b = WorkspaceState(session_id="s2", user_id="u2")
    a.event_ids.append("e1")
    assert b.event_ids == []


def test_workspace_state_records_event_ref():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    ws.event_ids.append("0000000001000abcdef012345")
    ws.current_mode = TeachingMode.FEYNMAN
    ws.turn_count = 3
    assert len(ws.event_ids) == 1
    assert ws.current_mode == "Feynman"
