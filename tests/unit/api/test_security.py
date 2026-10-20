"""Tests for security module (Task 9 / P0-③).

Verifies:
- hash_password returns bcrypt hash (not plaintext)
- verify_password correct/wrong
- create_access_token produces valid JWT with correct user_id
- Expired/forged tokens are detectable

Note: All tests are synchronous to avoid event loop interference with
test_sessions_api.py (which uses asyncio.run()). get_current_user will be
tested via integration tests in Task 11 (endpoint auth).
"""
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt


def test_hash_password_returns_bcrypt_hash():
    """hash_password 返回 $2b$ 前缀的 bcrypt 哈希，非明文。"""
    from app.core.security import hash_password
    hashed = hash_password("test123")
    assert hashed.startswith("$2b$")
    assert hashed != "test123"


def test_verify_password_correct():
    """verify_password 正确密码返回 True。"""
    from app.core.security import hash_password, verify_password
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed) is True


def test_verify_password_wrong():
    """verify_password 错误密码返回 False。"""
    from app.core.security import hash_password, verify_password
    hashed = hash_password("mypassword")
    assert verify_password("wrongpassword", hashed) is False


def test_create_access_token_contains_user_id():
    """create_access_token 生成的 JWT 包含正确的 user_id。"""
    from app.core.config import settings
    from app.core.security import create_access_token

    token = create_access_token(user_id=42)
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    assert payload["user_id"] == 42
    assert "exp" in payload


def test_expired_token_is_detectable():
    """过期 token 可被 jwt.decode 检测到（ExpiredSignatureError）。"""
    from jose import ExpiredSignatureError

    from app.core.config import settings

    expired_payload = {
        "user_id": 1,
        "exp": datetime.now(UTC) - timedelta(hours=1),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm="HS256")

    with pytest.raises(ExpiredSignatureError):
        jwt.decode(expired_token, settings.jwt_secret_key, algorithms=["HS256"])


def test_forged_token_is_detectable():
    """伪造 token（错误密钥）可被 jwt.decode 检测到（JWTError）。"""
    from jose import JWTError

    from app.core.config import settings

    forged_token = jwt.encode(
        {"user_id": 999, "exp": 9999999999},
        "wrong-secret-key",
        algorithm="HS256",
    )

    with pytest.raises(JWTError):
        jwt.decode(forged_token, settings.jwt_secret_key, algorithms=["HS256"])
