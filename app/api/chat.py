from fastapi import APIRouter

from app.models.schemas import ChatRequest, ChatResponse
from app.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat"])
_graph = build_learning_graph()


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    from app.harness.enums import Stage
    state = {
        "user_input": req.message,
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": req.session_id, "stage": Stage.INIT, "branch_trace": []},
    }
    config = {"configurable": {"thread_id": req.session_id}}
    result = await _graph.ainvoke(state, config=config)
    return ChatResponse(
        reply=result.get("teaching", {}).get("reply", "") or result.get("teaching", {}).get("summary", ""),
        session_id=req.session_id,
        mastery_score=result.get("evaluation", {}).get("mastery_score"),
    )
