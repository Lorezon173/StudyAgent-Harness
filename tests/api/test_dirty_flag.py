import pytest
from unittest.mock import patch
from app.api._dirty_flag import DirtyFlag


@pytest.fixture(autouse=True)
def cleanup_dirty_flag():
    """每个测试前后清理 dirty flag 状态"""
    DirtyFlag._reset()
    yield
    DirtyFlag._reset()


def test_mark_dirty_adds_user():
    """标记 user 为 dirty 后 is_dirty 返回 True"""
    assert not DirtyFlag.is_dirty(1)

    DirtyFlag.mark_dirty(1)
    assert DirtyFlag.is_dirty(1)


def test_clear_dirty_removes_user():
    """清除 dirty 标志后 is_dirty 返回 False"""
    DirtyFlag.mark_dirty(2)
    assert DirtyFlag.is_dirty(2)

    DirtyFlag.clear_dirty(2)
    assert not DirtyFlag.is_dirty(2)


def test_clear_dirty_idempotent():
    """重复 clear 不报错"""
    DirtyFlag.clear_dirty(3)
    DirtyFlag.clear_dirty(3)  # 应该不抛异常
    assert not DirtyFlag.is_dirty(3)


def test_multiple_users_independent():
    """多个 user 的 dirty 状态独立"""
    DirtyFlag.mark_dirty(10)
    assert DirtyFlag.is_dirty(10)
    assert not DirtyFlag.is_dirty(11)


def test_ttl_expiration():
    """TTL 过期后 is_dirty 返回 False"""
    # 模拟时间：先标记为 dirty，然后让时间前进超过 TTL
    with patch('app.api._dirty_flag.time.time') as mock_time:
        mock_time.return_value = 1000.0  # 初始时间
        DirtyFlag.mark_dirty(4, ttl=0.1)  # 0.1秒TTL
        assert DirtyFlag.is_dirty(4)

        # 时间前进 0.15 秒，超过 TTL
        mock_time.return_value = 1000.15
        assert not DirtyFlag.is_dirty(4)  # 过期后自动清理


def test_cleanup_expired():
    """cleanup_expired 清理所有过期条目"""
    with patch('app.api._dirty_flag.time.time') as mock_time:
        mock_time.return_value = 1000.0
        DirtyFlag.mark_dirty(5, ttl=0.1)
        DirtyFlag.mark_dirty(6, ttl=0.1)
        DirtyFlag.mark_dirty(7, ttl=3600)  # 不过期

        # 时间前进 0.15 秒
        mock_time.return_value = 1000.15

        cleaned = DirtyFlag.cleanup_expired()
        assert cleaned == 2
        assert not DirtyFlag.is_dirty(5)
        assert not DirtyFlag.is_dirty(6)
        assert DirtyFlag.is_dirty(7)


def test_mark_dirty_validates_ttl():
    """mark_dirty 验证 TTL 必须为正数"""
    with pytest.raises(ValueError, match="ttl must be positive"):
        DirtyFlag.mark_dirty(8, ttl=0)

    with pytest.raises(ValueError, match="ttl must be positive"):
        DirtyFlag.mark_dirty(9, ttl=-1)


def test_persist_failure_marks_dirty_user(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api._persist import persist_turn

            class BoomGraph:
                async def save(self):
                    raise RuntimeError("boom")

            async with session_factory() as db:
                result = await persist_turn(
                    db,
                    session_id="dirty-session",
                    user_id=42,
                    user_message="x",
                    reply="y",
                    graph=BoomGraph(),
                )
                assert result is None
                assert DirtyFlag.is_dirty(42) is True
        finally:
            await engine.dispose()

    db_fixture.run(_test())
