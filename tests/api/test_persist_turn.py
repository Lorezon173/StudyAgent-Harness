from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

import app.models.tables  # noqa: F401 — 确保 create_all 前表模型已注册到 Base.metadata
from app.api._persist import persist_turn


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
            from app.infrastructure.storage.sqlalchemy_mastery_store import (
                SQLAlchemyMasteryStore,
            )
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





@pytest.mark.asyncio
async def test_persist_success_returns_turn_index_and_clears_dirty():
    db = AsyncMock()
    row = MagicMock(next_turn_index=1)
    graph = MagicMock(save=AsyncMock())
    with patch("app.api._persist.ensure_session_writable", AsyncMock(return_value=row)), \
         patch("app.api._persist.MessageStore") as messages, \
         patch("app.api._persist.DirtyFlag") as dirty, \
         patch("app.api._persist.get_observability"):
        messages.return_value.list_by_session = AsyncMock(return_value=[])
        messages.return_value.add = AsyncMock()
        assert await persist_turn(db, "s", 1, "message", "reply", graph) == 1
        db.commit.assert_awaited_once()
        graph.save.assert_awaited_once()
        dirty.clear_dirty.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_persist_integrity_error_returns_none_no_clear():
    db = AsyncMock()
    db.commit.side_effect = IntegrityError("", "", "")
    with patch("app.api._persist.ensure_session_writable", AsyncMock(return_value=MagicMock(next_turn_index=0))), \
         patch("app.api._persist.MessageStore") as messages, \
         patch("app.api._persist.DirtyFlag") as dirty:
        messages.return_value.list_by_session = AsyncMock(return_value=[])
        messages.return_value.add = AsyncMock()
        assert await persist_turn(db, "s", 1, "message", "reply") is None
        assert db.rollback.await_count == 2
        dirty.clear_dirty.assert_not_called()
        dirty.mark_dirty.assert_called_once_with(1)


@pytest.mark.asyncio
@pytest.mark.parametrize("error,reason", [(RuntimeError("failure"), "programming_error"),
                                          (OperationalError("", "", Exception("lost")), "db_layer_error")])
async def test_persist_errors_log_and_mark_dirty(error, reason):
    db = AsyncMock()
    db.commit.side_effect = error
    with patch("app.api._persist.ensure_session_writable", AsyncMock(return_value=MagicMock(next_turn_index=0))), \
         patch("app.api._persist.MessageStore") as messages, \
         patch("app.api._persist.get_observability") as observer, \
         patch("app.api._persist.DirtyFlag") as dirty:
        messages.return_value.list_by_session = AsyncMock(return_value=[])
        messages.return_value.add = AsyncMock()
        assert await persist_turn(db, "s", 1, "message", "reply") is None
        db.rollback.assert_awaited_once()
        dirty.mark_dirty.assert_called_once_with(1)
        args = observer.return_value.log.call_args[0]
        assert args[0:2] == ("error", "persist_failure") and args[2]["reason"] == reason


@pytest.mark.asyncio
async def test_persist_retry_rechecks_owner_before_writing_messages():
    from fastapi import HTTPException
    db = AsyncMock()
    db.add = MagicMock()
    db.flush.side_effect = IntegrityError("", "", "")
    guard = AsyncMock(side_effect=[None, HTTPException(403, "forbidden")])
    with patch("app.api._persist.ensure_session_writable", guard), \
         patch("app.api._persist.MessageStore") as messages:
        messages.return_value.list_by_session = AsyncMock(return_value=[])
        messages.return_value.add = AsyncMock()
        with pytest.raises(HTTPException) as error:
            await persist_turn(db, "s", 1, "message", "reply")
        assert error.value.status_code == 403
        messages.return_value.add.assert_not_awaited()
        db.rollback.assert_awaited_once()
