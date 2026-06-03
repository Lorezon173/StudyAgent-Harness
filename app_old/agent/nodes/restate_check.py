from app_old.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage
from app_old.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="restate_check")
def restate_check_node(state: LearningState) -> dict:
    """检测用户复述的理解程度"""
    system_prompt = state["_system_prompt"]
    explanation = state.get("teaching", {}).get("explanation", "")
    user_input = state["user_input"]
    loop_count = state.get("teaching", {}).get("explain_loop_count", 0)
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt, f"讲解：{explanation}\n用户复述：{user_input}",
        session_id=session_id, node="restate_check", intent="teach_loop",
    )
    return {
        "teaching": {"restatement_eval": result, "explain_loop_count": loop_count},
        "meta": {"stage": Stage.RESTATE_CHECK},
    }
