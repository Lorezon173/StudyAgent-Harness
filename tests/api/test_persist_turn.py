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
