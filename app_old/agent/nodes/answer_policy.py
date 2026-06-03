from app_old.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage
from app_old.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="qa_direct", node="answer_policy")
def answer_policy_node(state: LearningState) -> dict:
    """根据 RAG 证据和策略生成回答"""
    system_prompt = state["_system_prompt"]
    rag_context = state.get("retrieval", {}).get("rag_context", "")
    user_input = state["user_input"]
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt,
        f"知识：{rag_context}\n用户问题：{user_input}",
        session_id=session_id, node="answer_policy", intent="qa_direct",
    )
    return {
        "teaching": {"reply": result},
        "meta": {"stage": Stage.EXPLAINING},
    }
