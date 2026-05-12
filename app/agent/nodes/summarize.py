from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage

_llm = FakeLLM()


def summarize_node(state: LearningState) -> dict:
    """生成学习总结与复习建议"""
    topic = state.get("memory", {}).get("topic", "")
    mastery = state.get("evaluation", {}).get("mastery_level", "")
    mastery_score = state.get("evaluation", {}).get("mastery_score", 0)
    rationale = state.get("evaluation", {}).get("mastery_rationale", "")
    result = _llm.invoke(
        "你是学习总结助手",
        f"主题：{topic}\n掌握等级：{mastery}\n掌握分数：{mastery_score}\n理由：{rationale}\n请生成学习总结",
    )
    return {
        "teaching": {"summary": result},
        "meta": {"stage": Stage.SUMMARIZE},
    }
