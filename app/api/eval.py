from fastapi import APIRouter, HTTPException

from app.models.schemas import EvalResponse
from app.infrastructure.storage.eval_store import EvalStore

router = APIRouter(prefix="/eval", tags=["eval"])
_store = EvalStore()


@router.get("/{session_id}", response_model=list[EvalResponse])
async def get_evals(session_id: str):
    evals = await _store.list_by_session(session_id)
    if not evals:
        return []
    return [
        EvalResponse(
            eval_id=e.get("id", 0),
            session_id=e.get("session_id", session_id),
            mastery_score=e.get("mastery_score", 0),
            mastery_level=e.get("mastery_level", ""),
            ragas_faithfulness=e.get("ragas_faithfulness"),
            ragas_relevancy=e.get("ragas_relevancy"),
            ragas_context_precision=e.get("ragas_context_precision"),
            ragas_context_recall=e.get("ragas_context_recall"),
        )
        for e in evals
    ]


@router.post("/{session_id}/rerun", response_model=EvalResponse)
async def rerun_eval(session_id: str):
    return EvalResponse(
        eval_id=0,
        session_id=session_id,
        mastery_score=0,
        mastery_level="",
    )
