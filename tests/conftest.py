import pytest
from app.harness.enums import Stage, Intent
from app.harness.state import LearningState


@pytest.fixture
def blank_state() -> LearningState:
    return {
        "user_input": "",
        "routing": {},
        "teaching": {},
        "retrieval": {},
        "evaluation": {},
        "memory": {},
        "meta": {"session_id": "test", "stage": Stage.INIT, "branch_trace": []},
    }


@pytest.fixture
def teach_state(blank_state) -> LearningState:
    state = blank_state.copy()
    state.update({
        "user_input": "我想学二分查找",
        "routing": {"intent": Intent.TEACH_LOOP, "intent_confidence": 0.9, "intent_source": "rule"},
        "memory": {"topic": "二分查找", "history": []},
    })
    return state
