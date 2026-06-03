import asyncio

from fastapi import APIRouter

from app.models.schemas import ChatRequest, ChatResponse
from app.core.feature_flags import use_new_agent_graph
from app_old.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat"])
_graph = build_learning_graph()


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if use_new_agent_graph():
        from app.orchestration.assembly import run_new_agent_session
        result = await asyncio.to_thread(
            run_new_agent_session,
            req.session_id,
            str(req.user_id) if req.user_id is not None else "anonymous",
            req.message,
        )
        return ChatResponse(
            reply=result.reply,
            session_id=req.session_id,
            mastery_score=result.mastery_score,
            turn_count=result.turn_count,
            mode_path=result.mode_path,
            cost_est_usd=result.cost_est_usd,
            stack="new",
        )

    # —— 老栈（关 flag 回退路径，逻辑与改造前一致）——
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
        stack="legacy",
    )
