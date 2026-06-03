from app_old.agent.nodes.rag_first import rag_first_node
from app_old.agent.nodes.evidence_gate import evidence_gate_node
from app_old.agent.nodes.answer_policy import answer_policy_node
from app_old.agent.nodes.replan import replan_node
from app_old.agent.nodes.recovery import recovery_node
from app.harness.enums import Intent, Stage, GateStatus
from app_old.harness.state import LearningState


def _base_state(**overrides) -> LearningState:
    state: LearningState = {
        "user_input": "二分查找是什么",
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    state.update(overrides)
    return state


def test_rag_first():
    state = _base_state()
    result = rag_first_node(state)
    assert result["retrieval"]["rag_found"] is True
    assert result["retrieval"]["rag_context"] != ""
    assert result["meta"]["stage"] == Stage.RETRIEVING


def test_evidence_gate_pass():
    state = _base_state(retrieval={"rag_found": True, "rag_confidence_level": "high"})
    result = evidence_gate_node(state)
    assert result["retrieval"]["gate_status"] == GateStatus.PASS
    assert result["retrieval"]["gate_coverage_score"] > 0.5


def test_evidence_gate_reject():
    state = _base_state(retrieval={"rag_found": False, "rag_confidence_level": "low"})
    result = evidence_gate_node(state)
    assert result["retrieval"]["gate_status"] == GateStatus.REJECT


def test_answer_policy():
    state = _base_state(retrieval={"rag_context": "二分查找是一种搜索算法"})
    result = answer_policy_node(state)
    assert "reply" in result["teaching"]
    assert result["meta"]["stage"] == Stage.EXPLAINING


def test_replan():
    state = _base_state()
    result = replan_node(state)
    assert result["routing"]["intent_source"] == "replan"
    assert result["memory"]["topic_changed"] is True
    assert result["meta"]["stage"] == Stage.ROUTING


def test_recovery():
    state = _base_state(meta={
        "session_id": "t", "stage": Stage.INIT, "branch_trace": [],
        "error_kind": "rag_timeout", "recovery_action": "retry",
    })
    result = recovery_node(state)
    assert result["meta"]["fallback_used"] is True
    assert result["meta"]["stage"] == Stage.RECOVERING
