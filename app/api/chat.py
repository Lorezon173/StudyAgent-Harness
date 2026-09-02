import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import ChatRequest, ChatResponse
from app.core.database import async_session
from app.core.security import get_current_user
from app.api._dirty_flag import DirtyFlag
from app.api._persist import ensure_session_writable, persist_turn
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    from app.orchestration.assembly import (
        OnlineRAGCompositionError, run_online_agent_session,
    )
    uid_int = current_user["user_id"]

    async with async_session() as auth_db:
        await ensure_session_writable(auth_db, req.session_id, uid_int)

    # ── 阶段①：加载掌握度图谱（短连接） ──
    async with async_session() as load_db:
        graph = MasteryGraph(user_id=uid_int, store=SQLAlchemyMasteryStore(load_db))
        await graph.load()
        if DirtyFlag.is_dirty(uid_int):
            DirtyFlag.clear_dirty(uid_int)

    # ── 阶段②：运行协作环（不持 DB 连接） ──
    # 在线入口 run_online_agent_session 先做 DEC-007 composition 校验：
    # 非 pgvector / 非 PostgreSQL dialect → fail-fast，分类 503，不回退 fake
    try:
        result = await asyncio.to_thread(
            run_online_agent_session, req.session_id, uid_int, req.message,
            None, graph,
        )
    except OnlineRAGCompositionError as e:
        logger.exception("online RAG composition failed for session %s",
                         req.session_id)
        raise HTTPException(status_code=503, detail={
            "error_code": e.error_code, "message": e.safe_summary})

    # ── 阶段③：持久化（新短连接 → rebind store） ──
    persisted = False
    turn_count = None
    try:
        async with async_session() as persist_db:
            graph._store = SQLAlchemyMasteryStore(persist_db)
            turn_index = await persist_turn(
                persist_db, session_id=req.session_id, user_id=current_user["user_id"],
                user_message=req.message, reply=result.reply, graph=graph,
            )
        turn_count = (turn_index + 1) if turn_index is not None else None
        persisted = turn_index is not None
    except HTTPException:
        raise
    except Exception:
        logger.exception("persist stage failed for session %s", req.session_id)

    return ChatResponse(
        reply=result.reply,
        session_id=req.session_id,
        mastery_score=result.mastery_score,
        turn_count=turn_count,
        mode_path=result.mode_path,
        cost_est_usd=result.cost_est_usd,
        stack="new",
        persisted=persisted,
    )
