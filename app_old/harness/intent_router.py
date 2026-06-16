from app.harness.enums import Intent
from app_old.harness.state.routing import RoutingState

RULE_MAP: list[tuple[list[str], str, float]] = [
    (["评估", "理解程度", "是什么", "怎么用"], Intent.QA_DIRECT, 0.95),
    (["复习", "回顾", "再看看"], Intent.REVIEW, 0.95),
    (["换个", "重新", "换方向"], Intent.REPLAN, 0.90),
]


class IntentRouter:
    def route(self, user_input: str, topic: str | None,
              history: list[str]) -> RoutingState:
        for keywords, intent, confidence in RULE_MAP:
            if any(kw in user_input for kw in keywords):
                return RoutingState(
                    intent=intent,
                    intent_confidence=confidence,
                    intent_source="rule",
                )
        return RoutingState(
            intent=Intent.TEACH_LOOP,
            intent_confidence=0.50,
            intent_source="fallback",
        )
