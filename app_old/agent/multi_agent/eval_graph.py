from langgraph.graph import END, StateGraph

from app.agent.multi_agent.state import MultiAgentState
from app.agent.node_wrapper import safe_node
from app.agent.nodes.evaluate import evaluate_node


def _eval_mastery_node(state: MultiAgentState) -> dict:
    return evaluate_node(state)


def _eval_ragas_node(state: MultiAgentState) -> dict:
    return {
        "evaluation": {
            "ragas_faithfulness": 0.0,
            "ragas_relevancy": 0.0,
            "ragas_context_precision": 0.0,
        },
    }


def build_eval_agent():
    graph = StateGraph(MultiAgentState)

    graph.add_node("evaluate_mastery", safe_node(_eval_mastery_node))
    graph.add_node("evaluate_ragas", safe_node(_eval_ragas_node))

    graph.set_entry_point("evaluate_mastery")
    graph.add_edge("evaluate_mastery", "evaluate_ragas")
    graph.add_edge("evaluate_ragas", END)

    return graph.compile()
