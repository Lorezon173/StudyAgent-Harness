from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


_PG_POOL_SIZE = 5
_PG_MAX_OVERFLOW = 10


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    """Create async engine with dialect-specific params."""
    if url.startswith("postgresql"):
        return create_async_engine(
            url,
            echo=False,
            pool_size=_PG_POOL_SIZE,
            max_overflow=_PG_MAX_OVERFLOW,
            pool_pre_ping=True,
        )
    # sqlite and other dialects: simplest params
    return create_async_engine(url, echo=False)


engine = _make_engine(settings.database_url)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        else:
            await conn.run_sync(Base.metadata.create_all)
