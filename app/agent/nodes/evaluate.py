from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage, MasteryLevel
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="evaluate")
def evaluate_node(state: LearningState) -> dict:
    """评估用户掌握程度"""
    system_prompt = state["_system_prompt"]
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    restatement_eval = state.get("teaching", {}).get("restatement_eval", "")
    result = _llm.invoke_json(
        system_prompt,
        f"诊断：{diagnosis}\n复述评估：{restatement_eval}\n请输出掌握度评估",
    )
    mastery_score = result.get("mastery_score", 50)
    if mastery_score >= 80:
        level = MasteryLevel.MASTERED
    elif mastery_score >= 50:
        level = MasteryLevel.PARTIAL
    else:
        level = MasteryLevel.WEAK
    return {
        "evaluation": {
            "mastery_score": mastery_score,
            "mastery_level": level,
            "mastery_rationale": result.get("mastery_rationale", ""),
        },
        "meta": {"stage": Stage.EVALUATE},
    }
