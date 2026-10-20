from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.infrastructure.storage.user_store import UserStore
from app.models.schemas import AuthLoginRequest, AuthRegisterRequest, AuthResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
async def register(req: AuthRegisterRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    store = UserStore(db)
    existing = await store.find_by_username(req.username)
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user_id = await store.create(req.username, req.password)
    token = create_access_token(user_id)
    return AuthResponse(user_id=user_id, username=req.username, token=token)


@router.post("/login", response_model=AuthResponse)
async def login(req: AuthLoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    store = UserStore(db)
    user = await store.find_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user["id"])
    return AuthResponse(user_id=user["id"], username=user["username"], token=token)
