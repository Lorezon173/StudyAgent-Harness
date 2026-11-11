"""在独立 SQLite/临时 PostgreSQL 数据库运行真实 Alembic 迁移。"""
import importlib
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import make_url

from alembic import command
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
    command.upgrade(config, CURRENT)
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
    with pytest.raises(RuntimeError, match=r"data|数据"):
        command.downgrade(config, PREVIOUS)
    connection.rollback()
    assert connection.scalar(sa.select(sa.func.count()).select_from(nodes)) == 4


def test_empty_upgrade_can_downgrade_without_data_loss(migration_db):
    connection, config = migration_db
    command.upgrade(config, CURRENT)
    command.downgrade(config, PREVIOUS)
    assert "topic_profiles" not in sa.inspect(connection).get_table_names()


def test_migrated_database_enforces_owner_and_same_profile_foreign_keys(migration_db):
    connection, config = migration_db
    seed_legacy(connection)
    command.upgrade(config, CURRENT)
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
    command.upgrade(config, CURRENT)
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


def test_dangling_legacy_edge_is_preserved_without_invalid_projection(migration_db):
    connection, config = migration_db
    seed_legacy(connection)
    connection.execute(sa.text("UPDATE mastery_edges SET to_topic='missing' WHERE user_id=2"))
    connection.commit()
    before = connection.execute(sa.text("SELECT * FROM mastery_edges ORDER BY id")).all()
    command.upgrade(config, CURRENT)
    assert connection.execute(sa.text("SELECT * FROM mastery_edges ORDER BY id")).all() == before
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM mastery_nodes")) == 4
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM profile_edges")) == 1
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM profile_edges e LEFT JOIN profile_nodes n ON n.profile_id=e.profile_id AND n.id=e.to_node_id WHERE n.id IS NULL")) == 0


WORKSPACE = "20261023_session_workspace_state"


def test_session_upgrade_keeps_messages_and_uses_owner_legacy_and_max_turn(migration_db):
    from uuid import NAMESPACE_URL, uuid5

    connection, config = migration_db
    seed_legacy(connection)
    connection.execute(sa.text("INSERT INTO sessions(id,user_id,state_json) VALUES ('old1',1,'{}'),('old3',3,'{}'),('unknown',NULL,'{}')"))
    connection.execute(sa.text("INSERT INTO messages(session_id,role,content,turn_index) VALUES ('old1','user','旧问题',2),('old1','assistant','异常高回合',8),('unknown','user','无归属',4)"))
    connection.commit()
    command.upgrade(config, WORKSPACE)
    sessions = connection.execute(sa.text("SELECT id,user_id,profile_id,next_turn_index FROM sessions ORDER BY id")).mappings().all()
    by_id = {row["id"]: row for row in sessions}
    assert by_id["old1"]["profile_id"] == str(uuid5(NAMESPACE_URL, "studyagent:legacy-profile:1"))
    assert by_id["old3"]["profile_id"] == str(uuid5(NAMESPACE_URL, "studyagent:legacy-profile:3"))
    assert by_id["old1"]["next_turn_index"] == 9
    assert by_id["old3"]["next_turn_index"] == 0
    assert by_id["unknown"]["profile_id"] is None
    assert by_id["unknown"]["next_turn_index"] == 5
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM messages")) == 3
    assert connection.scalar(sa.text("SELECT content FROM messages WHERE session_id='old1' AND turn_index=8")) == "异常高回合"
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM topic_profiles WHERE user_id=1 AND kind='legacy'")) == 1
    assert {"chat_requests", "profile_evidence", "session_view_states", "user_workspace_states"} <= set(sa.inspect(connection).get_table_names())
    if connection.dialect.name == "sqlite":
        assert connection.scalar(sa.text("PRAGMA foreign_keys")) == 1
        assert connection.execute(sa.text("PRAGMA foreign_key_check")).all() == []
    connection.commit()
    # 提交后由独立连接检查，不能把同一事务中的可见性误认成迁移持久化。
    with connection.engine.connect() as fresh:
        assert fresh.scalar(sa.text("SELECT COUNT(*) FROM messages")) == 3
        assert fresh.scalar(sa.text("SELECT version_num FROM alembic_version")) == WORKSPACE
        assert fresh.scalar(sa.text("SELECT next_turn_index FROM sessions WHERE id='old1'")) == 9
        if fresh.dialect.name == "sqlite":
            assert fresh.scalar(sa.text("PRAGMA foreign_keys")) == 1
        with pytest.raises(sa.exc.IntegrityError):
            fresh.execute(sa.text("INSERT INTO session_view_states(user_id,session_id) VALUES (2,'old1')"))
        fresh.rollback()


def test_workspace_migration_enforces_full_evidence_owner_chain_and_safe_downgrade(migration_db):
    connection, config = migration_db
    seed_legacy(connection)
    command.upgrade(config, WORKSPACE)
    profiles = dict(connection.execute(sa.text("SELECT user_id,id FROM topic_profiles")).all())
    node = connection.scalar(sa.text("SELECT id FROM profile_nodes WHERE profile_id=:p LIMIT 1"), {"p": profiles[1]})
    connection.execute(sa.text("INSERT INTO sessions(id,user_id,profile_id,state_json) VALUES ('s1',1,:p,'{}')"), {"p": profiles[1]})
    connection.execute(sa.text("INSERT INTO sessions(id,user_id,profile_id,state_json) VALUES ('s2',2,:p,'{}')"), {"p": profiles[2]})
    connection.execute(sa.text("INSERT INTO messages(session_id,role,content,turn_index) VALUES ('s1','assistant','真实来源',0),('s2','assistant','他人来源',0)"))
    connection.execute(sa.text("INSERT INTO chat_requests(user_id,session_id,request_id,profile_id,payload_hash,request_payload,base_state_version,status) VALUES (1,'s1','r1',:p,'h','{}',0,'completed')"), {"p": profiles[1]})
    connection.commit()
    for statement, values in [
        ("UPDATE sessions SET profile_id=:p WHERE id='s1'", {"p": profiles[2]}),
        ("INSERT INTO session_view_states(user_id,session_id) VALUES (2,'s1')", {}),
        ("INSERT INTO user_workspace_states(user_id,last_session_id) VALUES (1,'s2')", {}),
        ("INSERT INTO chat_requests(user_id,session_id,request_id,profile_id,payload_hash,request_payload,base_state_version,status) VALUES (2,'s1','bad',:p,'h','{}',0,'failed')", {"p": profiles[1]}),
        ("INSERT INTO profile_evidence(id,user_id,profile_id,node_id,session_id,request_id,message_id,score) VALUES ('e',1,:p,:n,'s1','r1',2,80)", {"p": profiles[1], "n": node}),
    ]:
        with connection.begin_nested() as savepoint:
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(sa.text(statement), values)
            savepoint.rollback()
    connection.execute(sa.text("INSERT INTO profile_evidence(id,user_id,profile_id,node_id,session_id,request_id,message_id,score) VALUES ('e',1,:p,:n,'s1','r1',1,80)"), {"p": profiles[1], "n": node})
    with connection.begin_nested() as savepoint:
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text("INSERT INTO profile_evidence(id,user_id,profile_id,node_id,session_id,request_id,message_id,score) VALUES ('e2',1,:p,:n,'s1','r1',1,80)"), {"p": profiles[1], "n": node})
        savepoint.rollback()
    connection.commit()
    with pytest.raises(RuntimeError, match=r"data|数据"):
        command.downgrade(config, CURRENT)
    connection.rollback()
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM profile_evidence")) == 1


def test_empty_workspace_upgrade_downgrade_preserves_old_session(migration_db):
    connection, config = migration_db
    connection.execute(sa.text("INSERT INTO sessions(id,user_id,state_json) VALUES ('unknown',NULL,'{}')"))
    connection.execute(sa.text("INSERT INTO messages(session_id,role,content,turn_index) VALUES ('unknown','user','保留',0)"))
    connection.commit()
    command.upgrade(config, WORKSPACE)
    command.downgrade(config, CURRENT)
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM messages")) == 1
    assert "profile_id" not in {c["name"] for c in sa.inspect(connection).get_columns("sessions")}


def test_workspace_rebuild_failure_rolls_back_schema_history_and_alembic_head(migration_db, monkeypatch):
    from alembic.operations import Operations

    connection, config = migration_db
    seed_legacy(connection)
    connection.execute(sa.text("INSERT INTO sessions(id,user_id,state_json) VALUES ('old',1,'{}')"))
    connection.execute(sa.text("INSERT INTO messages(session_id,role,content,turn_index) VALUES ('old','user','保留原文',7)"))
    connection.commit()
    command.upgrade(config, CURRENT)
    connection.commit()
    original_create = Operations.create_table

    def fail_after_parent_rebuild(self, table_name, *args, **kwargs):
        if table_name == "profile_evidence":
            raise RuntimeError("injected after session/message rebuild")
        return original_create(self, table_name, *args, **kwargs)

    monkeypatch.setattr(Operations, "create_table", fail_after_parent_rebuild)
    with pytest.raises(RuntimeError, match="injected"):
        command.upgrade(config, WORKSPACE)
    connection.rollback()
    with connection.engine.connect() as fresh:
        assert fresh.scalar(sa.text("SELECT version_num FROM alembic_version")) == CURRENT
        assert fresh.scalar(sa.text("SELECT content FROM messages WHERE session_id='old'")) == "保留原文"
        assert fresh.scalar(sa.text("SELECT COUNT(*) FROM sessions")) == 1
        assert "profile_id" not in {c["name"] for c in sa.inspect(fresh).get_columns("sessions")}
        assert "chat_requests" not in sa.inspect(fresh).get_table_names()
        if fresh.dialect.name == "sqlite":
            assert fresh.scalar(sa.text("PRAGMA foreign_keys")) == 1
            assert fresh.execute(sa.text("PRAGMA foreign_key_check")).all() == []


@pytest.mark.parametrize("fail_rebuild", [False, True])
def test_default_sqlite_alembic_connection_enables_foreign_keys_and_is_atomic(tmp_path, monkeypatch, fail_rebuild):
    """没有测试提供的connection，走与CLI相同的env.py自建engine路径。"""
    from alembic.operations import Operations

    from app.core.config import settings

    url = f"sqlite:///{tmp_path / 'default-alembic.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, CURRENT)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO users(id,username,password_hash) VALUES (1,'default-cli','x')"))
            connection.execute(sa.text("INSERT INTO sessions(id,user_id,state_json) VALUES ('old',1,'{}')"))
            connection.execute(sa.text("INSERT INTO messages(session_id,role,content,turn_index) VALUES ('old','user','CLI保留原文',7)"))
        create_table = Operations.create_table

        def observe_foreign_keys(self, name, *args, **kwargs):
            if name == "profile_evidence":
                assert op_foreign_keys(self) == 1
                if fail_rebuild:
                    raise RuntimeError("injected CLI rebuild failure")
            return create_table(self, name, *args, **kwargs)

        def op_foreign_keys(operation):
            return operation.get_bind().scalar(sa.text("PRAGMA foreign_keys"))

        monkeypatch.setattr(Operations, "create_table", observe_foreign_keys)
        if fail_rebuild:
            with pytest.raises(RuntimeError, match="injected CLI"):
                command.upgrade(config, "head")
        else:
            command.upgrade(config, "head")
        with engine.connect() as fresh:
            # FK 开关属于连接；新验证连接独立开启，不假设从迁移连接继承。
            fresh.exec_driver_sql("PRAGMA foreign_keys=ON")
            assert fresh.scalar(sa.text("PRAGMA foreign_keys")) == 1
            assert fresh.scalar(sa.text("SELECT content FROM messages")) == "CLI保留原文"
            assert fresh.scalar(sa.text("SELECT version_num FROM alembic_version")) == (CURRENT if fail_rebuild else "20261111_workspace_entered")
            columns = {c["name"] for c in sa.inspect(fresh).get_columns("sessions")}
            assert ("profile_id" in columns) is not fail_rebuild
            assert ("chat_requests" in sa.inspect(fresh).get_table_names()) is not fail_rebuild
            if not fail_rebuild:
                assert fresh.scalar(sa.text("SELECT next_turn_index FROM sessions")) == 8
                with fresh.begin_nested() as savepoint:
                    with pytest.raises(sa.exc.IntegrityError):
                        fresh.execute(sa.text("INSERT INTO session_view_states(user_id,session_id) VALUES (2,'old')"))
                    savepoint.rollback()
            assert fresh.execute(sa.text("PRAGMA foreign_key_check")).all() == []
            with pytest.raises(sa.exc.IntegrityError):
                fresh.execute(sa.text("INSERT INTO messages(session_id,role,content,turn_index) VALUES ('missing','user','非法引用',0)"))
            fresh.rollback()
    finally:
        engine.dispose()


def test_provided_sqlite_foreign_keys_off_rejects_real_transaction_without_ending_it(tmp_path, monkeypatch):
    from app.core.config import settings

    url = f"sqlite:///{tmp_path / 'provided-alembic.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, CURRENT)
    engine = sa.create_engine(url)
    try:
        with engine.connect() as provided:
            assert provided.scalar(sa.text("PRAGMA foreign_keys")) == 0
            provided.exec_driver_sql("BEGIN")
            provided.execute(sa.text("INSERT INTO users(id,username,password_hash) VALUES (99,'uncommitted-caller','x')"))
            driver = provided.connection.driver_connection
            assert driver.in_transaction is True
            config.attributes["connection"] = provided
            with pytest.raises(RuntimeError, match="cannot enable SQLite foreign_keys inside an existing transaction"):
                command.upgrade(config, WORKSPACE)
            # 迁移不得提交或回滚调用方已存在的真实事务。
            assert driver.in_transaction is True
            assert provided.in_transaction() is True
            assert provided.scalar(sa.text("SELECT username FROM users WHERE id=99")) == "uncommitted-caller"
            assert provided.scalar(sa.text("SELECT version_num FROM alembic_version")) == CURRENT
            assert "chat_requests" not in sa.inspect(provided).get_table_names()
            provided.rollback()
        with engine.connect() as fresh:
            fresh.exec_driver_sql("PRAGMA foreign_keys=ON")
            assert fresh.scalar(sa.text("PRAGMA foreign_keys")) == 1
            assert fresh.scalar(sa.text("SELECT COUNT(*) FROM users WHERE id=99")) == 0
            assert fresh.scalar(sa.text("SELECT version_num FROM alembic_version")) == CURRENT
            assert "profile_id" not in {c["name"] for c in sa.inspect(fresh).get_columns("sessions")}
            assert "chat_requests" not in sa.inspect(fresh).get_table_names()
    finally:
        engine.dispose()
