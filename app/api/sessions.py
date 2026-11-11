from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._disconnect import observe_http_disconnect
from app.core.database import get_db
from app.core.security import get_current_user
from app.infrastructure.storage.chat_request_store import WorkspaceConflict
from app.infrastructure.storage.session_store import SessionStore
from app.models.schemas import (
    ChatResponse,
    MessageItem,
    SessionResponse,
    SessionSummary,
)
from app.models.workspace_schemas import (
    ActiveNodePatch,
    GroupedSessions,
    MessagePage,
    RequestSnapshot,
    RetryRequest,
    SessionCreate,
    SessionSnapshot,
    ViewPatch,
    ViewState,
    WorkspaceSession,
)
from app.models.workspace_tables import TopicProfileTable
from app.orchestration.conversation_service import ConversationService
from app.orchestration.profile_service import InvalidProfileCursor, ProfileNotFound
from app.orchestration.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _operation(db, operation, write=False):
    try:
        response = await operation
        if write:
            await db.commit()
        return response
    except WorkspaceConflict as exc:
        await db.rollback()
        raise HTTPException(409, {"code": exc.code}) from exc
    except ProfileNotFound as exc:
        await db.rollback()
        raise HTTPException(404, "画像或知识点不存在") from exc
    except InvalidProfileCursor as exc:
        await db.rollback()
        raise HTTPException(422, "无效分页游标") from exc
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(403, "无权访问") from exc
    except Exception:
        await db.rollback()
        raise


@router.post("", response_model=WorkspaceSession)
async def create_session(req: SessionCreate, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    return await _operation(db, SessionService(db).create(user["user_id"], req.profile_id, req.title, req.active_node_id), True)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: Annotated[AsyncSession, Depends(get_db)], current_user: Annotated[dict, Depends(get_current_user)]):
    session = await SessionStore(db).get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.get("user_id") != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    return SessionResponse(
        session_id=session["session_id"],
        user_id=session.get("user_id"),
        state_json=session.get("state_json", "{}"),
    )


@router.get("", response_model=list[SessionSummary] | GroupedSessions)
async def list_sessions(db: Annotated[AsyncSession, Depends(get_db)], current_user: Annotated[dict, Depends(get_current_user)],
    group_by: str | None = Query(None, pattern="^profile$"),
    limit: int = Query(30, ge=1, le=100), group_limit: int = Query(30, ge=1, le=100),
    cursor: str | None = Query(None, max_length=2048), group_key: str | None = Query(None, max_length=36),
    session_cursor: str | None = Query(None, max_length=2048)):
    if group_by == "profile":
        return await _operation(db, SessionService(db).list_grouped(current_user["user_id"],
            limit, group_limit, cursor, group_key, session_cursor))
    if cursor is not None or group_key is not None or session_cursor is not None:
        raise HTTPException(422, "分页游标需要 group_by=profile")
    sessions = await SessionStore(db).list_by_user(current_user["user_id"])
    return [
        SessionSummary(
            session_id=s["session_id"],
            title=s.get("title", ""),
            updated_at=s.get("updated_at"),
        )
        for s in sessions
    ]


@router.get("/{session_id}/messages", response_model=list[MessageItem] | MessagePage)
async def get_session_messages(session_id: str, db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)], cursor: str | None = Query(None, max_length=2048),
    limit: int | None = Query(None, ge=1, le=100)):
    return await _operation(db, SessionService(db).load_messages(current_user["user_id"], session_id, cursor, limit))


@router.get("/{session_id}/snapshot", response_model=SessionSnapshot)
async def get_snapshot(session_id: str, request: Request, db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)], message_limit: int = Query(50, ge=1, le=100)):
    await _recover_requests(request, db, user["user_id"], session_id)
    service = SessionService(db)
    for attempt in range(2):
        try:
            await service._ensure_snapshot_transaction()
            row = await service._owned(user["user_id"], session_id, "write")
            service._state(row)
            if row.profile_id is None:
                profile = await db.scalar(select(TopicProfileTable).where(
                    TopicProfileTable.user_id == user["user_id"], TopicProfileTable.kind == "legacy"))
                if profile is None:
                    profile = TopicProfileTable(id=str(uuid4()), user_id=user["user_id"], name="历史待整理", kind="legacy")
                    db.add(profile)
                    await db.flush()
                row.profile_id = profile.id
                await db.flush()
            snapshot = await service.load_snapshot(user["user_id"], session_id, message_limit)
            row.workspace_entered = True
            await db.commit()
            return snapshot
        except IntegrityError as exc:
            await db.rollback()
            if attempt or not ConversationService._expected_unique(exc, 'uq_topic_profile_legacy_owner', 'topic_profiles.user_id'):
                raise
        except WorkspaceConflict as exc:
            await db.rollback()
            raise HTTPException(409, {"code": exc.code}) from exc
        except Exception:
            await db.rollback()
            raise
    raise HTTPException(409, {"code": "session_busy"})

@router.patch("/{session_id}/view-state", response_model=ViewState)
async def save_view(session_id: str, req: ViewPatch, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    changes = req.model_dump(exclude_unset=True, exclude={"expected_version"})
    return await _operation(db, SessionService(db).save_view_state(user["user_id"], session_id, req.expected_version, changes), True)


@router.patch("/{session_id}/active-node", response_model=WorkspaceSession)
async def set_node(session_id: str, req: ActiveNodePatch, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    return await _operation(db, SessionService(db).set_active_node(user["user_id"], session_id, req.expected_state_version, req.node_id), True)


@router.get("/{session_id}/requests/{request_id}", response_model=RequestSnapshot)
async def get_request(session_id: str, request_id: str, request: Request, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    await _recover_requests(request, db, user["user_id"], session_id, request_id)
    return await _operation(db, SessionService(db).get_request(user["user_id"], session_id, request_id))


@router.post("/{session_id}/requests/{request_id}/retry", response_model=ChatResponse)
async def retry_request(session_id: str, request_id: str, req: RetryRequest, request: Request,
    db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    await _operation(db, SessionService(db).prepare_retry(user["user_id"], session_id,
        request_id, req.expected_attempt, req.expected_state_version))
    service = getattr(request.app.state, "conversation_service", None)
    retry = getattr(service, "retry_turn", None)
    if not callable(retry):
        await db.rollback()
        raise HTTPException(503, {"code": "conversation_service_unavailable"})
    # 生成服务自己重新原子校验；路由不为长时间生成持有连接/锁。
    await db.rollback()
    async with observe_http_disconnect(request) as disconnected:
        return await _operation(db, retry(user_id=user["user_id"], session_id=session_id, request_id=request_id,
            expected_attempt=req.expected_attempt, expected_state_version=req.expected_state_version,
            disconnect_event=disconnected))


async def _recover_requests(request, db, user_id, session_id, request_id=None):
    from app.api.chat import conversation_service
    service = conversation_service(request)
    await db.rollback()
    await _operation(db, service.recover_session_requests(user_id, session_id, request_id))
