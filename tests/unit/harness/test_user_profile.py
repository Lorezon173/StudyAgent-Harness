import asyncio
import tempfile
import os

from app.harness.user_profile import UserProfile
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


async def _make_profile(user_id: str = "user_test"):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MasteryGraphStore(db_path=path)
    await store.init()
    profile = UserProfile(user_id=user_id, store=store)
    return profile, store, path


def test_user_profile_defaults():
    async def _test():
        profile, store, path = await _make_profile()
        assert profile.user_id == "user_test"
        assert profile.preferences == {"explanation_style": "verbal", "pace": "normal", "depth": "standard"}
        assert profile.topics_active == []
        assert profile.topics_mastered == []
        assert profile.learning_streak == 0
        assert profile.total_sessions == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_update_preferences():
    async def _test():
        profile, store, path = await _make_profile()
        profile.update_preferences(explanation_style="visual", pace="slow")
        assert profile.preferences["explanation_style"] == "visual"
        assert profile.preferences["pace"] == "slow"
        assert profile.preferences["depth"] == "standard"  # 未改的保持默认
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_sync_from_mastery_graph():
    async def _test():
        profile, store, path = await _make_profile()
        mastery_data = {"linear_algebra": 0.9, "calculus": 0.85, "attention": 0.3}
        profile.sync_from_mastery(mastery_data, mastered_threshold=0.8)
        assert "linear_algebra" in profile.topics_mastered
        assert "calculus" in profile.topics_mastered
        assert "attention" not in profile.topics_mastered
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_increment_session():
    async def _test():
        profile, store, path = await _make_profile()
        assert profile.total_sessions == 0
        profile.increment_session()
        assert profile.total_sessions == 1
        assert profile.learning_streak == 1
        profile.increment_session()
        assert profile.total_sessions == 2
        assert profile.learning_streak == 2
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_profile_persist_roundtrip():
    async def _test():
        profile, store, path = await _make_profile()
        profile.update_preferences(explanation_style="mathematical", depth="deep")
        profile.sync_from_mastery({"linear_algebra": 0.9}, mastered_threshold=0.8)
        profile.increment_session()
        await profile.save()
        profile2 = UserProfile(user_id="user_test", store=store)
        await profile2.load()
        assert profile2.preferences["explanation_style"] == "mathematical"
        assert profile2.preferences["depth"] == "deep"
        assert "linear_algebra" in profile2.topics_mastered
        assert profile2.total_sessions == 1
        assert profile2.learning_streak == 1
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
