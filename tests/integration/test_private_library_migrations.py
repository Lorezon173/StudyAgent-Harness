"""私有文本迁移：隔离 SQLite / 真实 PostgreSQL 随机子库。"""
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import make_url

from app.core.database import Base  # noqa: F401

pytestmark = pytest.mark.integration
PREVIOUS = "20261023_session_workspace_state"
CURRENT = "20261023_private_library"


@pytest.fixture(params=["sqlite", "postgresql"])
def library_migration_db(request, tmp_path, monkeypatch):
    maintenance = None
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path / 'private-library.db'}"
    else:
        configured = os.environ.get("WORKSPACE_TEST_DATABASE_URL")
        if not configured:
            pytest.skip("需 WORKSPACE_TEST_DATABASE_URL 指向独立测试PG")
        test_url = make_url(configured).set(drivername="postgresql+psycopg")
        database_name = "workspace_task4_" + uuid4().hex
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
    monkeypatch.setattr(settings, "database_url", url if isinstance(url, str) else url.render_as_string(hide_password=False))
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
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


def test_library_upgrade_preserves_legacy_and_enforces_owner_with_safe_downgrade(library_migration_db):
    connection, config = library_migration_db
    connection.execute(sa.text("INSERT INTO users(id,username,password_hash) VALUES (1,'one','x'),(2,'two','x')"))
    connection.execute(sa.text("INSERT INTO topic_profiles(id,user_id,name) VALUES ('profile1',1,'one'),('profile2',2,'two')"))
    connection.execute(sa.text("INSERT INTO knowledge(id,scope,user_id,content,source,doc_ids) VALUES (51,'user',1,'旧知识原文','旧来源','[]')"))
    connection.commit()
    command.upgrade(config, "head")
    connection.commit()
    with connection.engine.connect() as fresh:
        assert fresh.scalar(sa.text("SELECT version_num FROM alembic_version")) == CURRENT
        assert fresh.execute(sa.text("SELECT id,scope,user_id,content,source FROM knowledge")).one() == (51, "user", 1, "旧知识原文", "旧来源")
        assert fresh.scalar(sa.text("SELECT COUNT(*) FROM library_items")) == 0
        if fresh.dialect.name == "sqlite":
            assert fresh.scalar(sa.text("PRAGMA foreign_keys")) == 1
        with pytest.raises(sa.exc.IntegrityError):
            fresh.execute(sa.text("INSERT INTO library_items(user_id,profile_id,name) VALUES (1,'profile2','非法归属')"))
        fresh.rollback()
        fresh.execute(sa.text("INSERT INTO library_items(user_id,profile_id,name,content_text) VALUES (1,'profile1','新文本','真实内容')"))
        fresh.commit()
    with pytest.raises(RuntimeError, match="data|数据"):
        command.downgrade(config, PREVIOUS)
    connection.rollback()
    with connection.engine.connect() as fresh:
        assert fresh.scalar(sa.text("SELECT version_num FROM alembic_version")) == CURRENT
        assert fresh.scalar(sa.text("SELECT content_text FROM library_items")) == "真实内容"
        assert fresh.scalar(sa.text("SELECT content FROM knowledge WHERE id=51")) == "旧知识原文"
        fresh.execute(sa.text("DELETE FROM library_items"))
        fresh.commit()
    command.downgrade(config, PREVIOUS)
    connection.commit()
    with connection.engine.connect() as fresh:
        assert "library_items" not in sa.inspect(fresh).get_table_names()
        assert fresh.scalar(sa.text("SELECT content FROM knowledge WHERE id=51")) == "旧知识原文"
        assert fresh.scalar(sa.text("SELECT COUNT(*) FROM topic_profiles")) == 2
