from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import SessionResponse, SessionSummary, MessageItem
from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.message_store import MessageStore

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await SessionStore(db).get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionResponse(
        session_id=session["session_id"],
        user_id=session.get("user_id"),
        state_json=session.get("state_json", "{}"),
    )


@router.get("", response_model=list[SessionSummary])
async def list_sessions(user_id: int | None = None, db: AsyncSession = Depends(get_db)):
    if user_id is None:
        return []
    sessions = await SessionStore(db).list_by_user(user_id)
    return [
        SessionSummary(
            session_id=s["session_id"],
            title=s.get("title", ""),
            updated_at=s.get("updated_at"),
        )
        for s in sessions
    ]


@router.get("/{session_id}/messages", response_model=list[MessageItem])
async def get_session_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    messages = await MessageStore(db).list_by_session(session_id)
    return [
        MessageItem(
            role=m["role"],
            content=m["content"],
            created_at=m.get("created_at"),
        )
        for m in messages
    ]
