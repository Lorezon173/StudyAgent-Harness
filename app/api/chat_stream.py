import asyncio
import json
import logging
import sys
import threading
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api._dirty_flag import DirtyFlag
from app.api._persist import ensure_session_writable, persist_turn
from app.api._sse_projection import project_event
from app.api.chat import conversation_service
from app.core.database import async_session
from app.core.security import get_current_user
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.chat_request_store import WorkspaceConflict
from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
from app.models.schemas import ChatRequest

router = APIRouter(prefix="/chat", tags=["chat-stream"])
logger = logging.getLogger(__name__)

_SENTINEL = object()


@router.post("/stream")
async def chat_stream(req: ChatRequest, current_user: Annotated[dict, Depends(get_current_user)], request: Request = None):
    if req.request_id is not None:
        return await workspace_stream(req, request, current_user)
    from app.orchestration.assembly import (
        OnlineRAGCompositionError,
        run_online_agent_session,
    )
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
            run_online_agent_session, req.session_id, uid_int, req.message,
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
        except OnlineRAGCompositionError as e:
            # DEC-007 在线 composition fail-fast：分类错误事件，不回退 fake
            logger.exception("online RAG composition failed for session %s",
                             req.session_id)
            error_event = {
                "type": "error",
                "code": "RAG_BACKEND_UNAVAILABLE",
                "message": e.safe_summary,
                "error_code": e.error_code,
                "retryable": False,
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return
        except Exception:
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
        except HTTPException as error:
            detail = error.detail if isinstance(error.detail, dict) else {}
            code = detail.get("code", "SESSION_WRITE_REJECTED")
            yield f"data: {json.dumps({'type': 'error', 'code': code, 'message': '会话不可写，消息未保存', 'retryable': False}, ensure_ascii=False)}\n\n"
            return
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


class PreparedTurnStreamingResponse(StreamingResponse):
    def __init__(self, content, *, service, prepared, close):
        super().__init__(content, media_type='text/event-stream')
        self.service, self.prepared, self.close = service, prepared, close

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.close()
            with anyio.CancelScope(shield=True):
                await asyncio.shield(self.service.cancel_owned(self.prepared))


def frame(value):
    return 'data: ' + json.dumps(value, ensure_ascii=False) + '\n\n'


def project_response(response):
    body = response.model_dump(mode='json')
    if response.persisted and response.status == 'completed':
        return {'type':'final', **body}
    if response.status == 'running':
        return {'type':'status', **body}
    return {'type':'error', **body, 'code':'AGENT_ERROR' if response.error_code == 'turn_failed' else response.error_code or 'TURN_FAILED',
        'message':'处理过程中发生错误', 'retryable':False}


async def workspace_stream(req, request, current_user):
    service = conversation_service(request)
    queue = asyncio.Queue()
    closed = threading.Event()
    loop = asyncio.get_running_loop()
    def deliver(event):
        if not closed.is_set():
            queue.put_nowait(event)
    def callback(event):
        if closed.is_set():
            return
        try:
            loop.call_soon_threadsafe(deliver, event)
        except RuntimeError:
            pass
    try:
        prepared = await service.prepare_request(current_user['user_id'], req)
    except WorkspaceConflict as error:
        raise HTTPException(409, {'code':error.code}) from error
    try:
        async def generate():
            task = None
            try:
                task = asyncio.create_task(service.run_claim(prepared, on_event=callback))
                task.add_done_callback(lambda _: deliver(_SENTINEL))
                while True:
                    event = await queue.get()
                    if event is _SENTINEL:
                        break
                    projected = project_event(event)
                    if projected is not None:
                        yield frame(projected)
                try:
                    yield frame(project_response(await task))
                except HTTPException as error:
                    detail = error.detail if isinstance(error.detail,dict) else {}
                    code = detail.get('error_code', detail.get('code','TURN_FAILED'))
                    current = await service.cancel_owned(prepared)
                    yield frame({'type':'error','code':'RAG_BACKEND_UNAVAILABLE' if code == 'backend_unavailable' else code,
                        'error_code':code,'message':detail.get('message','教学回合未保存'),'retryable':False,
                        'request_id':prepared.request_id,'status':current.status,'attempt':current.attempt,'persisted':False})
            finally:
                closed.set()
                with anyio.CancelScope(shield=True):
                    await asyncio.shield(service.cancel_owned(prepared))
                    if task is not None:
                        await asyncio.gather(task, return_exceptions=True)
        return PreparedTurnStreamingResponse(generate(), service=service, prepared=prepared, close=closed.set)
    except asyncio.CancelledError:
        closed.set()
        await asyncio.shield(service.cancel_owned(prepared))
        raise
