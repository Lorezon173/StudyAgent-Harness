from app.api._dirty_flag import DirtyFlag


def test_mark_dirty_adds_user():
    """标记 user 为 dirty 后 is_dirty 返回 True"""
    DirtyFlag.clear_dirty("user1")  # 清理状态
    assert not DirtyFlag.is_dirty("user1")

    DirtyFlag.mark_dirty("user1")
    assert DirtyFlag.is_dirty("user1")


def test_clear_dirty_removes_user():
    """清除 dirty 标志后 is_dirty 返回 False"""
    DirtyFlag.mark_dirty("user2")
    assert DirtyFlag.is_dirty("user2")

    DirtyFlag.clear_dirty("user2")
    assert not DirtyFlag.is_dirty("user2")


def test_clear_dirty_idempotent():
    """重复 clear 不报错"""
    DirtyFlag.clear_dirty("user3")
    DirtyFlag.clear_dirty("user3")  # 应该不抛异常
    assert not DirtyFlag.is_dirty("user3")


def test_multiple_users_independent():
    """多个 user 的 dirty 状态独立"""
    DirtyFlag.clear_dirty("userA")
    DirtyFlag.clear_dirty("userB")

    DirtyFlag.mark_dirty("userA")
    assert DirtyFlag.is_dirty("userA")
    assert not DirtyFlag.is_dirty("userB")
