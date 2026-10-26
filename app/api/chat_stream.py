"""SSE是共享请求状态机的事件订阅与成功结果投影。"""
import asyncio
import anyio
import json
import threading
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.schemas import ChatRequest
from app.core.database import get_db
from app.core.security import get_current_user
from app.infrastructure.storage.chat_request_store import WorkspaceConflict
from app.api._sse_projection import project_event
from app.api.chat import conversation_service

router = APIRouter(prefix='/chat', tags=['chat-stream'])
_SENTINEL = object()


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


@router.post('/stream')
async def chat_stream(req: ChatRequest, request: Request, current_user: dict = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    service = conversation_service(request)
    await db.rollback()
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
