from app.infrastructure.storage.session_store import SessionStore


class EvalStore:
    """评估结果存储"""

    def __init__(self):
        self._evals: dict[int, dict] = {}
        self._next_id = 1

    async def save(self, session_id: str, eval_data: dict) -> int:
        eid = self._next_id
        self._next_id += 1
        self._evals[eid] = {"session_id": session_id, **eval_data}
        return eid

    async def get(self, eval_id: int) -> dict | None:
        return self._evals.get(eval_id)

    async def list_by_session(self, session_id: str) -> list[dict]:
        return [e for e in self._evals.values() if e.get("session_id") == session_id]
