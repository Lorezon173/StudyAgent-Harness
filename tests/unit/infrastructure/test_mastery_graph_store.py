import asyncio
import tempfile
import os

from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


async def _make_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MasteryGraphStore(db_path=path)
    await store.init()
    return store, path


def test_store_init_creates_tables():
    async def _test():
        store, path = await _make_store()
        await store._db.execute("SELECT 1 FROM mastery_nodes LIMIT 0")
        await store._db.execute("SELECT 1 FROM mastery_edges LIMIT 0")
        await store._db.execute("SELECT 1 FROM user_profile_l3 LIMIT 0")
        await store.close()
        os.unlink(path)
    asyncio.run(_test())