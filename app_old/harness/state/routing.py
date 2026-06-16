from typing import TypedDict


class RoutingState(TypedDict, total=False):
    intent: str
    intent_confidence: float
    intent_source: str
    tool_route: dict
    retrieval_strategy: dict
    retrieval_mode: str
