"""本人主题画像 API；写事务一次提交，所有异常完整回滚。"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.workspace_schemas import (
    NodeCreate,
    NodeMutationResponse,
    NodePatch,
    ProfileCreate,
    ProfileDetail,
    ProfilePage,
    ProfilePatch,
    ProfileSummary,
)
from app.orchestration.profile_service import (
    InvalidProfileCursor,
    ProfileNotFound,
    ProfileService,
    ProfileVersionConflict,
)

router = APIRouter(prefix="/topic-profiles", tags=["topic-profiles"])


async def _write(db, operation):
    try:
        response = await operation
        await db.commit()
        return response
    except ProfileNotFound as exc:
        await db.rollback()
        raise HTTPException(404, "画像或知识点不存在") from exc
    except ProfileVersionConflict as exc:
        await db.rollback()
        raise HTTPException(409, "画像版本已更新") from exc
    except Exception:
        await db.rollback()
        raise


@router.get("", response_model=ProfilePage)
async def list_profiles(db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)],
    limit: int = Query(30, ge=1, le=100), cursor: str | None = Query(None, max_length=1024)):
    try:
        return await ProfileService(db).list_owned(user["user_id"], limit, cursor)
    except InvalidProfileCursor as exc:
        raise HTTPException(422, "无效分页游标") from exc


@router.post("", response_model=ProfileDetail)
async def create_profile(req: ProfileCreate, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    return await _write(db, ProfileService(db).create(user["user_id"], req.name, req.scope_description))


@router.get("/{profile_id}", response_model=ProfileDetail)
async def get_profile(profile_id: str, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    try:
        return await ProfileService(db).get_detail(user["user_id"], profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "画像不存在") from exc


@router.patch("/{profile_id}", response_model=ProfileDetail)
async def update_profile(profile_id: str, req: ProfilePatch, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    changes = req.model_dump(exclude_unset=True, exclude={"expected_revision"})
    return await _write(db, ProfileService(db).update_profile(user["user_id"], profile_id, req.expected_revision, changes))


@router.post("/{profile_id}/nodes", response_model=NodeMutationResponse)
async def create_node(profile_id: str, req: NodeCreate, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    return await _write(db, ProfileService(db).add_node(user["user_id"], profile_id, req.expected_revision, req.title, req.description))


@router.patch("/{profile_id}/nodes/{node_id}", response_model=NodeMutationResponse)
async def update_node(profile_id: str, node_id: str, req: NodePatch, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    changes = req.model_dump(exclude_unset=True, exclude={"expected_revision"})
    return await _write(db, ProfileService(db).update_node(user["user_id"], profile_id, node_id, req.expected_revision, changes))


@router.get("/{profile_id}/summary", response_model=ProfileSummary)
async def get_summary(profile_id: str, db: Annotated[AsyncSession, Depends(get_db)], user: Annotated[dict, Depends(get_current_user)]):
    try:
        return await ProfileService(db).get_summary(user["user_id"], profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "画像不存在") from exc
