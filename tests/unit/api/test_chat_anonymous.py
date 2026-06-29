"""Tests for P1-⑥ anonymous user doesn't write mastery (Task 8).

Verifies:
- user_id=None → MasteryGraph NOT constructed (no "anonymous" graph pollution)
- user_id=None → HTTP 200 + reply still returned
- user_id=None → messages still persist to DB
- Both non-streaming (chat.py) and streaming (chat_stream.py) endpoints
"""
import asyncio
import json
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
    """user_id=None → MasteryGraph NOT constructed, reply still returned."""
    from unittest.mock import patch

    # Patch run_new_agent_session to return a fake result
    from dataclasses import dataclass, field

    @dataclass
    class FakeResult:
        reply: str = "anonymous reply"
        mastery_score: int | None = None
        turn_count: int = 1
        mode_path: list[str] = field(default_factory=list)
        cost_est_usd: float | None = None

    monkeypatch.setattr(
        "app.orchestration.assembly.run_new_agent_session",
        lambda *a, **kw: FakeResult(),
    )
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")

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
                        # MasteryGraph must NOT be constructed
                        mock_mg.assert_not_called()
                finally:
                    client.close()

                assert resp.status_code == 200
                data = resp.json()
                assert data["reply"] == "anonymous reply"
                assert data["stack"] == "new"
        finally:
            await engine.dispose()

    db_fixture.run(_test())


def test_anonymous_chat_messages_persist(monkeypatch, db_fixture):
    """user_id=None → messages still persist to DB."""
    from dataclasses import dataclass, field

    @dataclass
    class FakeResult:
        reply: str = "anon reply"
        mastery_score: int | None = None
        turn_count: int = 1
        mode_path: list[str] = field(default_factory=list)
        cost_est_usd: float | None = None

    monkeypatch.setattr(
        "app.orchestration.assembly.run_new_agent_session",
        lambda *a, **kw: FakeResult(),
    )
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")

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
                    assert resp.status_code == 200

                    # Messages should persist
                    from sqlalchemy import select
                    from app.models.tables import MessageTable
                    r = await session.execute(
                        select(MessageTable).where(MessageTable.session_id == "s-anon-persist")
                    )
                    msgs = r.scalars().all()
                    assert len(msgs) == 2
                    assert msgs[0].role == "user"
                    assert msgs[1].role == "assistant"
                finally:
                    client.close()
        finally:
            await engine.dispose()

    db_fixture.run(_test())


# ── Streaming tests ──


def test_anonymous_stream_no_mastery_graph(monkeypatch):
    """user_id=None → MasteryGraph NOT constructed in stream endpoint."""
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
    monkeypatch.setattr(cs, "use_new_agent_graph", lambda: True)

    from app.orchestration.assembly import NewStackResult

    def fake_run(session_id, user_id, message, current_topic=None, graph=None, on_event=None):
        return NewStackResult(reply="stream anon reply", mastery_score=None,
                              turn_count=1, mode_path=[], cost_est_usd=None, events=[])

    monkeypatch.setattr("app.orchestration.assembly.run_new_agent_session", fake_run)

    try:
        client = TestClient(app)
        with patch("app.api.chat_stream.MasteryGraph") as mock_mg:
            with client.stream("POST", "/api/chat/stream",
                               json={"message": "hi", "session_id": "st-anon",
                                     "user_id": None}) as r:
                body = "".join(chunk for chunk in r.iter_text())
            # MasteryGraph must NOT be constructed
            mock_mg.assert_not_called()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    # Should still get a final event with reply
    events = []
    for line in body.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))

    final_events = [e for e in events if e.get("type") == "final"]
    assert len(final_events) == 1
    assert final_events[0]["reply"] == "stream anon reply"
