from fastapi import APIRouter

from app.models.schemas import ChatRequest, ChatResponse
from app.harness.enums import Stage

router = APIRouter(prefix="/chat", tags=["chat-multi"])


@router.post("/multi", response_model=ChatResponse)
async def chat_multi(req: ChatRequest):
    state = {
        "user_input": req.message,
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": req.session_id, "stage": Stage.INIT, "branch_trace": []},
    }
    return ChatResponse(
        reply="Multi-Agent 模式暂未实现",
        session_id=req.session_id,
    )
