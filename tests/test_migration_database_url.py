"""Migration URL contracts: synchronous drivers and lossless configuration."""

import runpy
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url


@pytest.mark.parametrize(("source", "driver", "database"), [
    ("postgresql+asyncpg://user:pass@localhost/db", "postgresql+psycopg", "db"),
    ("postgresql://user:pass@localhost/db", "postgresql+psycopg", "db"),
    ("postgresql+psycopg://user:pass@localhost/db", "postgresql+psycopg", "db"),
    ("sqlite+aiosqlite:///./relative.db", "sqlite", "./relative.db"),
    ("sqlite:///./relative.db", "sqlite", "./relative.db"),
    ("sqlite+aiosqlite:///:memory:", "sqlite", ":memory:"),
    ("sqlite+aiosqlite:////absolute/example.db", "sqlite", "/absolute/example.db"),
])
def test_migration_selects_installed_sync_driver(source, driver, database):
    from app.core.database_url import build_sync_database_url

    result = build_sync_database_url(source)
    assert result.drivername == driver
    assert result.database == database
    assert not result.get_dialect().is_async
    assert result.get_dialect().import_dbapi().__name__ in {"psycopg", "sqlite3.dbapi2"}


def test_migration_preserves_encoded_credentials_and_query():
    from app.core.database_url import build_sync_database_url

    source = "postgresql+asyncpg://user%40name:p%40ss%25word%2F@localhost:5433/db?application_name=migrate%25&options=a&options=b"
    result = build_sync_database_url(source)
    assert result.username == "user@name"
    assert result.password == "p@ss%word/"
    assert result.host == "localhost"
    assert result.port == 5433
    assert result.query == {"application_name": "migrate%", "options": ("a", "b")}
    assert make_url(result.render_as_string(hide_password=False)) == result


def test_migration_rejects_unsupported_backend_without_credentials():
    from app.core.database_url import build_sync_database_url

    with pytest.raises(ValueError) as error:
        build_sync_database_url("mysql+aiomysql://private:secret@localhost/db")
    assert "sqlite" in str(error.value)
    assert "postgresql" in str(error.value)
    assert "private" not in str(error.value)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("source, password, query", [
    ("postgresql+asyncpg://user:pass@localhost/db", "pass", {}),
    ("postgresql+asyncpg://user:p%40ss%25word@localhost/db?application_name=migrate%25",
     "p@ss%word", {"application_name": "migrate%"}),
])
def test_alembic_environment_preserves_percent_url(monkeypatch, source, password, query):
    # Load the application engine using its normal test configuration before
    # overriding only the migration setting; no database connection is needed.
    import app.core.database  # noqa: F401 - initialize application metadata
    from app.core.config import settings

    monkeypatch.setattr(settings, "database_url", source)
    config = Config()
    config.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(config)
    with EnvironmentContext(config, script, as_sql=True, fn=lambda revision, context: []):
        runpy.run_path(str(Path("alembic/env.py")))
    restored = make_url(config.get_main_option("sqlalchemy.url"))
    assert restored.drivername == "postgresql+psycopg"
    assert restored.password == password
    assert restored.query == query
