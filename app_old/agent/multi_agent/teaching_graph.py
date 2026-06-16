from langgraph.graph import END, StateGraph

from app_old.agent.multi_agent.state import MultiAgentState
from app_old.agent.node_wrapper import safe_node
from app_old.agent.nodes.diagnose import diagnose_node
from app_old.agent.nodes.explain import explain_node
from app_old.agent.nodes.restate_check import restate_check_node
from app_old.agent.nodes.followup import followup_node
from app_old.agent.routers import route_after_restate


def build_teaching_agent():
    graph = StateGraph(MultiAgentState)

    graph.add_node("diagnose", safe_node(diagnose_node))
    graph.add_node("explain", safe_node(explain_node))
    graph.add_node("restate_check", safe_node(restate_check_node))
    graph.add_node("followup", safe_node(followup_node))

    graph.set_entry_point("diagnose")
    graph.add_edge("diagnose", "explain")
    graph.add_edge("explain", "restate_check")
    graph.add_conditional_edges("restate_check", route_after_restate, {
        "followup": "followup",
        "explain": "explain",
        "summarize": END,
    })
    graph.add_edge("followup", END)

    return graph.compile()
