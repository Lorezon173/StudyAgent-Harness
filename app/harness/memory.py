from dataclasses import dataclass

from app.harness.enums import MemoryScope


@dataclass
class MemoryItem:
    content: str
    source: str
    scope: MemoryScope
    score: float = 0.0
    metadata: dict | None = None


class MemoryManager:
    def __init__(self):
        self._store: dict[str, MemoryItem] = {}

    def recall(self, query: str, user_id: int | None,
               scopes: list[MemoryScope]) -> list[MemoryItem]:
        results = [
            item for item in self._store.values()
            if item.scope in scopes and query.lower() in item.content.lower()
        ]
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def memorize(self, content: str, scope: MemoryScope,
                 user_id: int | None = None, metadata: dict | None = None) -> str:
        item_id = f"{scope.value}_{len(self._store)}"
        self._store[item_id] = MemoryItem(
            content=content,
            source=f"user_{user_id or 'anon'}",
            scope=scope,
            metadata=metadata,
        )
        return item_id
