from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage

_llm = FakeLLM()


def restate_check_node(state: LearningState) -> dict:
    """检测用户复述的理解程度"""
    explanation = state.get("teaching", {}).get("explanation", "")
    user_input = state["user_input"]
    loop_count = state.get("teaching", {}).get("explain_loop_count", 0)
    result = _llm.invoke("你是复述评估助手", f"讲解：{explanation}\n用户复述：{user_input}\n请评估理解程度")
    return {
        "teaching": {"restatement_eval": result, "explain_loop_count": loop_count},
        "meta": {"stage": Stage.RESTATE_CHECK},
    }
