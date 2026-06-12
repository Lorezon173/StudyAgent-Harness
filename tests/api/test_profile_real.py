import app.models.tables  # ensure tables are registered before create_all


def test_profile_reads_real_sessions_and_avg_mastery(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api.profile import get_profile
            from app.infrastructure.storage.session_store import SessionStore
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                await SessionStore(db).save("s1", state={}, user_id=1, title="t1")
                await SessionStore(db).save("s2", state={}, user_id=1, title="t2")
                store = SQLAlchemyMasteryStore(db)
                await store.save_nodes("1", [
                    {"topic_id": "a", "topic_name": "a", "mastery": 70.0,
                     "last_practiced_at": 0, "practice_count": 1,
                     "confusion_with": [], "rationale": ""},
                    {"topic_id": "b", "topic_name": "b", "mastery": 90.0,
                     "last_practiced_at": 0, "practice_count": 1,
                     "confusion_with": [], "rationale": ""},
                ])
                await db.commit()
                resp = await get_profile(1, db=db)
            assert resp["stats"]["sessions"] == 2
            assert resp["stats"]["avg_mastery"] == 80
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_profile_empty_returns_zero(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api.profile import get_profile
            async with session_factory() as db:
                resp = await get_profile(999, db=db)
            assert resp["stats"]["sessions"] == 0
            assert resp["stats"]["avg_mastery"] == 0
        finally:
            await engine.dispose()
    db_fixture.run(_test())
