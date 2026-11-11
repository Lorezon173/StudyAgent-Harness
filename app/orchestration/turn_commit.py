from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select

from app.infrastructure.storage.chat_request_store import (
    ChatRequestStore,
    WorkspaceConflict,
)
from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
from app.models.schemas import ChatResponse
from app.models.tables import MessageTable, SessionTable
from app.models.workspace_tables import TopicProfileTable


@dataclass(frozen=True)
class CommitResult:
    turn_index: int
    state_version: int
    profile_revision: int
    request_id: str
    response: ChatResponse


async def commit_turn(db, *, user_id, session_id, request_id, attempt, base_state_version,
                      result, graph, context_reduced=None, reduction_reasons=None, now=None):
    row = await db.scalar(select(SessionTable).where(SessionTable.id == session_id)
        .with_for_update().execution_options(populate_existing=True))
    if row is None or row.user_id is None or row.user_id != user_id:
        raise HTTPException(403, '无权写入该会话')
    store = ChatRequestStore(db)
    _, request = await store.validate_running(user_id, session_id, request_id, attempt, now=now)
    if (row.state_version != base_state_version or request.base_state_version != base_state_version
            or request.profile_id != row.profile_id or request.active_node_id != row.active_node_id):
        raise WorkspaceConflict('stale_context')
    profile = await db.scalar(select(TopicProfileTable).where(TopicProfileTable.id == row.profile_id,
        TopicProfileTable.user_id == user_id).with_for_update().execution_options(populate_existing=True))
    if profile is None:
        raise WorkspaceConflict('profile_context_mismatch')
    turn_index = row.next_turn_index
    db.add_all([MessageTable(session_id=session_id, role='user', content=request.request_payload['message'], turn_index=turn_index),
        MessageTable(session_id=session_id, role='assistant', content=result.reply, turn_index=turn_index)])
    graph._store = SQLAlchemyMasteryStore(db)
    await graph.save()
    row.state_version += 1
    row.next_turn_index += 1
    response = ChatResponse(reply=result.reply, session_id=session_id, request_id=request_id, status='completed',
        attempt=attempt, state_version=row.state_version, profile_revision=profile.revision,
        active_node_id=row.active_node_id, mastery_score=result.mastery_score, turn_count=turn_index + 1,
        mode_path=result.mode_path, cost_est_usd=result.cost_est_usd, stack='new', persisted=True)
    await store.complete(user_id, session_id, request_id, attempt, response.model_dump(mode='json'), now=now)
    await db.flush()
    return CommitResult(turn_index, row.state_version, profile.revision, request_id, response)
