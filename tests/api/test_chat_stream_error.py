"""SSE error event schema test (Task 7 / P1-④).

Verifies that when the collaboration loop raises an exception,
the SSE stream yields a structured error event with the design-doc schema:
  {"type": "error", "code": "AGENT_ERROR", "message": "...", "retryable": false}
and the stream terminates normally (no crash).
"""
import json
import os
import tempfile


def test_chat_stream_yields_error_event_on_agent_failure(monkeypatch):
    """Collab loop raises → SSE yields structured error event, stream ends cleanly."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.main import app
    from app.core.database import Base
    import app.models.tables as _tables  # noqa: F401
    import app.api.chat_stream as cs

    # DB isolation (same pattern as test_chat_stream_realtime.py)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    sync_engine = create_engine(f"sqlite:///{tmp.name}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    aengine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", echo=False)
    test_sessionmaker = async_sessionmaker(aengine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(cs, "async_session", test_sessionmaker)
    monkeypatch.setattr(cs, "use_new_agent_graph", lambda: True)

    def fake_run_crash(session_id, user_id, message, current_topic=None, graph=None, on_event=None):
        raise RuntimeError("agent boom")

    monkeypatch.setattr("app.orchestration.assembly.run_new_agent_session", fake_run_crash)

    try:
        client = TestClient(app)
        with client.stream("POST", "/api/chat/stream",
                           json={"message": "hi", "session_id": "st-err", "user_id": 1}) as r:
            body = "".join(chunk for chunk in r.iter_text())
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    # Parse all SSE data lines
    events = []
    for line in body.splitlines():
        if line.startswith("data:"):
            payload = json.loads(line[len("data:"):].strip())
            events.append(payload)

    # Find error event
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1, f"Expected 1 error event, got {len(error_events)}: {events}"

    err = error_events[0]
    assert err["code"] == "AGENT_ERROR"
    assert err["message"] == "agent boom"
    assert err["retryable"] is False

    # No final event when agent crashes (stream ends with error)
    final_events = [e for e in events if e.get("type") == "final"]
    assert len(final_events) == 0, "No final event when agent crashes"
