from dataclasses import dataclass
from types import SimpleNamespace
from sqlalchemy import select
from app.models.tables import SessionTable, MessageTable
from app.models.workspace_tables import TopicProfileTable, ProfileNodeTable
from app.models.schemas import ChatResponse
from app.harness.teaching_context import parse_teaching_state, valid_score
from app.infrastructure.storage.chat_request_store import ChatRequestStore, WorkspaceConflict
from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore
import logging
import json
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, OperationalError, DatabaseError

from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.message_store import MessageStore
from app.infrastructure.storage.dirty_flag import DirtyFlag
from app.harness.observability import get_observability

logger = logging.getLogger(__name__)


async def _session_for_write(db, session_id, user_id):
    existing = await SessionStore(db).get(session_id)
    if existing is not None and (existing.get("user_id") is None or user_id is None or existing.get("user_id") != user_id):
        raise HTTPException(403, "无权写入该会话")
    return existing


async def ensure_session_writable(db: AsyncSession, session_id: str, user_id: int | None) -> None:
    await _session_for_write(db, session_id, user_id)


def mark_user_dirty(user_id: int | None, *, profile_id: str | None = None) -> None:
    """在持久化失败后标记用户，令下次请求从 DB 重建图谱。"""
    if user_id is not None:
        DirtyFlag.mark_dirty(user_id) if profile_id is None else DirtyFlag.mark_dirty(user_id, profile_id=profile_id)


async def persist_legacy_turn(db: AsyncSession, session_id: str, user_id: int | None,
                       user_message: str, reply: str, graph=None) -> int | None:
    """原子落库一轮：session(upsert) + user/assistant 两条消息 (+ 可选 graph.save()).

    返回算出的 turn_index（供 API 回填 turn_count=turn_index+1）；失败 rollback 返回 None.
    成功一次 commit（C3）。
    """
    try:
        # S1 IDOR 防护：若会话已存在且归属其他用户，拒绝写入
        existing_session = await _session_for_write(db, session_id, user_id)
        if not _legacy_allowed(existing_session):
            return None
        session_store = SessionStore(db)

        existing = await MessageStore(db).list_by_session(session_id)
        turn_index = len(existing) // 2

        title = None
        if len(existing) == 0:
            title = user_message.strip()[:24] if user_message.strip() else "新会话"

        await session_store.save(session_id, state={}, user_id=user_id, title=title)
        await db.flush()
        try:
            await MessageStore(db).add(session_id, "user", user_message, turn_index)
            await MessageStore(db).add(session_id, "assistant", reply, turn_index)
            if graph is not None:
                await graph.save()
            await db.commit()
        except IntegrityError:
            # M1 竞态降级：并发请求可能算出相同 turn_index，重新查询并重试一次
            await db.rollback()
            existing_session = await _session_for_write(db, session_id, user_id)
            if not _legacy_allowed(existing_session):
                return None
            session_store = SessionStore(db)
            existing = await MessageStore(db).list_by_session(session_id)
            turn_index = len(existing) // 2
            title = None
            if len(existing) == 0:
                title = user_message.strip()[:24] if user_message.strip() else "新会话"
            await session_store.save(session_id, state={}, user_id=user_id, title=title)
            await db.flush()
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


def _legacy_allowed(row):
    if row is None:
        return True
    try:
        state = json.loads(row.get("state_json", "{}"))
        return row.get("profile_id") is None and isinstance(state, dict) and "schema_version" not in state
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class CommitResult:
    turn_index: int
    state_version: int
    profile_revision: int
    request_id: str
    response: ChatResponse


async def commit_turn(db, *, user_id, session_id, request_id, attempt, base_state_version,
                      result, context_reduced=None, reduction_reasons=None, now=None):
    """唯一workspace业务提交核心；只flush，外层执行一次commit。"""
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
    if row.active_node_id is not None and await db.scalar(select(ProfileNodeTable.id).where(
            ProfileNodeTable.id == row.active_node_id, ProfileNodeTable.profile_id == row.profile_id,
            ProfileNodeTable.archived.is_(False))) is None:
        raise WorkspaceConflict('graph_context_mismatch')
    old_data = json.loads(row.state_json)
    session = SimpleNamespace(session_id=session_id, active_node_id=row.active_node_id)
    old_snapshot = SimpleNamespace(session=session,
        teaching_state=old_data if 'schema_version' in old_data else None, legacy_state=old_data)
    messages = list((await db.scalars(select(MessageTable).where(MessageTable.session_id == session_id))).all())
    previous = parse_teaching_state(old_snapshot, messages)
    candidate = parse_teaching_state(SimpleNamespace(session=session, teaching_state=result.teaching_state), messages)
    if candidate.active_node_id != row.active_node_id or candidate.committed_turn_count != previous.committed_turn_count + 1:
        raise WorkspaceConflict('invalid_teaching_state')
    ordered = sorted(messages, key=lambda m: (m.turn_index, {'user':0,'assistant':1}.get(m.role,2),m.id))
    question = next((m for m in reversed(ordered) if m.role == 'assistant'), None)
    deltas = list(result.assessment_deltas)
    for delta in deltas:
        if (delta.node_id != row.active_node_id or not valid_score(delta.score)
                or not isinstance(delta.rationale, str) or not isinstance(delta.source_event_id,str) or not delta.source_event_id
                or 'schema_version' not in old_data or previous.stage != 'awaiting_response'
                or question is None or previous.last_question != question.content
                or delta.question_message_id != question.id):
            raise WorkspaceConflict('invalid_assessment_delta')
    await db.flush()
    turn_index = row.next_turn_index
    user_message = MessageTable(session_id=session_id, role='user', content=request.request_payload['message'], turn_index=turn_index)
    db.add(user_message)
    await db.flush()
    db.add(MessageTable(session_id=session_id, role='assistant', content=result.reply, turn_index=turn_index))
    await db.flush()
    if any(delta.answer_message_id is not None and delta.answer_message_id != user_message.id for delta in deltas):
        raise WorkspaceConflict('invalid_assessment_delta')
    revision = await ProfileMasteryStore(db, row.profile_id).apply_assessment_delta(
        user_id, session_id, request_id, user_message.id, deltas)
    row.state_json = json.dumps(candidate.to_dict(), ensure_ascii=False, allow_nan=False)
    row.state_version += 1
    row.next_turn_index += 1
    response = ChatResponse(reply=result.reply, session_id=session_id, request_id=request_id, status='completed',
        attempt=attempt, state_version=row.state_version, profile_revision=revision, active_node_id=row.active_node_id,
        mastery_score=deltas[-1].score if deltas else None, turn_count=candidate.committed_turn_count,
        mode_path=result.mode_path, cost_est_usd=result.cost_est_usd, stack='new', persisted=True,
        context_reduced=context_reduced, reduction_reasons=list(reduction_reasons) if reduction_reasons is not None else None)
    await store.complete(user_id, session_id, request_id, attempt, response.model_dump(mode='json'), now=now)
    await db.flush()
    return CommitResult(turn_index, row.state_version, revision, request_id, response)
