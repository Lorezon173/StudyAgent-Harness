from langgraph.graph import END, StateGraph

from app_old.harness.state import LearningState
from app_old.agent.node_wrapper import safe_node
from app_old.agent.system_eval.teaching_eval import TeachingEval
from app_old.agent.system_eval.orchestrator_eval import OrchestratorEval


def _teaching_eval_node(state: LearningState) -> dict:
    evaluator = TeachingEval()
    result = evaluator.evaluate_teaching(state)
    return {"evaluation": {"teaching_eval": result}}


def _orchestrator_eval_node(state: LearningState) -> dict:
    evaluator = OrchestratorEval()
    result = evaluator.evaluate_flow(state)
    existing = state.get("evaluation", {})
    return {"evaluation": {**existing, "orchestrator_eval": result}}


def build_system_eval_graph():
    graph = StateGraph(LearningState)

    graph.add_node("teaching_eval", safe_node(_teaching_eval_node))
    graph.add_node("orchestrator_eval", safe_node(_orchestrator_eval_node))

    graph.set_entry_point("teaching_eval")
    graph.add_edge("teaching_eval", "orchestrator_eval")
    graph.add_edge("orchestrator_eval", END)

    return graph.compile()
