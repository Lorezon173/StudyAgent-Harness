# Persistence + Streaming 批次二 Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.
> **设计来源**：`docs/designs/2026-06-14-fix-persistence-streaming-issues.md` §P1-④、§P1-⑥、§落地顺序「批次二」。
> **前置**：批次一（Task 1-6）已完成并通过审查（commit 6c52d30 + 审查修复 9dc1bd8）。

**Goal:** 修复 persistence + streaming 的 2 个 P1 问题（P1-④ SSE 中途异常未结构化暴露、P1-⑥ 匿名用户图谱共享污染）。

**Architecture:** 不改批次一已建立的三段连接骨架；P1-④ 仅规范化 error 事件 schema（已部分实现，本批次补齐 code/message/retryable 字段）；P1-⑥ 在 load 阶段按 `user_id is None` 跳过 MasteryGraph 构造（graph=None），并守卫 persist 阶段的 store rebind。

**Tech Stack:** FastAPI, SQLAlchemy (async), pytest, SSE (Server-Sent Events)。

## Global Constraints

- 四层架构单向依赖：API → Orchestration → Harness → Infrastructure，严禁反向依赖
- 不引入新依赖
- 不修改任何冻结接口（协作环对外是一次同步调用）
- 所有命令用 `uv run` 前缀（项目用 uv 管理）
- 编码完成后必须经 code-review-three-rounds skill 审查通过再提交

---

## 验证状态表（提交 review 前的事实核实记录）

| 断言 | 验证状态 | 依据 |
|---|---|---|
| `chat_stream.py:63-68` 现有 error 事件 schema 为 `{"type":"error","error":str(e),"persisted":False}` | ✅ Read | 当前文件 line 63-68 |
| 设计文档要求 schema 为 `{"type":"error","code":...,"message":...,"retryable":false}` | ✅ Read | design doc line 322-325 |
| `chat.py:41` / `chat_stream.py:76` 无条件执行 `graph._store = SQLAlchemyMasteryStore(persist_db)` | ✅ Read | 当前文件，graph=None 时会 AttributeError |
| `persist_turn` 已支持 `graph=None`（`if graph is not None` 跳过 save） | ✅ Read | `_persist.py:31` |
| `persist_turn` 已支持 `user_id=None`（`if user_id is not None` 跳过 clear_dirty） | ✅ Read | `_persist.py:36-37` |
| `test_chat_stream_realtime.py` 仅测 happy path，不覆盖 error 事件 | ✅ Read | 该文件无 "error" 断言，改 schema 不破坏它 |
| 现有 `chat.py`/`chat_stream.py` 对匿名用户构造 `MasteryGraph(user_id="anonymous")` | ✅ Read | `chat.py:23,27` / `chat_stream.py:29,37` |
| `run_new_agent_session` 第 5 个位置参数为 graph，可接受 None | ✅ Read | `assembly.py:132-134`；`build_new_stack` graph=None 时内部自建 :memory: store |

---

## File Structure

| 文件 | 责任 | 操作 |
|---|---|---|
| `app/api/chat_stream.py` | error 事件 schema 规范化（P1-④）+ 匿名跳过图谱（P1-⑥） | 修改 |
| `app/api/chat.py` | 匿名跳过图谱 + 守卫 rebind（P1-⑥） | 修改 |
| `tests/api/test_chat_stream_error.py` | SSE error 事件 schema 单元测试（P1-④） | 新建 |
| `tests/unit/api/test_chat_anonymous.py` | 匿名用户不写 mastery 单元测试（P1-⑥） | 新建 |

---

### Task 7: P1-④ SSE error 事件 schema 规范化

**问题**：批次一审查修复时实现了 SSE error 事件，但 schema 与设计文档不符——
- 现状（`chat_stream.py:63-68`）：`{"type":"error","error":str(e),"persisted":False}`
- 设计文档（design doc:322-325）：`{"type":"error","code":"AGENT_ERROR"|"PERSIST_FAILED","message":...,"retryable":false}`

**Files:**
- Modify: `app/api/chat_stream.py:59-69`（协作环失败的 error 事件）
- Create: `tests/api/test_chat_stream_error.py`

**Interfaces:**
- Produces: SSE error 事件，schema = `{"type":"error","code":str,"message":str,"retryable":bool}`

**code 取值约定**（设计文档 S-5）：
- `AGENT_ERROR`：协作环（`await task`）抛异常 → 当前 Task 7 范围
- `PERSIST_FAILED`：persist 阶段失败 → 当前 persist 失败走的是 `persisted=false` final 事件，**不**改为 error 事件（保持批次一语义：persist 失败仍返回 reply）。故本批次 error 事件只有 `AGENT_ERROR` 一种来源。

- [ ] **Step 1: Write failing test**

```python
# tests/api/test_chat_stream_error.py
# 复用 test_chat_stream_realtime.py 的 DB 隔离 + monkeypatch 模式。
# fake_run 抛异常 → 验证 SSE 流以结构化 error 事件结束（含 code/message/retryable）。
```

测试要点：
- mock `run_new_agent_session` 抛 `RuntimeError("agent boom")`
- 断言 body 含一个 `{"type":"error","code":"AGENT_ERROR","message":"agent boom","retryable":false}` 事件
- 断言流正常结束（不是连接崩断）

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_chat_stream_error.py -v`
Expected: FAIL（当前 schema 是 `{"error":...}` 无 `code`/`message`/`retryable`）

- [ ] **Step 3: Implement schema 规范化**

`chat_stream.py:63-68` 改为：
```python
error_event = {
    "type": "error",
    "code": "AGENT_ERROR",
    "message": str(e),
    "retryable": False,
}
```
（移除 `persisted` 字段——error 事件不是 final 事件，不承载 persisted 语义）

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_chat_stream_error.py -v`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `uv run pytest tests/ -q`
Expected: 全绿（含 test_chat_stream_realtime.py happy path 不受影响）

- [ ] **Step 6: 代码审查（code-review-three-rounds skill）→ commit**

---

### Task 8: P1-⑥ 匿名用户不写 mastery

**问题**：当前 `req.user_id is None` 时仍构造 `MasteryGraph(user_id="anonymous")`，所有匿名用户共享同一张 "anonymous" 图谱 → 污染。

**决策（设计文档 N2 降级）**：匿名请求 `graph=None`，根本不碰图谱。

**Files:**
- Modify: `app/api/chat.py`（load 阶段跳过构造 + persist 阶段守卫 rebind）
- Modify: `app/api/chat_stream.py`（同上）
- Create: `tests/unit/api/test_chat_anonymous.py`

**Interfaces:**
- Consumes: `persist_turn(graph=None)`（已支持，无需改 _persist.py）

**关键改动（两处文件对称）**：

1. **load 阶段**：`user_id is None` 时不构造 MasteryGraph
```python
graph = None
if req.user_id is not None:
    async with async_session() as load_db:
        graph = MasteryGraph(user_id=uid_str, store=SQLAlchemyMasteryStore(load_db))
        await graph.load()
```

2. **persist 阶段守卫 rebind**（关键——否则 graph=None 时 `graph._store=...` 会 AttributeError）：
```python
async with async_session() as persist_db:
    if graph is not None:
        graph._store = SQLAlchemyMasteryStore(persist_db)
    turn_index = await persist_turn(persist_db, ..., graph=graph)
```

3. `uid_str` 仍传给 `run_new_agent_session`（协作环内部 graph=None 时自建 :memory: store，行为不变）

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/api/test_chat_anonymous.py
# 复用 test_chat_persist.py 的 _make_client_with_patched_db + db_fixture 模式。
```

测试要点（非流式 + 流式各一组）：
- `user_id=None` 请求 → 验证 MasteryGraph **未被构造**（patch MasteryGraph 断言 not called，或验证 mastery_nodes 表无 "anonymous" 行）
- `user_id=None` 请求 → 仍返回 200 + reply（功能不降级）
- `user_id=None` 请求 → messages 仍落库（session/message 不依赖 graph）

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/api/test_chat_anonymous.py -v`
Expected: FAIL（当前 anonymous 会构造图谱并写 mastery_nodes）

- [ ] **Step 3: Implement chat.py 改动**

按上述 load 跳过 + persist 守卫 rebind。

- [ ] **Step 4: Implement chat_stream.py 改动**

对称改动（注意 chat_stream 的 load 在 `generate_new()` 内部）。

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/api/test_chat_anonymous.py -v`
Expected: PASS

- [ ] **Step 6: 全量回归**

Run: `uv run pytest tests/ -q`
Expected: 全绿

- [ ] **Step 7: 代码审查（code-review-three-rounds skill）→ commit**

---

## Batch 2 Complete - 验收标准

- All tests pass（含新增 test_chat_stream_error.py + test_chat_anonymous.py）
- **happy-path**：
  - SSE 协作环异常 → 客户端收到 `{"type":"error","code":"AGENT_ERROR",...}` 事件且流正常结束
  - 匿名请求（user_id=None）→ 200 + reply + messages 落库，但 mastery_nodes 无 "anonymous" 行
- **降级路径**：
  - 已登录用户（user_id≠None）→ 行为与批次一完全一致（graph 正常 load/save）
  - persist 失败 → 仍走 `persisted=false` final 事件（不改为 error 事件）

---

## 与批次三的边界

- P0-③（JWT 鉴权）属批次三，本批次不碰。
- N2 降级的前提：批次三 JWT 上线后"匿名用户"概念消失，本批次的 `if user_id is None` 分支届时成为永不执行的死代码——这是**已知的、可接受的**短期负债（设计文档 §P1-⑥ N2 理由）。
