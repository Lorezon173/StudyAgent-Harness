from app_old.harness.state_manager import StateManager
from app.harness.enums import Stage
from app_old.harness.state import LearningState


def test_transition_merges_sub_state():
    sm = StateManager()
    state: LearningState = {
        "user_input": "", "routing": {}, "teaching": {},
        "retrieval": {}, "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = sm.transition(state, {"routing": {"intent": "teach_loop", "intent_confidence": 0.9}})
    assert result["routing"]["intent"] == "teach_loop"


def test_transition_top_level_key():
    sm = StateManager()
    state: LearningState = {
        "user_input": "", "routing": {}, "teaching": {},
        "retrieval": {}, "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = sm.transition(state, {"user_input": "hello"})
    assert result["user_input"] == "hello"


def test_transition_stage_change_appends_trace():
    sm = StateManager()
    state: LearningState = {
        "user_input": "", "routing": {}, "teaching": {},
        "retrieval": {}, "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = sm.transition(state, {"meta": {"stage": Stage.ROUTING}})
    assert len(result["meta"]["branch_trace"]) == 1
    assert result["meta"]["branch_trace"][0]["from"] == Stage.INIT
    assert result["meta"]["branch_trace"][0]["to"] == Stage.ROUTING


def test_snapshot_and_restore():
    sm = StateManager()
    state: LearningState = {
        "user_input": "test", "routing": {"intent": "teach_loop"}, "teaching": {},
        "retrieval": {}, "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    sid = sm.snapshot(state)
    assert sid
    restored = sm.restore(sid)
    assert restored["user_input"] == "test"
    assert restored["routing"]["intent"] == "teach_loop"
