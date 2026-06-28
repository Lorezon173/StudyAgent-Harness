"""Dirty-flag 故障恢复机制（批次一：内存实现）。

persist_turn 失败时标记 user_id 为 dirty，下次 load 强制从 DB 重建。
批次一用模块级 Set（单进程足够），将来迁 PG 多进程时改为 DB 字段。
"""

_dirty_users: set[str] = set()


class DirtyFlag:
    """Dirty-flag 接口（阶段一：内存 Set；阶段二：DB 字段）。"""

    @staticmethod
    def mark_dirty(user_id: str) -> None:
        """标记 user 为 dirty（persist 失败时调用）。"""
        _dirty_users.add(user_id)

    @staticmethod
    def is_dirty(user_id: str) -> bool:
        """检查 user 是否 dirty（load 前调用）。"""
        return user_id in _dirty_users

    @staticmethod
    def clear_dirty(user_id: str) -> None:
        """清除 dirty 标志（persist 成功时调用）。"""
        _dirty_users.discard(user_id)
