"""Tests for Task 11 鉴权后的匿名端点行为。

Task 11 给 chat / chat_stream 加了 Depends(get_current_user)。
此前（Task 8）测试 user_id=None 是否跳过 MasteryGraph；现在无 token 的请求
会被鉴权层挡在 401，根本到不了业务逻辑。
故此文件改为验证：未带 Authorization → 401，保护业务逻辑不被匿名流量触达。
"""
import asyncio
import os
import tempfile
from contextlib import asynccontextmanager

from starlette.testclient import TestClient

from app.main import app


# ── Non-streaming tests ──


def _make_client_for_chat(monkeypatch, db_session):
    """Patch chat.async_session to yield the test session."""
    import app.api.chat as chat_mod

    @asynccontextmanager
    async def _fake_session():
        yield db_session

    monkeypatch.setattr(chat_mod, "async_session", _fake_session)
    return TestClient(app)


def test_anonymous_chat_no_mastery_graph(monkeypatch, db_fixture):
    """无 Authorization → 401，业务逻辑（含 MasteryGraph 构造）不被触达。"""
    from unittest.mock import patch

    # Patch run_new_agent_session to return a fake result (不应被调用)
    from dataclasses import dataclass, field

    @dataclass
    class FakeResult:
        reply: str = "anonymous reply"
        mastery_score: int | None = None
        turn_count: int = 1
        mode_path: list[str] = field(default_factory=list)
        cost_est_usd: float | None = None

    monkeypatch.setattr(
        "app.orchestration.assembly.run_online_agent_session",
        lambda *a, **kw: FakeResult(),
    )

    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            async with session_factory() as session:
                client = _make_client_for_chat(monkeypatch, session)
                try:
                    with patch("app.api.chat.MasteryGraph") as mock_mg:
                        resp = client.post("/api/chat", json={
                            "message": "hello",
                            "session_id": "s-anon",
                            "user_id": None,
                        })
                        # MasteryGraph 必须未被构造（请求被鉴权层拦截）
                        mock_mg.assert_not_called()
                finally:
                    client.close()

            assert resp.status_code == 401
        finally:
            await engine.dispose()

    db_fixture.run(_test())


def test_anonymous_chat_messages_persist(monkeypatch, db_fixture):
    """无 Authorization → 401，无消息被持久化。"""
    from dataclasses import dataclass, field

    @dataclass
    class FakeResult:
        reply: str = "anon reply"
        mastery_score: int | None = None
        turn_count: int = 1
        mode_path: list[str] = field(default_factory=list)
        cost_est_usd: float | None = None

    monkeypatch.setattr(
        "app.orchestration.assembly.run_online_agent_session",
        lambda *a, **kw: FakeResult(),
    )

    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            async with session_factory() as session:
                client = _make_client_for_chat(monkeypatch, session)
                try:
                    resp = client.post("/api/chat", json={
                        "message": "test msg",
                        "session_id": "s-anon-persist",
                        "user_id": None,
                    })
                    assert resp.status_code == 401

                    # 被鉴权层拦截，无消息持久化
                    from sqlalchemy import select
                    from app.models.tables import MessageTable
                    r = await session.execute(
                        select(MessageTable).where(MessageTable.session_id == "s-anon-persist")
                    )
                    msgs = r.scalars().all()
                    assert len(msgs) == 0
                finally:
                    client.close()
        finally:
            await engine.dispose()

    db_fixture.run(_test())


# ── Streaming tests ──


def test_anonymous_stream_no_mastery_graph(monkeypatch):
    """无 Authorization → 401，流式端点同样被鉴权层拦截。"""
    from unittest.mock import patch
    from sqlalchemy import create_engine
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.database import Base
    import app.models.tables as _tables  # noqa: F401
    import app.api.chat_stream as cs

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    sync_engine = create_engine(f"sqlite:///{tmp.name}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    aengine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", echo=False)
    test_sessionmaker = async_sessionmaker(aengine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(cs, "async_session", test_sessionmaker)

    from app.orchestration.assembly import NewStackResult

    def fake_run(session_id, user_id, message, current_topic=None, graph=None, on_event=None):
        return NewStackResult(reply="stream anon reply", mastery_score=None,
                              turn_count=1, mode_path=[], cost_est_usd=None, events=[])

    monkeypatch.setattr("app.orchestration.assembly.run_online_agent_session", fake_run)

    try:
        client = TestClient(app)
        with patch("app.api.chat_stream.MasteryGraph") as mock_mg:
            resp = client.post("/api/chat/stream",
                               json={"message": "hi", "session_id": "st-anon",
                                     "user_id": None})
            # MasteryGraph 不应被构造（鉴权层拦截）
            mock_mg.assert_not_called()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    # 无 token → 401
    assert resp.status_code == 401
