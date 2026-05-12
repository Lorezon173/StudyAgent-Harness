from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.harness.state import LearningState
from app.agent.node_wrapper import safe_node
from app.agent.nodes.route_intent import route_intent_node
from app.agent.nodes.history_check import history_check_node
from app.agent.nodes.knowledge_retrieval import knowledge_retrieval_node
from app.agent.nodes.diagnose import diagnose_node
from app.agent.nodes.explain import explain_node
from app.agent.nodes.restate_check import restate_check_node
from app.agent.nodes.followup import followup_node
from app.agent.nodes.evaluate import evaluate_node
from app.agent.nodes.summarize import summarize_node
from app.agent.routers import (
    route_by_intent,
    route_after_history,
    route_after_restate,
)


def build_learning_graph():
    graph = StateGraph(LearningState)

    graph.add_node("route_intent", safe_node(route_intent_node))
    graph.add_node("history_check", safe_node(history_check_node))
    graph.add_node("knowledge_retrieval", safe_node(knowledge_retrieval_node))
    graph.add_node("diagnose", safe_node(diagnose_node))
    graph.add_node("explain", safe_node(explain_node))
    graph.add_node("restate_check", safe_node(restate_check_node))
    graph.add_node("followup", safe_node(followup_node))
    graph.add_node("evaluate", safe_node(evaluate_node))
    graph.add_node("summarize", safe_node(summarize_node))

    graph.set_entry_point("route_intent")

    # 条件边: route_intent → 分支
    graph.add_conditional_edges("route_intent", route_by_intent, {
        "history_check": "history_check",
        "diagnose": "diagnose",
        "summarize": "summarize",
    })

    # teach_loop 分支
    graph.add_conditional_edges("history_check", route_after_history, {
        "diagnose": "diagnose",
    })
    graph.add_edge("diagnose", "knowledge_retrieval")
    graph.add_edge("knowledge_retrieval", "explain")
    graph.add_edge("explain", "restate_check")
    graph.add_conditional_edges("restate_check", route_after_restate, {
        "followup": "followup",
        "explain": "explain",
        "summarize": "summarize",
    })
    graph.add_edge("followup", "evaluate")

    # 汇合
    graph.add_edge("evaluate", "summarize")
    graph.add_edge("summarize", END)

    return graph.compile(checkpointer=MemorySaver())
