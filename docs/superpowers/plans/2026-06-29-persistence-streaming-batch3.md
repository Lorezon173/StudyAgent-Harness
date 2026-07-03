# Persistence + Streaming 批次三 Implementation Plan（v3 · 二轮评审修订版）

> **设计来源**：`docs/designs/2026-06-14-fix-persistence-streaming-issues.md` §P0-③
> **前置**：批次一（Task 1-6）+ 批次二（Task 7-8）已完成。
> **v2→v3 修订**：基于第二轮隔离评审——弃用 passlib 改用 bcrypt 直接调用、补所有权校验、明确匿名功能下线、补 chat_multi 覆盖、修正测试文件数。

**Goal:** P0-③ 鉴权体系——密码哈希修复 + JWT 签发/校验 + 全端点 IDOR 阻断（含所有权校验）+ 前端同步适配 + 匿名功能下线。

**Architecture:** FastAPI `Depends(get_current_user)` 依赖注入 + bcrypt 库直接哈希。register 存哈希、login 验哈希后签 JWT。受保护端点从 token 提取 user_id，对资源类端点（sessions/eval）加所有权校验。前端在 `client.ts` 统一注入 `Authorization: Bearer <token>`。

**Tech Stack:** FastAPI, python-jose（pyproject.toml:21）, bcrypt（pyproject.toml:20 已声明 passlib，实际用 bcrypt 5.0.0 直接调用）, Pydantic Settings, React TypeScript。

## Global Constraints

- 四层架构单向依赖：API → Orchestration → Harness → Infrastructure
- **不引入新依赖**（python-jose + bcrypt 均已可用）
- 不修改冻结接口（协作环对外是一次同步调用）
- JWT phase 1 范围：**仅签发 + 校验 + 过期 + 密码哈希**。不含 refresh_token / blacklist / 密钥轮换
- 所有命令用 `uv run` 前缀
- 编码完成后必须经 code-review-three-rounds skill 审查通过再提交
- **前后端同步上线**：后端上 JWT 而前端不适配 → 全量 401 中断
- **匿名功能下线**：所有受保护端点强制 JWT，`user_id=None` → 401。P1-⑥ 的匿名分支代码清理
- **鉴权 ≠ 授权**：JWT 验证身份，资源端点（sessions/eval）额外校验所有权

## 验证状态表

| 断言 | 验证状态 | 依据 |
|---|---|---|
| `python-jose>=3.3.0` 在 pyproject.toml:21 | ✅ grep | pyproject.toml |
| `passlib>=1.7.0` 在 pyproject.toml:20 | ✅ grep | pyproject.toml |
| passlib 1.7.4 + bcrypt 5.0.0 **不兼容** | ✅ 实测 | `CryptContext(schemes=['bcrypt']).hash('test')` → `AttributeError` + `ValueError` |
| bcrypt 5.0.0 直接调用可用 | ✅ 实测 | `bcrypt.hashpw(b'test', bcrypt.gensalt())` 正常 |
| `auth.py:19-24` login 不验密码 | ✅ Read | 仅 `find_by_username` |
| `user_store.py:12` create 存明文 | ✅ Read | 直接写入 `password_hash` |
| `AuthResponse.token` 字段已存在 | ✅ Read | schemas.py:37 |
| `app/core/security.py` 不存在 | ✅ ls | 不存在 |
| `config.py` 无 JWT_SECRET_KEY | ✅ Read | config.py 全文 |
| 前端 client.ts 无 Authorization header | ✅ Read | 全文 |
| 前端 auth.tsx 仅存 userId/username | ✅ Read | 全文 |
| `sessions.py` 三个端点 | ✅ grep | list_sessions/get_session/get_session_messages |
| `eval.py` 两个端点 | ✅ grep | get_evals/rerun_eval |
| `chat_multi.py` 端点存在但未实现 | ✅ Read | `app/api/chat_multi.py:9` |
| `knowledge` 端点无 user_id 绑定 | ✅ Read | 无 IDOR |
| 9 个测试文件调受保护端点 | ✅ grep | tests/ 目录 |

---

## File Structure

| 文件 | 责任 | 操作 |
|---|---|---|
| `app/core/security.py` | JWT 签发/验证 + `get_current_user` + 密码哈希（bcrypt 直接调用） | 新建 |
| `app/core/config.py` | 加 `jwt_secret_key` + `jwt_expire_minutes` | 修改 |
| `app/api/auth.py` | register 存哈希 + login 验哈希 + 签发 JWT | 修改 |
| `app/infrastructure/storage/user_store.py` | `create` 参数名语义修正 | 修改 |
| `app/api/chat.py` | 加 `Depends(get_current_user)` + token user_id 覆盖 | 修改 |
| `app/api/chat_stream.py` | 同上 | 修改 |
| `app/api/chat_multi.py` | 加 `Depends(get_current_user)` | 修改 |
| `app/api/profile.py` | 加 `Depends(get_current_user)` + token user_id 覆盖 path 参数 | 修改 |
| `app/api/sessions.py` | 加 `Depends(get_current_user)` + 所有权校验 | 修改 |
| `app/api/eval.py` | 加 `Depends(get_current_user)` + 所有权校验 | 修改 |
| `tests/conftest.py` | 加 `auth_headers` fixture | 修改 |
| `tests/unit/api/test_security.py` | JWT + 密码哈希单元测试 | 新建 |
| `web/src/store/auth.tsx` | 加 token 存储 | 修改 |
| `web/src/api/client.ts` | 注入 Authorization header + 401 处理 | 修改 |
| `web/src/pages/Login.tsx` | 传 token 到 login() | 修改 |
| 9 个已有测试文件 | 加 Authorization header / 匿名测试改 401 | 修改 |

---

### Task 9: 密码哈希 + JWT 基础设施

**Files:**
- Create: `app/core/security.py`
- Modify: `app/core/config.py`
- Create: `tests/unit/api/test_security.py`

**Interfaces:**
- Produces:
  - `hash_password(password: str) -> str`：bcrypt 哈希（直接调 bcrypt 库）
  - `verify_password(plain: str, hashed: str) -> bool`：验证密码
  - `create_access_token(user_id: int) -> str`：签发 JWT（HS256, payload: user_id + exp）
  - `get_current_user(token) -> dict`：FastAPI 依赖，验签 + 过期 + 返回 `{"user_id": int}`

**config.py 加：**
```python
jwt_secret_key: str = "dev-secret-change-me-in-production"
jwt_expire_minutes: int = 1440  # 24 小时（dev 环境；上 prod 前需重审）
```

**security.py（弃用 passlib，直接用 bcrypt）：**
```python
from datetime import datetime, timedelta
from jose import jwt, JWTError
import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"user_id": user_id, "exp": expire},
                      settings.jwt_secret_key, algorithm="HS256")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="无效 token")
        return {"user_id": user_id}
    except JWTError:
        raise HTTPException(status_code=401, detail="token 验证失败")
```

**测试：**
- hash_password 返回非明文（$2b$ 前缀）
- verify_password 正确/错误密码
- create_access_token → get_current_user 提取 user_id
- 过期 token → 401
- 伪造 token → 401
- 无 token → 401

---

### Task 10: Auth 端点改造（密码验证 + JWT 签发）

**Files:**
- Modify: `app/api/auth.py`
- Modify: `app/infrastructure/storage/user_store.py`

**改动：**

1. **user_store.py**：`create` 参数名 `password_hash` → `password`，内部调 `hash_password(password)` 存哈希。

2. **auth.py register**：
   - 调 `_store.create(req.username, req.password)`（store 内部哈希）
   - 签发 JWT：`token=create_access_token(user_id)`
   - 返回 `AuthResponse(user_id=..., username=..., token=...)`

3. **auth.py login**：
   - `find_by_username(req.username)` → 获取用户
   - `verify_password(req.password, user["password_hash"])` 验密码
   - 失败 → 401
   - 成功 → 签发 JWT

**数据迁移**：清空 users 表重新注册（dev 环境，无真实用户）。

---

### Task 11: 后端端点加鉴权 + 所有权校验

**Files:**
- Modify: `app/api/chat.py`
- Modify: `app/api/chat_stream.py`
- Modify: `app/api/chat_multi.py`
- Modify: `app/api/profile.py`
- Modify: `app/api/sessions.py`
- Modify: `app/api/eval.py`

**两种校验模式：**

| 模式 | 适用端点 | 逻辑 |
|------|---------|------|
| **身份覆盖** | chat, chat_stream, chat_multi, profile | `current_user["user_id"]` 覆盖请求中的 user_id |
| **身份 + 所有权** | sessions, eval | 先验证 JWT 身份，再校验 `session.user_id == token.user_id`，不匹配 → 403 |

**各端点改动：**

| 端点 | 改动 |
|------|------|
| `chat.py` | + `Depends(get_current_user)`，`req.user_id` → `current_user["user_id"]` |
| `chat_stream.py` | 同上 |
| `chat_multi.py` | + `Depends(get_current_user)` |
| `profile.py` | + `Depends(get_current_user)`，URL `user_id` → `current_user["user_id"]`（路径改为 `/profile` 不带参数，或校验 path == token） |
| `sessions.py:25` list_sessions | query `user_id` → `current_user["user_id"]` |
| `sessions.py:13` get_session | + 所有权校验：session.user_id ≠ token.user_id → 403 |
| `sessions.py:40` get_session_messages | + 所有权校验同上 |
| `eval.py:11` get_evals | + 所有权校验 |
| `eval.py:31` rerun_eval | + 所有权校验 |

**ChatRequest.user_id**：保留字段但加注释 `# deprecated: user_id 来自 JWT token，此字段被忽略`。

**P1-⑥ 匿名分支**：chat.py/chat_stream.py 中 `if req.user_id is None` 分支清理（JWT 后 user_id 从 token 来，必有值）。`test_chat_anonymous.py` 改为验证 401。

**knowledge 端点不加鉴权**：无 user_id 绑定，无 IDOR。

**测试：**
- 无 token → 401（chat/profile/sessions/eval）
- 带 token → 200，user_id 以 token 为准
- token user_id=1 + body user_id=2 → 实际写入 user_id=1
- 带 token 访问他人 session → 403

---

### Task 12: 前端适配

**Files:**
- Modify: `web/src/store/auth.tsx`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/pages/Login.tsx`

**改动同 v2（不变）。**

---

### Task 13: 已有测试加 token fixture

**Files:**
- Modify: `tests/conftest.py`
- Modify: **9 个**测试文件（修正 v2 的 8 个）

**9 个文件：**
1. `tests/unit/api/test_chat_feature_flag.py`
2. `tests/unit/api/test_chat_stream_feature_flag.py`
3. `tests/unit/api/test_chat_persist.py`
4. `tests/unit/api/test_api.py`
5. `tests/unit/api/test_chat_anonymous.py`（改为验证 401）
6. `tests/unit/api/test_sessions_api.py`（v2 遗漏）
7. `tests/integration/test_plan_d_stack_parity.py`
8. `tests/api/test_chat_stream_error.py`
9. `tests/api/test_chat_stream_realtime.py`

**注意**：直接调用函数的测试（如 `test_chat_turn_count_is_teaching_round`）不走 HTTP，不需要 auth_headers。`test_profile_real.py` 若通过 HTTP 调 profile 也需改造。

---

## Batch 3 Complete - 验收标准

- **happy-path**：
  - register 存密码哈希（非明文）
  - login 正确密码 → 返回 token；错误密码 → 401
  - 带 token 调 /api/chat → 200 + reply
  - 带 token 调 /api/sessions → 只返回自己的会话
  - 带 token 调他人 session → 403
  - 前端登录后所有请求自动带 Authorization header
- **降级路径**：
  - 无 token 调受保护端点 → 401
  - 过期 token → 401
  - 伪造 token → 401
  - token user_id ≠ body user_id → 以 token 为准
  - 匿名请求（无 token）→ 401
- **全量回归**：582 + 新增测试全绿

## 与 phase 2 的边界

- refresh_token / blacklist / 密钥轮换：属 phase 2
- 匿名功能：本批次下线，phase 2 视需求决定是否恢复（Optional auth）
- knowledge 端点鉴权：phase 2 视需求决定
- 24h token 过期：dev 环境可接受，上 prod 前需重审（tech debt）
- session_id 客户端生成可预测：tech debt，phase 2 改服务端 UUID
