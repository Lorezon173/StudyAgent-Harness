"""主题画像作用域、数据库归属和兼容写入的真实 SQLite 测试。"""
import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.tables import UserTable


def test_base_create_all_registers_workspace_tables():
    # 缺失注册会让仅依赖 Base 的启动/测试路径漏建新表。
    assert {"topic_profiles", "profile_nodes", "profile_edges"} <= set(Base.metadata.tables)


@pytest.fixture
def profile_db(tmp_path):
    async def run(check):
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'profiles.db'}")

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as db:
                db.add_all([UserTable(id=1, username="one", password_hash="x"),
                            UserTable(id=2, username="two", password_hash="x")])
                await db.commit()
            await check(factory)
        finally:
            await engine.dispose()

    return lambda check: asyncio.run(run(check))


def test_same_title_nodes_are_uuid_scoped_and_unassessed_is_null(profile_db):
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore

    async def check(factory):
        async with factory() as db:
            profiles = TopicProfileStore(db)
            first = await profiles.create(1, "通信", "第一范围")
            second = await profiles.create(1, "通信", "第二范围")
            first_id, second_id = str(uuid4()), str(uuid4())
            await ProfileMasteryStore(db, first.id).save_nodes(1, [{"topic_id": first_id, "topic_name": "信道"}])
            await ProfileMasteryStore(db, second.id).save_nodes(1, [{"topic_id": second_id, "topic_name": "信道", "mastery": 80}])
            await db.commit()
        async with factory() as db:
            left = await ProfileMasteryStore(db, first.id).load_nodes(1)
            right = await ProfileMasteryStore(db, second.id).load_nodes(1)
            assert UUID(first.id) and UUID(second.id)
            assert set(left) == {first_id}
            assert left[first_id]["mastery"] is None
            assert right[second_id]["mastery"] == 80
            assert (await TopicProfileStore(db).get_owned(1, first.id)).scope_description == "第一范围"
            assert await TopicProfileStore(db).get_owned(2, first.id) is None
    profile_db(check)


@pytest.mark.parametrize("operation", ["save_nodes", "load_nodes", "save_edges", "load_edges"])
def test_every_compatibility_method_rejects_another_owner(profile_db, operation):
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore

    async def check(factory):
        async with factory() as db:
            profile = await TopicProfileStore(db).create(1, "本人", "")
            store = ProfileMasteryStore(db, profile.id)
            args = (2, []) if operation.startswith("save") else (2,)
            with pytest.raises(PermissionError):
                await getattr(store, operation)(*args)
    profile_db(check)


@pytest.mark.parametrize("target", ["other_profile", "other_user", "unknown_profile"])
def test_database_rejects_edges_outside_profile(profile_db, target):
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.models.workspace_tables import ProfileNodeTable, ProfileEdgeTable

    async def check(factory):
        async with factory() as db:
            left = await TopicProfileStore(db).create(1, "一", "")
            right = await TopicProfileStore(db).create(2 if target == "other_user" else 1, "二", "")
            a, b = str(uuid4()), str(uuid4())
            db.add_all([ProfileNodeTable(id=a, profile_id=left.id, title="同名"),
                        ProfileNodeTable(id=b, profile_id=right.id, title="同名")])
            await db.flush()
            db.add(ProfileEdgeTable(profile_id=str(uuid4()) if target == "unknown_profile" else left.id,
                                    from_node_id=a, to_node_id=b, type="PREREQ"))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
    profile_db(check)


def test_profile_owner_must_exist_and_legacy_is_unique(profile_db):
    from app.models.workspace_tables import TopicProfileTable

    async def check(factory):
        async with factory() as db:
            db.add(TopicProfileTable(id=str(uuid4()), user_id=999, name="无归属"))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
        async with factory() as db:
            db.add_all([TopicProfileTable(id=str(uuid4()), user_id=1, name="历史一", kind="legacy"),
                        TopicProfileTable(id=str(uuid4()), user_id=1, name="历史二", kind="legacy")])
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
    profile_db(check)


def test_compatibility_roundtrip_edges_and_caller_owns_transaction(profile_db):
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore
    from app.models.workspace_tables import TopicProfileTable

    async def check(factory):
        async with factory() as db:
            profile = await TopicProfileStore(db).create(1, "可回滚", "")
            profile_id = profile.id
            a, b = str(uuid4()), str(uuid4())
            store = ProfileMasteryStore(db, profile.id)
            await store.save_nodes(1, [{"topic_id": a, "topic_name": "甲"}, {"topic_id": b, "topic_name": "乙"}])
            await store.save_edges(1, [{"from_topic": a, "to_topic": b, "type": "RELATED", "source": "DOC_ORDER"}])
            edges = await store.load_edges(1)
            assert [(edge["from_topic"], edge["to_topic"], edge["type"]) for edge in edges] == [(a, b, "RELATED")]
            await db.rollback()
        async with factory() as db:
            assert await db.get(TopicProfileTable, profile_id) is None
    profile_db(check)


def test_stale_compatibility_save_cannot_overwrite_newer_node_revision(profile_db):
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore
    from app.models.workspace_tables import ProfileNodeTable

    async def check(factory):
        node_id = str(uuid4())
        async with factory() as db:
            profile = await TopicProfileStore(db).create(1, "版本", "")
            await ProfileMasteryStore(db, profile.id).save_nodes(1, [{"topic_id": node_id, "mastery": 30}])
            await db.commit()
        async with factory() as old_db:
            stale_store = ProfileMasteryStore(old_db, profile.id)
            old_nodes = await stale_store.load_nodes(1)
            await old_db.commit()
            async with factory() as new_db:
                fresh_store = ProfileMasteryStore(new_db, profile.id)
                fresh_nodes = await fresh_store.load_nodes(1)
                fresh_nodes[node_id]["mastery"] = 90
                await fresh_store.save_nodes(1, list(fresh_nodes.values()))
                await new_db.commit()
            old_nodes[node_id]["mastery"] = 10
            with pytest.raises(ValueError, match="revision"):
                await stale_store.save_nodes(1, list(old_nodes.values()))
            await old_db.rollback()
        async with factory() as db:
            assert (await db.scalar(select(ProfileNodeTable).where(ProfileNodeTable.id == node_id))).mastery == 90
    profile_db(check)


def test_stale_edges_and_unversioned_existing_nodes_are_rejected(profile_db):
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore

    async def check(factory):
        a, b = str(uuid4()), str(uuid4())
        async with factory() as db:
            profile = await TopicProfileStore(db).create(1, "边版本", "")
            store = ProfileMasteryStore(db, profile.id)
            await store.save_nodes(1, [{"topic_id": a}, {"topic_id": b}])
            await store.save_edges(1, [{"from_topic": a, "to_topic": b}])
            await db.commit()
        async with factory() as old_db:
            stale = ProfileMasteryStore(old_db, profile.id)
            edges = await stale.load_edges(1)
            await old_db.commit()
            async with factory() as fresh_db:
                fresh = ProfileMasteryStore(fresh_db, profile.id)
                fresh_edges = await fresh.load_edges(1)
                fresh_edges[0]["weight"] = 0.9
                await fresh.save_edges(1, fresh_edges)
                await fresh_db.commit()
            edges[0]["weight"] = 0.1
            with pytest.raises(ValueError, match="revision"):
                await stale.save_edges(1, edges)
            await old_db.rollback()
        async with factory() as db:
            with pytest.raises(ValueError, match="revision"):
                await ProfileMasteryStore(db, profile.id).save_nodes(1, [{"topic_id": a, "mastery": 5}])
            await db.rollback()
            with pytest.raises(ValueError, match="revision"):
                await ProfileMasteryStore(db, profile.id).save_edges(1, [{"from_topic": a, "to_topic": b}])
            await db.rollback()
            assert (await ProfileMasteryStore(db, profile.id).load_edges(1))[0]["weight"] == 0.9
    profile_db(check)


def test_initializing_new_nodes_does_not_authorize_overwriting_unread_edges(profile_db):
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore

    async def check(factory):
        a, b = str(uuid4()), str(uuid4())
        async with factory() as db:
            profile = await TopicProfileStore(db).create(1, "已有边", "")
            store = ProfileMasteryStore(db, profile.id)
            await store.save_nodes(1, [{"topic_id": a}, {"topic_id": b}])
            await store.save_edges(1, [{"from_topic": a, "to_topic": b, "weight": 0.9}])
            await db.commit()
        async with factory() as db:
            unobserved = ProfileMasteryStore(db, profile.id)
            await unobserved.save_nodes(1, [{"topic_id": str(uuid4())}])
            with pytest.raises(ValueError, match="revision|snapshot"):
                await unobserved.save_edges(1, [{"from_topic": a, "to_topic": b, "weight": 0.1}])
            await db.rollback()
            assert (await ProfileMasteryStore(db, profile.id).load_edges(1))[0]["weight"] == 0.9
    profile_db(check)


def test_loading_edges_cannot_refresh_an_older_node_snapshot(profile_db):
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore

    async def check(factory):
        node_id = str(uuid4())
        async with factory() as db:
            profile = await TopicProfileStore(db).create(1, "一致快照", "")
            await ProfileMasteryStore(db, profile.id).save_nodes(1, [{"topic_id": node_id}])
            await db.commit()
        async with factory() as db:
            stale = ProfileMasteryStore(db, profile.id)
            await stale.load_nodes(1)
            await db.commit()
            async with factory() as other:
                fresh = ProfileMasteryStore(other, profile.id)
                await fresh.save_nodes(1, [{"topic_id": str(uuid4())}])
                await other.commit()
            with pytest.raises(ValueError, match="revision"):
                await stale.load_edges(1)
    profile_db(check)


def test_failed_flush_requires_new_store_after_caller_rollback(profile_db):
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore

    async def check(factory):
        async with factory() as db:
            profile = await TopicProfileStore(db).create(1, "失败事务", "")
            profile_id = profile.id
            await db.commit()
            store = ProfileMasteryStore(db, profile.id)
            with pytest.raises(IntegrityError):
                await store.save_edges(1, [{"from_topic": str(uuid4()), "to_topic": str(uuid4())}])
            await db.rollback()
            with pytest.raises(RuntimeError, match="store|Store"):
                await store.save_nodes(1, [{"topic_id": str(uuid4())}])
            fresh = ProfileMasteryStore(db, profile_id)
            assert await fresh.load_nodes(1) == {}
    profile_db(check)


def test_graph_roundtrip_preserves_description_and_archived_until_explicit_update(profile_db):
    from app.harness.mastery_graph import MasteryGraph
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore

    async def check(factory):
        node_id = str(uuid4())
        async with factory() as db:
            profile = await TopicProfileStore(db).create(1, "图谱往返", "")
            profile_id = profile.id
            await ProfileMasteryStore(db, profile_id).save_nodes(1, [{
                "topic_id": node_id, "topic_name": "旧知识点", "description": "人工说明",
                "archived": True, "mastery": 60, "practice_count": 2, "rationale": "真实依据",
            }])
            await db.commit()
        async with factory() as db:
            graph = MasteryGraph(1, ProfileMasteryStore(db, profile_id))
            await graph.load()
            await graph.save()
            await db.commit()
        async with factory() as db:
            store = ProfileMasteryStore(db, profile_id)
            nodes = await store.load_nodes(1)
            assert nodes[node_id]["description"] == "人工说明"
            assert nodes[node_id]["archived"] is True
            await store.save_nodes(1, [{"topic_id": node_id, "description": "", "archived": False}])
            await db.commit()
        async with factory() as db:
            saved = (await ProfileMasteryStore(db, profile_id).load_nodes(1))[node_id]
            assert saved["description"] == ""
            assert saved["archived"] is False
            assert saved["topic_name"] == "旧知识点"
            assert saved["mastery"] == 60
            assert saved["practice_count"] == 2
            assert saved["rationale"] == "真实依据"
    profile_db(check)


def test_graph_skips_unknown_prerequisite_and_keeps_null_after_save(profile_db):
    from app.harness.mastery_graph import MasteryGraph
    from app.infrastructure.storage.topic_profile_store import TopicProfileStore
    from app.infrastructure.storage.profile_mastery_store import ProfileMasteryStore

    async def check(factory):
        unknown, weak, target = str(uuid4()), str(uuid4()), str(uuid4())
        async with factory() as db:
            profile = await TopicProfileStore(db).create(1, "未知前置", "")
            profile_id = profile.id
            store = ProfileMasteryStore(db, profile_id)
            await store.save_nodes(1, [{"topic_id": unknown}, {"topic_id": weak, "mastery": 20}, {"topic_id": target}])
            await store.save_edges(1, [{"from_topic": unknown, "to_topic": target},
                                       {"from_topic": weak, "to_topic": target}])
            await db.commit()
        async with factory() as db:
            graph = MasteryGraph(1, ProfileMasteryStore(db, profile_id))
            await graph.load()
            assert graph.get_node(unknown).mastery is None
            weak_prereqs = graph.find_weak_prereqs(target)
            assert [(item["prereq_topic_id"], item["mastery"]) for item in weak_prereqs] == [(weak, 20)]
            await graph.save()
            await db.commit()
        async with factory() as db:
            saved = await ProfileMasteryStore(db, profile_id).load_nodes(1)
            assert saved[unknown]["mastery"] is None
            assert saved[unknown]["practice_count"] == 0
            assert saved[weak]["mastery"] == 20
    profile_db(check)
