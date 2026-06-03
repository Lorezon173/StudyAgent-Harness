from typing import TypedDict, List


class RetrievalState(TypedDict, total=False):
    rag_context: str
    rag_citations: List[dict]
    rag_found: bool
    rag_confidence_level: str
    rag_avg_score: float
    rag_source_count: int
    rag_strategy: str
    gate_status: str
    gate_coverage_score: float
    gate_missing_keywords: List[str]
