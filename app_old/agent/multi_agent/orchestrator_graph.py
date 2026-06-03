from langgraph.graph import END, StateGraph

from app_old.agent.multi_agent.state import MultiAgentState
from agent.node_wrapper import safe_node


def _orchestrate_node(state: MultiAgentState) -> dict:
    return {"current_agent": "teaching"}


def build_orchestrator():
    graph = StateGraph(MultiAgentState)

    graph.add_node("orchestrate", safe_node(_orchestrate_node))
    graph.add_node("summarize", safe_node(lambda s: {"teaching": {"summary": "学习完成"}}))

    graph.set_entry_point("orchestrate")
    graph.add_edge("orchestrate", "summarize")
    graph.add_edge("summarize", END)

    return graph.compile()
