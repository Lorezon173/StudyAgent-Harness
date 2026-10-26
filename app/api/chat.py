"""普通HTTP只负责身份、断开通知与共享服务委托。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.schemas import ChatRequest, ChatResponse
from app.core.database import get_db
from app.core.security import get_current_user
from app.infrastructure.storage.chat_request_store import WorkspaceConflict
from app.api._disconnect import observe_http_disconnect

router = APIRouter(prefix='/chat', tags=['chat'])


def conversation_service(request):
    service = getattr(request.app.state, 'conversation_service', None)
    if service is None:
        raise HTTPException(503, {'code':'conversation_service_unavailable'})
    return service


@router.post('', response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request, current_user: dict = Depends(get_current_user),
               db: AsyncSession = Depends(get_db)):
    service = conversation_service(request)
    await db.rollback()
    try:
        async with observe_http_disconnect(request) as disconnected:
            return await service.submit_turn(current_user['user_id'], req, disconnect_event=disconnected)
    except WorkspaceConflict as error:
        raise HTTPException(409, {'code':error.code}) from error
