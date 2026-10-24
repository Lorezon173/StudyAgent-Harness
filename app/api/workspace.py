"""认证用户的工作区偏好；CAS 冲突由共享错误映射返回。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.sessions import _operation
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.workspace_schemas import WorkspacePatch, WorkspaceState
from app.orchestration.session_service import SessionService

router = APIRouter(prefix="/workspace-state", tags=["workspace"])


@router.get("", response_model=WorkspaceState)
async def get_workspace(db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    return await _operation(db, SessionService(db).get_workspace(user["user_id"]))


@router.patch("", response_model=WorkspaceState)
async def save_workspace(req: WorkspacePatch, db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    changes = req.model_dump(exclude_unset=True, exclude={"expected_version"})
    return await _operation(db, SessionService(db).save_workspace(user["user_id"], req.expected_version, changes), True)
