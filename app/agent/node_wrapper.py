from app.harness.error_handler import get_error_handler
from app.harness.observability import get_observability
from app.harness.state import LearningState


def safe_node(func):
    """节点安全包装器：统一错误处理 + 可观测性追踪"""
    def wrapper(state: LearningState) -> dict:
        obs = get_observability()
        handler = get_error_handler()
        session_id = state.get("meta", {}).get("session_id", "")
        try:
            obs.trace(session_id, func.__name__, "start")
            result = func(state)
            obs.trace(session_id, func.__name__, "end")
            return result
        except Exception as e:
            obs.trace(session_id, func.__name__, "error", {"error": str(e)})
            return handler.handle(e, state)
    wrapper.__name__ = func.__name__
    return wrapper
