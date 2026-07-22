"""会话所有权拒绝必须发生在生成教学回复之前。"""
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from unittest.mock import Mock

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat import router as chat_router
from app.api.chat_stream import router as chat_stream_router
from app.core.security import get_current_user
from app.infrastructure.storage.message_store import MessageStore
from app.infrastructure.storage.session_store import SessionStore


@dataclass
class _FakeResult:
    reply: str = "不应返回"
    mastery_score: int | None = None
    turn_count: int = 1
    mode_path: list[str] = field(default_factory=list)
    cost_est_usd: float | None = None


def _make_client(session, monkeypatch, user_id: int):
    import app.api.chat as chat_mod
    import app.api.chat_stream as stream_mod

    @asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(chat_mod, "async_session", _fake_session)
    monkeypatch.setattr(stream_mod, "async_session", _fake_session)
    app = FastAPI()
    app.include_router(chat_router, prefix="/api")
    app.include_router(chat_stream_router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": user_id}
    return TestClient(app)


async def _message_count(session, session_id: str) -> int:
    return len(await MessageStore(session).list_by_session(session_id))


def test_chat_rejects_null_owned_existing_session_before_generation(monkeypatch, db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            async with session_factory() as session:
                await SessionStore(session).save("null-owned-session", {}, user_id=None)
                await session.commit()
                client = _make_client(session, monkeypatch, user_id=2)
                try:
                    fake_run = Mock(return_value=_FakeResult())
                    monkeypatch.setattr(
                        "app.orchestration.assembly.run_new_agent_session",
                        fake_run,
                    )
                    response = client.post(
                        "/api/chat",
                        json={"message": "hi", "session_id": "null-owned-session"},
                    )
                finally:
                    client.close()

                fake_run.assert_not_called()
                assert response.status_code == 403
                assert response.json() == {"detail": "无权写入该会话"}
                assert await _message_count(session, "null-owned-session") == 0
        finally:
            await engine.dispose()

    db_fixture.run(_test())


def test_chat_rejects_other_users_session_before_generation(monkeypatch, db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            async with session_factory() as session:
                await SessionStore(session).save("owned-session", {}, user_id=1)
                await session.commit()
                client = _make_client(session, monkeypatch, user_id=2)
                try:
                    fake_run = Mock(return_value=_FakeResult())
                    monkeypatch.setattr(
                        "app.orchestration.assembly.run_new_agent_session",
                        fake_run,
                    )
                    response = client.post(
                        "/api/chat",
                        json={"message": "hi", "session_id": "owned-session"},
                    )
                finally:
                    client.close()

                fake_run.assert_not_called()
                assert response.status_code == 403
                assert response.json() == {"detail": "无权写入该会话"}
                assert await _message_count(session, "owned-session") == 0
        finally:
            await engine.dispose()

    db_fixture.run(_test())


def test_stream_rejects_other_users_session_before_sse(monkeypatch, db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            async with session_factory() as session:
                await SessionStore(session).save("owned-stream", {}, user_id=1)
                await session.commit()
                client = _make_client(session, monkeypatch, user_id=2)
                try:
                    fake_run = Mock(return_value=_FakeResult())
                    monkeypatch.setattr(
                        "app.orchestration.assembly.run_new_agent_session",
                        fake_run,
                    )
                    response = client.post(
                        "/api/chat/stream",
                        json={"message": "hi", "session_id": "owned-stream"},
                    )
                finally:
                    client.close()

                fake_run.assert_not_called()
                assert response.status_code == 403
                assert response.json() == {"detail": "无权写入该会话"}
                assert await _message_count(session, "owned-stream") == 0
        finally:
            await engine.dispose()

    db_fixture.run(_test())
