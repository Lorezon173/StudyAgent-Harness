"""
test_database.py — Smoke tests for app.core.database module.

Verifies:
- Module imports without error
- engine.dialect.name is "sqlite" with default config
- init_db() completes without error
"""
import asyncio
import os


def test_database_module_imports():
    """database.py 模块可以正常导入，关键对象都存在"""
    from app.core.database import Base, engine, async_session, get_db, init_db

    assert Base is not None
    assert engine is not None
    assert async_session is not None
    assert callable(get_db)
    assert callable(init_db)


def test_engine_dialect_is_sqlite_by_default():
    """默认配置下 engine 的 dialect 应该是 sqlite"""
    from app.core.database import engine

    assert engine.dialect.name == "sqlite"


def test_init_db_completes():
    """init_db() 在默认 sqlite 配置下应能正常执行"""
    from app.core.database import init_db

    asyncio.run(init_db())


def test_make_engine_sqlite():
    """_make_engine 对 sqlite URL 应返回 sqlite dialect"""
    from app.core.database import _make_engine

    eng = _make_engine("sqlite+aiosqlite:///./test_smoke.db")
    assert eng.dialect.name == "sqlite"
    # 清理
    if os.path.exists("./test_smoke.db"):
        os.remove("./test_smoke.db")


def test_make_engine_postgresql_pool_params():
    """_make_engine 对 postgresql URL 应带连接池参数"""
    from app.core.database import _make_engine, _PG_POOL_SIZE, _PG_MAX_OVERFLOW

    # 用 postgresql+asyncpg 前缀，但不真正连接
    eng = _make_engine("postgresql+asyncpg://user:pass@localhost:5432/fakedb")
    assert eng.dialect.name == "postgresql"
    pool = eng.pool
    assert pool.size() == _PG_POOL_SIZE
    assert pool._max_overflow == _PG_MAX_OVERFLOW
