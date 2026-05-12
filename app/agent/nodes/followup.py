from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage

_llm = FakeLLM()


def followup_node(state: LearningState) -> dict:
    """针对理解薄弱点追问"""
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    restatement_eval = state.get("teaching", {}).get("restatement_eval", "")
    result = _llm.invoke("你是追问助手", f"诊断：{diagnosis}\n复述评估：{restatement_eval}\n请追问")
    return {
        "teaching": {"followup_question": result},
        "meta": {"stage": Stage.FOLLOWUP},
    }
