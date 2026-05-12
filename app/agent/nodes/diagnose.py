from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM

_llm = FakeLLM()


def diagnose_node(state: LearningState) -> dict:
    """诊断用户对主题的理解程度"""
    topic = state.get("memory", {}).get("topic", "")
    user_input = state["user_input"]
    result = _llm.invoke("你是学习诊断助手", f"主题：{topic}\n用户：{user_input}\n请诊断")
    return {"teaching": {"diagnosis": result}}
