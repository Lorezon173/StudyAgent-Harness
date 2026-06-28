import asyncio
import json
import logging
import sys

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest
from app.core.feature_flags import use_new_agent_graph
from app.core.database import async_session
from app.api._sse_projection import project_event
from app.api._persist import persist_turn
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
from app_old.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat-stream"])
_graph = build_learning_graph()
logger = logging.getLogger(__name__)

_SENTINEL = object()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    if use_new_agent_graph():
        from app.orchestration.assembly import run_new_agent_session
        uid_str = str(req.user_id) if req.user_id is not None else "anonymous"

        async def generate_new():
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()

            # ── 阶段①：加载掌握度图谱（短连接） ──
            async with async_session() as load_db:
                graph = MasteryGraph(user_id=uid_str, store=SQLAlchemyMasteryStore(load_db))
                await graph.load()

            # ── 阶段②：运行协作环 + 流式推送（不持 DB 连接） ──
            def cb(ev):  # 工作线程内执行 → 跨线程投递
                loop.call_soon_threadsafe(queue.put_nowait, ev)

            task = asyncio.create_task(asyncio.to_thread(
                run_new_agent_session, req.session_id, uid_str, req.message,
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
                    "error": str(e),
                    "persisted": False,
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
                        persist_db, session_id=req.session_id, user_id=req.user_id,
                        user_message=req.message, reply=result.reply, graph=graph,
                    )
                turn_count = (turn_index + 1) if turn_index is not None else None
                was_persisted = turn_index is not None
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

    # —— 老栈（关 flag 回退路径，逻辑与改造前一致）——
    from app.harness.enums import Stage

    async def generate():
        state = {
            "user_input": req.message,
            "routing": {}, "teaching": {}, "retrieval": {},
            "evaluation": {}, "memory": {},
            "meta": {"session_id": req.session_id, "stage": Stage.INIT, "branch_trace": []},
        }
        config = {"configurable": {"thread_id": req.session_id}}
        async for event in _graph.astream_events(state, config=config, version="v2"):
            kind = event.get("event", "")
            if kind == "on_chain_end":
                data = event.get("data", {}).get("output", {})
                if isinstance(data, dict) and "teaching" in data:
                    reply = data["teaching"].get("reply", "") or data["teaching"].get("summary", "")
                    if reply:
                        yield f"data: {reply}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
