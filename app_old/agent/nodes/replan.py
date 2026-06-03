from app_old.harness.state import LearningState
from app.harness.enums import Stage
from app_old.agent.spec_decorator import with_spec


@with_spec(intent="replan", node="replan")
def replan_node(state: LearningState) -> dict:
    """重新规划学习路径"""
    user_input = state["user_input"]
    return {
        "routing": {"intent_source": "replan"},
        "memory": {"topic_changed": True, "topic_reason": user_input},
        "meta": {"stage": Stage.ROUTING},
    }
