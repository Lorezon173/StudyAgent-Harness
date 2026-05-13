import asyncio
import tempfile
import os

from app.infrastructure.storage.memory_store import MemoryStore
from app.harness.memory import MemoryItem
from app.harness.enums import MemoryScope


async def _make_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MemoryStore(db_path=path)
    await store.init()
    return store, path


def test_memory_store_crud():
    async def _test():
        store, path = await _make_store()
        item = MemoryItem(id="m1", content="二分查找", scope=MemoryScope.USER, source="test")
        mid = await store.store(item, user_id=1)
        assert mid == "m1"
        results = await store.search("二分", [MemoryScope.USER], user_id=1)
        assert len(results) == 1
        assert results[0].content == "二分查找"
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_memory_store_fts_search():
    async def _test():
        store, path = await _make_store()
        await store.store(MemoryItem(id="m1", content="二分查找算法", scope=MemoryScope.USER, source="test"), 1)
        await store.store(MemoryItem(id="m2", content="快速排序算法", scope=MemoryScope.USER, source="test"), 1)
        results = await store.search("二分", [MemoryScope.USER], user_id=1)
        assert len(results) == 1
        assert results[0].id == "m1"
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_memory_store_scope_filter():
    async def _test():
        store, path = await _make_store()
        await store.store(MemoryItem(id="m1", content="test", scope=MemoryScope.USER, source="test"), 1)
        await store.store(MemoryItem(id="m2", content="test", scope=MemoryScope.GLOBAL, source="test"), 1)
        results = await store.search("test", [MemoryScope.USER])
        assert all(r.scope == MemoryScope.USER for r in results)
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_memory_store_summary():
    async def _test():
        store, path = await _make_store()
        sid = await store.store_summary(1, "session", "学习了二分查找", ["m1"])
        assert sid is not None
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_memory_store_user_profile():
    async def _test():
        store, path = await _make_store()
        assert await store.get_user_profile(1) is None
        await store.update_user_profile(1, topics=["算法"], total_sessions=1)
        profile = await store.get_user_profile(1)
        assert profile is not None
        assert profile["topics"] == ["算法"]
        assert profile["total_sessions"] == 1
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
