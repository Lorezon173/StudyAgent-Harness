"""Tests for SessionStore (dual-mode: memory + DB).

Covers:
- Title INSERT / first-write-wins semantics
- R1: explicit updated_at refresh on UPDATE (DB mode)
- C2: list_by_user returns {session_id, title, updated_at} shape, sorted desc
- C3: save() does NOT commit internally (caller commits)
"""
import asyncio
import time

from app.infrastructure.storage.session_store import SessionStore


# ---------------------------------------------------------------------------
# Memory-mode tests
# ---------------------------------------------------------------------------

class TestSessionStoreMemory:
    """Tests for SessionStore in memory mode (no db)."""

    def test_save_with_title_stores_title(self):
        async def _test():
            store = SessionStore()
            await store.save("s1", {"k": "v"}, user_id=1, title="Hello World")
            row = store._memory["s1"]
            assert row["title"] == "Hello World"
            assert row["session_id"] == "s1"
            assert row["user_id"] == 1
            assert row["_updated_seq"] == 1

        asyncio.run(_test())

    def test_second_save_with_none_title_preserves_first(self):
        """First-write-wins: second save with title=None keeps the original title."""
        async def _test():
            store = SessionStore()
            await store.save("s1", {"k": "v1"}, user_id=1, title="Original")
            await store.save("s1", {"k": "v2"}, user_id=1, title=None)
            assert store._memory["s1"]["title"] == "Original"
            # _updated_seq should advance on each save
            assert store._memory["s1"]["_updated_seq"] == 2

        asyncio.run(_test())

    def test_seq_advances_on_each_save(self):
        async def _test():
            store = SessionStore()
            await store.save("s1", {}, user_id=1)
            await store.save("s2", {}, user_id=1)
            await store.save("s1", {}, user_id=1)
            # s1 saved twice: seq=1 then seq=3; s2 saved once: seq=2
            assert store._memory["s1"]["_updated_seq"] == 3
            assert store._memory["s2"]["_updated_seq"] == 2

        asyncio.run(_test())

    def test_list_by_user_returns_c2_shape_sorted_desc(self):
        """C2: memory branch returns {session_id, title, updated_at}, sorted by updated_at desc."""
        async def _test():
            store = SessionStore()
            await store.save("s1", {}, user_id=1, title="First")
            await store.save("s2", {}, user_id=1, title="Second")
            await store.save("s3", {}, user_id=2, title="Other user")
            await store.save("s1", {}, user_id=1, title=None)  # s1 most recently updated

            items = await store.list_by_user(user_id=1)
            assert len(items) == 2

            # Check shape: exactly these keys
            expected_keys = {"session_id", "title", "updated_at"}
            for item in items:
                assert set(item.keys()) == expected_keys

            # Sorted by updated_at desc: s1 (seq=4) before s2 (seq=2)
            assert items[0]["session_id"] == "s1"
            assert items[0]["title"] == "First"  # preserved, not overwritten
            assert items[0]["updated_at"] == 4

            assert items[1]["session_id"] == "s2"
            assert items[1]["title"] == "Second"
            assert items[1]["updated_at"] == 2

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# DB-mode tests
# ---------------------------------------------------------------------------

class TestSessionStoreDB:
    """Tests for SessionStore in DB mode (with AsyncSession)."""

    def test_save_insert_with_title(self, db_fixture):
        """INSERT branch: title is stored on first save."""
        async def _test():
            engine, session_factory = await db_fixture.setup_db()
            try:
                async with session_factory() as session:
                    store = SessionStore(db=session)
                    await store.save("s1", {"k": "v"}, user_id=1, title="Hello")
                    await session.commit()

                    # Read back via get()
                    row = await store.get("s1")
                    assert row is not None
                    assert row["session_id"] == "s1"

                    # Verify title directly from DB
                    from sqlalchemy import select
                    from app.models.tables import SessionTable
                    result = await session.execute(
                        select(SessionTable).where(SessionTable.id == "s1")
                    )
                    db_row = result.scalar_one()
                    assert db_row.title == "Hello"
            finally:
                await engine.dispose()

        db_fixture.run(_test())

    def test_second_save_does_not_overwrite_title(self, db_fixture):
        """UPDATE branch: second save with a different title keeps the original (first-write-wins)."""
        async def _test():
            engine, session_factory = await db_fixture.setup_db()
            try:
                async with session_factory() as session:
                    store = SessionStore(db=session)
                    await store.save("s1", {"k": "v1"}, user_id=1, title="Original")
                    await session.commit()

                    # Second save — save() ignores title on UPDATE (first-write-wins)
                    await store.save("s1", {"k": "v2"}, user_id=1, title="Ignored")
                    await session.commit()

                    from sqlalchemy import select
                    from app.models.tables import SessionTable
                    result = await session.execute(
                        select(SessionTable).where(SessionTable.id == "s1")
                    )
                    db_row = result.scalar_one()
                    assert db_row.title == "Original"
                    # But state should be updated
                    assert db_row.state_json == '{"k": "v2"}'
            finally:
                await engine.dispose()

        db_fixture.run(_test())

    def test_r1_updated_at_advances_on_identical_state(self, db_fixture):
        """R1: two saves with identical state {} — updated_at still advances.

        Without the explicit `row.updated_at = func.now()`, SQLAlchemy onupdate
        may not fire when no column value actually changes.
        """
        async def _test():
            engine, session_factory = await db_fixture.setup_db()
            try:
                async with session_factory() as session:
                    store = SessionStore(db=session)
                    await store.save("s1", {}, user_id=1, title="T")
                    await session.commit()

                    from sqlalchemy import select
                    from app.models.tables import SessionTable

                    result = await session.execute(
                        select(SessionTable).where(SessionTable.id == "s1")
                    )
                    updated_at_1 = result.scalar_one().updated_at

                    # Wait to ensure CURRENT_TIMESTAMP advances (SQLite has 1s precision)
                    time.sleep(1.1)

                    # Second save with identical state
                    await store.save("s1", {}, user_id=1)
                    await session.commit()

                    # Expire to force reload from DB
                    session.expire_all()
                    result = await session.execute(
                        select(SessionTable).where(SessionTable.id == "s1")
                    )
                    updated_at_2 = result.scalar_one().updated_at

                    assert updated_at_2 is not None
                    assert updated_at_2 > updated_at_1, (
                        f"R1 failed: updated_at did not advance. "
                        f"T1={updated_at_1}, T2={updated_at_2}"
                    )
            finally:
                await engine.dispose()

        db_fixture.run(_test())

    def test_c3_save_does_not_commit_internally(self, db_fixture):
        """C3: save() must NOT call commit — caller is responsible.

        We verify this by saving, NOT committing, then rolling back.
        If save() committed internally, the row would persist despite rollback.
        """
        async def _test():
            engine, session_factory = await db_fixture.setup_db()
            try:
                async with session_factory() as session:
                    store = SessionStore(db=session)
                    await store.save("s1", {}, user_id=1, title="WillBeRolledBack")
                    # Do NOT commit — rollback instead
                    await session.rollback()

                    # Row should not exist
                    from sqlalchemy import select
                    from app.models.tables import SessionTable
                    result = await session.execute(
                        select(SessionTable).where(SessionTable.id == "s1")
                    )
                    assert result.scalar_one_or_none() is None
            finally:
                await engine.dispose()

        db_fixture.run(_test())

    def test_list_by_user_returns_c2_shape_sorted_desc(self, db_fixture):
        """C2: DB branch returns {session_id, title, updated_at}, sorted by updated_at desc."""
        async def _test():
            engine, session_factory = await db_fixture.setup_db()
            try:
                async with session_factory() as session:
                    store = SessionStore(db=session)

                    # Create two sessions with a time gap to ensure distinct updated_at
                    await store.save("s1", {}, user_id=1, title="First")
                    await session.commit()

                    time.sleep(1.1)

                    await store.save("s2", {}, user_id=1, title="Second")
                    await session.commit()

                    items = await store.list_by_user(user_id=1)
                    assert len(items) == 2

                    # Check shape
                    expected_keys = {"session_id", "title", "updated_at"}
                    for item in items:
                        assert set(item.keys()) == expected_keys

                    # Sorted by updated_at desc: s2 (newer) before s1
                    assert items[0]["session_id"] == "s2"
                    assert items[0]["title"] == "Second"
                    assert items[1]["session_id"] == "s1"
                    assert items[1]["title"] == "First"
            finally:
                await engine.dispose()

        db_fixture.run(_test())
