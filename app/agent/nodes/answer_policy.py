from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage

_llm = FakeLLM()


def answer_policy_node(state: LearningState) -> dict:
    """根据 RAG 证据和策略生成回答"""
    rag_context = state.get("retrieval", {}).get("rag_context", "")
    user_input = state["user_input"]
    result = _llm.invoke(
        "你是问答助手",
        f"知识：{rag_context}\n用户问题：{user_input}\n请回答",
    )
    return {
        "teaching": {"reply": result},
        "meta": {"stage": Stage.EXPLAINING},
    }
