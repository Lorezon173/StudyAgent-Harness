from app.harness.state import LearningState
from app.harness.enums import Stage, RecoveryAction, ErrorKind
from app.agent.spec_decorator import with_spec


@with_spec(intent="teach_loop", node="recovery")
def recovery_node(state: LearningState) -> dict:
    """错误恢复节点：根据错误类型选择恢复策略"""
    error_kind = state.get("meta", {}).get("error_kind", ErrorKind.FATAL)
    recovery_action = state.get("meta", {}).get("recovery_action", RecoveryAction.ABORT)
    return {
        "meta": {
            "stage": Stage.RECOVERING,
            "fallback_used": True,
            "error_kind": error_kind,
            "recovery_action": recovery_action,
        },
    }
