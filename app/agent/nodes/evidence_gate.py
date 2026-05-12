from app.harness.state import LearningState
from app.harness.enums import Stage, GateStatus


def evidence_gate_node(state: LearningState) -> dict:
    """证据守门：评估 RAG 检索质量，决定是否继续"""
    rag_found = state.get("retrieval", {}).get("rag_found", False)
    rag_confidence = state.get("retrieval", {}).get("rag_confidence_level", "low")
    if rag_found and rag_confidence in ("high", "medium"):
        gate_status = GateStatus.PASS
        coverage = 0.8
    elif rag_found:
        gate_status = GateStatus.SUPPLEMENT
        coverage = 0.4
    else:
        gate_status = GateStatus.REJECT
        coverage = 0.0
    return {
        "retrieval": {"gate_status": gate_status, "gate_coverage_score": coverage},
        "meta": {"stage": Stage.RETRIEVING},
    }
