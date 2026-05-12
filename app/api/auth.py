from fastapi import APIRouter, HTTPException

from app.models.schemas import AuthRegisterRequest, AuthLoginRequest, AuthResponse
from app.infrastructure.storage.user_store import UserStore

router = APIRouter(prefix="/auth", tags=["auth"])
_store = UserStore()


@router.post("/register", response_model=AuthResponse)
async def register(req: AuthRegisterRequest):
    existing = await _store.find_by_username(req.username)
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user_id = await _store.create(req.username, req.password)
    return AuthResponse(user_id=user_id, username=req.username)


@router.post("/login", response_model=AuthResponse)
async def login(req: AuthLoginRequest):
    user = await _store.find_by_username(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return AuthResponse(user_id=user["id"], username=user["username"])
