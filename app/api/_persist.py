"""保留旧公开签名；持久化实现单向委托编排层。"""
from app.orchestration import turn_commit


async def ensure_session_writable(db, session_id, user_id):
    return await turn_commit.ensure_session_writable(db, session_id, user_id)


def mark_user_dirty(user_id):
    return turn_commit.mark_user_dirty(user_id)


async def persist_turn(db, session_id, user_id, user_message, reply, graph=None):
    return await turn_commit.persist_legacy_turn(db, session_id, user_id, user_message, reply, graph)
