from app.agent.multi_agent.teaching_graph import build_teaching_agent
from app.agent.multi_agent.eval_graph import build_eval_agent
from app.agent.multi_agent.retrieval_graph import build_retrieval_agent
from app.agent.multi_agent.routers import route_to_agent
from app.harness.enums import Intent, AgentRole, Stage
from app.agent.multi_agent.state import MultiAgentState


def _base_state(**overrides) -> MultiAgentState:
    state: MultiAgentState = {
        "user_input": "我想学二分查找",
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": "t", "stage": Stage.INIT, "branch_trace": []},
    }
    state.update(overrides)
    return state


def test_teaching_agent_runs():
    agent = build_teaching_agent()
    state = _base_state()
    result = agent.invoke(state)
    assert "teaching" in result


def test_eval_agent_runs():
    agent = build_eval_agent()
    state = _base_state(teaching={"diagnosis": "test", "restatement_eval": "ok"})
    result = agent.invoke(state)
    assert "evaluation" in result
    assert "ragas_faithfulness" in result["evaluation"]


def test_retrieval_agent_runs():
    agent = build_retrieval_agent()
    state = _base_state(memory={"topic": "二分查找"})
    result = agent.invoke(state)
    assert "retrieval" in result


def test_route_to_agent_teaching():
    state = _base_state(routing={"intent": Intent.TEACH_LOOP})
    assert route_to_agent(state) == AgentRole.TEACHING


def test_route_to_agent_eval():
    state = _base_state(routing={"intent": Intent.REVIEW})
    assert route_to_agent(state) == AgentRole.EVAL
