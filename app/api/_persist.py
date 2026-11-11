import json
import logging

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._dirty_flag import DirtyFlag
from app.harness.observability import get_observability
from app.infrastructure.storage.message_store import MessageStore
from app.models.tables import SessionTable

logger = logging.getLogger(__name__)


async def ensure_session_writable(db: AsyncSession, session_id: str,
                                  user_id: int | None) -> None:
    """严格 Direction A：既有会话仅原 owner 可写，NULL owner 不可 claim。"""
    row = await db.scalar(select(SessionTable).where(SessionTable.id == session_id)
        .with_for_update().execution_options(populate_existing=True))
    if row is None:
        return None
    if row.user_id is None or user_id is None or row.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权写入该会话")
    try:
        state = json.loads(row.state_json)
    except (TypeError, ValueError):
        state = None
    if row.workspace_entered or row.active_request_id is not None or not isinstance(state, dict) or 'schema_version' in state:
        raise HTTPException(status_code=409, detail={"code": "workspace_session"})
    result = await db.execute(update(SessionTable).where(SessionTable.id == session_id,
        SessionTable.user_id == user_id, SessionTable.workspace_entered.is_(False),
        SessionTable.active_request_id.is_(None)).values(state_version=SessionTable.state_version))
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail={"code": "workspace_session"})
    return row


def mark_user_dirty(user_id: int | None) -> None:
    """在持久化失败后标记用户，令下次请求从 DB 重建图谱。"""
    if user_id is not None:
        DirtyFlag.mark_dirty(user_id)


async def persist_turn(db: AsyncSession, session_id: str, user_id: int | None,
                       user_message: str, reply: str, graph=None) -> int | None:
    """原子落库一轮：session(upsert) + user/assistant 两条消息 (+ 可选 graph.save()).

    返回算出的 turn_index（供 API 回填 turn_count=turn_index+1）；失败 rollback 返回 None.
    成功一次 commit（C3）。
    """
    try:
        for attempt in range(2):
            try:
                row = await ensure_session_writable(db, session_id, user_id)
                existing = await MessageStore(db).list_by_session(session_id)
                message_next = max((item["turn_index"] for item in existing), default=-1) + 1
                turn_index = max(row.next_turn_index or 0, message_next) if row is not None else message_next
                if row is None:
                    title = user_message.strip()[:24] if user_message.strip() else "新会话"
                    row = SessionTable(id=session_id, user_id=user_id, state_json="{}", title=title)
                    db.add(row)
                    await db.flush()
                else:
                    row.state_json = "{}"
                    row.updated_at = func.now()
                await MessageStore(db).add(session_id, "user", user_message, turn_index)
                await MessageStore(db).add(session_id, "assistant", reply, turn_index)
                if graph is not None:
                    await graph.save()
                row.next_turn_index = turn_index + 1
                await db.commit()
                break
            except IntegrityError:
                await db.rollback()
                if attempt:
                    mark_user_dirty(user_id)
                    return None

        # 成功时清除 dirty-flag
        if user_id is not None:
            DirtyFlag.clear_dirty(user_id)

        # 观测性：persist 成功
        try:
            get_observability().log("info", "persist_success", {"session_id": session_id})
        except Exception as obs_err:
            logger.warning(f"Failed to log persist_success: {obs_err}")

        return turn_index
    except HTTPException:
        # S1 IDOR 拒绝 —— 不吞异常，直接向上抛
        raise
    except IntegrityError as e:
        await db.rollback()
        try:
            get_observability().log("error", "persist_failure", {
                "session_id": session_id,
                "reason": "integrity_conflict",
                "error": str(e)
            })
        except Exception as obs_err:
            logger.warning(f"Failed to log persist_failure: {obs_err}")
        mark_user_dirty(user_id)
        return None
    except (OperationalError, DatabaseError) as e:
        # DB 层异常（连接丢失、锁超时等）—— 显式捕获并记录
        await db.rollback()
        logger.exception(f"DB layer error during persist for session {session_id}")
        try:
            get_observability().log("error", "persist_failure", {
                "session_id": session_id,
                "reason": "db_layer_error",
                "error": str(e)
            })
        except Exception as obs_err:
            logger.warning(f"Failed to log persist_failure: {obs_err}")
        mark_user_dirty(user_id)
        return None
    except Exception as e:
        # 最后兜底：编程错误（AttributeError、TypeError 等）—— 仍记录但标记为 programming_error
        await db.rollback()
        logger.exception(f"Programming error during persist for session {session_id}")
        try:
            get_observability().log("error", "persist_failure", {
                "session_id": session_id,
                "reason": "programming_error",
                "error": str(e)
            })
        except Exception as obs_err:
            logger.warning(f"Failed to log persist_failure: {obs_err}")
        mark_user_dirty(user_id)
        return None
