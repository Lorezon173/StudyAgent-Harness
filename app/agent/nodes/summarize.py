from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="summarize")
def summarize_node(state: LearningState) -> dict:
    """生成学习总结与复习建议"""
    system_prompt = state["_system_prompt"]
    topic = state.get("memory", {}).get("topic", "")
    mastery = state.get("evaluation", {}).get("mastery_level", "")
    mastery_score = state.get("evaluation", {}).get("mastery_score", 0)
    rationale = state.get("evaluation", {}).get("mastery_rationale", "")
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt,
        f"主题：{topic}\n掌握等级：{mastery}\n掌握分数：{mastery_score}\n理由：{rationale}",
        session_id=session_id, node="summarize", intent="teach_loop",
    )
    return {
        "teaching": {"summary": result},
        "meta": {"stage": Stage.SUMMARIZE},
    }
