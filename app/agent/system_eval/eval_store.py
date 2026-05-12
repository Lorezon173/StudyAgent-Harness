class EvalStore:
    """系统评估结果存储"""

    def __init__(self):
        self._results: dict[str, dict] = {}

    def save(self, session_id: str, results: dict):
        self._results[session_id] = results

    def get(self, session_id: str) -> dict | None:
        return self._results.get(session_id)
