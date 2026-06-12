import json
import os
import tempfile


def test_chat_stream_emits_incremental_agent_events(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.main import app
    from app.core.database import Base
    import app.models.tables as _tables  # noqa: F401 — 注册表模型到 Base.metadata（别名避免遮蔽 app）
    import app.api.chat_stream as cs
    from app.orchestration.assembly import NewStackResult
    from app.harness.events import Event
    from app.harness.enums import EventType, EventSource

    # 隔离 DB：用临时 sqlite 文件，避免污染开发库 + 保证可重复运行（幂等）。
    # 表用同步 engine 建好（不触异步事件循环），请求侧再用 async engine 读同一文件。
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    sync_engine = create_engine(f"sqlite:///{tmp.name}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    aengine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", echo=False)
    test_sessionmaker = async_sessionmaker(aengine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(cs, "async_session", test_sessionmaker)

    monkeypatch.setattr(cs, "use_new_agent_graph", lambda: True)

    def fake_run(session_id, user_id, message, current_topic=None, graph=None, on_event=None):
        # 模拟协作环逐事件回调
        if on_event:
            on_event(Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR,
                           session_id=session_id, payload={"content": "Q?"}))
            on_event(Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                           session_id=session_id, payload={"score": 80, "level": "good"}))
        return NewStackResult(reply="最终回答", mastery_score=80, turn_count=11,
                              mode_path=["socratic"], cost_est_usd=None, events=[])

    monkeypatch.setattr("app.orchestration.assembly.run_new_agent_session", fake_run)

    try:
        client = TestClient(app)
        with client.stream("POST", "/api/chat/stream",
                           json={"message": "hi", "session_id": "st1", "user_id": 1}) as r:
            body = "".join(chunk for chunk in r.iter_text())
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    # 逐事件：至少一个 agent_event + 一个 final
    assert "agent_event" in body
    assert "TutorAsked" in body
    final_lines = [l for l in body.splitlines() if l.startswith("data:") and "final" in l]
    assert final_lines, "应有 final 事件"
    payload = json.loads(final_lines[-1][len("data:"):].strip())
    assert payload["reply"] == "最终回答"
    assert payload["turn_count"] == 1   # 教学回合，非 11
