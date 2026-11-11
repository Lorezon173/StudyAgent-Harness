"""Task6：真实 JWT、独立文件 SQLite 与每连接外键验证工作区会话。"""
import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.tables import MessageTable, SessionTable, UserTable
from app.models.workspace_tables import (
    ChatRequestTable,
)


def headers(owner=1):
    return {"Authorization": f"Bearer {create_access_token(owner)}"}


@pytest.fixture
def workspace(tmp_path):
    async def run(check):
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}", poolclass=NullPool)
        @event.listens_for(engine.sync_engine, "connect")
        def fk(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add_all([UserTable(id=i, username=str(i), password_hash="x") for i in (1, 2)])
            await db.commit()
        active = []
        async def override():
            async with factory() as db:
                active.append(db)
                try:
                    yield db
                finally:
                    active.remove(db)
        old = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override
        from app.orchestration.conversation_service import ConversationService
        app.state.conversation_service = ConversationService(factory)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                await check(client, factory, active)
        finally:
            if old is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = old
            if hasattr(app.state, "conversation_service"):
                del app.state.conversation_service
            await engine.dispose()
    return lambda check: asyncio.run(run(check))


async def profile(client, owner=1):
    result = await client.post("/api/topic-profiles", json={"name": "主题"}, headers=headers(owner))
    assert result.status_code == 200, result.text
    item = result.json()
    return item["profile"]["id"], item["nodes"][0]["id"]


async def create(client, pid, **fields):
    response = await client.post("/api/sessions", json={"profile_id": pid, **fields}, headers=headers())
    assert response.status_code == 200, response.text
    return response.json()


async def pending(factory, sid, pid, *, status="failed", active=False):
    async with factory() as db:
        db.add(ChatRequestTable(user_id=1, session_id=sid, request_id="request", profile_id=pid,
            payload_hash="hash", request_payload={"message": "未完成原文"}, base_state_version=0,
            status=status, attempt=2, lease_until=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1), error_code="original"))
        await db.flush()
        if active:
            await db.execute(update(SessionTable).where(SessionTable.id == sid).values(active_request_id="request"))
        if status == "running":
            await db.flush()
            await db.execute(update(SessionTable).where(SessionTable.id == sid).values(active_request_id="request"))
        await db.commit()


def test_empty_creation_snapshot_and_real_independent_restore(workspace):
    async def check(client, factory, active):
        pid, nid = await profile(client)
        item = await create(client, pid, title=" 空会话 ", active_node_id=nid)
        sid = item["session_id"]
        assert item["title"] == "空会话" and item["user_id"] == 1
        assert item["state_version"] == item["next_turn_index"] == 0
        assert item["active_request_id"] is None
        async with factory() as db:
            row = await db.get(SessionTable, sid)
            state = json.loads(row.state_json)
            assert state == {}
            assert (await db.scalars(select(MessageTable))).all() == []
        snap = (await client.get(f"/api/sessions/{sid}/snapshot", headers=headers())).json()
        assert snap["teaching_state_source"] == "legacy" and snap["teaching_state"] is None and snap["legacy_state"] == state
        assert snap["messages"] == {"items": [], "next_cursor": None}
        assert snap["view_state"] == {"draft": "", "reading_anchor": None, "version": 0, "updated_at": None}
        assert snap["profile"]["id"] == pid and snap["profile_summary"]["profile_revision"] == 0
        assert (await create(client, pid))["active_node_id"] is None
    workspace(check)


def test_owner_scope_and_create_validation(workspace):
    async def check(client, factory, active):
        pid, _nid = await profile(client)
        other, other_node = await profile(client, 2)
        sid = (await create(client, pid))["session_id"]
        assert (await client.post("/api/sessions", json={"profile_id": pid})).status_code == 401
        for body in [{"profile_id": other}, {"profile_id": pid, "active_node_id": other_node}]:
            assert (await client.post("/api/sessions", json=body, headers=headers())).status_code == 404
        for body in [{"profile_id": pid, "user_id": 2}, {"profile_id": pid, "title": " "}, {"profile_id": pid, "id": "x"}]:
            assert (await client.post("/api/sessions", json=body, headers=headers())).status_code == 422
        async with factory() as db:
            db.add(SessionTable(id="null", user_id=None, state_json="{}"))
            await db.commit()
        for suffix in ["", "/snapshot", "/messages", "/requests/request"]:
            assert (await client.get(f"/api/sessions/{sid}{suffix}", headers=headers(2))).status_code == 403
            assert (await client.get(f"/api/sessions/null{suffix}", headers=headers())).status_code == 403
            assert (await client.get(f"/api/sessions/missing{suffix}", headers=headers())).status_code == 404
    workspace(check)


def test_view_workspace_versions_anchor_and_node_are_independent(workspace):
    async def check(client, factory, active):
        pid, nid = await profile(client)
        sid = (await create(client, pid))["session_id"]
        view = f"/api/sessions/{sid}/view-state"
        response = await client.patch(view, json={"expected_version": 0, "draft": "草稿"}, headers=headers())
        assert response.status_code == 200 and response.json()["version"] == 1
        assert (await client.patch(view, json={"expected_version": 0, "draft": "丢失"}, headers=headers())).status_code == 409
        assert (await client.patch(view, json={"expected_version": 1, "reading_anchor": {"message_id": 99, "offset_ratio": .5}}, headers=headers())).status_code == 422
        response = await client.patch(f"/api/sessions/{sid}/active-node", json={"expected_state_version": 0, "node_id": nid}, headers=headers())
        assert response.status_code == 200 and response.json()["state_version"] == 1
        same = await client.patch(f"/api/sessions/{sid}/active-node", json={"expected_state_version": 1, "node_id": nid}, headers=headers())
        assert same.json()["state_version"] == 1
        snap = (await client.get(f"/api/sessions/{sid}/snapshot", headers=headers())).json()
        assert snap["view_state"]["draft"] == "草稿" and snap["session"]["active_node_id"] == nid
        default = (await client.get("/api/workspace-state", headers=headers())).json()
        assert default == {"last_session_id": None, "sidebar_pinned": True, "sidebar_collapsed": False, "progress_y_ratio": .5, "version": 0, "updated_at": None}
        saved = await client.patch("/api/workspace-state", json={"expected_version": 0, "last_session_id": sid}, headers=headers())
        assert saved.status_code == 200 and saved.json()["version"] == 1
        assert (await client.patch("/api/workspace-state", json={"expected_version": 0, "sidebar_pinned": False}, headers=headers())).status_code == 409
        assert (await client.patch("/api/workspace-state", json={"expected_version": 0, "last_session_id": sid}, headers=headers(2))).status_code == 403
        await pending(factory, sid, pid, active=True)
        assert (await client.patch(f"/api/sessions/{sid}/active-node", json={"expected_state_version": 1, "node_id": None}, headers=headers())).json()["detail"]["code"] == "session_busy"
    workspace(check)


@pytest.mark.parametrize("path,body", [
    ("/api/workspace-state", {"expected_version": 0}),
    ("/api/workspace-state", {"expected_version": True, "sidebar_pinned": True}),
    ("/api/workspace-state", {"expected_version": 0, "progress_y_ratio": True}),
    ("/api/workspace-state", {"expected_version": 0, "progress_y_ratio": 1.1}),
    ("/api/workspace-state", {"expected_version": 0, "sidebar_pinned": "true"}),
    ("/api/workspace-state", {"expected_version": 0, "version": 10}),
])
def test_strict_write_dto(workspace, path, body):
    async def check(client, factory, active):
        assert (await client.patch(path, json=body, headers=headers())).status_code == 422
    workspace(check)


def test_group_and_session_cursors_empty_groups_unassigned_null_times(workspace):
    async def check(client, factory, active):
        pid, _ = await profile(client)
        empty, _ = await profile(client)
        await profile(client, 2)
        async with factory() as db:
            for i in range(65):
                db.add(SessionTable(id=f"s{i:03}", user_id=1, profile_id=pid, state_json="{}", updated_at=datetime(2026, 1, 1)))
            db.add(SessionTable(id="legacy", user_id=1, state_json="{}"))
            await db.flush()
            await db.execute(update(SessionTable).where(SessionTable.id == "s000").values(updated_at=None))
            await db.commit()
        collected = []
        cursor = None
        for expected in (30, 30, 5):
            params = {"group_by": "profile", "group_key": pid, "limit": 30}
            if cursor:
                params["session_cursor"] = cursor
            response = await client.get("/api/sessions", params=params, headers=headers())
            assert response.status_code == 200, response.text
            group = response.json()["groups"][0]
            assert len(group["sessions"]) == expected
            collected += [s["session_id"] for s in group["sessions"]]
            cursor = group["next_session_cursor"]
        assert len(set(collected)) == 65 and collected[-1] == "s000" and cursor is None
        page = (await client.get("/api/sessions?group_by=profile&group_limit=1", headers=headers())).json()
        assert page["next_group_cursor"] is not None
        assert any(g["group_key"] == "unassigned" and g["profile"] is None for g in page["groups"])
        next_page = (await client.get("/api/sessions", params={"group_by": "profile", "cursor": page["next_group_cursor"]}, headers=headers())).json()
        assert all(g["group_key"] != "unassigned" for g in next_page["groups"])
        assert any(g["group_key"] == empty and g["sessions"] == [] for g in page["groups"] + next_page["groups"])
        for params in [{"session_cursor": "bad"}, {"group_key": pid, "session_cursor": "bad"}, {"group_key": pid, "cursor": "bad"}]:
            assert (await client.get("/api/sessions", params={"group_by": "profile", **params}, headers=headers())).status_code == 422
        assert isinstance((await client.get("/api/sessions?user_id=2", headers=headers())).json(), list)
    workspace(check)


def test_message_snapshot_pagination_pending_and_legacy_schema(workspace):
    async def check(client, factory, active):
        pid, _ = await profile(client)
        sid = (await create(client, pid))["session_id"]
        async with factory() as db:
            for i in range(3):
                for role in ("user", "assistant", "system"):
                    db.add(MessageTable(session_id=sid, turn_index=i, role=role, content=f"{i}-{role}"))
            db.add(SessionTable(id="legacy", user_id=1, state_json='{"foo":"bar"}'))
            await db.commit()
        await pending(factory, sid, pid, status="running")
        snap = (await client.get(f"/api/sessions/{sid}/snapshot?message_limit=4", headers=headers())).json()
        assert snap["pending_requests"][0]["request_payload"]["message"] == "未完成原文"
        assert snap["pending_requests"][0]["lease_expired"] is False
        assert snap["pending_requests"][0]["status"] == "interrupted"
        assert snap["session"]["active_request_id"] is None
        page, items = snap["messages"], []
        while True:
            items = page["items"] + items
            if not page["next_cursor"]:
                break
            response = await client.get(f"/api/sessions/{sid}/messages", params={"cursor": page["next_cursor"], "limit": 4}, headers=headers())
            assert response.status_code == 200, response.text
            page = response.json()
        assert len(items) == len({m["id"] for m in items}) == 9
        assert [m["content"] for m in items] == [f"{i}-{r}" for i in range(3) for r in ("user", "assistant", "system")]
        assert all("turn_index" in m for m in items)
        assert isinstance((await client.get(f"/api/sessions/{sid}/messages", headers=headers())).json(), list)
        old = (await client.get("/api/sessions/legacy/snapshot", headers=headers())).json()
        assert old["teaching_state"] is None and old["legacy_state"] == {"foo": "bar"}
        assert old["session"]["profile_id"] == old["profile"]["id"] and old["profile"]["kind"] == "legacy"
        for raw, code in [('broken', 'invalid_teaching_state'), ('{"schema_version":2}', 'unsupported_teaching_schema')]:
            async with factory() as db:
                await db.execute(update(SessionTable).where(SessionTable.id == "legacy").values(state_json=raw))
                await db.commit()
            response = await client.get("/api/sessions/legacy/snapshot", headers=headers())
            assert response.status_code == 409 and response.json()["detail"]["code"] == code
    workspace(check)


def test_legacy_message_order_preserves_insertion_while_pagination_uses_turn_order(workspace):
    async def check(client, factory, active):
        pid, _ = await profile(client)
        sid = (await create(client, pid))["session_id"]
        ids = []
        async with factory() as db:
            for turn, role, content in [(1, "assistant", "先写的后回合"),
                                        (0, "user", "后写的用户消息"),
                                        (0, "assistant", "最后写的前回合回复")]:
                row = MessageTable(session_id=sid, turn_index=turn, role=role, content=content)
                db.add(row)
                await db.flush()
                ids.append(row.id)
            await db.commit()
        assert ids[0] < ids[1] < ids[2]
        url = f"/api/sessions/{sid}/messages"
        legacy = await client.get(url, headers=headers())
        assert legacy.status_code == 200, legacy.text
        assert all(set(item) == {"role", "content", "created_at"} for item in legacy.json())
        assert [item["content"] for item in legacy.json()] == ["先写的后回合", "后写的用户消息", "最后写的前回合回复"]
        response = await client.get(url, params={"limit": 2}, headers=headers())
        assert response.status_code == 200, response.text
        page = response.json()
        assert [item["id"] for item in page["items"]] == [ids[2], ids[0]]
        older = await client.get(url, params={"limit": 2, "cursor": page["next_cursor"]}, headers=headers())
        assert older.status_code == 200, older.text
        previous = older.json()
        assert [item["id"] for item in previous["items"]] == [ids[1]]
        assert previous["next_cursor"] is None
        combined = previous["items"] + page["items"]
        assert [item["id"] for item in combined] == [ids[1], ids[2], ids[0]]
        assert len({item["id"] for item in combined}) == 3
    workspace(check)


def test_retry_precheck_unavailable_is_unchanged_and_spy_releases_transaction(workspace, monkeypatch):
    async def check(client, factory, active):
        pid, _ = await profile(client)
        sid = (await create(client, pid))["session_id"]
        await pending(factory, sid, pid)
        url = f"/api/sessions/{sid}/requests/request"
        body = {"expected_attempt": 2, "expected_state_version": 0}
        class Guard:
            @property
            def retry_turn(self):
                raise AssertionError("不得先于 owner 校验访问能力")
        app.state.conversation_service = Guard()
        assert (await client.post(url + "/retry", json=body, headers=headers(2))).status_code == 403
        from app.orchestration.conversation_service import ConversationService
        recovery_service = ConversationService(factory)
        app.state.conversation_service = recovery_service
        before = (await client.get(url, headers=headers())).json()
        del app.state.conversation_service
        response = await client.post(url + "/retry", json=body, headers=headers())
        app.state.conversation_service = recovery_service
        assert response.status_code == 503 and response.json()["detail"]["code"] == "conversation_service_unavailable"
        assert (await client.get(url, headers=headers())).json() == before
        async with factory() as db:
            row = await db.get(ChatRequestTable, (1, sid, "request"))
            assert row.attempt == 2 and row.status == "failed" and row.error_code == "original"
            assert (await db.get(SessionTable, sid)).active_request_id is None
        calls = []
        observed = []
        from contextlib import asynccontextmanager

        import app.api.sessions as sessions_api
        original_observe = sessions_api.observe_http_disconnect
        @asynccontextmanager
        async def observe(request):
            async with original_observe(request) as event:
                observed.append(event)
                yield event
        monkeypatch.setattr(sessions_api, "observe_http_disconnect", observe)
        async def retry_turn(**kwargs):
            assert all(not db.in_transaction() for db in active)
            assert isinstance(kwargs["disconnect_event"], asyncio.Event)
            calls.append(kwargs)
            return {"reply": "仅契约 spy", "session_id": sid, "persisted": False}
        app.state.conversation_service = SimpleNamespace(retry_turn=retry_turn, recover_session_requests=recovery_service.recover_session_requests)
        response = await client.post(url + "/retry", json=body, headers=headers())
        assert response.status_code == 200 and response.json()["persisted"] is False
        assert calls == [{"user_id": 1, "session_id": sid, "request_id": "request", **body,
            "disconnect_event": observed[0]}]
        assert (await client.get(url, headers=headers())).json() == before
        assert (await client.post(url + "/retry", json={**body, "expected_attempt": 1}, headers=headers())).status_code == 409
        async with factory() as db:
            await db.execute(update(SessionTable).where(SessionTable.id == sid).values(active_request_id="request"))
            await db.commit()
        assert (await client.post(url + "/retry", json=body, headers=headers())).json()["detail"]["code"] == "session_busy"
        assert len(observed) == 1
    workspace(check)


def test_failed_snapshot_does_not_enter_workspace(workspace):
    async def check(client, factory, active):
        async with factory() as db:
            db.add(SessionTable(id='broken-first', user_id=1, state_json='broken'))
            await db.commit()
        response = await client.get('/api/sessions/broken-first/snapshot', headers=headers())
        assert response.status_code == 409
        async with factory() as db:
            assert not (await db.get(SessionTable, 'broken-first')).workspace_entered
            from app.models.workspace_tables import TopicProfileTable
            assert (await db.scalars(select(TopicProfileTable))).all() == []
    workspace(check)


def test_legacy_null_title_in_snapshot_and_groups(workspace):
    async def check(client, factory, active):
        async with factory() as db:
            db.add(SessionTable(id='null-title', user_id=1, state_json='{}'))
            await db.flush()
            await db.execute(update(SessionTable).where(SessionTable.id == 'null-title').values(title=None))
            await db.commit()
        snap = await client.get('/api/sessions/null-title/snapshot', headers=headers())
        assert snap.status_code == 200 and snap.json()['session']['title'] == ''
        groups = await client.get('/api/sessions', params={'group_by':'profile'}, headers=headers())
        assert groups.status_code == 200
        assert next(item for group in groups.json()['groups'] for item in group['sessions'] if item['session_id'] == 'null-title')['title'] == ''
    workspace(check)


def test_legacy_unbound_snapshot_then_new_request(workspace, monkeypatch):
    from app.orchestration.assembly import NewStackResult
    async def check(client, factory, active):
        import app.api.chat as chat_module
        monkeypatch.setattr(chat_module, 'async_session', factory)
        async with factory() as db:
            db.add(SessionTable(id='old-unbound', user_id=1, state_json='{}'))
            await db.commit()
        snapshot = await client.get('/api/sessions/old-unbound/snapshot', headers=headers())
        assert snapshot.status_code == 200
        pid = snapshot.json()['session']['profile_id']
        assert pid and snapshot.json()['profile']['kind'] == 'legacy'
        assert (await client.post('/api/chat', headers=headers(), json={'session_id':'old-unbound','message':'old'})).status_code == 409
        app.state.conversation_service.runner = lambda *args: NewStackResult(reply='ok', mastery_score=None, turn_count=1, mode_path=[], cost_est_usd=None)
        response = await client.post('/api/chat', headers=headers(), json={'session_id':'old-unbound','message':'new', 'request_id':'new', 'profile_id':pid, 'expected_state_version':0})
        assert response.status_code == 200 and response.json()['status'] == 'completed' and response.json()['persisted']
    workspace(check)
