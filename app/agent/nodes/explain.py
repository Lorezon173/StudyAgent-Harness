from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM

_llm = FakeLLM()


def explain_node(state: LearningState) -> dict:
    """讲解知识点"""
    topic = state.get("memory", {}).get("topic", "")
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    result = _llm.invoke("你是教学助手", f"主题：{topic}\n诊断：{diagnosis}\n请讲解")
    return {"teaching": {"explanation": result, "reply": result}}
