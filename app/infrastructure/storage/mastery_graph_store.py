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