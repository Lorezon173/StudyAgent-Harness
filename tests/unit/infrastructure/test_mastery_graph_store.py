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


def test_save_and_load_nodes():
    async def _test():
        store, path = await _make_store()
        nodes = [
            {"topic_id": "linear_algebra", "topic_name": "线性代数", "mastery": 0.8,
             "last_practiced_at": 1717200000.0, "practice_count": 5,
             "confusion_with": []},
            {"topic_id": "attention", "topic_name": "注意力机制", "mastery": 0.2,
             "last_practiced_at": 1717200100.0, "practice_count": 1,
             "confusion_with": ["self_attention"]},
        ]
        await store.save_nodes("user_1", nodes)
        loaded = await store.load_nodes("user_1")
        assert len(loaded) == 2
        assert loaded["linear_algebra"]["mastery"] == 0.8
        assert loaded["linear_algebra"]["practice_count"] == 5
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_save_and_load_edges():
    async def _test():
        store, path = await _make_store()
        edges = [
            {"from_topic": "linear_algebra", "to_topic": "attention",
             "type": "PREREQ", "weight": 1.0, "confidence": 0.5, "source": "DOC_ORDER"},
            {"from_topic": "attention", "to_topic": "transformer",
             "type": "PREREQ", "weight": 1.0, "confidence": 0.3, "source": "LLM_INFER"},
        ]
        await store.save_edges("user_1", edges)
        loaded = await store.load_edges("user_1")
        assert len(loaded) == 2
        assert loaded[0]["from_topic"] == "linear_algebra"
        assert loaded[0]["confidence"] == 0.5
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_save_and_load_profile():
    async def _test():
        store, path = await _make_store()
        await store.save_profile("user_1", {
            "preferences": {"explanation_style": "visual", "pace": "slow", "depth": "standard"},
            "topics_active": ["attention"],
            "topics_mastered": ["linear_algebra"],
            "learning_streak": 3,
            "total_sessions": 10,
        })
        loaded = await store.load_profile("user_1")
        assert loaded is not None
        assert loaded["preferences"]["explanation_style"] == "visual"
        assert loaded["learning_streak"] == 3
        assert loaded["topics_mastered"] == ["linear_algebra"]
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_load_nonexistent_user_returns_defaults():
    async def _test():
        store, path = await _make_store()
        nodes = await store.load_nodes("ghost_user")
        assert nodes == {}
        edges = await store.load_edges("ghost_user")
        assert edges == []
        profile = await store.load_profile("ghost_user")
        assert profile is None
        await store.close()
        os.unlink(path)
    asyncio.run(_test())