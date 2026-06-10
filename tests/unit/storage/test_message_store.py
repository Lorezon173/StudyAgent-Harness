"""Tests for MessageStore (dual-mode: memory + DB)."""
import asyncio
from datetime import datetime

from app.infrastructure.storage.message_store import MessageStore


# ---------------------------------------------------------------------------
# Memory-mode tests
# ---------------------------------------------------------------------------

class TestMessageStoreMemory:
    """Tests for MessageStore in memory mode (no db)."""

    def test_add_returns_incrementing_ids(self):
        async def _test():
            store = MessageStore()
            id1 = await store.add("s1", "user", "hello", 0)
            id2 = await store.add("s1", "assistant", "hi", 1)
            id3 = await store.add("s1", "user", "bye", 2)
            assert id1 == 1
            assert id2 == 2
            assert id3 == 3

        asyncio.run(_test())

    def test_list_by_session_returns_correct_order_and_shape(self):
        async def _test():
            store = MessageStore()
            await store.add("s1", "user", "first", 0)
            await store.add("s1", "assistant", "second", 1)
            await store.add("s1", "user", "third", 2)

            msgs = await store.list_by_session("s1")
            assert len(msgs) == 3

            # Check shape: each dict has exactly these keys
            expected_keys = {"role", "content", "turn_index", "created_at"}
            for msg in msgs:
                assert set(msg.keys()) == expected_keys

            # Check order (by insertion = id order)
            assert msgs[0]["role"] == "user"
            assert msgs[0]["content"] == "first"
            assert msgs[0]["turn_index"] == 0
            assert isinstance(msgs[0]["created_at"], datetime)

            assert msgs[1]["role"] == "assistant"
            assert msgs[1]["content"] == "second"
            assert msgs[1]["turn_index"] == 1

            assert msgs[2]["role"] == "user"
            assert msgs[2]["content"] == "third"
            assert msgs[2]["turn_index"] == 2

        asyncio.run(_test())

    def test_list_by_session_filters_by_session_id(self):
        async def _test():
            store = MessageStore()
            await store.add("s1", "user", "msg-a", 0)
            await store.add("s2", "user", "msg-b", 0)
            await store.add("s1", "assistant", "msg-c", 1)

            msgs_s1 = await store.list_by_session("s1")
            assert len(msgs_s1) == 2
            assert msgs_s1[0]["content"] == "msg-a"
            assert msgs_s1[1]["content"] == "msg-c"

            msgs_s2 = await store.list_by_session("s2")
            assert len(msgs_s2) == 1
            assert msgs_s2[0]["content"] == "msg-b"

        asyncio.run(_test())

    def test_list_by_session_returns_empty_for_unknown_session(self):
        async def _test():
            store = MessageStore()
            msgs = await store.list_by_session("nonexistent")
            assert msgs == []

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# DB-mode tests
# ---------------------------------------------------------------------------

class TestMessageStoreDB:
    """Tests for MessageStore in DB mode (with AsyncSession)."""

    def test_add_returns_id_after_flush(self, db_fixture):
        async def _test():
            engine, session_factory = await db_fixture.setup_db()
            try:
                async with session_factory() as session:
                    # Need a session row first (FK constraint)
                    from app.models.tables import SessionTable
                    session.add(SessionTable(id="s1", state_json="{}"))
                    await session.commit()

                    store = MessageStore(db=session)
                    id1 = await store.add("s1", "user", "hello", 0)
                    id2 = await store.add("s1", "assistant", "hi", 1)
                    assert isinstance(id1, int)
                    assert isinstance(id2, int)
                    assert id2 > id1
                    await session.commit()
            finally:
                await engine.dispose()

        db_fixture.run(_test())

    def test_list_by_session_returns_correct_order_and_shape(self, db_fixture):
        async def _test():
            engine, session_factory = await db_fixture.setup_db()
            try:
                async with session_factory() as session:
                    from app.models.tables import SessionTable
                    session.add(SessionTable(id="s1", state_json="{}"))
                    await session.commit()

                    store = MessageStore(db=session)
                    await store.add("s1", "user", "first", 0)
                    await store.add("s1", "assistant", "second", 1)
                    await store.add("s1", "user", "third", 2)
                    await session.commit()

                    msgs = await store.list_by_session("s1")
                    assert len(msgs) == 3

                    expected_keys = {"role", "content", "turn_index", "created_at"}
                    for msg in msgs:
                        assert set(msg.keys()) == expected_keys

                    assert msgs[0]["role"] == "user"
                    assert msgs[0]["content"] == "first"
                    assert msgs[0]["turn_index"] == 0

                    assert msgs[1]["role"] == "assistant"
                    assert msgs[1]["content"] == "second"
                    assert msgs[1]["turn_index"] == 1

                    assert msgs[2]["role"] == "user"
                    assert msgs[2]["content"] == "third"
                    assert msgs[2]["turn_index"] == 2
            finally:
                await engine.dispose()

        db_fixture.run(_test())

    def test_list_by_session_filters_by_session_id(self, db_fixture):
        async def _test():
            engine, session_factory = await db_fixture.setup_db()
            try:
                async with session_factory() as session:
                    from app.models.tables import SessionTable
                    session.add(SessionTable(id="s1", state_json="{}"))
                    session.add(SessionTable(id="s2", state_json="{}"))
                    await session.commit()

                    store = MessageStore(db=session)
                    await store.add("s1", "user", "msg-a", 0)
                    await store.add("s2", "user", "msg-b", 0)
                    await store.add("s1", "assistant", "msg-c", 1)
                    await session.commit()

                    msgs_s1 = await store.list_by_session("s1")
                    assert len(msgs_s1) == 2
                    assert msgs_s1[0]["content"] == "msg-a"
                    assert msgs_s1[1]["content"] == "msg-c"

                    msgs_s2 = await store.list_by_session("s2")
                    assert len(msgs_s2) == 1
                    assert msgs_s2[0]["content"] == "msg-b"
            finally:
                await engine.dispose()

        db_fixture.run(_test())

    def test_list_by_session_returns_empty_for_unknown_session(self, db_fixture):
        async def _test():
            engine, session_factory = await db_fixture.setup_db()
            try:
                async with session_factory() as session:
                    store = MessageStore(db=session)
                    msgs = await store.list_by_session("nonexistent")
                    assert msgs == []
            finally:
                await engine.dispose()

        db_fixture.run(_test())
