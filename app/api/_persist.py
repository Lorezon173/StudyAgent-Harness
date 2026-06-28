import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, OperationalError, DatabaseError

from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.message_store import MessageStore
from app.api._dirty_flag import DirtyFlag
from app.harness.observability import get_observability

logger = logging.getLogger(__name__)


async def persist_turn(db: AsyncSession, session_id: str, user_id: int | None,
                       user_message: str, reply: str, graph=None) -> int | None:
    """原子落库一轮：session(upsert) + user/assistant 两条消息 (+ 可选 graph.save()).

    返回算出的 turn_index（供 API 回填 turn_count=turn_index+1）；失败 rollback 返回 None.
    成功一次 commit（C3）。
    """
    try:
        existing = await MessageStore(db).list_by_session(session_id)
        turn_index = len(existing) // 2

        title = None
        if len(existing) == 0:
            title = user_message.strip()[:24] if user_message.strip() else "新会话"

        await SessionStore(db).save(session_id, state={}, user_id=user_id, title=title)
        await MessageStore(db).add(session_id, "user", user_message, turn_index)
        await MessageStore(db).add(session_id, "assistant", reply, turn_index)
        if graph is not None:
            await graph.save()
        await db.commit()

        # 成功时清除 dirty-flag
        if user_id is not None:
            DirtyFlag.clear_dirty(str(user_id))

        # 观测性：persist 成功
        try:
            get_observability().log("info", "persist_success", {"session_id": session_id})
        except Exception as obs_err:
            logger.warning(f"Failed to log persist_success: {obs_err}")

        return turn_index
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
        return None
