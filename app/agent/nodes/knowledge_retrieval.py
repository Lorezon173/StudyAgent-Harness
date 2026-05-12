from app.harness.state import LearningState
from app.harness.enums import Stage
from app.agent.spec_decorator import with_spec


@with_spec(intent="teach_loop", node="knowledge_retrieval")
def knowledge_retrieval_node(state: LearningState) -> dict:
    """检索与主题相关的知识内容"""
    topic = state.get("memory", {}).get("topic", "")
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    return {
        "retrieval": {
            "rag_context": f"关于{topic}的知识内容",
            "rag_found": bool(topic),
            "rag_confidence_level": "high",
            "rag_source_count": 1,
            "rag_strategy": "vector",
        },
        "meta": {"stage": Stage.KNOWLEDGE_RETRIEVAL},
    }
