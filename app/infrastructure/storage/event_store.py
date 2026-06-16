import json
import sqlite3
from pathlib import Path

from app.harness.events import Event
from app.harness.enums import EventType, EventSource


class EventStore:
    """事件持久化 + 回放（§3.1）。

    用同步 sqlite3：协作环是单线程同步事件循环（§3.5），EventStore.append 在
    循环内被调用，同步实现最契合、零异步开销。回放按 id 升序 —— id 是时序可排
    ULID，故等价于全序时序回放（满足 §5 replay 需求）。
    """

    def __init__(self, db_path: str = "data/events.db"):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def init(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                ts REAL NOT NULL,
                session_id TEXT NOT NULL,
                source TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT DEFAULT '{}',
                parent_id TEXT,
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);
        """)
        self._conn.commit()

    def append(self, event: Event) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO events
               (id, ts, session_id, source, type, payload, parent_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.id, event.ts, event.session_id, str(event.source),
             str(event.type), json.dumps(event.payload), event.parent_id,
             json.dumps(event.metadata)),
        )
        self._conn.commit()

    def replay(self, session_id: str) -> list[Event]:
        rows = self._conn.execute(
            """SELECT id, ts, session_id, source, type, payload, parent_id, metadata
               FROM events WHERE session_id = ? ORDER BY id ASC""",
            (session_id,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row) -> Event:
        return Event(
            id=row[0], ts=row[1], session_id=row[2],
            source=EventSource(row[3]), type=EventType(row[4]),
            payload=json.loads(row[5]), parent_id=row[6],
            metadata=json.loads(row[7]),
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
