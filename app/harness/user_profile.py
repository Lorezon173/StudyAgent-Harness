from dataclasses import dataclass, field

from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


DEFAULT_PREFERENCES = {
    "explanation_style": "verbal",    # visual | verbal | mathematical
    "pace": "normal",                 # slow | normal | fast
    "depth": "standard",              # shallow | standard | deep
}


@dataclass
class UserProfile:
    """用户级偏好与进度（§6 L3 画像记忆）。

    与 MasteryGraph 并列构成 L3 画像记忆：MasteryGraph 关注知识点掌握度 +
    前置依赖推理；UserProfile 关注学习偏好、进度、活跃主题。
    """

    user_id: str
    store: MasteryGraphStore
    preferences: dict = field(default_factory=lambda: dict(DEFAULT_PREFERENCES))
    topics_active: list[str] = field(default_factory=list)
    topics_mastered: list[str] = field(default_factory=list)
    learning_streak: int = 0
    total_sessions: int = 0

    def update_preferences(self, **kwargs) -> None:
        """合并更新偏好，仅 explanation_style/pace/depth 三个键生效，未传则保持。"""
        for key in ("explanation_style", "pace", "depth"):
            if key in kwargs and kwargs[key] is not None:
                self.preferences[key] = kwargs[key]

    def sync_from_mastery(self, mastery_snapshot: dict[str, float],
                          mastered_threshold: float = 0.8) -> None:
        """从 MasteryGraph 掌握度快照同步 mastered topics 列表。"""
        self.topics_mastered = sorted(
            tid for tid, m in mastery_snapshot.items() if m >= mastered_threshold
        )

    def increment_session(self) -> None:
        """新会话开始时调用，自增会话计数与连续学习计数。"""
        self.total_sessions += 1
        self.learning_streak += 1  # 简化：每次 +1（精确 streak 需日期计算，后续迭代）

    # ---- 持久化 ----

    async def save(self) -> None:
        await self.store.save_profile(self.user_id, {
            "preferences": self.preferences,
            "topics_active": self.topics_active,
            "topics_mastered": self.topics_mastered,
            "learning_streak": self.learning_streak,
            "total_sessions": self.total_sessions,
        })

    async def load(self) -> None:
        data = await self.store.load_profile(self.user_id)
        if data is None:
            return  # 新用户，保留默认值
        self.preferences = data.get("preferences", dict(DEFAULT_PREFERENCES))
        self.topics_active = data.get("topics_active", [])
        self.topics_mastered = data.get("topics_mastered", [])
        self.learning_streak = data.get("learning_streak", 0)
        self.total_sessions = data.get("total_sessions", 0)
