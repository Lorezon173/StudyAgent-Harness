from app.agent.nodes.history_check import history_check_node
from app.agent.nodes.knowledge_retrieval import knowledge_retrieval_node
from app.agent.nodes.restate_check import restate_check_node
from app.agent.nodes.followup import followup_node
from app.agent.nodes.evaluate import evaluate_node
from app.agent.nodes.summarize import summarize_node
from app.harness.enums import Intent, Stage, MasteryLevel
from app.harness.state import LearningState


def _base_state(**overrides) -> LearningState:
    state: LearningState = {
        "user_input": "我想学二分查找",
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    state.update(overrides)
    return state


def test_history_check_no_history():
    state = _base_state()
    result = history_check_node(state)
    assert result["memory"]["has_history"] is False
    assert result["meta"]["stage"] == Stage.HISTORY_CHECK


def test_history_check_with_history():
    state = _base_state(memory={"has_history": True, "history_summary": "之前学过排序"})
    result = history_check_node(state)
    assert result["memory"]["has_history"] is True
    assert result["memory"]["history_summary"] == "之前学过排序"


def test_knowledge_retrieval():
    state = _base_state(memory={"topic": "二分查找"}, teaching={"diagnosis": "理解薄弱"})
    result = knowledge_retrieval_node(state)
    assert result["retrieval"]["rag_found"] is True
    assert result["retrieval"]["rag_context"] != ""
    assert result["meta"]["stage"] == Stage.KNOWLEDGE_RETRIEVAL


def test_restate_check():
    state = _base_state(teaching={"explanation": "二分查找的核心是...", "explain_loop_count": 0})
    result = restate_check_node(state)
    assert "restatement_eval" in result["teaching"]
    assert result["meta"]["stage"] == Stage.RESTATE_CHECK


def test_followup():
    state = _base_state(teaching={"diagnosis": "基础薄弱", "restatement_eval": "部分理解"})
    result = followup_node(state)
    assert "followup_question" in result["teaching"]
    assert result["meta"]["stage"] == Stage.FOLLOWUP


def test_evaluate():
    state = _base_state(teaching={"diagnosis": "初学者", "restatement_eval": "理解较好"})
    result = evaluate_node(state)
    assert "mastery_score" in result["evaluation"]
    assert result["evaluation"]["mastery_level"] in (
        MasteryLevel.MASTERED, MasteryLevel.PARTIAL, MasteryLevel.WEAK,
    )
    assert result["meta"]["stage"] == Stage.EVALUATE


def test_summarize():
    state = _base_state(
        memory={"topic": "二分查找"},
        evaluation={"mastery_level": MasteryLevel.PARTIAL, "mastery_score": 60, "mastery_rationale": "基本概念理解"},
    )
    result = summarize_node(state)
    assert "summary" in result["teaching"]
    assert result["meta"]["stage"] == Stage.SUMMARIZE
