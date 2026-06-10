from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import MessageTable


class MessageStore:
    """Dual-mode message store: DB-backed when db is provided, in-memory otherwise."""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db
        self._memory: list[dict] = []
        self._next_id = 1

    async def add(self, session_id: str, role: str, content: str, turn_index: int) -> int:
        """Insert a message row.

        Does NOT commit (C3: caller commits). Uses flush to obtain the id.
        In memory mode, assigns an incrementing id and appends to the list.
        """
        if self.db:
            row = MessageTable(
                session_id=session_id,
                role=role,
                content=content,
                turn_index=turn_index,
            )
            self.db.add(row)
            await self.db.flush()
            return row.id
        else:
            msg_id = self._next_id
            self._next_id += 1
            self._memory.append({
                "id": msg_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "turn_index": turn_index,
                "created_at": datetime.now(timezone.utc),
            })
            return msg_id

    async def list_by_session(self, session_id: str) -> list[dict]:
        """Return messages for a session, ordered by id ascending (R2).

        Returns a list of dicts with keys: {role, content, turn_index, created_at}.
        """
        if self.db:
            result = await self.db.execute(
                select(MessageTable)
                .where(MessageTable.session_id == session_id)
                .order_by(MessageTable.id.asc())
            )
            return [
                {
                    "role": r.role,
                    "content": r.content,
                    "turn_index": r.turn_index,
                    "created_at": r.created_at,
                }
                for r in result.scalars().all()
            ]
        else:
            return [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "turn_index": m["turn_index"],
                    "created_at": m["created_at"],
                }
                for m in sorted(self._memory, key=lambda x: x["id"])
                if m["session_id"] == session_id
            ]
