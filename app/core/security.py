"""Security utilities: password hashing (bcrypt) + JWT token management (Task 9 / P0-③).

- hash_password / verify_password: bcrypt 直接调用（弃用 passlib，5.0 不兼容）
- create_access_token: HS256 JWT 签发
- get_current_user: FastAPI 依赖函数，验签 + 过期检查
"""
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    """bcrypt 哈希密码。"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码是否匹配哈希。"""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int) -> str:
    """签发 JWT（HS256，payload 含 user_id + exp）。"""
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"user_id": user_id, "exp": expire},
        settings.jwt_secret_key,
        algorithm="HS256",
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """FastAPI 依赖：验签 + 检查过期 + 提取 user_id + 确认用户仍存在。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="无效 token")

        # S5: 确认用户仍存在于数据库（延迟 import 避免循环依赖）
        from app.infrastructure.storage.user_store import UserStore
        store = UserStore(db)
        user = await store.find_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="用户不存在")

        return {"user_id": user_id}
    except JWTError as e:
        raise HTTPException(status_code=401, detail="token 验证失败") from e
