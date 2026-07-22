import asyncio
import json
import logging
import sys

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest
from app.core.database import async_session
from app.core.security import get_current_user
from app.api._sse_projection import project_event
from app.api._dirty_flag import DirtyFlag
from app.api._persist import ensure_session_writable, persist_turn
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore

router = APIRouter(prefix="/chat", tags=["chat-stream"])
logger = logging.getLogger(__name__)

_SENTINEL = object()


@router.post("/stream")
async def chat_stream(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    from app.orchestration.assembly import run_new_agent_session
    uid_int = current_user["user_id"]

    async with async_session() as auth_db:
        await ensure_session_writable(auth_db, req.session_id, uid_int)

    async def generate_new():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        # ── 阶段①：加载掌握度图谱（短连接） ──
        async with async_session() as load_db:
            graph = MasteryGraph(user_id=uid_int, store=SQLAlchemyMasteryStore(load_db))
            await graph.load()
            if DirtyFlag.is_dirty(uid_int):
                DirtyFlag.clear_dirty(uid_int)

        # ── 阶段②：运行协作环 + 流式推送（不持 DB 连接） ──
        def cb(ev):  # 工作线程内执行 → 跨线程投递
            loop.call_soon_threadsafe(queue.put_nowait, ev)

        task = asyncio.create_task(asyncio.to_thread(
            run_new_agent_session, req.session_id, uid_int, req.message,
            None, graph, cb,
        ))
        task.add_done_callback(
            lambda _: loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL))

        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            sse = project_event(item)
            if sse is not None:
                yield f"data: {json.dumps(sse, ensure_ascii=False)}\n\n"

        try:
            result = await task   # 取结果 + re-raise 工作线程异常
        except Exception as e:
            logger.exception("collab loop failed for session %s", req.session_id)
            error_event = {
                "type": "error",
                "code": "AGENT_ERROR",
                "message": "处理过程中发生错误",
                "retryable": False,
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return

        # ── 阶段③：持久化（新短连接 → rebind store） ──
        was_persisted = False
        turn_count = None
        try:
            async with async_session() as persist_db:
                graph._store = SQLAlchemyMasteryStore(persist_db)
                turn_index = await persist_turn(
                    persist_db, session_id=req.session_id, user_id=current_user["user_id"],
                    user_message=req.message, reply=result.reply, graph=graph,
                )
            turn_count = (turn_index + 1) if turn_index is not None else None
            was_persisted = turn_index is not None
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("stream persist stage failed for session %s", req.session_id)
            # Fallback: if logging is not configured (e.g. test env), print to stderr
            print(f"[chat_stream] persist failed: {e}", file=sys.stderr)

        final = {
            "type": "final",
            "reply": result.reply,
            "turn_count": turn_count,
            "mastery_score": result.mastery_score,
            "mode_path": result.mode_path,
            "persisted": was_persisted,
        }
        yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate_new(), media_type="text/event-stream")
