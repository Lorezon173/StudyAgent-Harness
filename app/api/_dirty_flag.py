"""Dirty-flag 故障恢复机制（批次一：内存实现）。

persist_turn 失败时标记 user_id 为 dirty，下次 load 强制从 DB 重建。
批次一用内存 Dict + Lock（支持多线程单进程），将来迁 PG 多进程时改为 DB 字段。
"""

import threading
import time
from typing import Dict, Tuple

_dirty_users: Dict[str, Tuple[float, float]] = {}  # {user_id: (mark_time, ttl)}
_lock = threading.Lock()
_DEFAULT_TTL = 3600  # 1小时TTL


class DirtyFlag:
    """Dirty-flag 接口（阶段一：内存 Dict；阶段二：DB 字段）。"""

    @staticmethod
    def mark_dirty(user_id: str, ttl: float = _DEFAULT_TTL) -> None:
        """标记 user 为 dirty（persist 失败时调用）。

        Args:
            user_id: 用户ID
            ttl: 过期时间（秒），默认1小时，必须大于0

        Raises:
            ValueError: 如果 ttl <= 0
        """
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        with _lock:
            _dirty_users[user_id] = (time.time(), ttl)

    @staticmethod
    def is_dirty(user_id: str) -> bool:
        """检查 user 是否 dirty（load 前调用）。

        自动清理过期条目。
        """
        with _lock:
            if user_id not in _dirty_users:
                return False
            mark_time, ttl = _dirty_users[user_id]
            if time.time() - mark_time > ttl:
                del _dirty_users[user_id]
                return False
            return True

    @staticmethod
    def clear_dirty(user_id: str) -> None:
        """清除 dirty 标志（persist 成功时调用）。"""
        with _lock:
            _dirty_users.pop(user_id, None)

    @staticmethod
    def cleanup_expired() -> int:
        """清理所有过期条目，返回清理数量。

        可由定时任务调用。
        """
        with _lock:
            now = time.time()
            expired = [uid for uid, (mark_time, ttl) in _dirty_users.items()
                      if now - mark_time > ttl]
            for uid in expired:
                del _dirty_users[uid]
            return len(expired)

    @staticmethod
    def _reset() -> None:
        """重置所有状态（仅用于测试）。"""
        with _lock:
            _dirty_users.clear()
