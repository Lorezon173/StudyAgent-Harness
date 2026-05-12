from app.harness.state import LearningState
from app.harness.state.routing import RoutingState
from app.harness.state.teaching import TeachingState
from app.harness.state.retrieval import RetrievalState
from app.harness.state.evaluation import EvalState
from app.harness.state.memory import MemoryState
from app.harness.state.meta import MetaState


def test_routing_state():
    state: RoutingState = {"intent": "teach_loop", "intent_confidence": 0.9}
    assert state["intent"] == "teach_loop"


def test_retrieval_state_has_rag_fields():
    state: RetrievalState = {"rag_context": "...", "rag_found": True, "rag_source_count": 3, "rag_strategy": "hybrid"}
    assert state["rag_source_count"] == 3


def test_eval_state_has_ragas_fields():
    state: EvalState = {"mastery_score": 65, "ragas_faithfulness": 0.85}
    assert state["ragas_faithfulness"] == 0.85


def test_learning_state_combines_all():
    state: LearningState = {
        "user_input": "我想学二分查找",
        "routing": {"intent": "teach_loop"},
        "teaching": {}, "retrieval": {}, "evaluation": {}, "memory": {},
        "meta": {"session_id": "test", "stage": "init", "branch_trace": []},
    }
    assert state["user_input"] == "我想学二分查找"
    assert state["routing"]["intent"] == "teach_loop"


def test_learning_state_total_false():
    state: LearningState = {"user_input": "hello"}
    assert state["user_input"] == "hello"
