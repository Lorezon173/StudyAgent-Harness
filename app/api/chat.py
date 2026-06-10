import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ChatRequest, ChatResponse
from app.core.feature_flags import use_new_agent_graph
from app.core.database import get_db
from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.message_store import MessageStore
from app_old.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat"])
_graph = build_learning_graph()


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    if use_new_agent_graph():
        from app.orchestration.assembly import run_new_agent_session
        result = await asyncio.to_thread(
            run_new_agent_session,
            req.session_id,
            str(req.user_id) if req.user_id is not None else "anonymous",
            req.message,
        )

        # ── 持久化：session + messages（C3: 原子提交）──
        try:
            # 1. 计算 turn_index
            existing_messages = await MessageStore(db).list_by_session(req.session_id)
            turn_index = len(existing_messages) // 2

            # 2. 生成 title（仅首轮）
            title = None
            if len(existing_messages) == 0:
                title = req.message.strip()[:24] if req.message.strip() else "新会话"

            # 3. 保存 session (upsert)
            await SessionStore(db).save(
                req.session_id,
                state={},
                user_id=req.user_id,
                title=title,
            )

            # 4. 添加 user message
            await MessageStore(db).add(req.session_id, "user", req.message, turn_index)

            # 5. 添加 assistant message
            await MessageStore(db).add(req.session_id, "assistant", result.reply, turn_index)

            # 6. 单次 commit（C3: all-or-nothing）
            await db.commit()
        except Exception as e:
            await db.rollback()
            # 通过 observability 记录错误；延迟 import 避免模块加载期初始化
            try:
                from app.harness.observability import get_observability
                get_observability().log_event("persist_error", {"session_id": req.session_id, "error": str(e)})
            except Exception:
                pass

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
