import app.models.tables  # noqa: F401 — 确保 create_all 前表模型已注册到 Base.metadata


async def _foreign_key_database(db_fixture):
    from sqlalchemy import event
    from app.models.tables import UserTable

    engine, factory = await db_fixture.setup_db()
    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    await engine.dispose()
    async with factory() as db:
        db.add(UserTable(id=1, username="persist-fk-test", password_hash="unused"))
        await db.commit()
    return engine, factory


def test_new_session_and_integrity_retry_flush_parent_before_messages(db_fixture):
    async def run():
        from sqlalchemy import event, text
        from sqlalchemy.exc import IntegrityError
        from app.api._persist import persist_turn

        engine, factory = await _foreign_key_database(db_fixture)
        commits = []
        attempts = []
        try:
            @event.listens_for(engine.sync_engine, "before_cursor_execute")
            def check_parent(connection, cursor, statement, parameters, context, executemany):
                if statement.startswith("INSERT INTO messages"):
                    assert connection.scalar(text("SELECT COUNT(*) FROM sessions WHERE id='fk-new'")) == 1
                    attempts.append(statement)
                    if len(attempts) == 1:
                        raise IntegrityError(statement, parameters, Exception("controlled first conflict"))
            @event.listens_for(engine.sync_engine, "commit")
            def committed(connection):
                commits.append(True)
            async with factory() as db:
                result = await persist_turn(db, "fk-new", 1, "问题", "回答")
            async with factory() as db:
                assert await db.scalar(text("SELECT COUNT(*) FROM messages WHERE session_id='fk-new'")) == 2
            assert result == 0
            assert len(attempts) == 3
            assert len(commits) == 1
        finally:
            await engine.dispose()
    db_fixture.run(run())


def test_failure_after_flushed_messages_rolls_back_parent_and_children(db_fixture):
    async def run():
        from sqlalchemy import text
        from app.api._persist import persist_turn

        engine, factory = await _foreign_key_database(db_fixture)
        graph_reached = []
        try:
            async with factory() as db:
                class FailingGraph:
                    async def save(self):
                        await db.flush()
                        assert await db.scalar(text("SELECT COUNT(*) FROM messages")) == 2
                        graph_reached.append(True)
                        raise RuntimeError("controlled graph failure")
                assert await persist_turn(db, "fk-rollback", 1, "问题", "回答", FailingGraph()) is None
            assert graph_reached == [True]
            async with factory() as db:
                assert await db.scalar(text("SELECT COUNT(*) FROM sessions")) == 0
                assert await db.scalar(text("SELECT COUNT(*) FROM messages")) == 0
        finally:
            await engine.dispose()
    db_fixture.run(run())


def test_persist_turn_writes_session_messages_and_returns_turn_index(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api._persist import persist_turn
            from app.infrastructure.storage.message_store import MessageStore
            async with session_factory() as db:
                ti = await persist_turn(db, session_id="s1", user_id=1,
                                        user_message="你好", reply="回应", graph=None)
                msgs = await MessageStore(db).list_by_session("s1")
            assert ti == 0  # 首轮 turn_index
            assert len(msgs) == 2
            assert msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant"
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_persist_turn_saves_graph(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api._persist import persist_turn
            from app.harness.mastery_graph import MasteryGraph
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                graph = MasteryGraph(user_id=1, store=SQLAlchemyMasteryStore(db))
                graph.add_node("二分查找", "二分查找", mastery=70.0)
                await persist_turn(db, session_id="s2", user_id=1,
                                   user_message="二分", reply="r", graph=graph)
                # 重新载入验证落库
                graph2 = MasteryGraph(user_id=1, store=SQLAlchemyMasteryStore(db))
                await graph2.load()
            assert graph2.get_node("二分查找").mastery == 70.0
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_persist_turn_rolls_back_and_returns_none_on_error(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api._persist import persist_turn

            class BoomGraph:
                async def save(self):
                    raise RuntimeError("boom")
            async with session_factory() as db:
                ti = await persist_turn(db, session_id="s3", user_id=1,
                                        user_message="x", reply="y", graph=BoomGraph())
                from app.infrastructure.storage.message_store import MessageStore
                msgs = await MessageStore(db).list_by_session("s3")
            assert ti is None          # 失败返回 None
            assert len(msgs) == 0      # 整体回滚，不半落库
        finally:
            await engine.dispose()
    db_fixture.run(_test())


# ===== 批次一新增测试 =====

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError, OperationalError
from app.api._persist import persist_turn


@pytest.mark.asyncio
async def test_persist_success_returns_turn_index_and_clears_dirty():
    """persist 成功返回 turn_index，清除 dirty-flag"""
    db = AsyncMock()
    graph = MagicMock()
    graph.save = AsyncMock()  # 必须是 AsyncMock 才能 await

    with patch("app.orchestration.turn_commit.MessageStore") as mock_store, \
         patch("app.orchestration.turn_commit.SessionStore") as mock_session, \
         patch("app.orchestration.turn_commit.DirtyFlag") as mock_dirty, \
         patch("app.orchestration.turn_commit.get_observability"):
        # 设置 MessageStore 实例的方法
        mock_store.return_value.list_by_session = AsyncMock(return_value=[{"role": "user"}, {"role": "assistant"}])
        mock_store.return_value.add = AsyncMock()

        # 设置 SessionStore 实例的方法
        mock_session.return_value.get = AsyncMock(return_value=None)
        mock_session.return_value.save = AsyncMock()

        result = await persist_turn(db, "sess1", 1, "user msg", "reply", graph)

        assert result == 1  # len([user, assistant]) // 2 = 1
        db.commit.assert_called_once()
        graph.save.assert_called_once()
        mock_dirty.clear_dirty.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_persist_integrity_error_returns_none_no_clear():
    """IntegrityError（唯一约束冲突）返回 None，不清 dirty"""
    db = AsyncMock()
    db.commit.side_effect = IntegrityError("", "", "")

    with patch("app.orchestration.turn_commit.MessageStore"), \
         patch("app.orchestration.turn_commit.SessionStore"), \
         patch("app.orchestration.turn_commit.DirtyFlag") as mock_dirty:
        result = await persist_turn(db, "sess1", 1, "msg", "reply", None)

        assert result is None
        db.rollback.assert_called_once()
        mock_dirty.clear_dirty.assert_not_called()
        mock_dirty.mark_dirty.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_persist_uses_log_not_log_event():
    """修复 log_event bug，改用 log()"""
    db = AsyncMock()
    db.commit.side_effect = Exception("DB error")

    with patch("app.orchestration.turn_commit.get_observability") as mock_obs, \
         patch("app.orchestration.turn_commit.MessageStore"), \
         patch("app.orchestration.turn_commit.SessionStore"), \
         patch("app.orchestration.turn_commit.DirtyFlag") as mock_dirty:
        await persist_turn(db, "sess1", 1, "msg", "reply", None)

        # 验证调用 log() 而非 log_event()
        mock_obs.return_value.log.assert_called_once()
        args = mock_obs.return_value.log.call_args[0]
        assert args[0] == "error"
        assert args[1] == "persist_failure"  # 修复：实际事件名是 persist_failure
        mock_dirty.mark_dirty.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_persist_operational_error_returns_none_and_logs():
    """OperationalError（连接丢失/锁超时）返回 None，标记 reason=db_layer_error"""
    db = AsyncMock()
    db.commit.side_effect = OperationalError("", "", Exception("connection lost"))

    with patch("app.orchestration.turn_commit.MessageStore") as mock_store, \
         patch("app.orchestration.turn_commit.SessionStore") as mock_session, \
         patch("app.orchestration.turn_commit.get_observability") as mock_obs, \
         patch("app.orchestration.turn_commit.DirtyFlag") as mock_dirty:
        # MessageStore/SessionStore 需要 AsyncMock 才能 await
        mock_store.return_value.list_by_session = AsyncMock(return_value=[])
        mock_store.return_value.add = AsyncMock()
        mock_session.return_value.get = AsyncMock(return_value=None)
        mock_session.return_value.save = AsyncMock()

        result = await persist_turn(db, "sess1", 1, "msg", "reply", None)

        assert result is None
        db.rollback.assert_called_once()
        mock_dirty.clear_dirty.assert_not_called()
        mock_dirty.mark_dirty.assert_called_once_with(1)
        # 验证观测性日志 reason 为 db_layer_error
        mock_obs.return_value.log.assert_called_once()
        args = mock_obs.return_value.log.call_args[0]
        assert args[0] == "error"
        assert args[1] == "persist_failure"
        assert args[2]["reason"] == "db_layer_error"


@pytest.mark.asyncio
async def test_persist_retry_rechecks_owner_before_writing_messages():
    """A conflicting retry must not write messages after ownership changes."""
    db = AsyncMock()
    db.commit.side_effect = [IntegrityError("", "", ""), None]

    with patch("app.orchestration.turn_commit.MessageStore") as mock_messages, \
         patch("app.orchestration.turn_commit.SessionStore") as mock_sessions, \
         patch("app.orchestration.turn_commit.get_observability"), \
         patch("app.orchestration.turn_commit.DirtyFlag"):
        mock_sessions.return_value.get = AsyncMock(
            side_effect=[None, {"session_id": "sess1", "user_id": 2}]
        )
        mock_sessions.return_value.save = AsyncMock()
        mock_messages.return_value.list_by_session = AsyncMock(return_value=[])
        mock_messages.return_value.add = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await persist_turn(db, "sess1", 1, "msg", "reply", None)

        assert getattr(exc_info.value, "status_code", None) == 403
        assert mock_messages.return_value.add.await_count == 2
        assert db.rollback.await_count == 1
