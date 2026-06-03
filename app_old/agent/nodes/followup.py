from app_old.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage
from app_old.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="followup")
def followup_node(state: LearningState) -> dict:
    """针对理解薄弱点追问"""
    system_prompt = state["_system_prompt"]
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    restatement_eval = state.get("teaching", {}).get("restatement_eval", "")
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt, f"诊断：{diagnosis}\n复述评估：{restatement_eval}",
        session_id=session_id, node="followup", intent="teach_loop",
    )
    return {
        "teaching": {"followup_question": result},
        "meta": {"stage": Stage.FOLLOWUP},
    }
