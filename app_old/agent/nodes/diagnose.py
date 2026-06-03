from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="diagnose")
def diagnose_node(state: LearningState) -> dict:
    """诊断用户对主题的理解程度"""
    system_prompt = state["_system_prompt"]
    topic = state.get("memory", {}).get("topic", "")
    user_input = state["user_input"]
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt, f"主题：{topic}\n用户：{user_input}",
        session_id=session_id, node="diagnose", intent="teach_loop",
    )
    return {"teaching": {"diagnosis": result}}
