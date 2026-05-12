from app.agent.nodes.route_intent import route_intent_node
from app.harness.enums import Intent, Stage
from app.harness.state import LearningState
from app.agent.node_wrapper import safe_node


def test_route_intent_returns_routing_state():
    state: LearningState = {
        "user_input": "帮我复习二分查找",
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = route_intent_node(state)
    assert result["routing"]["intent"] == Intent.REVIEW
    assert result["routing"]["intent_source"] == "rule"


def test_safe_node_catches_exception():
    def bad_node(state):
        raise ValueError("test error")

    wrapped = safe_node(bad_node)
    state: LearningState = {
        "user_input": "", "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    result = wrapped(state)
    assert "meta" in result
    assert result["meta"]["error_kind"] is not None
