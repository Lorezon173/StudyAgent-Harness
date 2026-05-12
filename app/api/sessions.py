from fastapi import APIRouter

from app.models.schemas import SessionResponse
from app.infrastructure.storage.session_store import SessionStore

router = APIRouter(prefix="/sessions", tags=["sessions"])
_store = SessionStore()


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    session = await _store.get(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionResponse(
        session_id=session["session_id"],
        user_id=session.get("user_id"),
        state_json=session.get("state_json", "{}"),
    )


@router.get("", response_model=list[SessionResponse])
async def list_sessions(user_id: int | None = None):
    if user_id:
        sessions = await _store.list_by_user(user_id)
    else:
        sessions = []
    return [
        SessionResponse(session_id=s["session_id"], user_id=s.get("user_id"), state_json=s.get("state_json", "{}"))
        for s in sessions
    ]
