"""私有文本卡片：真实 JWT、每请求会话与独立连接持久化。"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.tables import UserTable
from app.models.workspace_tables import TopicProfileTable


@pytest_asyncio.fixture
async def library(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'library.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add_all([UserTable(id=i, username=f"user{i}", password_hash="x") for i in (1, 2)])
        await db.flush()
        db.add_all([TopicProfileTable(id=f"profile{i}", user_id=i, name=f"主题{i}") for i in (1, 2)])
        await db.commit()

    async def override_db():
        async with factory() as db:
            yield db

    original = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    headers = {i: {"Authorization": f"Bearer {create_access_token(i)}"} for i in (1, 2)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, headers, factory
    finally:
        if original is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original
        await engine.dispose()


async def create(client, headers, **fields):
    response = await client.post("/api/knowledge", headers=headers, json={"name": "卡片", **fields})
    assert response.status_code == 200, response.text
    return response.json()


async def read_item_independently(database_url, item_id):
    """使用另一个 engine 的新物理连接验证已提交文件数据。"""
    engine = create_async_engine(database_url, poolclass=NullPool)

    @event.listens_for(engine.sync_engine, "connect")
    def enable_fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        async with engine.connect() as connection:
            assert (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one() == 1
            row = (await connection.execute(text(
                "SELECT id,name,description,content_text,profile_id FROM library_items WHERE id=:id"
            ), {"id": item_id})).mappings().one_or_none()
            return dict(row) if row is not None else None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_all_endpoints_require_real_authentication(library):
    client, _, _ = library
    for method, path, body in [
        ("GET", "", None), ("POST", "", {"name": "x"}),
        ("GET", "/1", None), ("PATCH", "/1", {"name": "x"}), ("DELETE", "/1", None),
    ]:
        assert (await client.request(method, "/api/knowledge" + path, json=body)).status_code == 401
    assert (await client.get("/api/knowledge", headers={"Authorization": f"Bearer {create_access_token(999)}"})).status_code == 401


@pytest.mark.asyncio
async def test_crud_persists_with_fresh_connections_and_patch_preserves_fields(library):
    client, headers, factory = library
    database_url = factory.kw["bind"].url
    item = await create(client, headers[1], name="  算法  ", description="说明", content_text="正文", profile_id="profile1")
    assert item["name"] == "算法"
    assert item["user_id"] == 1 and item["source_type"] == "manual"
    assert item["created_at"] and item["updated_at"]
    kid = item["id"]
    created = await read_item_independently(database_url, kid)
    assert created == {"id": kid, "name": "算法", "description": "说明", "content_text": "正文", "profile_id": "profile1"}
    response = await client.patch(f"/api/knowledge/{kid}", headers=headers[1], json={"name": "新名称", "profile_id": None})
    assert response.status_code == 200
    assert response.json()["description"] == "说明" and response.json()["content_text"] == "正文"
    updated = await read_item_independently(database_url, kid)
    assert updated == {"id": kid, "name": "新名称", "description": "说明", "content_text": "正文", "profile_id": None}
    assert (await client.get(f"/api/knowledge/{kid}", headers=headers[1])).json() == response.json()
    assert (await client.delete(f"/api/knowledge/{kid}", headers=headers[1])).json() == {"status": "ok"}
    assert await read_item_independently(database_url, kid) is None
    async with factory() as db:
        assert (await db.execute(text("SELECT COUNT(*) FROM library_items"))).scalar_one() == 0
    assert (await client.get(f"/api/knowledge/{kid}", headers=headers[1])).status_code == 404


@pytest.mark.asyncio
async def test_owner_scope_and_invalid_profile_never_partially_update(library):
    client, headers, factory = library
    item = await create(client, headers[2], profile_id="profile2", description="秘密")
    kid = item["id"]
    assert (await client.get("/api/knowledge", headers=headers[1])).json() == []
    for method in ("GET", "PATCH", "DELETE"):
        kwargs = {"json": {"name": "篡改"}} if method == "PATCH" else {}
        assert (await client.request(method, f"/api/knowledge/{kid}", headers=headers[1], **kwargs)).status_code == 404
        assert (await client.request(method, "/api/knowledge/9999", headers=headers[1], **kwargs)).status_code == 404
    for profile in ("profile1", "missing"):
        assert (await client.post("/api/knowledge", headers=headers[2], json={"name": "bad", "profile_id": profile})).status_code == 404
        assert (await client.patch(f"/api/knowledge/{kid}", headers=headers[2], json={"name": "篡改", "profile_id": profile})).status_code == 404
    async with factory() as db:
        assert (await db.execute(text("SELECT name,profile_id FROM library_items"))).one() == ("卡片", "profile2")
        with pytest.raises(IntegrityError):
            await db.execute(text("INSERT INTO library_items(user_id,profile_id,name) VALUES (1,'profile2','绕过API')"))
        await db.rollback()


@pytest.mark.parametrize("field,value", [("user_id", 2), ("id", 99), ("source_type", "manual"), ("source_type", "uploaded"), ("source_type", "indexed")])
@pytest.mark.asyncio
async def test_readonly_body_fields_are_rejected_without_writes(library, field, value):
    client, headers, factory = library
    item = await create(client, headers[1])
    assert (await client.post("/api/knowledge", headers=headers[1], json={"name": "伪造", field: value})).status_code == 422
    assert (await client.patch(f"/api/knowledge/{item['id']}", headers=headers[1], json={"name": "篡改", field: value})).status_code == 422
    async with factory() as db:
        assert (await db.execute(text("SELECT user_id,name,source_type FROM library_items"))).all() == [(1, "卡片", "manual")]


@pytest.mark.parametrize("body", [
    {"name": " "}, {"name": "x" * 129}, {"name": None}, {"name": 123},
    {"description": "x" * 2001}, {"description": None}, {"description": 123},
    {"content_text": "x" * 100001}, {"content_text": None}, {"content_text": []},
    {"profile_id": "x" * 37}, {"profile_id": 123}, {"unknown": "x"},
])
@pytest.mark.asyncio
async def test_input_validation_rejects_invalid_fields(library, body):
    client, headers, factory = library
    item = await create(client, headers[1])
    assert (await client.post("/api/knowledge", headers=headers[1], json={"name": "x", **body})).status_code == 422
    assert (await client.patch(f"/api/knowledge/{item['id']}", headers=headers[1], json=body)).status_code == 422
    async with factory() as db:
        assert (await db.execute(text("SELECT name,description,content_text FROM library_items"))).all() == [("卡片", "", "")]


@pytest.mark.asyncio
async def test_boundary_lengths_and_empty_patch(library):
    client, headers, _ = library
    item = await create(client, headers[1], name="x" * 128, description="d" * 2000, content_text="c" * 100000)
    assert len(item["content_text"]) == 100000
    assert (await client.patch(f"/api/knowledge/{item['id']}", headers=headers[1], json={})).status_code == 422


@pytest.mark.asyncio
async def test_literal_search_owner_profile_filters_and_stable_id_pagination(library):
    client, headers, factory = library
    items = []
    for fields in [{"name": "a%b"}, {"description": "a_b"}, {"content_text": "a\\b"}, {"name": "普通", "profile_id": "profile1"}, {"name": "最后"}]:
        items.append(await create(client, headers[1], **fields))
    await create(client, headers[2], name="a%b", description="a_b", content_text="a\\b", profile_id="profile2")
    async with factory() as db:
        await db.execute(text("UPDATE library_items SET updated_at=:at"), {"at": "2026-01-01 00:00:00"})
        await db.commit()
    async with factory() as db:
        assert (await db.execute(text("SELECT DISTINCT updated_at FROM library_items"))).scalars().all() == ["2026-01-01 00:00:00"]
    for query, expected in [("%", items[0]), ("_", items[1]), ("\\", items[2])]:
        result = await client.get("/api/knowledge", headers=headers[1], params={"q": query})
        assert [r["id"] for r in result.json()] == [expected["id"]]
    assert (await client.get("/api/knowledge", headers=headers[1], params={"profile_id": "profile2", "q": "%"})).json() == []
    assert [r["id"] for r in (await client.get("/api/knowledge", headers=headers[1], params={"profile_id": "profile1"})).json()] == [items[3]["id"]]
    found, before = [], None
    while True:
        params = {"limit": 2}
        if before:
            params["before_id"] = before
        page = (await client.get("/api/knowledge", headers=headers[1], params=params)).json()
        found.extend(r["id"] for r in page)
        if len(page) < 2:
            break
        before = page[-1]["id"]
        await client.patch(f"/api/knowledge/{page[0]['id']}", headers=headers[1], json={"description": "编辑不改变游标"})
    assert found == [r["id"] for r in reversed(items)]
    for params in ({"q": "x" * 257}, {"limit": 0}, {"limit": 101}, {"before_id": 0}):
        assert (await client.get("/api/knowledge", headers=headers[1], params=params)).status_code == 422


@pytest.mark.asyncio
async def test_write_failure_rolls_back_entire_api_transaction(library):
    client, headers, factory = library
    item = await create(client, headers[1], description="原说明")
    async with factory() as db:
        await db.execute(text("CREATE TRIGGER reject_library_update AFTER UPDATE ON library_items BEGIN SELECT RAISE(ABORT, 'injected write failure'); END"))
        await db.commit()
    with pytest.raises(IntegrityError):
        await client.patch(f"/api/knowledge/{item['id']}", headers=headers[1], json={"name": "失败修改", "description": "失败说明"})
    async with factory() as db:
        assert (await db.execute(text("SELECT name,description FROM library_items"))).one() == ("卡片", "原说明")


@pytest.mark.asyncio
async def test_store_keeps_caller_transaction_and_checks_profile_owner(library):
    from app.infrastructure.storage.library_store import LibraryStore

    _, _, factory = library
    async with factory() as db:
        store = LibraryStore(db)
        with pytest.raises(PermissionError):
            await store.create(1, {"name": "非法", "profile_id": "profile2"})
        item = await store.create(1, {"name": "待提交"})
        kid = item.id
        async with factory() as fresh:
            assert (await fresh.execute(text("SELECT COUNT(*) FROM library_items"))).scalar_one() == 0
        await db.rollback()
    async with factory() as db:
        item = await LibraryStore(db).create(1, {"name": "原名"})
        kid = item.id
        await db.commit()
    async with factory() as db:
        store = LibraryStore(db)
        with pytest.raises(PermissionError):
            await store.update(1, kid, {"name": "篡改", "profile_id": "profile2"})
        assert (await store.get(1, kid)).name == "原名"
        assert await store.get(2, kid) is None
        assert await store.update(2, kid, {"name": "篡改"}) is None
        assert await store.delete(2, kid) is False
        await store.update(1, kid, {"name": "待提交修改"})
        await db.rollback()
    async with factory() as db:
        assert (await LibraryStore(db).get(1, kid)).name == "原名"
        assert await LibraryStore(db).delete(1, kid) is True
        await db.rollback()
    async with factory() as fresh:
        assert (await fresh.execute(text("SELECT name FROM library_items"))).scalar_one() == "原名"


@pytest.mark.asyncio
async def test_api_writes_commit_once_and_failed_commit_rolls_back(library, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    client, headers, factory = library
    commit = AsyncSession.commit
    counts = {"commit": 0, "rollback": 0}
    rollback = AsyncSession.rollback

    async def counted_commit(db):
        counts["commit"] += 1
        await commit(db)

    async def counted_rollback(db):
        counts["rollback"] += 1
        await rollback(db)

    monkeypatch.setattr(AsyncSession, "commit", counted_commit)
    monkeypatch.setattr(AsyncSession, "rollback", counted_rollback)
    item = await create(client, headers[1])
    assert counts == {"commit": 1, "rollback": 0}
    assert (await client.patch(f"/api/knowledge/{item['id']}", headers=headers[1], json={"name": "已修改"})).status_code == 200
    assert counts == {"commit": 2, "rollback": 0}
    assert (await client.delete(f"/api/knowledge/{item['id']}", headers=headers[1])).status_code == 200
    assert counts == {"commit": 3, "rollback": 0}

    async def failed_commit(db):
        raise RuntimeError("injected commit failure")

    monkeypatch.setattr(AsyncSession, "commit", failed_commit)
    with pytest.raises(RuntimeError, match="injected commit failure"):
        await client.post("/api/knowledge", headers=headers[1], json={"name": "不可保存"})
    assert counts["rollback"] == 1
    async with factory() as fresh:
        assert (await fresh.execute(text("SELECT COUNT(*) FROM library_items"))).scalar_one() == 0
