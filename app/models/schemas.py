from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    session_id: str = Field(default_factory=lambda: f"s-{uuid4().hex}")
    user_id: int | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    mastery_score: int | None = None
    # —— 新栈协作环指标 ——
    turn_count: int | None = None          # 协作环回合数
    mode_path: list[str] | None = None     # 教学模式路径（来自 PolicyTransition）
    cost_est_usd: float | None = None      # 本会话 LLM 估算成本（best-effort）
    stack: Literal["new"] | None = None   # 当前仅保留新栈标识
    persisted: bool = True                 # 落库是否成功（P0-② 显式暴露）


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


class KnowledgeCreateRequest(BaseModel):
    name: str
    description: str = ""


class KnowledgeResponse(BaseModel):
    id: int
    name: str
    description: str


class SessionResponse(BaseModel):
    session_id: str
    user_id: int | None = None
    state_json: str = "{}"


class SessionSummary(BaseModel):
    session_id: str
    title: str
    updated_at: Any = None  # datetime | None — Any to avoid serialization issues with int (memory mode _updated_seq)


class MessageItem(BaseModel):
    role: str
    content: str
    created_at: Any = None  # datetime | None
