from typing import TypedDict


class TeachingState(TypedDict, total=False):
    diagnosis: str
    explanation: str
    restatement_eval: str
    followup_question: str
    summary: str
    reply: str
    explain_loop_count: int
    user_choice: str
    waiting_for_choice: bool
