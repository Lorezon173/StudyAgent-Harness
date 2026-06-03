from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="explain")
def explain_node(state: LearningState) -> dict:
    """讲解知识点"""
    system_prompt = state["_system_prompt"]
    topic = state.get("memory", {}).get("topic", "")
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt, f"主题：{topic}\n诊断：{diagnosis}\n请讲解",
        session_id=session_id, node="explain", intent="teach_loop",
    )
    return {"teaching": {"explanation": result, "reply": result}}
