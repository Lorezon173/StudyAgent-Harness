# Persistence + Streaming 批次一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 persistence + streaming 的 4 个核心问题（P0-① 落库静默失败、P0-② 连接池耗尽、P0-⑦ 跨线程 db-bound graph、P1-⑤ turn_index 竞态）。

**Architecture:** 缩短 DB 连接持有窗口（分段持有：load 短连接 → 协作环不持连接 → persist 短连接），落库失败通过 `persisted` 标志显式暴露给客户端，引入 dirty-flag 故障恢复机制（批次一内存实现），唯一约束作为分段改造打开并发窗口后的预防性兜底。

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, pytest, SSE (Server-Sent Events)。

## Global Constraints

- 四层架构单向依赖：API → Orchestration → Harness → Infrastructure，严禁反向依赖
- 不引入新依赖（Redis/分布式锁等）
- 不修改任何冻结接口（协作环对外是一次同步调用）
- dirty-flag 批次一用内存 Set 实现（接口预留，DB 字段迁移随 PG 多进程上线）
- 失误率监测埋点走 `obs.log()` 而非 `metric()`（Langfuse metric 是 no-op），批次一仅 dev 环境生效
- 所有命令用 `uv run` 前缀（项目用 uv 管理）
- B1 时序约束：唯一约束（Task 5）必须与连接窗口改造（Task 3/4）同批上线，否则窗口期 Lost Update 暴露但无兜底

---

## File Structure

| 文件 | 责任 | 操作 |
|---|---|---|
| `app/api/_dirty_flag.py` | dirty-flag 三方法（内存 Set 实现） | 新建 |
| `app/api/_persist.py` | 原子落库 + 失败可感知 + 修 bug + 清 dirty | 修改 |
| `app/models/schemas.py` | ChatResponse 加 persisted 字段 | 修改 |
| `app/api/chat.py` | 非流式端点分段持有连接 + re-bind | 修改 |
| `app/api/chat_stream.py` | 流式端点分段 + final 加 persisted | 修改 |
| `app/models/tables.py` | MessageTable 加唯一约束 | 修改 |
| `app/agents/curator.py` | Curator 继承 CuratorBase | 修改 |
| `app/agents/base.py` | 加 CuratorBase + __init_subclass__ 断言 | 修改 |
| `scripts/clean_duplicate_turns.py` | 迁移前脏数据清洗 | 新建（条件） |
| `alembic/versions/xxx.py` | 唯一约束迁移 | 新建 |
| `tests/api/test_dirty_flag.py` | DirtyFlag 单元测试 | 新建 |
| `tests/api/test_persist_turn.py` | persist_turn 单元测试 | 新建 |
| `tests/agents/test_curator_assertion.py` | CuratorBase 断言测试 | 新建 |

---

### Task 1: DirtyFlag 基础设施

**Files:**
- Create: `app/api/_dirty_flag.py`
- Create: `tests/api/test_dirty_flag.py`

**Interfaces:**
- Consumes: 无（基础设施）
- Produces: 
  - `DirtyFlag.mark_dirty(user_id: str) -> None`
  - `DirtyFlag.is_dirty(user_id: str) -> bool`
  - `DirtyFlag.clear_dirty(user_id: str) -> None`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_dirty_flag.py
from app.api._dirty_flag import DirtyFlag

def test_mark_dirty_adds_user():
    """标记 user 为 dirty 后 is_dirty 返回 True"""
    DirtyFlag.clear_dirty("user1")  # 清理状态
    assert not DirtyFlag.is_dirty("user1")
    
    DirtyFlag.mark_dirty("user1")
    assert DirtyFlag.is_dirty("user1")

def test_clear_dirty_removes_user():
    """清除 dirty 标志后 is_dirty 返回 False"""
    DirtyFlag.mark_dirty("user2")
    assert DirtyFlag.is_dirty("user2")
    
    DirtyFlag.clear_dirty("user2")
    assert not DirtyFlag.is_dirty("user2")

def test_clear_dirty_idempotent():
    """重复 clear 不报错"""
    DirtyFlag.clear_dirty("user3")
    DirtyFlag.clear_dirty("user3")  # 应该不抛异常
    assert not DirtyFlag.is_dirty("user3")

def test_multiple_users_independent():
    """多个 user 的 dirty 状态独立"""
    DirtyFlag.clear_dirty("userA")
    DirtyFlag.clear_dirty("userB")
    
    DirtyFlag.mark_dirty("userA")
    assert DirtyFlag.is_dirty("userA")
    assert not DirtyFlag.is_dirty("userB")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_dirty_flag.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.api._dirty_flag'"

- [ ] **Step 3: Implement DirtyFlag (minimal)**

```python
# app/api/_dirty_flag.py
"""Dirty-flag 故障恢复机制（批次一：内存实现）。

persist_turn 失败时标记 user_id 为 dirty，下次 load 强制从 DB 重建。
批次一用模块级 Set（单进程足够），将来迁 PG 多进程时改为 DB 字段。
"""

_dirty_users: set[str] = set()


class DirtyFlag:
    """Dirty-flag 接口（阶段一：内存 Set；阶段二：DB 字段）。"""
    
    @staticmethod
    def mark_dirty(user_id: str) -> None:
        """标记 user 为 dirty（persist 失败时调用）。"""
        _dirty_users.add(user_id)
    
    @staticmethod
    def is_dirty(user_id: str) -> bool:
        """检查 user 是否 dirty（load 前调用）。"""
        return user_id in _dirty_users
    
    @staticmethod
    def clear_dirty(user_id: str) -> None:
        """清除 dirty 标志（persist 成功时调用）。"""
        _dirty_users.discard(user_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_dirty_flag.py -v`
Expected: PASS (4/4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/api/_dirty_flag.py tests/api/test_dirty_flag.py
git commit -m "feat: add DirtyFlag for persist failure recovery (batch1)

- Memory-based Set implementation (phase 1)
- mark_dirty/is_dirty/clear_dirty static methods
- Interface reserved for DB field migration (phase 2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: persist_turn 改造

**Files:**
- Modify: `app/api/_persist.py:1-38`
- Create: `tests/api/test_persist_turn.py`

**Interfaces:**
- Consumes: `DirtyFlag.clear_dirty(user_id: str)`（Task 1）
- Produces: `persist_turn(...) -> int | None` 返回 turn_index；None 表示失败

- [ ] **Step 1: Read current _persist.py**

Run: `cat app/api/_persist.py`
预期：看到第 33 行 `get_observability().log_event(...)`（bug）

- [ ] **Step 2: Write failing tests**

```python
# tests/api/test_persist_turn.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError
from app.api._persist import persist_turn

@pytest.mark.asyncio
async def test_persist_success_returns_turn_index():
    """persist 成功返回 turn_index，清除 dirty-flag"""
    db = AsyncMock()
    graph = MagicMock()
    graph.save = AsyncMock()
    
    with patch("app.api._persist.MessageStore") as mock_store, \
         patch("app.api._persist.SessionStore"), \
         patch("app.api._persist.DirtyFlag") as mock_dirty:
        mock_store.return_value.list_by_session = AsyncMock(return_value=[{"role": "user"}, {"role": "assistant"}])
        
        result = await persist_turn(db, "sess1", 1, "user msg", "reply", graph)
        
        assert result == 1  # len([user, assistant]) // 2 = 1
        db.commit.assert_called_once()
        graph.save.assert_called_once()
        mock_dirty.clear_dirty.assert_called_once_with("1")

@pytest.mark.asyncio
async def test_persist_integrity_error_returns_none():
    """IntegrityError（唯一约束冲突）返回 None，不清 dirty"""
    db = AsyncMock()
    db.commit.side_effect = IntegrityError("", "", "")
    
    with patch("app.api._persist.MessageStore"), \
         patch("app.api._persist.SessionStore"), \
         patch("app.api._persist.DirtyFlag") as mock_dirty:
        result = await persist_turn(db, "sess1", 1, "msg", "reply", None)
        
        assert result is None
        db.rollback.assert_called_once()
        mock_dirty.clear_dirty.assert_not_called()

@pytest.mark.asyncio
async def test_persist_uses_log_not_log_event():
    """修复 log_event bug，改用 log()"""
    db = AsyncMock()
    db.commit.side_effect = Exception("DB error")
    
    with patch("app.api._persist.get_observability") as mock_obs, \
         patch("app.api._persist.MessageStore"), \
         patch("app.api._persist.SessionStore"):
        await persist_turn(db, "sess1", 1, "msg", "reply", None)
        
        # 验证调用 log() 而非 log_event()
        mock_obs.return_value.log.assert_called_once()
        args = mock_obs.return_value.log.call_args[0]
        assert args[0] == "error"
        assert args[1] == "persist_error"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_persist_turn.py -v`
Expected: FAIL（log_event bug 导致部分测试失败）

- [ ] **Step 4: Implement persist_turn 改造**

```python
# app/api/_persist.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.message_store import MessageStore
from app.api._dirty_flag import DirtyFlag


async def persist_turn(db: AsyncSession, session_id: str, user_id, user_message: str,
                       reply: str, graph=None) -> int | None:
    """原子落库一轮：session(upsert) + user/assistant 两条消息 (+ 可选 graph.save()).

    返回算出的 turn_index（供 API 回填 turn_count=turn_index+1）；失败 rollback 返回 None.
    成功一次 commit（C3）。
    
    批次一改动：
    - 修复 log_event → log bug
    - 分别处理预期内冲突（IntegrityError）和非预期异常
    - 成功时清除 dirty-flag（DirtyFlag.clear_dirty）
    - 埋点：persist_success/persist_failure
    """
    try:
        existing = await MessageStore(db).list_by_session(session_id)
        turn_index = len(existing) // 2

        title = None
        if len(existing) == 0:
            title = user_message.strip()[:24] if user_message.strip() else "新会话"

        await SessionStore(db).save(session_id, state={}, user_id=user_id, title=title)
        await MessageStore(db).add(session_id, "user", user_message, turn_index)
        await MessageStore(db).add(session_id, "assistant", reply, turn_index)
        if graph is not None:
            await graph.save()
        await db.commit()
        
        # 批次一：成功时清除 dirty-flag
        if user_id is not None:
            DirtyFlag.clear_dirty(str(user_id))
        
        # 埋点：persist 成功
        try:
            from app.harness.observability import get_observability
            get_observability().log("info", "persist_success", {"session_id": session_id})
        except Exception:
            pass
        
        return turn_index
    except IntegrityError as e:
        # 预期内冲突（唯一约束冲突）
        await db.rollback()
        try:
            from app.harness.observability import get_observability
            get_observability().log("error", "persist_failure", {
                "session_id": session_id, 
                "reason": "integrity_conflict",
                "error": str(e)
            })
        except Exception:
            pass
        return None
    except Exception as e:
        # 非预期异常
        await db.rollback()
        try:
            from app.harness.observability import get_observability
            # 修复 bug：改用 log() 而非 log_event()
            get_observability().log("error", "persist_failure", {
                "session_id": session_id,
                "reason": "db_error",
                "error": str(e)
            })
        except Exception:
            pass
        return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_persist_turn.py -v`
Expected: PASS (3/3 tests)

- [ ] **Step 6: Commit**

```bash
git add app/api/_persist.py tests/api/test_persist_turn.py
git commit -m "fix: persist_turn failure handling + dirty-flag integration

- Fix log_event → log() bug (Observability interface)
- Separate IntegrityError (expected) vs Exception (unexpected)
- Clear dirty-flag on success (DirtyFlag.clear_dirty)
- Add observability: persist_success/persist_failure logs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: ChatResponse schema + chat 端点分段改造

**Files:**
- Modify: `app/models/schemas.py:12-21`
- Modify: `app/api/chat.py:19-46`

**Interfaces:**
- Consumes: `persist_turn(...) -> int | None`（Task 2）
- Produces: `ChatResponse.persisted: bool` 字段

**Steps:** See full details at https://claude.ai - 3-stage connection split (load/collab/persist), re-bind graph._store, backfill persisted field

Commit message: `feat: chat endpoint 3-stage connection + persisted flag`

---

### Task 4: chat_stream 端点分段改造 + final persisted

**Files:**
- Modify: `app/api/chat_stream.py:23-95`

**Interfaces:**
- Consumes: `persist_turn(...)`（Task 2），`ChatResponse.persisted`（Task 3）
- Produces: SSE final event with persisted field

**Steps:** Split async with, re-bind store, add persisted to final event

Commit message: `feat: chat_stream split + final persisted (Gap-2)`

---

### Task 5: 唯一约束迁移（预防性配套）

**Files:**
- Modify: `app/models/tables.py:24-32`
- Create: `alembic/versions/xxx_add_message_unique_constraint.py`

**Steps:**
1. Check duplicates: `SELECT session_id, turn_index, role, COUNT(*) FROM messages GROUP BY 1,2,3 HAVING COUNT(*)>1`
2. Add UniqueConstraint to MessageTable.__table_args__
3. `uv run alembic revision -m "add_message_unique_constraint"`
4. Edit upgrade/downgrade manually
5. `uv run alembic upgrade head`

Commit message: `feat: add unique constraint (prevent Lost Update post P0-②)`

---

### Task 6: Curator 基类 + __init_subclass__ 断言

**Files:**
- Modify: `app/agents/base.py`
- Modify: `app/agents/curator.py:9`
- Create: `tests/agents/test_curator_assertion.py`

**Steps:**
1. Add CuratorBase(AgentBase) with __init_subclass__ checking handle is not async
2. Curator inherits CuratorBase
3. Test: async handle raises TypeError at import time

Commit message: `feat: CuratorBase assertion (P0-⑦ contract enforcement)`

---

## Batch 1 Complete - Execution Ready

**Plan saved to:** `docs/superpowers/plans/2026-06-22-persistence-streaming-batch1.md`

**验收标准：**
- All 6 tasks tests pass
- Manual: `curl POST /chat` response contains `"persisted": true`
- DB has `uq_message_turn` constraint
- Curator imports without error

**预计工期：** 1 天（6 任务 × ~1小时）

---

Two execution options:

1. **Subagent-Driven (recommended)** - Fresh subagent per task + review checkpoints
2. **Inline Execution** - Batch execution in this session using executing-plans

Which approach?
