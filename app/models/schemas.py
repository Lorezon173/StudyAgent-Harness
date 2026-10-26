from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, FiniteFloat, field_validator
from app.models.workspace_schemas import LibraryCreate, LibraryItem


class ChatRequest(BaseModel):
    message: str = Field(strict=True, max_length=4000)
    session_id: str = Field(default_factory=lambda: f"s-{uuid4().hex}", strict=True, min_length=1, max_length=64)
    user_id: int | None = None
    request_id: str | None = Field(None, strict=True, min_length=1, max_length=64)
    profile_id: str | None = None
    expected_state_version: int | None = Field(None, strict=True, ge=0)

    @field_validator("profile_id")
    @classmethod
    def canonical_profile(cls, value):
        return str(UUID(value)) if value is not None else None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    mastery_score: FiniteFloat | None = None
    # —— 新栈协作环指标 ——
    turn_count: int | None = None          # 成功提交的用户教学往返数
    mode_path: list[str] | None = None     # 教学模式路径（来自 PolicyTransition）
    cost_est_usd: float | None = None      # 本会话 LLM 估算成本（best-effort）
    stack: Literal["new"] | None = None   # 当前仅保留新栈标识
    persisted: bool = True                 # 落库是否成功（P0-② 显式暴露）
    request_id: str | None = None
    state_version: int | None = None
    profile_revision: int | None = None
    active_node_id: str | None = None
    status: str | None = None
    attempt: int | None = None
    error_code: str | None = None
    context_reduced: bool | None = None
    reduction_reasons: list[str] | None = None


class AuthRegisterRequest(BaseModel):
    username: str
    password: str


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user_id: int
    username: str
    token: str | None = None


class EvalResponse(BaseModel):
    eval_id: int
    session_id: str
    mastery_score: int
    mastery_level: str
    ragas_faithfulness: float | None = None
    ragas_relevancy: float | None = None
    ragas_context_precision: float | None = None
    ragas_context_recall: float | None = None


class KnowledgeCreateRequest(LibraryCreate):
    pass


class KnowledgeResponse(LibraryItem):
    pass


class SessionResponse(BaseModel):
    session_id: str
    user_id: int | None = None
    state_json: str = "{}"


class SessionSummary(BaseModel):
    session_id: str
    title: str
    updated_at: Any = None  # datetime | None — Any to avoid serialization issues with int (memory mode _updated_seq)


class MessageItem(BaseModel):
    id: int | None = None
    turn_index: int | None = None
    role: str
    content: str
    created_at: Any = None  # datetime | None
