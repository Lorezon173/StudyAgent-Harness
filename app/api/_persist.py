import logging
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, OperationalError, DatabaseError

from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.message_store import MessageStore
from app.api._dirty_flag import DirtyFlag
from app.harness.observability import get_observability

logger = logging.getLogger(__name__)


async def ensure_session_writable(db: AsyncSession, session_id: str,
                                  user_id: int | None) -> None:
    """严格 Direction A：既有会话仅原 owner 可写，NULL owner 不可 claim。"""
    existing_session = await SessionStore(db).get(session_id)
    if existing_session is None:
        return

    existing_owner = existing_session.get("user_id")
    if existing_owner is None or user_id is None or existing_owner != user_id:
        raise HTTPException(status_code=403, detail="无权写入该会话")


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
        # S1 IDOR 防护：若会话已存在且归属其他用户，拒绝写入
        await ensure_session_writable(db, session_id, user_id)
        session_store = SessionStore(db)

        existing = await MessageStore(db).list_by_session(session_id)
        turn_index = len(existing) // 2

        title = None
        if len(existing) == 0:
            title = user_message.strip()[:24] if user_message.strip() else "新会话"

        await session_store.save(session_id, state={}, user_id=user_id, title=title)
        try:
            await MessageStore(db).add(session_id, "user", user_message, turn_index)
            await MessageStore(db).add(session_id, "assistant", reply, turn_index)
            if graph is not None:
                await graph.save()
            await db.commit()
        except IntegrityError:
            # M1 竞态降级：并发请求可能算出相同 turn_index，重新查询并重试一次
            await db.rollback()
            await ensure_session_writable(db, session_id, user_id)
            session_store = SessionStore(db)
            existing = await MessageStore(db).list_by_session(session_id)
            turn_index = len(existing) // 2
            title = None
            if len(existing) == 0:
                title = user_message.strip()[:24] if user_message.strip() else "新会话"
            await session_store.save(session_id, state={}, user_id=user_id, title=title)
            try:
                await MessageStore(db).add(session_id, "user", user_message, turn_index)
                await MessageStore(db).add(session_id, "assistant", reply, turn_index)
                if graph is not None:
                    await graph.save()
                await db.commit()
            except IntegrityError as e:
                await db.rollback()
                try:
                    get_observability().log("error", "persist_failure", {
                        "session_id": session_id,
                        "reason": "integrity_conflict_retry_exhausted",
                        "error": str(e)
                    })
                except Exception as obs_err:
                    logger.warning(f"Failed to log persist_failure: {obs_err}")
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
