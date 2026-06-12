import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ChatRequest, ChatResponse
from app.core.feature_flags import use_new_agent_graph
from app.core.database import get_db
from app.api._persist import persist_turn
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
from app_old.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat"])
_graph = build_learning_graph()


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    if use_new_agent_graph():
        from app.orchestration.assembly import run_new_agent_session
        uid_str = str(req.user_id) if req.user_id is not None else "anonymous"

        graph = MasteryGraph(user_id=uid_str, store=SQLAlchemyMasteryStore(db))
        await graph.load()

        result = await asyncio.to_thread(
            run_new_agent_session, req.session_id, uid_str, req.message,
            None, graph,        # current_topic=None, graph=graph
        )

        turn_index = await persist_turn(
            db, session_id=req.session_id, user_id=req.user_id,
            user_message=req.message, reply=result.reply, graph=graph,
        )
        turn_count = (turn_index + 1) if turn_index is not None else None

        return ChatResponse(
            reply=result.reply,
            session_id=req.session_id,
            mastery_score=result.mastery_score,
            turn_count=turn_count,
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
