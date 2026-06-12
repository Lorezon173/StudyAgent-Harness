from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.message_store import MessageStore


async def persist_turn(db: AsyncSession, session_id: str, user_id, user_message: str,
                       reply: str, graph=None) -> int | None:
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
        return turn_index
    except Exception as e:
        await db.rollback()
        try:
            from app.harness.observability import get_observability
            get_observability().log_event("persist_error",
                                           {"session_id": session_id, "error": str(e)})
        except Exception:
            pass
        return None
