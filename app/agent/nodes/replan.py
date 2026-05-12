from app.harness.state import LearningState
from app.harness.enums import Stage


def replan_node(state: LearningState) -> dict:
    """重新规划学习路径"""
    user_input = state["user_input"]
    return {
        "routing": {"intent_source": "replan"},
        "memory": {"topic_changed": True, "topic_reason": user_input},
        "meta": {"stage": Stage.ROUTING},
    }
