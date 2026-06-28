"""Tests for chat.py persistence (Task 7 / E.2).

Verifies:
- Happy path: session + 2 messages persisted with title on first turn
- Second turn: turn_index increments, title NOT overwritten
- Error resilience: persist failure → rollback + HTTP 200 with reply
"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from starlette.testclient import TestClient

from app.main import app
from app.infrastructure.storage.message_store import MessageStore
from app.infrastructure.storage.session_store import SessionStore


# ── Helpers ──


def _run(coro):
    """Run async coroutine synchronously."""
    return asyncio.run(coro)


def _make_client(monkeypatch, db_session):
    """Create TestClient with chat.async_session patched to yield the test session.

    After the Task 3 refactor, chat() no longer uses FastAPI Depends(get_db);
    it calls module-level async_session().  This helper replaces that callable
    so all internal sessions resolve to *db_session*.
    """
    import app.api.chat as chat_mod

    @asynccontextmanager
    async def _fake_session():
        yield db_session

    monkeypatch.setattr(chat_mod, "async_session", _fake_session)
    return TestClient(app)


def _cleanup_client(client):
    client.close()


@dataclass
class FakeNewStackResult:
    reply: str = "这是 AI 回复"
    mastery_score: int | None = 60
    turn_count: int = 1
    mode_path: list[str] = field(default_factory=lambda: ["Socratic"])
    cost_est_usd: float | None = 0.001


def _patch_new_stack(monkeypatch, result=None):
    """Mock run_new_agent_session to return a fixed result."""
    if result is None:
        result = FakeNewStackResult()

    def fake_run(session_id, user_id, user_message, *args, **kwargs):
        # *args 吸收 chat.py 透传的 current_topic / graph 位置参数
        return result

    monkeypatch.setattr(
        "app.orchestration.assembly.run_new_agent_session",
        fake_run,
    )
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")


async def _count_sessions(db_session):
    from sqlalchemy import select
    from app.models.tables import SessionTable
    r = await db_session.execute(select(SessionTable))
    return len(r.scalars().all())


async def _get_session_row(db_session, session_id):
    from sqlalchemy import select
    from app.models.tables import SessionTable
    r = await db_session.execute(select(SessionTable).where(SessionTable.id == session_id))
    return r.scalar_one_or_none()


async def _get_messages(db_session, session_id):
    from sqlalchemy import select
    from app.models.tables import MessageTable
    r = await db_session.execute(
        select(MessageTable)
        .where(MessageTable.session_id == session_id)
        .order_by(MessageTable.id.asc())
    )
    return r.scalars().all()


# ── Tests ──


def test_chat_persist_happy_path(monkeypatch, db_fixture):
    """First turn: session row with title, 2 messages with turn_index=0."""
    _patch_new_stack(monkeypatch)

    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            async with session_factory() as session:
                client = _make_client(monkeypatch, session)
                try:
                    resp = client.post("/api/chat", json={
                        "message": "帮我理解 RAG",
                        "session_id": "s-happy",
                        "user_id": 1,
                    })
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["stack"] == "new"
                    assert data["reply"] == "这是 AI 回复"
                    assert data["persisted"] is True

                    # Verify session row
                    sess = await _get_session_row(session, "s-happy")
                    assert sess is not None
                    assert sess.title == "帮我理解 RAG"
                    assert sess.user_id == 1

                    # Verify messages
                    msgs = await _get_messages(session, "s-happy")
                    assert len(msgs) == 2
                    assert msgs[0].role == "user"
                    assert msgs[0].content == "帮我理解 RAG"
                    assert msgs[0].turn_index == 0
                    assert msgs[1].role == "assistant"
                    assert msgs[1].content == "这是 AI 回复"
                    assert msgs[1].turn_index == 0
                finally:
                    _cleanup_client(client)
        finally:
            await engine.dispose()

    db_fixture.run(_test())


def test_chat_persist_second_turn(monkeypatch, db_fixture):
    """Second turn: 4 messages total, second pair has turn_index=1, title NOT overwritten."""
    _patch_new_stack(monkeypatch)

    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            async with session_factory() as session:
                client = _make_client(monkeypatch, session)
                try:
                    # First turn
                    resp1 = client.post("/api/chat", json={
                        "message": "第一个问题",
                        "session_id": "s-turn2",
                        "user_id": 2,
                    })
                    assert resp1.status_code == 200

                    # Second turn
                    resp2 = client.post("/api/chat", json={
                        "message": "第二个问题",
                        "session_id": "s-turn2",
                        "user_id": 2,
                    })
                    assert resp2.status_code == 200

                    # Verify 4 messages
                    msgs = await _get_messages(session, "s-turn2")
                    assert len(msgs) == 4

                    # First pair: turn_index=0
                    assert msgs[0].turn_index == 0
                    assert msgs[1].turn_index == 0

                    # Second pair: turn_index=1
                    assert msgs[2].turn_index == 1
                    assert msgs[3].turn_index == 1
                    assert msgs[2].role == "user"
                    assert msgs[2].content == "第二个问题"
                    assert msgs[3].role == "assistant"

                    # Title NOT overwritten (still from first turn)
                    sess = await _get_session_row(session, "s-turn2")
                    assert sess.title == "第一个问题"
                finally:
                    _cleanup_client(client)
        finally:
            await engine.dispose()

    db_fixture.run(_test())


def test_chat_persist_error_resilience(monkeypatch, db_fixture):
    """MessageStore.add raises on second call → rollback (0 messages), HTTP still 200."""
    _patch_new_stack(monkeypatch)

    # Monkeypatch MessageStore.add to raise on second call
    original_add = MessageStore.add
    call_count = {"n": 0}

    async def flaky_add(self, session_id, role, content, turn_index):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("模拟 DB 故障")
        return await original_add(self, session_id, role, content, turn_index)

    monkeypatch.setattr(MessageStore, "add", flaky_add)

    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            async with session_factory() as session:
                client = _make_client(monkeypatch, session)
                try:
                    resp = client.post("/api/chat", json={
                        "message": "测试错误恢复",
                        "session_id": "s-err",
                        "user_id": 3,
                    })
                    # HTTP still 200 with reply, persisted=False
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["reply"] == "这是 AI 回复"
                    assert data["stack"] == "new"
                    assert data["persisted"] is False

                    # Rollback: 0 messages persisted
                    msgs = await _get_messages(session, "s-err")
                    assert len(msgs) == 0
                finally:
                    _cleanup_client(client)
        finally:
            await engine.dispose()

    db_fixture.run(_test())


def test_chat_turn_count_is_teaching_round(db_fixture, monkeypatch):
    # 第一轮 turn_count 应为 1（turn_index 0 + 1），非事件循环次数
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.orchestration.assembly import NewStackResult
            import app.api.chat as chat_mod
            from app.api.chat import chat
            from app.models.schemas import ChatRequest

            # fake_run 接收 chat.py 透传的 5 个位置参数
            # (session_id, user_id, message, current_topic, graph)，
            # *args 吸收 current_topic / graph，避免 TypeError。
            def fake_run(session_id, user_id, message, *args, **kw):
                return NewStackResult(reply="R", mastery_score=80, turn_count=11,
                                      mode_path=["socratic"], cost_est_usd=None, events=[])
            monkeypatch.setattr("app.orchestration.assembly.run_new_agent_session", fake_run)
            monkeypatch.setattr(chat_mod, "use_new_agent_graph", lambda: True)

            async with session_factory() as db:
                # Patch async_session so chat()'s internal sessions resolve to our test db
                @asynccontextmanager
                async def _fake_session():
                    yield db
                monkeypatch.setattr(chat_mod, "async_session", _fake_session)

                resp = await chat(ChatRequest(message="hi", session_id="sc1", user_id=1))
            assert resp.turn_count == 1   # 不是 11
            assert resp.persisted is True
        finally:
            await engine.dispose()
    db_fixture.run(_test())
