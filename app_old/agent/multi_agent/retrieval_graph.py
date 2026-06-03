from langgraph.graph import END, StateGraph

from app_old.agent.multi_agent.state import MultiAgentState
from app_old.agent.node_wrapper import safe_node
from app_old.agent.nodes.knowledge_retrieval import knowledge_retrieval_node


def build_retrieval_agent():
    graph = StateGraph(MultiAgentState)

    graph.add_node("retrieve", safe_node(knowledge_retrieval_node))

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", END)

    return graph.compile()
