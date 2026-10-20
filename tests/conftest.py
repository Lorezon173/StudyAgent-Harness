import asyncio
import os
import tempfile
from dataclasses import dataclass

import pytest


# === Plan C：LLM Mock fixture（决策 #22 — fixture+monkeypatch）===
# 用法：mock_llm_invoke_json({"tutor_ask": {...}, "critic_eval": {...}})
# 三 Agent 测试统一通过此 fixture 注入「intent → 结构化 dict」映射。
@pytest.fixture
def mock_llm_invoke_json(monkeypatch):
    def _install(intent_to_response: dict):
        def _fake_invoke_json(self, system_prompt, user_prompt,
                              session_id="", node="", intent="", **kwargs):
            return intent_to_response.get(intent, {})
        monkeypatch.setattr(
            "app.infrastructure.llm.LLMService.invoke_json",
            _fake_invoke_json,
        )
    return _install


# ---------------------------------------------------------------------------
# Async DB test fixture
# ---------------------------------------------------------------------------

@dataclass
class DbFixture:
    """Wraps a temporary SQLite file path and provides helpers for async tests.

    Usage in sync test functions:
        def test_something(db_fixture):
            async def _test():
                engine, session_factory = await db_fixture.setup_db()
                try:
                    async with session_factory() as session:
                        ...
                finally:
                    await engine.dispose()
            db_fixture.run(_test())
    """
    db_path: str

    def run(self, coro):
        """Run an async coroutine synchronously via asyncio.run.

        After asyncio.run() closes the loop, a fresh event loop is installed
        so that subsequent tests using asyncio.get_event_loop() are not affected.
        """
        try:
            return asyncio.run(coro)
        finally:
            asyncio.set_event_loop(asyncio.new_event_loop())

    async def setup_db(self):
        """Create a fresh async engine + run create_all.

        Returns (engine, session_factory). Caller must call `await engine.dispose()`.
        """
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

        from app.core.database import Base

        engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        return engine, session_factory


@pytest.fixture
def db_fixture():
    """Provides a DbFixture backed by a temporary SQLite file.

    The file is created before yield and removed after the test.
    Engine creation and table setup happen inside the test's asyncio.run()
    to avoid cross-event-loop issues with SQLAlchemy async engines.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()

    yield DbFixture(db_path=tmp_path)

    try:
        os.unlink(tmp_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Auth fixture (Task 13)
# ---------------------------------------------------------------------------
# Task 11 给受保护端点加了 Depends(get_current_user)。get_current_user 除了验签，
# 还会查 DB 确认用户存在（S5），测试场景下若不 seed 用户会拿到 401。
# 此 fixture 既注入合法 Bearer JWT（确保 Authorization header 真实存在），
# 又覆写 get_current_user 依赖跳过 DB 查询，使测试无需 seed 用户即可鉴权通过。
@pytest.fixture
def auth_headers():
    """提供已认证用户的 Authorization header（工厂模式）。

    用法：
        client.post("/api/chat", json={...}, headers=auth_headers())
        client.post("/api/chat", json={...}, headers=auth_headers(user_id=2))

    副作用：覆写 app.main.app 的 get_current_user 依赖为返回
    ``{"user_id": user_id}``，测试结束后自动还原。
    """
    from app.core.security import create_access_token, get_current_user
    from app.main import app

    # 进入时捕获原 override（可能为 None）
    original_override = app.dependency_overrides.get(get_current_user)
    override_installed = {"done": False}

    def _make(user_id: int = 1) -> dict:
        token = create_access_token(user_id)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": user_id}
        override_installed["done"] = True
        return {"Authorization": f"Bearer {token}"}

    yield _make

    # 仅在 _make 被调用过时还原
    if override_installed["done"]:
        if original_override is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = original_override
