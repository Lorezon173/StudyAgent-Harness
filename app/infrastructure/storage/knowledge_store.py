class KnowledgeStore:
    """知识库 CRUD 存储"""

    def __init__(self):
        self._items: dict[int, dict] = {}
        self._next_id = 1

    async def create(self, name: str, description: str = "", user_id: int | None = None) -> int:
        kid = self._next_id
        self._next_id += 1
        self._items[kid] = {"id": kid, "name": name, "description": description, "user_id": user_id}
        return kid

    async def get(self, knowledge_id: int) -> dict | None:
        return self._items.get(knowledge_id)

    async def list_all(self) -> list[dict]:
        return list(self._items.values())

    async def delete(self, knowledge_id: int) -> bool:
        if knowledge_id in self._items:
            del self._items[knowledge_id]
            return True
        return False
