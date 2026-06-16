from app_old.harness.state import LearningState
from app.harness.enums import Stage
from app_old.agent.spec_decorator import with_spec


@with_spec(intent="teach_loop", node="history_check")
def history_check_node(state: LearningState) -> dict:
    """检查用户是否有该主题的历史学习记录"""
    memory = state.get("memory", {})
    has_history = memory.get("has_history", False)
    history_summary = memory.get("history_summary", "")
    return {
        "memory": {"has_history": has_history, "history_summary": history_summary},
        "meta": {"stage": Stage.HISTORY_CHECK},
    }
