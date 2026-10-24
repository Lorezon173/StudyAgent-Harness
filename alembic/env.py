from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.core.config import settings
from app.core.database import Base
from app.models.tables import *  # noqa: F401,F403 — register all tables

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from settings (async → sync for migration engine)
sync_url = settings.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
config.set_main_option("sqlalchemy.url", sync_url)

target_metadata = Base.metadata


def prepare_connection(connection) -> None:
    """在 SQLite 的真实 BEGIN 前启用 FK，不结束调用方拥有的事务。"""
    if connection.dialect.name != "sqlite":
        return
    driver = connection.connection.driver_connection
    cursor = driver.cursor()
    try:
        # 直接读取连接pragma，避免SQLAlchemy autobegin使Alembic误判为外部事务。
        if cursor.execute("PRAGMA foreign_keys").fetchone()[0] == 1:
            return
        if driver.in_transaction:
            raise RuntimeError("cannot enable SQLite foreign_keys inside an existing transaction; caller must rollback or commit first")
        cursor.execute("PRAGMA foreign_keys=ON")
        if cursor.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("failed to enable SQLite foreign_keys before migration")
    finally:
        cursor.close()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (sync engine from async URL)."""
    provided_connection = config.attributes.get("connection")
    if provided_connection is not None:
        prepare_connection(provided_connection)
        context.configure(connection=provided_connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        prepare_connection(connection)
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
