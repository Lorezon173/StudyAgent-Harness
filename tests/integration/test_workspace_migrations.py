"""在独立 SQLite/临时 PostgreSQL 数据库运行真实 Alembic 迁移。"""
import importlib
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import make_url

from app.core.database import Base  # noqa: F401 — settings替换前注册应用模型/异步引擎


pytestmark = pytest.mark.integration
PREVIOUS = "20260729_chunk_id"
CURRENT = "20261023_topic_profiles"


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_db(request, tmp_path, monkeypatch):
    """PG 仅允许显式测试URL，每次生成随机子库，绝不清理现有库。"""
    maintenance = None
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path / 'migration.db'}"
    else:
        configured = os.environ.get("WORKSPACE_TEST_DATABASE_URL")
        if not configured:
            pytest.skip("需 WORKSPACE_TEST_DATABASE_URL 指向独立测试PG")
        test_url = make_url(configured).set(drivername="postgresql+psycopg")
        database_name = "workspace_task2_" + uuid4().hex
        maintenance = sa.create_engine(test_url, isolation_level="AUTOCOMMIT")
        with maintenance.connect() as connection:
            connection.execute(sa.text(f'CREATE DATABASE "{database_name}"'))
        url = test_url.set(database=database_name)
    engine = sa.create_engine(url)
    if request.param == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    from app.core.config import settings
    monkeypatch.setattr(settings, "database_url", str(url) if isinstance(url, str) else url.render_as_string(hide_password=False))
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    # 使用同一个开启FK的连接，也覆盖Alembic外部连接入口。
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, PREVIOUS)
            yield connection, config
    finally:
        engine.dispose()
        if maintenance is not None:
            with maintenance.connect() as connection:
                connection.execute(sa.text(f'DROP DATABASE "{database_name}"'))
            maintenance.dispose()


def seed_legacy(connection):
    metadata = sa.MetaData()
    metadata.reflect(connection)
    connection.execute(metadata.tables["users"].insert(), [
        {"id": 1, "username": "one", "password_hash": "x"},
        {"id": 2, "username": "two", "password_hash": "x"},
        {"id": 3, "username": "without-graph", "password_hash": "x"},
    ])
    topics = ["长" * 500 + "甲", "长" * 500 + "乙"]
    connection.execute(metadata.tables["mastery_nodes"].insert(), [
        {"user_id": owner, "topic_id": topic, "topic_name": "同名知识点", "mastery": 20 + owner,
         "last_practiced_at": 123.0, "practice_count": 2, "confusion_with": [], "rationale": "历史依据"}
        for owner in (1, 2) for topic in topics
    ])
    connection.execute(metadata.tables["mastery_edges"].insert(), [
        {"user_id": owner, "from_topic": topics[0], "to_topic": topics[1], "type": "RELATED",
         "weight": 0.7, "confidence": 0.8, "source": "INTERACTION"} for owner in (1, 2)
    ])
    connection.commit()
    return topics


def test_upgrade_keeps_legacy_owned_deterministic_and_idempotent(migration_db):
    connection, config = migration_db
    seed_legacy(connection)
    command.upgrade(config, "head")
    tables = sa.MetaData()
    tables.reflect(connection)
    assert {"topic_profiles", "profile_nodes", "profile_edges"} <= set(tables.tables)
    profiles = tables.tables["topic_profiles"]
    nodes = tables.tables["profile_nodes"]
    edges = tables.tables["profile_edges"]
    assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == CURRENT
    owners = connection.execute(sa.select(profiles.c.user_id, profiles.c.id, profiles.c.kind)).all()
    assert {(row.user_id, row.kind) for row in owners} == {(1, "legacy"), (2, "legacy")}
    original_ids = set(connection.execute(sa.select(nodes.c.profile_id, nodes.c.id)).all())
    assert len(original_ids) == 4
    assert len({row.id for row in connection.execute(sa.select(nodes.c.id))}) == 4
    for owner, profile_id, _ in owners:
        assert connection.execute(sa.select(nodes.c.mastery).where(nodes.c.profile_id == profile_id)).scalars().all() == [20 + owner] * 2
        owned_nodes = set(connection.execute(sa.select(nodes.c.id).where(nodes.c.profile_id == profile_id)).scalars())
        edge = connection.execute(sa.select(edges).where(edges.c.profile_id == profile_id)).one()
        assert {edge.from_node_id, edge.to_node_id} == owned_nodes
        assert edge.source == "INTERACTION"
    # 项目alembic目录不是Python包，以文件入口载入真实迁移函数。
    spec = importlib.util.spec_from_file_location("topic_profile_migration", Path(__file__).resolve().parents[2] / "alembic/versions/20261023_topic_profiles.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration._migrate_legacy_graphs(connection)
    assert set(connection.execute(sa.select(nodes.c.profile_id, nodes.c.id)).all()) == original_ids
    assert connection.scalar(sa.select(sa.func.count()).select_from(profiles)) == 2
    assert connection.scalar(sa.select(sa.func.count()).select_from(edges)) == 2
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM mastery_nodes")) == 4
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM mastery_edges")) == 2
    assert "profile_evidence" not in tables.tables
    connection.commit()
    with pytest.raises(RuntimeError, match="data|数据"):
        command.downgrade(config, PREVIOUS)
    connection.rollback()
    assert connection.scalar(sa.select(sa.func.count()).select_from(nodes)) == 4


def test_empty_upgrade_can_downgrade_without_data_loss(migration_db):
    connection, config = migration_db
    command.upgrade(config, "head")
    command.downgrade(config, PREVIOUS)
    assert "topic_profiles" not in sa.inspect(connection).get_table_names()


def test_migrated_database_enforces_owner_and_same_profile_foreign_keys(migration_db):
    connection, config = migration_db
    seed_legacy(connection)
    command.upgrade(config, "head")
    owner_profiles = connection.execute(sa.text("SELECT user_id,id FROM topic_profiles ORDER BY user_id")).all()
    left, right = owner_profiles[0].id, owner_profiles[1].id
    nodes = connection.execute(sa.text("SELECT id,profile_id FROM profile_nodes")).all()
    a = next(row.id for row in nodes if row.profile_id == left)
    b = next(row.id for row in nodes if row.profile_id == right)
    with connection.begin_nested() as savepoint:
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text("INSERT INTO profile_edges(profile_id,from_node_id,to_node_id,type) VALUES (:p,:a,:b,'CONFLICT')"), {"p": left, "a": a, "b": b})
        savepoint.rollback()
    with connection.begin_nested() as savepoint:
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text("INSERT INTO topic_profiles(id,user_id,name) VALUES (:id,999,'orphan')"), {"id": str(uuid4())})
        savepoint.rollback()
    connection.commit()


def test_preexisting_legacy_profile_is_reused_without_copying_into_normal_profile(migration_db):
    connection, config = migration_db
    command.upgrade(config, "head")
    seed_legacy(connection)
    legacy_id, normal_id = str(uuid4()), str(uuid4())
    connection.execute(sa.text("INSERT INTO topic_profiles(id,user_id,name,kind) VALUES (:id,1,'existing','legacy')"), {"id": legacy_id})
    connection.execute(sa.text("INSERT INTO topic_profiles(id,user_id,name,kind) VALUES (:id,1,'normal','normal')"), {"id": normal_id})
    spec = importlib.util.spec_from_file_location("topic_profile_migration_existing", Path(__file__).resolve().parents[2] / "alembic/versions/20261023_topic_profiles.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration._migrate_legacy_graphs(connection)
    migration._migrate_legacy_graphs(connection)
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM profile_nodes WHERE profile_id=:id"), {"id": legacy_id}) == 2
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM profile_nodes WHERE profile_id=:id"), {"id": normal_id}) == 0
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM topic_profiles WHERE user_id=1 AND kind='legacy'")) == 1
    connection.commit()


def test_dangling_legacy_edge_refuses_partial_copy(migration_db):
    connection, config = migration_db
    seed_legacy(connection)
    connection.execute(sa.text("UPDATE mastery_edges SET to_topic='missing' WHERE user_id=2"))
    connection.commit()
    with pytest.raises(ValueError, match="endpoint|端点"):
        command.upgrade(config, "head")
    connection.rollback()
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM mastery_nodes")) == 4
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM mastery_edges")) == 2
    if "topic_profiles" in sa.inspect(connection).get_table_names():
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM topic_profiles")) == 0
