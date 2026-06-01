from dataclasses import dataclass, field

from app.harness.enums import TeachingMode


@dataclass
class WorkspaceState:
    """会话内共享状态（§6）。事件正文存 EventStore，这里只持引用 id。

    注意：Agent 不直接写 WorkspaceState（§2.2），由协作环/Orchestrator 维护。
    evidence_pool / critic_state / profile_snapshot 在 Plan 0 用 dict 占位，
    Wave 1（Plan A/B）落地具体结构后可替换为强类型。
    """
    session_id: str
    user_id: str
    current_topic: str | None = None
    current_mode: TeachingMode = TeachingMode.SOCRATIC
    turn_count: int = 0
    event_ids: list[str] = field(default_factory=list)       # 仅引用，正文存 EventStore
    evidence_pool: list[dict] = field(default_factory=list)  # Retriever 最近输出
    critic_state: dict = field(default_factory=dict)         # Critic 最近一次评估
    profile_snapshot: dict = field(default_factory=dict)     # 进入会话时画像快照
