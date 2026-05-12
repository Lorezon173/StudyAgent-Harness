from app.harness.enums import Intent, GateStatus
from app.harness.state import LearningState


def route_by_intent(state: LearningState) -> str:
    intent = state.get("routing", {}).get("intent", Intent.TEACH_LOOP)
    return {
        Intent.TEACH_LOOP: "history_check",
        Intent.QA_DIRECT: "diagnose",
        Intent.REPLAN: "diagnose",
        Intent.REVIEW: "summarize",
    }[intent]


def route_after_history(state: LearningState) -> str:
    if state.get("memory", {}).get("has_history", False):
        return "diagnose"
    return "diagnose"


def route_after_restate(state: LearningState) -> str:
    loops = state.get("teaching", {}).get("explain_loop_count", 0)
    eval_text = state.get("teaching", {}).get("restatement_eval", "")
    if any(k in eval_text for k in ("已理解", "准确", "完整")):
        return "summarize"
    if any(k in eval_text for k in ("错误", "混淆", "误解")) and loops < 3:
        return "explain"
    return "followup"


def route_after_gate(state: LearningState) -> str:
    if state.get("retrieval", {}).get("gate_status") == GateStatus.REJECT:
        return "recovery"
    return "answer_policy"
