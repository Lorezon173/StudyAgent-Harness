from typing import TypedDict, List, Optional


class MetaState(TypedDict, total=False):
    session_id: str
    user_id: Optional[int]
    stage: str
    stream_output: bool
    branch_trace: List[dict]
    next_stage: str
    current_plan: dict
    current_step_index: int
    need_replan: bool
    replan_reason: str
    error_kind: str
    error_detail: str
    recovery_action: str
    fallback_used: bool
    retry_trace: List[dict]
