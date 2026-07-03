import threading
from collections import OrderedDict

from app.infrastructure.storage.session_store import SessionStore

_MAX_EVALS = 1000


class EvalStore:
    """评估结果存储（线程安全，LRU 淘汰最近 1000 条）"""

    def __init__(self):
        self._evals: OrderedDict[int, dict] = OrderedDict()
        self._next_id = 1
        self._lock = threading.Lock()

    async def save(self, session_id: str, eval_data: dict) -> int:
        with self._lock:
            eid = self._next_id
            self._next_id += 1
            self._evals[eid] = {"session_id": session_id, **eval_data}
            if len(self._evals) > _MAX_EVALS:
                self._evals.popitem(last=False)
            return eid

    async def get(self, eval_id: int) -> dict | None:
        with self._lock:
            return self._evals.get(eval_id)

    async def list_by_session(self, session_id: str) -> list[dict]:
        with self._lock:
            return [e for e in self._evals.values() if e.get("session_id") == session_id]
