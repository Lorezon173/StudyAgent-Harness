from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.harness.state import LearningState
from app.agent.node_wrapper import safe_node
from app.agent.nodes.route_intent import route_intent_node
from app.agent.nodes.diagnose import diagnose_node
from app.agent.nodes.explain import explain_node
from app.agent.routers import route_by_intent


def build_learning_graph():
    graph = StateGraph(LearningState)

    graph.add_node("route_intent", safe_node(route_intent_node))
    graph.add_node("diagnose", safe_node(diagnose_node))
    graph.add_node("explain", safe_node(explain_node))

    graph.set_entry_point("route_intent")

    graph.add_conditional_edges("route_intent", route_by_intent, {
        "diagnose": "diagnose",
    })
    graph.add_edge("diagnose", "explain")
    graph.add_edge("explain", END)

    return graph.compile(checkpointer=MemorySaver())
