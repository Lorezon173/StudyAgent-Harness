"""真实 JWT、FK SQLite 验证主题画像的归属、版本和真实指标。"""
import asyncio
import base64
import json
from datetime import datetime
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.tables import MessageTable, SessionTable, UserTable
from app.models.workspace_tables import (ChatRequestTable, ProfileEvidenceTable,
                                        ProfileNodeTable, TopicProfileTable)


@pytest.fixture
def profiles(tmp_path):
    async def run(check):
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'profiles-api.db'}")

        @event.listens_for(engine.sync_engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add_all([UserTable(id=1, username="one", password_hash="x"),
                        UserTable(id=2, username="two", password_hash="x")])
            await db.commit()

        async def override_db():
            async with factory() as db:
                yield db
        original = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                await check(client, factory)
        finally:
            if original is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = original
            await engine.dispose()
    return lambda check: asyncio.run(run(check))


def headers(owner=1):
    return {"Authorization": f"Bearer {create_access_token(owner)}"}


async def create(client, name="通信", owner=1):
    response = await client.post("/api/topic-profiles", json={"name": name, "scope_description": "范围"}, headers=headers(owner))
    assert response.status_code == 200, response.text
    return response.json()


def test_create_uuid_null_nodes_and_versioned_explicit_changes(profiles):
    async def check(client, factory):
        first = await create(client)
        second = await create(client)
        pid, nid = first["profile"]["id"], first["nodes"][0]["id"]
        assert UUID(pid) and UUID(nid)
        assert pid != second["profile"]["id"]
        assert first["profile_revision"] == first["nodes"][0]["revision"] == 0
        assert first["nodes"][0]["mastery"] is None
        assert first["nodes"][0]["title"] == "通信" and first["edges"] == []
        url = f"/api/topic-profiles/{pid}"
        changed = await client.patch(url, json={"expected_revision": 0, "name": " 改名 "}, headers=headers())
        assert changed.status_code == 200, changed.text
        assert changed.json()["profile"]["id"] == pid
        assert changed.json()["profile"]["scope_description"] == "范围"
        node = await client.patch(f"{url}/nodes/{nid}", json={"expected_revision": 1, "title": "节点", "description": ""}, headers=headers())
        assert node.status_code == 200, node.text
        assert node.json()["node"]["id"] == nid and node.json()["node"]["revision"] == 1
        assert node.json()["profile_revision"] == 2
        stale = await client.patch(f"{url}/nodes/{nid}", json={"expected_revision": 1, "title": "覆盖"}, headers=headers())
        assert stale.status_code == 409
        added = await client.post(f"{url}/nodes", json={"expected_revision": 2, "title": "新增"}, headers=headers())
        assert added.status_code == 200, added.text
        assert added.json()["node"]["mastery"] is None
        detail = (await client.get(url, headers=headers())).json()
        assert detail["profile_revision"] == 3 and len(detail["nodes"]) == 2
        assert next(n for n in detail["nodes"] if n["id"] == nid)["title"] == "节点"
    profiles(check)


def test_authentication_owner_and_node_scope(profiles):
    async def check(client, factory):
        assert (await client.get("/api/topic-profiles")).status_code == 401
        own = await create(client)
        other = await create(client, owner=2)
        pid = own["profile"]["id"]
        for suffix in ["", "/summary"]:
            assert (await client.get(f"/api/topic-profiles/{pid}{suffix}", headers=headers(2))).status_code == 404
        assert (await client.patch(f"/api/topic-profiles/{pid}", json={"expected_revision": 999, "name": "x"}, headers=headers(2))).status_code == 404
        assert (await client.post(f"/api/topic-profiles/{pid}/nodes", json={"expected_revision": 0, "title": "x"}, headers=headers(2))).status_code == 404
        response = await client.patch(f"/api/topic-profiles/{pid}/nodes/{other['nodes'][0]['id']}", json={"expected_revision": 0, "title": "x"}, headers=headers())
        assert response.status_code == 404
        assert (await client.get(f"/api/topic-profiles/{pid}", headers=headers())).json()["profile_revision"] == 0
    profiles(check)


@pytest.mark.parametrize("body", [{"name": " "}, {"name": 3}, {"name": None}, {"name": "x", "user_id": 2}, {"name": "x", "revision": 5}])
def test_create_rejects_invalid_and_readonly_fields(profiles, body):
    async def check(client, factory):
        assert (await client.post("/api/topic-profiles", json=body, headers=headers())).status_code == 422
    profiles(check)


@pytest.mark.parametrize("body", [{"expected_revision": 0}, {"expected_revision": True, "title": "x"}, {"expected_revision": -1, "title": "x"}, {"expected_revision": "0", "title": "x"}, {"expected_revision": 0, "title": None}, {"expected_revision": 0, "mastery": 80}, {"expected_revision": 0, "archived": "true"}, {"expected_revision": 0, "practice_count": 2}])
def test_node_patch_rejects_invalid_or_assessment_writes(profiles, body):
    async def check(client, factory):
        item = await create(client)
        response = await client.patch(f"/api/topic-profiles/{item['profile']['id']}/nodes/{item['nodes'][0]['id']}", json=body, headers=headers())
        assert response.status_code == 422, response.text
    profiles(check)


def test_summary_null_mean_coverage_archive_and_real_evidence(profiles):
    async def check(client, factory):
        item = await create(client)
        pid, nid = item["profile"]["id"], item["nodes"][0]["id"]
        url = f"/api/topic-profiles/{pid}"
        unknown = (await client.get(url + "/summary", headers=headers())).json()
        assert unknown["mastery_score"] is None and unknown["assessment_coverage"] == 0
        async with factory() as db:
            node = await db.get(ProfileNodeTable, nid)
            node.mastery = 80
            db.add(ProfileNodeTable(profile_id=pid, title="未评估"))
            db.add(SessionTable(id="s", user_id=1, profile_id=pid, state_json="{}", title="真实会话"))
            await db.flush()
            db.add(ChatRequestTable(user_id=1, session_id="s", request_id="r", profile_id=pid, payload_hash="x", request_payload={}, base_state_version=0, status="completed"))
            msg = MessageTable(session_id="s", role="user", content="真实原文", turn_index=0)
            db.add(msg)
            await db.flush()
            db.add(ProfileEvidenceTable(user_id=1, profile_id=pid, node_id=nid, session_id="s", request_id="r", message_id=msg.id, score=80, rationale="证据"))
            await db.commit()
        summary = (await client.get(url + "/summary", headers=headers())).json()
        assert (summary["mastery_score"], summary["assessed_count"], summary["total_count"], summary["assessment_coverage"]) == (80, 1, 2, .5)
        assert summary["metric_kind"] == "assessed_mean" and summary["edges"] == []
        evidence = summary["recent_evidence"][0]
        assert (evidence["session_id"], evidence["request_id"], evidence["message_id"], evidence["score"]) == ("s", "r", msg.id, 80)
        assert (await client.get(url + "/summary", headers=headers(2))).status_code == 404
        response = await client.patch(f"{url}/nodes/{nid}", json={"expected_revision": 0, "archived": True}, headers=headers())
        assert response.status_code == 200, response.text
        archived = (await client.get(url + "/summary", headers=headers())).json()
        assert archived["mastery_score"] is None and archived["total_count"] == 1
        assert archived["recent_evidence"][0]["id"] == evidence["id"]
        remaining = archived["nodes"][0]["id"]
        await client.patch(f"{url}/nodes/{remaining}", json={"expected_revision": 1, "archived": True}, headers=headers())
        empty = (await client.get(url + "/summary", headers=headers())).json()
        assert (empty["mastery_score"], empty["assessment_coverage"], empty["total_count"], empty["assessed_count"]) == (None, None, 0, 0)
        restored = await client.patch(f"{url}/nodes/{nid}", json={"expected_revision": 2, "archived": False}, headers=headers())
        assert restored.json()["node"]["mastery"] == 80
        assert restored.json()["profile_revision"] == (await client.get(url, headers=headers())).json()["profile_revision"]
    profiles(check)


def test_stable_cursor_and_owner_filter(profiles):
    async def check(client, factory):
        ids = [(await create(client))["profile"]["id"] for _ in range(3)]
        other = await create(client, owner=2)
        async with factory() as db:
            rows = (await db.scalars(select(TopicProfileTable))).all()
            for row in rows:
                row.created_at = datetime(2026, 1, 1)
            await db.commit()
        first = (await client.get("/api/topic-profiles?limit=2", headers=headers())).json()
        assert [p["id"] for p in first["items"]] == sorted(ids, reverse=True)[:2]
        second = (await client.get("/api/topic-profiles", params={"limit": 2, "cursor": first["next_cursor"]}, headers=headers())).json()
        assert [p["id"] for p in second["items"]] == sorted(ids, reverse=True)[2:]
        assert second["next_cursor"] is None
        foreign = (await client.get("/api/topic-profiles", params={"cursor": first["next_cursor"]}, headers=headers(2))).json()
        assert all(p["id"] == other["profile"]["id"] for p in foreign["items"])
        for cursor in ["!", "e30", "WyIyMDI2LTAxLTAxIiwgImJhZCJd"]:
            assert (await client.get("/api/topic-profiles", params={"cursor": cursor}, headers=headers())).status_code == 422
        for limit in [0, 101]:
            assert (await client.get("/api/topic-profiles", params={"limit": limit}, headers=headers())).status_code == 422
    profiles(check)


@pytest.mark.parametrize("form", ["date_only", "padding", "standard_base64"])
def test_cursor_rejects_noncanonical_but_decodable_inputs(profiles, form):
    # 这些载荷都能被旧decoder解析；不能把本来就无效的乱码当规范校验。
    value = {"created_at": "2026-01-01T00:00:00", "id": "00000000-0000-0000-0000-000000000001"}
    if form == "date_only":
        value["created_at"] = "2026-01-01"
    payload = json.dumps(value).encode()
    if form == "standard_base64":
        payload = b"\xef\xbb\xbf" + payload
        cursor = base64.b64encode(payload).decode().rstrip("=")
        assert "/" in cursor or "+" in cursor
    elif form == "padding":
        while len(payload) % 3 == 0:
            payload += b" "
        cursor = base64.urlsafe_b64encode(payload).decode()
        assert cursor.endswith("=")
    else:
        cursor = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
    assert json.loads(decoded) == value
    assert datetime.fromisoformat(value["created_at"]) == datetime(2026, 1, 1)
    assert str(UUID(value["id"])) == value["id"]

    async def check(client, factory):
        response = await client.get("/api/topic-profiles", params={"cursor": cursor}, headers=headers())
        assert response.status_code == 422, response.text
    profiles(check)
