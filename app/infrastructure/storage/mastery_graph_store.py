import json
from pathlib import Path

import aiosqlite


class MasteryGraphStore:
    """MasteryGraph + UserProfile 的 SQLite 持久化存储。

    表结构：
      mastery_nodes  — 知识点节点 (user_id, topic_id, topic_name, mastery, ...)
      mastery_edges  — 图谱边 (user_id, from_topic, to_topic, type, confidence, source, ...)
      user_profile_l3 — L3 用户画像 (user_id, preferences_json, topics_active_json, ...)
    """

    def __init__(self, db_path: str = "data/mastery_graph.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS mastery_nodes (
                user_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                topic_name TEXT NOT NULL DEFAULT '',
                mastery REAL NOT NULL DEFAULT 0.0,
                last_practiced_at REAL NOT NULL DEFAULT 0.0,
                practice_count INTEGER NOT NULL DEFAULT 0,
                confusion_with TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (user_id, topic_id)
            );
            CREATE TABLE IF NOT EXISTS mastery_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                from_topic TEXT NOT NULL,
                to_topic TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'PREREQ',
                weight REAL NOT NULL DEFAULT 1.0,
                confidence REAL NOT NULL DEFAULT 0.5,
                source TEXT NOT NULL DEFAULT 'LLM_INFER',
                UNIQUE(user_id, from_topic, to_topic, type)
            );
            CREATE INDEX IF NOT EXISTS idx_edges_user_from ON mastery_edges(user_id, from_topic);
            CREATE INDEX IF NOT EXISTS idx_edges_user_to ON mastery_edges(user_id, to_topic);
            CREATE TABLE IF NOT EXISTS user_profile_l3 (
                user_id TEXT PRIMARY KEY,
                preferences_json TEXT NOT NULL DEFAULT '{}',
                topics_active_json TEXT NOT NULL DEFAULT '[]',
                topics_mastered_json TEXT NOT NULL DEFAULT '[]',
                learning_streak INTEGER NOT NULL DEFAULT 0,
                total_sessions INTEGER NOT NULL DEFAULT 0
            );
        """)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def save_nodes(self, user_id: str, nodes: list[dict]) -> None:
        """批量 upsert 节点。每个 dict 含 topic_id, topic_name, mastery, last_practiced_at, practice_count, confusion_with。"""
        for n in nodes:
            await self._db.execute(
                """INSERT OR REPLACE INTO mastery_nodes
                   (user_id, topic_id, topic_name, mastery, last_practiced_at,
                    practice_count, confusion_with)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, n["topic_id"], n.get("topic_name", ""),
                 n.get("mastery", 0.0), n.get("last_practiced_at", 0.0),
                 n.get("practice_count", 0),
                 json.dumps(n.get("confusion_with", []))),
            )
        await self._db.commit()

    async def load_nodes(self, user_id: str) -> dict[str, dict]:
        """返回 {topic_id: {topic_id, topic_name, mastery, ...}}。"""
        cursor = await self._db.execute(
            "SELECT topic_id, topic_name, mastery, last_practiced_at, practice_count, confusion_with "
            "FROM mastery_nodes WHERE user_id = ?", (user_id,)
        )
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            result[row[0]] = {
                "topic_id": row[0],
                "topic_name": row[1],
                "mastery": row[2],
                "last_practiced_at": row[3],
                "practice_count": row[4],
                "confusion_with": json.loads(row[5]),
            }
        return result

    async def save_edges(self, user_id: str, edges: list[dict]) -> None:
        """批量 upsert 边。每个 dict 含 from_topic, to_topic, type, weight, confidence, source。"""
        for e in edges:
            await self._db.execute(
                """INSERT OR REPLACE INTO mastery_edges
                   (user_id, from_topic, to_topic, type, weight, confidence, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, e["from_topic"], e["to_topic"], e.get("type", "PREREQ"),
                 e.get("weight", 1.0), e.get("confidence", 0.5),
                 e.get("source", "LLM_INFER")),
            )
        await self._db.commit()

    async def load_edges(self, user_id: str) -> list[dict]:
        """返回 [{id, from_topic, to_topic, type, weight, confidence, source}, ...]。"""
        cursor = await self._db.execute(
            "SELECT id, from_topic, to_topic, type, weight, confidence, source "
            "FROM mastery_edges WHERE user_id = ?", (user_id,)
        )
        rows = await cursor.fetchall()
        return [
            {"id": row[0], "from_topic": row[1], "to_topic": row[2],
             "type": row[3], "weight": row[4], "confidence": row[5], "source": row[6]}
            for row in rows
        ]

    async def save_profile(self, user_id: str, profile: dict) -> None:
        """写入 L3 画像。profile 含 preferences, topics_active, topics_mastered, learning_streak, total_sessions。"""
        await self._db.execute(
            """INSERT OR REPLACE INTO user_profile_l3
               (user_id, preferences_json, topics_active_json, topics_mastered_json,
                learning_streak, total_sessions)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id,
             json.dumps(profile.get("preferences", {})),
             json.dumps(profile.get("topics_active", [])),
             json.dumps(profile.get("topics_mastered", [])),
             profile.get("learning_streak", 0),
             profile.get("total_sessions", 0)),
        )
        await self._db.commit()

    async def load_profile(self, user_id: str) -> dict | None:
        """读取 L3 画像，不存在返回 None。"""
        cursor = await self._db.execute(
            "SELECT preferences_json, topics_active_json, topics_mastered_json, "
            "learning_streak, total_sessions FROM user_profile_l3 WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "preferences": json.loads(row[0]),
            "topics_active": json.loads(row[1]),
            "topics_mastered": json.loads(row[2]),
            "learning_streak": row[3],
            "total_sessions": row[4],
        }