from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    user_id: int | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    mastery_score: int | None = None


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
