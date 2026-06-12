"""Tests for SQLAlchemyMasteryStore (复刻旧 MasteryGraphStore 4 方法契约)."""
import pytest

import app.models.tables  # noqa: F401 — ensure tables are registered with Base.metadata before create_all


def test_save_load_nodes_roundtrip(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                store = SQLAlchemyMasteryStore(db)
                await store.save_nodes("u1", [{
                    "topic_id": "二分查找", "topic_name": "二分查找",
                    "mastery": 75.0, "last_practiced_at": 1.5,
                    "practice_count": 2, "confusion_with": ["排序"],
                    "rationale": "答对核心问题",
                }])
                await db.commit()
                loaded = await store.load_nodes("u1")
            assert loaded["二分查找"]["mastery"] == 75.0
            assert loaded["二分查找"]["rationale"] == "答对核心问题"
            assert loaded["二分查找"]["confusion_with"] == ["排序"]
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_save_nodes_upsert_updates(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                store = SQLAlchemyMasteryStore(db)
                await store.save_nodes("u1", [{"topic_id": "t", "topic_name": "t",
                    "mastery": 10.0, "last_practiced_at": 0, "practice_count": 1,
                    "confusion_with": [], "rationale": ""}])
                await db.commit()
                await store.save_nodes("u1", [{"topic_id": "t", "topic_name": "t",
                    "mastery": 90.0, "last_practiced_at": 0, "practice_count": 2,
                    "confusion_with": [], "rationale": ""}])
                await db.commit()
                loaded = await store.load_nodes("u1")
            assert loaded["t"]["mastery"] == 90.0  # 同 PK 覆盖而非重复
            assert loaded["t"]["practice_count"] == 2
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_save_load_edges_roundtrip(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                store = SQLAlchemyMasteryStore(db)
                await store.save_edges("u1", [{
                    "from_topic": "a", "to_topic": "b", "type": "PREREQ",
                    "weight": 1.0, "confidence": 0.8, "source": "INTERACTION",
                }])
                await db.commit()
                loaded = await store.load_edges("u1")
            assert len(loaded) == 1
            assert loaded[0]["from_topic"] == "a" and loaded[0]["confidence"] == 0.8
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_load_empty_user_returns_defaults(db_fixture):
    """不存在用户返回空结果 (复刻旧 store test_load_nonexistent_user_returns_defaults)。"""
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                store = SQLAlchemyMasteryStore(db)
                nodes = await store.load_nodes("ghost_user")
                assert nodes == {}
                edges = await store.load_edges("ghost_user")
                assert edges == []
        finally:
            await engine.dispose()
    db_fixture.run(_test())
