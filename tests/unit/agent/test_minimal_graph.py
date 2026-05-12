from app.agent.graph import build_learning_graph
from app.harness.enums import Intent, Stage
from app.harness.state import LearningState


def test_minimal_graph_route_intent():
    graph = build_learning_graph()
    state: LearningState = {
        "user_input": "我想学二分查找",
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "test", "stage": Stage.INIT, "branch_trace": []},
    }
    result = graph.invoke(state, config={"configurable": {"thread_id": "test"}})
    assert "routing" in result
    assert result["routing"]["intent"] == Intent.TEACH_LOOP
    assert "teaching" in result
    assert result["teaching"].get("explanation") is not None
