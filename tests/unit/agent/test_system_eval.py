from app_old.agent.system_eval.teaching_eval import TeachingEval
from app_old.agent.system_eval.orchestrator_eval import OrchestratorEval
from app_old.agent.system_eval.eval_store import EvalStore as SystemEvalStore
from app_old.agent.system_eval.eval_graph import build_system_eval_graph
from app.harness.enums import Stage


def test_teaching_eval():
    evaluator = TeachingEval()
    result = evaluator.evaluate_teaching({
        "evaluation": {"mastery_score": 75},
        "teaching": {"explanation": "二分查找是一种搜索算法..."},
    })
    assert result["teaching_quality"] == "high"
    assert result["explanation_length"] > 0


def test_orchestrator_eval():
    evaluator = OrchestratorEval()
    result = evaluator.evaluate_flow({
        "meta": {"branch_trace": [{"from": Stage.INIT, "to": Stage.ROUTING}]},
    })
    assert result["flow_correct"] is True
    assert len(result["completed_stages"]) == 1


def test_system_eval_store():
    store = SystemEvalStore()
    store.save("s1", {"score": 85})
    assert store.get("s1")["score"] == 85
    assert store.get("s2") is None


def test_system_eval_graph():
    graph = build_system_eval_graph()
    state = {
        "user_input": "test",
        "routing": {}, "teaching": {"explanation": "test"},
        "retrieval": {}, "evaluation": {"mastery_score": 60},
        "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": [{"from": Stage.INIT, "to": Stage.ROUTING}]},
    }
    result = graph.invoke(state)
    assert "evaluation" in result
    assert "teaching_eval" in result["evaluation"]
