import json
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.harness.enums import MemoryScope
from app.harness.memory import MemoryItem


class MemoryStore:
    """SQLite 持久化存储 — 长期记忆"""

    def __init__(self, db_path: str = "data/memory.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                scope TEXT NOT NULL,
                source TEXT,
                score REAL DEFAULT 0,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                accessed_at TEXT,
                access_count INTEGER DEFAULT 0,
                user_id INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_scope ON memory_entries(scope);
            CREATE INDEX IF NOT EXISTS idx_user ON memory_entries(user_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                USING fts5(id, content, tags, tokenize="trigram");
            CREATE TABLE IF NOT EXISTS memory_summaries (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                scope TEXT NOT NULL,
                summary TEXT NOT NULL,
                source_ids TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                topics TEXT DEFAULT '[]',
                mastery_summary TEXT DEFAULT '{}',
                learning_style TEXT DEFAULT '',
                total_sessions INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );
        """)
        await self._db.commit()

    async def store(self, item: MemoryItem, user_id: int | None = None) -> str:
        await self._db.execute(
            """INSERT OR REPLACE INTO memory_entries
               (id, content, scope, source, score, tags, metadata,
                created_at, accessed_at, access_count, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.id, item.content, item.scope, item.source, item.score,
             json.dumps(item.tags), json.dumps(item.metadata),
             item.created_at.isoformat(), item.accessed_at.isoformat(),
             item.access_count, user_id)
        )
        await self._db.execute(
            "INSERT OR REPLACE INTO memory_fts (id, content, tags) VALUES (?, ?, ?)",
            (item.id, item.content, " ".join(item.tags))
        )
        await self._db.commit()
        return item.id

    async def search(self, query: str, scopes: list[MemoryScope],
                     user_id: int | None = None, top_k: int = 5) -> list[MemoryItem]:
        scope_clause = ",".join("?" for _ in scopes)
        sql = f"""
            SELECT * FROM memory_entries
            WHERE scope IN ({scope_clause})
            AND content LIKE ?
        """
        params = [*scopes, f"%{query}%"]
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        sql += " ORDER BY score DESC LIMIT ?"
        params.append(top_k)
        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._row_to_item(r, cursor) for r in rows]

    async def store_summary(self, user_id: int, scope: str,
                            summary: str, source_ids: list[str]) -> str:
        sid = str(uuid.uuid4())
        await self._db.execute(
            """INSERT INTO memory_summaries
               (id, user_id, scope, summary, source_ids, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sid, user_id, scope, summary, json.dumps(source_ids),
             datetime.now().isoformat())
        )
        await self._db.commit()
        return sid

    async def get_user_profile(self, user_id: int) -> dict | None:
        cursor = await self._db.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        result = dict(zip(cols, row))
        result["topics"] = json.loads(result.get("topics", "[]"))
        result["mastery_summary"] = json.loads(result.get("mastery_summary", "{}"))
        return result

    async def update_user_profile(self, user_id: int, **fields) -> None:
        cols = list(fields.keys())
        vals = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in fields.values()]
        now = datetime.now().isoformat()
        placeholders = ",".join("?" for _ in cols)
        update_sets = ",".join(f"{c}=excluded.{c}" for c in cols)
        sql = f"""INSERT INTO user_profiles (user_id, {','.join(cols)}, updated_at)
                   VALUES (?, {placeholders}, ?)
                   ON CONFLICT(user_id) DO UPDATE SET {update_sets}, updated_at=excluded.updated_at"""
        await self._db.execute(sql, [user_id, *vals, now])
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    def _row_to_item(self, row, cursor) -> MemoryItem:
        cols = [d[0] for d in cursor.description]
        r = dict(zip(cols, row))
        return MemoryItem(
            id=r["id"], content=r["content"], scope=MemoryScope(r["scope"]),
            source=r.get("source", "") or "", score=r.get("score", 0) or 0.0,
            tags=json.loads(r.get("tags", "[]") or "[]"),
            metadata=json.loads(r.get("metadata", "{}") or "{}"),
            created_at=datetime.fromisoformat(r["created_at"]),
            accessed_at=datetime.fromisoformat(r["accessed_at"]) if r.get("accessed_at") else datetime.now(),
            access_count=r.get("access_count", 0) or 0,
        )
