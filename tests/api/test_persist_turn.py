import app.models.tables  # noqa: F401 — 确保 create_all 前表模型已注册到 Base.metadata


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
                graph = MasteryGraph(user_id="1", store=SQLAlchemyMasteryStore(db))
                graph.add_node("二分查找", "二分查找", mastery=70.0)
                await persist_turn(db, session_id="s2", user_id=1,
                                   user_message="二分", reply="r", graph=graph)
                # 重新载入验证落库
                graph2 = MasteryGraph(user_id="1", store=SQLAlchemyMasteryStore(db))
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

    with patch("app.api._persist.MessageStore") as mock_store, \
         patch("app.api._persist.SessionStore") as mock_session, \
         patch("app.api._persist.DirtyFlag") as mock_dirty, \
         patch("app.api._persist.get_observability"):
        # 设置 MessageStore 实例的方法
        mock_store.return_value.list_by_session = AsyncMock(return_value=[{"role": "user"}, {"role": "assistant"}])
        mock_store.return_value.add = AsyncMock()

        # 设置 SessionStore 实例的方法
        mock_session.return_value.save = AsyncMock()

        result = await persist_turn(db, "sess1", 1, "user msg", "reply", graph)

        assert result == 1  # len([user, assistant]) // 2 = 1
        db.commit.assert_called_once()
        graph.save.assert_called_once()
        mock_dirty.clear_dirty.assert_called_once_with("1")


@pytest.mark.asyncio
async def test_persist_integrity_error_returns_none_no_clear():
    """IntegrityError（唯一约束冲突）返回 None，不清 dirty"""
    db = AsyncMock()
    db.commit.side_effect = IntegrityError("", "", "")

    with patch("app.api._persist.MessageStore"), \
         patch("app.api._persist.SessionStore"), \
         patch("app.api._persist.DirtyFlag") as mock_dirty:
        result = await persist_turn(db, "sess1", 1, "msg", "reply", None)

        assert result is None
        db.rollback.assert_called_once()
        mock_dirty.clear_dirty.assert_not_called()


@pytest.mark.asyncio
async def test_persist_uses_log_not_log_event():
    """修复 log_event bug，改用 log()"""
    db = AsyncMock()
    db.commit.side_effect = Exception("DB error")

    with patch("app.api._persist.get_observability") as mock_obs, \
         patch("app.api._persist.MessageStore"), \
         patch("app.api._persist.SessionStore"):
        await persist_turn(db, "sess1", 1, "msg", "reply", None)

        # 验证调用 log() 而非 log_event()
        mock_obs.return_value.log.assert_called_once()
        args = mock_obs.return_value.log.call_args[0]
        assert args[0] == "error"
        assert args[1] == "persist_failure"  # 修复：实际事件名是 persist_failure


@pytest.mark.asyncio
async def test_persist_operational_error_returns_none_and_logs():
    """OperationalError（连接丢失/锁超时）返回 None，标记 reason=db_layer_error"""
    db = AsyncMock()
    db.commit.side_effect = OperationalError("", "", Exception("connection lost"))

    with patch("app.api._persist.MessageStore") as mock_store, \
         patch("app.api._persist.SessionStore") as mock_session, \
         patch("app.api._persist.get_observability") as mock_obs, \
         patch("app.api._persist.DirtyFlag") as mock_dirty:
        # MessageStore/SessionStore 需要 AsyncMock 才能 await
        mock_store.return_value.list_by_session = AsyncMock(return_value=[])
        mock_store.return_value.add = AsyncMock()
        mock_session.return_value.save = AsyncMock()

        result = await persist_turn(db, "sess1", 1, "msg", "reply", None)

        assert result is None
        db.rollback.assert_called_once()
        mock_dirty.clear_dirty.assert_not_called()
        # 验证观测性日志 reason 为 db_layer_error
        mock_obs.return_value.log.assert_called_once()
        args = mock_obs.return_value.log.call_args[0]
        assert args[0] == "error"
        assert args[1] == "persist_failure"
        assert args[2]["reason"] == "db_layer_error"
