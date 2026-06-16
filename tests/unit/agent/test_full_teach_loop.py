from app_old.agent.graph import build_learning_graph
from app.harness.enums import Intent, Stage
from app_old.harness.state import LearningState


def test_teach_loop_full_flow():
    graph = build_learning_graph()
    state: LearningState = {
        "user_input": "我想学二分查找",
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "test", "stage": Stage.INIT, "branch_trace": []},
    }
    result = graph.invoke(state, config={"configurable": {"thread_id": "test"}})
    assert result["routing"]["intent"] == Intent.TEACH_LOOP
    assert result["teaching"].get("summary") is not None
    assert "rag_context" in result["retrieval"]


def test_review_intent_goes_to_summarize():
    graph = build_learning_graph()
    state: LearningState = {
        "user_input": "帮我复习二分查找",
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "test", "stage": Stage.INIT, "branch_trace": []},
    }
    result = graph.invoke(state, config={"configurable": {"thread_id": "test2"}})
    assert result["routing"]["intent"] == Intent.REVIEW
    assert result["teaching"].get("summary") is not None
