from app.harness.enums import Intent
from app.harness.state import LearningState


def route_by_intent(state: LearningState) -> str:
    intent = state.get("routing", {}).get("intent", Intent.TEACH_LOOP)
    return {
        Intent.TEACH_LOOP: "diagnose",
        Intent.QA_DIRECT: "diagnose",
        Intent.REPLAN: "diagnose",
        Intent.REVIEW: "diagnose",
    }[intent]
