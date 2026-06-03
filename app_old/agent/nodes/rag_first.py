from app_old.harness.state import LearningState
from app.harness.enums import Stage
from app_old.agent.spec_decorator import with_spec


@with_spec(intent="qa_direct", node="rag_first")
def rag_first_node(state: LearningState) -> dict:
    """qa_direct 分支：优先检索 RAG 知识"""
    user_input = state["user_input"]
    return {
        "retrieval": {
            "rag_context": f"关于用户问题的知识：{user_input}",
            "rag_found": bool(user_input),
            "rag_confidence_level": "medium",
            "rag_source_count": 1,
            "rag_strategy": "vector",
        },
        "meta": {"stage": Stage.RETRIEVING},
    }
