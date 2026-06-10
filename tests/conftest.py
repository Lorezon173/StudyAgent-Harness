import asyncio
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import pytest

from app.harness.enums import Stage, Intent
from app_old.harness.state import LearningState


@pytest.fixture
def blank_state() -> LearningState:
    return {
        "user_input": "",
        "routing": {},
        "teaching": {},
        "retrieval": {},
        "evaluation": {},
        "memory": {},
        "meta": {"session_id": "test", "stage": Stage.INIT, "branch_trace": []},
    }


@pytest.fixture
def teach_state(blank_state) -> LearningState:
    state = blank_state.copy()
    state.update({
        "user_input": "我想学二分查找",
        "routing": {"intent": Intent.TEACH_LOOP, "intent_confidence": 0.9, "intent_source": "rule"},
        "memory": {"topic": "二分查找", "history": []},
    })
    return state


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
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
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
