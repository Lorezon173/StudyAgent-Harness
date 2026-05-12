from typing import TypedDict, List


class EvalState(TypedDict, total=False):
    mastery_score: int
    mastery_level: str
    mastery_rationale: str
    error_labels: List[str]
    answer_template_id: str
    boundary_notice: str
    ragas_faithfulness: float
    ragas_relevancy: float
    ragas_context_precision: float
