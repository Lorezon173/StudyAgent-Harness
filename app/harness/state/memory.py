from typing import TypedDict, List, Optional


class MemoryState(TypedDict, total=False):
    topic: Optional[str]
    topic_confidence: float
    topic_changed: bool
    topic_reason: str
    topic_context: str
    topic_segments: List[dict]
    comparison_mode: bool
    history: List[str]
    has_history: bool
    history_summary: str
    history_mastery: str
    short_term_ids: List[str]
    long_term_context: str
    user_profile_summary: str
    mastery_history: List[dict]
