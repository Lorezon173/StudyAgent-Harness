from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.schemas import EvalResponse
from app.infrastructure.storage.eval_store import EvalStore
from app.infrastructure.storage.session_store import SessionStore

router = APIRouter(prefix="/eval", tags=["eval"])
_store = EvalStore()


@router.get("/{session_id}", response_model=list[EvalResponse])
async def get_evals(session_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    session = await SessionStore(db).get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.get("user_id") != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问该会话")
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
async def rerun_eval(session_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    session = await SessionStore(db).get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.get("user_id") != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    return EvalResponse(
        eval_id=0,
        session_id=session_id,
        mastery_score=0,
        mastery_level="",
    )
