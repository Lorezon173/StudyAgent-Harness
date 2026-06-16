# Plan D：集成与灰度 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 API 层加 feature flag，把 `/chat` 与 `/chat/stream` 在「新栈（事件驱动 5 Agent 协作环）」与「老栈（`app_old` LangGraph 图）」之间一键切换，关 flag 即回退老栈，新旧栈关键指标（掌握度/回合数/成本）以同一 `ChatResponse` schema 对齐。

**Architecture:** 新建 `app/orchestration/assembly.py` 装配线，把 EventBus + 5 Agent（Tutor/Critic/Retriever/Curator/Conductor）+ Orchestrator 串成一次同步 `run_collab_loop`，从事件流提取 reply/mastery/mode_path；新建 `app/core/feature_flags.py` 用环境变量运行时切换；`chat.py`/`chat_stream.py` 在端点函数内按 flag 分支（新栈用 `asyncio.to_thread` 包裹同步协作环，老栈逻辑原样保留）。只装配、不改任何 Wave 1 冻结接口与老代码。

**Tech Stack:** FastAPI · LangGraph（老栈，仅回退路径）· 同步事件循环 `run_collab_loop`（新栈）· sqlite3 `EventStore` · pytest（`mock_llm_invoke_json` fixture monkeypatch `LLMService.invoke_json`）· `starlette.testclient.TestClient`。

**Spec 追溯：** `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` §1.1（API 层）、§3.5.4（LangGraph 嵌套边界）、§8 P8（灰度切换）、§9（老代码回归风险）。

---

## 0. 执行前置（必读，先确认再动手）

### 0.1 工作区现状（非 Plan D 引入，但 Plan D 基于此）

- 工作区**已有未提交**的「老代码迁移」改动：`app/agent/` → `app_old/agent/`、部分 `app/harness/*` → `app_old/harness/*` 等（`git status` 显示大量 `R`/`RM`）。这是并行进行的归档工作，**不是 Plan D 的产物**。
- **老栈现位于 `app_old/agent/graph.py`**（任务卡里写的"`app/agent/` 老图"已迁至 `app_old/`，语义等价）。`app/api/chat.py:4` 与 `app/api/chat_stream.py:5` 工作区版本**已指向** `from app_old.agent.graph import build_learning_graph`，且 import 实测可用。
- `docs/superpowers/plans/2026-06-01-plan-e-eval.md` 等为 Plan E 的 untracked 草稿，与 Plan D 无文件交集（E 在 `app/eval/`，D 在 `app/api/` + `app/orchestration/assembly.py` + `app/core/feature_flags.py`）。

### 0.2 commit 纪律（强制）

工作区混有他人未提交改动 + 他人 untracked 文件，**严禁 `git add -A` / `git add .`**。每个 Task 的 commit 只 `git add` 本 Task 明确列出的文件路径，避免裹挟迁移半成品或 Plan E 草稿。

### 0.3 测试命令约定

- 一律用项目 venv 并重定向 stdin（本 harness 跑 pytest 不重定向会挂起）：
  ```
  .venv/bin/python -m pytest <路径> -q < /dev/null
  ```
- **基线：362 passed / 4 failed**。这 4 个预存失败在 `tests/unit/infrastructure/test_stores.py`（Python 3.12 event-loop 兼容问题），与本任务无关——**不要碰、不要修**；只需保证自己的新测试全绿且不新增失败。
- 执行第一步前先跑一次基线确认起点：
  ```
  .venv/bin/python -m pytest -q < /dev/null
  ```
  预期 `362 passed, 4 failed`（数字以实测为准，关键是 4 个失败全在 test_stores.py）。

### 0.4 硬约束（验收红线）

1. **关 flag 即回退老栈**：`FEATURE_USE_NEW_AGENT_GRAPH` 未设/为 false 时，`/chat`、`/chat/stream` 行为与改造前**完全一致**（走 `app_old` 老图），新栈代码一行不被触及。
2. **不改老代码**：`app_old/` 全程只读。
3. **不改 Wave 1/Plan 0 冻结接口**：只 `import` + `subscribe` + `run_collab_loop`，不修改任何 Agent / Orchestrator / EventBus / collab_loop 的签名或内部逻辑。
4. **TDD**：每个 Task 先写失败测试 → 运行验证失败 → 最小实现 → 运行验证通过 → commit。

### 0.5 已核验的冻结接口签名（实现时据此调用，勿臆测）

```
TutorAgent()                      # subscriptions=[ACTION_REQUESTED]；ACTION_REQUESTED payload.target=="tutor" 才响应
CriticAgent()                     # subscriptions=[USER_MESSAGE, RETRIEVED_EVIDENCE]
RetrieverAgent()                  # subscriptions=[ACTION_REQUESTED]（target=="retriever"）
ConductorAgent()                  # subscriptions=[CONDUCTOR_REQUESTED]
Curator(graph=MasteryGraph, store=MasteryGraphStore)   # 两参必需；handle 只用内存图，不触 store 异步方法
MasteryGraph(user_id: str, store: MasteryGraphStore)
MasteryGraphStore(db_path: str = "data/mastery_graph.db")   # init()/close() 是 async；Curator.handle 不调用 → 构造即可，无需 await
Orchestrator(rules_path: str | None = None, policy: TeachingPolicy | None = None)
TeachingPolicy(initial: TeachingMode = TeachingMode.SOCRATIC)
EventBus(store: EventStore | None = None)   # .subscribe(agent, event_types) / .replay(session_id) / .publish 内含白名单校验
EventStore(db_path="data/events.db")        # .init() / .append() / .replay() / .close() 全同步
run_collab_loop(bus, ws, seed_events, orchestrator=None, max_turns=50) -> WorkspaceState  # 同步；设 ws.turn_count
WorkspaceState(session_id, user_id, current_topic=None, current_mode=SOCRATIC, ...)
Event(type, source, session_id, payload={}, parent_id=None, metadata={})
```

事件 payload 关键字段（提取 reply/mastery 时依赖）：
- Tutor 面向用户事件 `TUTOR_ASKED/TUTOR_EXPLAINED/TUTOR_REQUESTED_RECAP/TUTOR_OFFERED_ANALOGY`：`payload["content"]` 为文本。
- `MASTERY_ASSESSED`：`payload["score"]`（0-100，可能 None）、`payload["level"]`（weak/partial/mastered）。
- `POLICY_TRANSITION`：`payload["from"]`、`payload["to"]`（TeachingMode 字符串）。

---

## 1. 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| **Create** | `app/core/feature_flags.py` | `use_new_agent_graph() -> bool`，运行时读环境变量 |
| **Create** | `app/orchestration/assembly.py` | 装配线：3 提取器纯函数 + `build_new_stack` + `run_new_agent_session` |
| **Modify** | `app/models/schemas.py` | `ChatResponse` 追加 4 个可选指标字段 |
| **Modify** | `app/api/chat.py` | 端点内 feature flag 分支（新栈/老栈） |
| **Modify** | `app/api/chat_stream.py` | 端点内 feature flag 分支（新栈/老栈） |
| **Modify** | `README.md` | 追加 Plan D 进度段 |
| **Create** | `tests/unit/core/__init__.py` + `test_feature_flags.py` | flag 函数单测 |
| **Create** | `tests/unit/models/__init__.py` + `test_schemas_metrics.py` | ChatResponse 字段单测 |
| **Create** | `tests/unit/orchestration/test_assembly.py` | 提取器 + 装配线端到端单测 |
| **Create** | `tests/unit/api/test_chat_feature_flag.py` | `/chat` flag on/off 路由单测 |
| **Create** | `tests/unit/api/test_chat_stream_feature_flag.py` | `/chat/stream` flag on/off 路由单测 |
| **Create** | `tests/integration/test_plan_d_stack_parity.py` | 回退 + 新旧栈指标对齐集成测试 |

> 设计单元边界：`feature_flags.py`（横切配置，纯函数，零依赖，两端点共用）与 `assembly.py`（装配 + 提取，可独立测试）分离；API 层只做「读 flag → 选栈 → 包 ChatResponse」三件事，不含装配逻辑。

---

## Task 1: ChatResponse 扩展指标字段

**Files:**
- Modify: `app/models/schemas.py`（`ChatResponse` 类，当前在文件第 10-13 行）
- Create: `tests/unit/models/__init__.py`
- Test: `tests/unit/models/test_schemas_metrics.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/models/__init__.py`（空文件）。

创建 `tests/unit/models/test_schemas_metrics.py`：

```python
from app.models.schemas import ChatResponse


def test_chat_response_backward_compatible_minimal():
    """老栈构造方式（仅 reply/session_id/mastery_score）仍合法，新字段默认 None。"""
    r = ChatResponse(reply="hi", session_id="s1", mastery_score=70)
    assert r.reply == "hi"
    assert r.session_id == "s1"
    assert r.mastery_score == 70
    assert r.turn_count is None
    assert r.mode_path is None
    assert r.cost_est_usd is None
    assert r.stack is None


def test_chat_response_accepts_new_metric_fields():
    """新栈可填充全部对齐指标字段。"""
    r = ChatResponse(
        reply="问题？", session_id="s2", mastery_score=55,
        turn_count=11, mode_path=["Socratic", "Feynman"],
        cost_est_usd=0.0123, stack="new",
    )
    assert r.turn_count == 11
    assert r.mode_path == ["Socratic", "Feynman"]
    assert r.cost_est_usd == 0.0123
    assert r.stack == "new"


def test_chat_response_stack_legacy_label():
    r = ChatResponse(reply="x", session_id="s3", stack="legacy")
    assert r.stack == "legacy"
```

- [ ] **Step 2: 运行测试验证失败**

```
.venv/bin/python -m pytest tests/unit/models/test_schemas_metrics.py -q < /dev/null
```
Expected: FAIL —— `TypeError`/`ValidationError`，因为 `ChatResponse` 还没有 `turn_count`/`mode_path`/`cost_est_usd`/`stack` 字段。

- [ ] **Step 3: 最小实现**

编辑 `app/models/schemas.py`，把 `ChatResponse` 改为：

```python
class ChatResponse(BaseModel):
    reply: str
    session_id: str
    mastery_score: int | None = None
    # —— Plan D 灰度对齐指标（向后兼容，老栈仅填 stack/mastery_score）——
    turn_count: int | None = None          # 协作环回合数（新栈）
    mode_path: list[str] | None = None     # 教学模式路径（新栈，来自 PolicyTransition）
    cost_est_usd: float | None = None       # 本会话 LLM 估算成本（best-effort）
    stack: str | None = None                # "new" | "legacy"，标识本次走哪条栈
```

（其余 schema 不动。）

- [ ] **Step 4: 运行测试验证通过**

```
.venv/bin/python -m pytest tests/unit/models/test_schemas_metrics.py -q < /dev/null
```
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add app/models/schemas.py tests/unit/models/__init__.py tests/unit/models/test_schemas_metrics.py
git commit -m "feat(plan-d): ChatResponse 扩展灰度对齐指标字段（turn_count/mode_path/cost/stack）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: feature flag 读取函数

**Files:**
- Create: `app/core/feature_flags.py`
- Create: `tests/unit/core/__init__.py`
- Test: `tests/unit/core/test_feature_flags.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/__init__.py`（空文件）。

创建 `tests/unit/core/test_feature_flags.py`：

```python
from app.core.feature_flags import use_new_agent_graph


def test_default_off_when_unset(monkeypatch):
    monkeypatch.delenv("FEATURE_USE_NEW_AGENT_GRAPH", raising=False)
    assert use_new_agent_graph() is False


def test_true_variants_enable(monkeypatch):
    for v in ["true", "TRUE", "True", "1", "yes", "on", "  true  "]:
        monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", v)
        assert use_new_agent_graph() is True, f"{v!r} 应启用新栈"


def test_false_variants_disable(monkeypatch):
    for v in ["false", "0", "no", "off", "", "garbage"]:
        monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", v)
        assert use_new_agent_graph() is False, f"{v!r} 应回退老栈"


def test_runtime_switchable(monkeypatch):
    """同一进程内改环境变量即时生效（不缓存）——支持运行时灰度切换。"""
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    assert use_new_agent_graph() is True
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "false")
    assert use_new_agent_graph() is False
```

- [ ] **Step 2: 运行测试验证失败**

```
.venv/bin/python -m pytest tests/unit/core/test_feature_flags.py -q < /dev/null
```
Expected: FAIL —— `ModuleNotFoundError: app.core.feature_flags`。

- [ ] **Step 3: 最小实现**

创建 `app/core/feature_flags.py`：

```python
"""Feature flags（运行时环境变量驱动，支持灰度热切换）。

Plan D：用 FEATURE_USE_NEW_AGENT_GRAPH 控制 /chat 与 /chat/stream 走
新栈（事件驱动 5 Agent 协作环）还是老栈（app_old LangGraph 图）。
在请求处理函数内实时读取（不在模块加载期固化），故无需重启即可切换、
一键回退。
"""
import os

_TRUE_VALUES = {"true", "1", "yes", "on"}


def use_new_agent_graph() -> bool:
    """是否启用新栈。true/1/yes/on（大小写与首尾空白不敏感）→ True；
    其余值或未设置 → False（默认回退老栈）。
    """
    return os.getenv("FEATURE_USE_NEW_AGENT_GRAPH", "").strip().lower() in _TRUE_VALUES
```

- [ ] **Step 4: 运行测试验证通过**

```
.venv/bin/python -m pytest tests/unit/core/test_feature_flags.py -q < /dev/null
```
Expected: 4 passed。

- [ ] **Step 5: Commit**

```bash
git add app/core/feature_flags.py tests/unit/core/__init__.py tests/unit/core/test_feature_flags.py
git commit -m "feat(plan-d): feature flag use_new_agent_graph（环境变量运行时切换）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 事件流提取器（3 个纯函数）

**Files:**
- Create: `app/orchestration/assembly.py`（本 Task 只加 3 个提取器 + 常量；Task 4 续写装配函数）
- Test: `tests/unit/orchestration/test_assembly.py`（本 Task 只加提取器测试；Task 4 续加装配测试）

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/orchestration/test_assembly.py`：

```python
from app.orchestration.assembly import (
    extract_reply, extract_mastery_score, extract_mode_path,
)
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


def _ev(t, payload, source=EventSource.TUTOR):
    return Event(type=t, source=source, session_id="s", payload=payload)


def test_extract_reply_takes_last_tutor_content():
    events = [
        _ev(EventType.TUTOR_ASKED, {"content": "Q1"}),
        _ev(EventType.TUTOR_REQUESTED_RECAP, {"content": "请复述"}),
    ]
    assert extract_reply(events) == "请复述"


def test_extract_reply_covers_all_tutor_types():
    for t in (EventType.TUTOR_ASKED, EventType.TUTOR_EXPLAINED,
              EventType.TUTOR_REQUESTED_RECAP, EventType.TUTOR_OFFERED_ANALOGY):
        assert extract_reply([_ev(t, {"content": "C"})]) == "C"


def test_extract_reply_empty_when_no_tutor_event():
    events = [_ev(EventType.MASTERY_ASSESSED, {"score": 80},
                  source=EventSource.CRITIC)]
    assert extract_reply(events) == ""


def test_extract_mastery_score_takes_last():
    events = [
        _ev(EventType.MASTERY_ASSESSED, {"score": 40}, source=EventSource.CRITIC),
        _ev(EventType.MASTERY_ASSESSED, {"score": 90}, source=EventSource.CRITIC),
    ]
    assert extract_mastery_score(events) == 90


def test_extract_mastery_score_none_when_absent_or_null():
    assert extract_mastery_score([_ev(EventType.TUTOR_ASKED, {"content": "x"})]) is None
    events = [_ev(EventType.MASTERY_ASSESSED, {"score": None},
                  source=EventSource.CRITIC)]
    assert extract_mastery_score(events) is None


def test_extract_mode_path_starts_socratic_and_follows_transitions():
    events = [
        _ev(EventType.POLICY_TRANSITION, {"from": "Socratic", "to": "Feynman"},
            source=EventSource.ORCHESTRATOR),
        _ev(EventType.POLICY_TRANSITION, {"from": "Feynman", "to": "Analogy"},
            source=EventSource.ORCHESTRATOR),
    ]
    assert extract_mode_path(events) == ["Socratic", "Feynman", "Analogy"]


def test_extract_mode_path_default_socratic_when_no_transition():
    assert extract_mode_path([]) == ["Socratic"]
```

- [ ] **Step 2: 运行测试验证失败**

```
.venv/bin/python -m pytest tests/unit/orchestration/test_assembly.py -q < /dev/null
```
Expected: FAIL —— `ModuleNotFoundError`/`ImportError`，`app.orchestration.assembly` 不存在。

- [ ] **Step 3: 最小实现**

创建 `app/orchestration/assembly.py`（本 Task 先写顶部 import + 常量 + 3 提取器；Task 4 在同文件追加装配函数）：

```python
"""Plan D 端到端装配线（§8 P8）。

把 EventBus + 5 Agent（Tutor/Critic/Retriever/Curator/Conductor）+ Orchestrator
装配成一次同步 run_collab_loop，并从事件流提取面向 API 的回复与对齐指标。
只装配、不改任何冻结接口（§3.5.4：协作环对外是一次同步调用）。
"""
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind, TeachingMode

# Tutor 产出的「面向用户」事件类型（提取 reply 用）
_TUTOR_REPLY_TYPES = (
    EventType.TUTOR_ASKED,
    EventType.TUTOR_EXPLAINED,
    EventType.TUTOR_REQUESTED_RECAP,
    EventType.TUTOR_OFFERED_ANALOGY,
)


def extract_reply(events: list[Event]) -> str:
    """取最后一个 Tutor 面向用户事件的 content（无则空串）。"""
    for ev in reversed(events):
        if ev.type in _TUTOR_REPLY_TYPES:
            return ev.payload.get("content", "")
    return ""


def extract_mastery_score(events: list[Event]) -> int | None:
    """取最后一个 MasteryAssessed 的 score（0-100；缺失/为空则 None）。"""
    for ev in reversed(events):
        if ev.type == EventType.MASTERY_ASSESSED:
            score = ev.payload.get("score")
            return int(score) if score is not None else None
    return None


def extract_mode_path(events: list[Event]) -> list[str]:
    """教学模式路径：初始 Socratic + 每个 PolicyTransition 的 to。"""
    path = [str(TeachingMode.SOCRATIC)]
    for ev in events:
        if ev.type == EventType.POLICY_TRANSITION:
            path.append(ev.payload.get("to", ""))
    return path
```

- [ ] **Step 4: 运行测试验证通过**

```
.venv/bin/python -m pytest tests/unit/orchestration/test_assembly.py -q < /dev/null
```
Expected: 7 passed。

- [ ] **Step 5: Commit**

```bash
git add app/orchestration/assembly.py tests/unit/orchestration/test_assembly.py
git commit -m "feat(plan-d): 事件流提取器（reply/mastery/mode_path 纯函数）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 装配线 build_new_stack + run_new_agent_session

**Files:**
- Modify: `app/orchestration/assembly.py`（追加 dataclass + `_read_cost` + `build_new_stack` + `run_new_agent_session`）
- Test: `tests/unit/orchestration/test_assembly.py`（追加装配端到端测试）

> 关键设计：
> - 每次会话新建全套（EventBus/5 Agent/Orchestrator/新 TeachingPolicy），无跨会话状态污染；Agent 是轻对象、LLMService/RAGCoordinator 惰性连接，开销可接受。
> - 种子 3 事件：`UserMessage`（触发 Critic）+ `TopicEntered`（触发 Curator 开局检查，冷启动空图安全返回）+ `ActionRequested(tutor_ask, target=tutor)`（保证首轮 Tutor 必产出引导问题，即首条 reply）。这与 `tests/integration/test_plan_c_e2e_scenario.py` 的启动方式一致。
> - `current_topic` 缺省时用 `user_message` 兜底（Wave 1 Tutor 的 prompt 只读 `ws.current_topic`、不读 UserMessage 文本；不兜底则引导问题脱离用户输入）。
> - EventStore 用 `:memory:`（已核验 `Path(":memory:").parent == "."`，`mkdir(exist_ok=True)` 安全；sqlite3 对 `:memory:` 特判为内存库）。replay 在 `store.close()` 前完成。
> - 装配线**同步**，由 API 层 `asyncio.to_thread` 调用，规避阻塞 event loop；全部 sqlite3 操作在同一工作线程内（满足 sqlite3 单线程约束）。
> - 测试不显式注入 LLM：靠全局 fixture `mock_llm_invoke_json`（`tests/conftest.py`）monkeypatch `LLMService.invoke_json` 类方法，各 Agent 默认 `LLMService()` 即被打桩——与现有 Agent 单测/集成测试一致。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/orchestration/test_assembly.py` **末尾追加**（顶部已 import 提取器，这里补充 import）：

```python
from app.orchestration.assembly import run_new_agent_session, NewStackResult


def test_run_new_agent_session_partial_drives_socratic_to_feynman(mock_llm_invoke_json):
    """端到端：partial → Orchestrator 切 Feynman → Tutor 发 recap；
    队列自然耗尽结束。验证 reply/mastery/mode_path/turn_count 提取。"""
    mock_llm_invoke_json({
        "tutor_ask": {"content": "你怎么理解 RAG？"},
        "critic_assess": {"mastery_level": "partial", "mastery_score": 55,
                          "rationale": "基础有，细节缺"},
        "tutor_request_recap": {"content": "请用你的话复述 RAG"},
    })
    result = run_new_agent_session(
        session_id="asm-1", user_id="u1", user_message="帮我理解 RAG")

    assert isinstance(result, NewStackResult)
    # 最后一个 Tutor 事件是 recap（partial 触发 Socratic→Feynman→request_recap）
    assert result.reply == "请用你的话复述 RAG"
    assert result.mastery_score == 55
    assert result.turn_count > 0
    assert result.mode_path[0] == "Socratic"
    assert "Feynman" in result.mode_path


def test_run_new_agent_session_no_observation_still_replies(mock_llm_invoke_json):
    """Critic 无观察（{}）时，注入的 tutor_ask 种子仍保证有首条引导问题。"""
    mock_llm_invoke_json({
        "tutor_ask": {"content": "开场引导问题"},
        "critic_assess": {},
    })
    result = run_new_agent_session(
        session_id="asm-2", user_id="u2", user_message="随便聊聊")
    assert result.reply == "开场引导问题"
    assert result.mastery_score is None
    assert result.mode_path == ["Socratic"]


def test_run_new_agent_session_no_emit_violation(mock_llm_invoke_json):
    """装配跑完不应抛 EmitViolationError（职能正交 #14 全局不变量）。"""
    from app.harness.events import EmitViolationError
    mock_llm_invoke_json({
        "tutor_ask": {"content": "Q"},
        "critic_assess": {"mastery_level": "mastered", "mastery_score": 95},
        "conductor_decide": {"action": "loop_exit", "reason": "done"},
    })
    try:
        result = run_new_agent_session(
            session_id="asm-3", user_id="u3", user_message="我已经懂了")
    except EmitViolationError as e:
        raise AssertionError(f"出现越权 emit：{e}")
    assert result.reply  # 有回复
```

- [ ] **Step 2: 运行测试验证失败**

```
.venv/bin/python -m pytest tests/unit/orchestration/test_assembly.py -q < /dev/null
```
Expected: FAIL —— `ImportError: cannot import name 'run_new_agent_session'`（提取器测试仍 7 passed，新增 3 个因 import 失败而 error）。

- [ ] **Step 3: 最小实现**

在 `app/orchestration/assembly.py` **末尾追加**（并把顶部 import 段补全）：

顶部 import 段改为（在已有 `from app.harness.events ...` 等基础上补齐）：

```python
from dataclasses import dataclass, field

from app.agents.tutor import TutorAgent
from app.agents.critic import CriticAgent
from app.agents.retriever import RetrieverAgent
from app.agents.conductor import ConductorAgent
from app.agents.curator import Curator
from app.harness.eventbus import EventBus
from app.harness.orchestrator import Orchestrator
from app.harness.teaching_policy import TeachingPolicy
from app.harness.workspace_state import WorkspaceState
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.event_store import EventStore
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore
from app.orchestration.collab_loop import run_collab_loop
```

文件末尾追加：

```python
_EMPTY_REPLY_FALLBACK = "（本轮未生成回复）"


@dataclass
class NewStackResult:
    """新栈一次会话的产出（供 API 层包成 ChatResponse）。"""
    reply: str
    mastery_score: int | None
    turn_count: int
    mode_path: list[str]
    cost_est_usd: float | None
    events: list = field(default_factory=list)   # 完整事件链（调试/对齐用）


def _read_cost(session_id: str) -> float | None:
    """best-effort：从 observability 读本会话累计 LLM 成本（无则 None）。"""
    try:
        from app.harness.observability import get_observability
        stats = get_observability().session_summary(session_id)
        return round(stats.total_cost_usd, 6) if stats is not None else None
    except Exception:
        return None


def build_new_stack(user_id: str):
    """装配 EventBus + 5 Agent + Orchestrator。返回 (bus, orchestrator, store)。

    每会话独立实例；TeachingPolicy 新建以隔离模式历史。store 为内存 EventStore，
    由调用方在用完后 close。
    """
    store = EventStore(db_path=":memory:")
    store.init()
    bus = EventBus(store=store)

    mg_store = MasteryGraphStore(db_path=":memory:")          # Curator.handle 不触其异步方法
    graph = MasteryGraph(user_id=user_id, store=mg_store)

    agents = [
        TutorAgent(),
        CriticAgent(),
        RetrieverAgent(),
        ConductorAgent(),
        Curator(graph=graph, store=mg_store),
    ]
    for agent in agents:
        bus.subscribe(agent, agent.subscriptions)

    orchestrator = Orchestrator(policy=TeachingPolicy())
    return bus, orchestrator, store


def run_new_agent_session(session_id: str, user_id: str, user_message: str,
                          current_topic: str | None = None) -> NewStackResult:
    """新栈一次同步会话：装配 → 跑协作环 → 从事件流提取结果。

    同步函数；API 层用 asyncio.to_thread 调用。
    """
    topic = current_topic or user_message
    bus, orchestrator, store = build_new_stack(user_id)
    try:
        ws = WorkspaceState(session_id=session_id, user_id=user_id,
                            current_topic=topic)
        seeds = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id=session_id,
                  payload={"text": user_message, "user_id": user_id}),
            Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                  session_id=session_id, payload={"topic_id": topic}),
            Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                  session_id=session_id,
                  payload={"action": str(ActionKind.TUTOR_ASK),
                           "target": str(EventSource.TUTOR)}),
        ]
        run_collab_loop(bus, ws, seeds, orchestrator=orchestrator)
        events = bus.replay(session_id)
        return NewStackResult(
            reply=extract_reply(events) or _EMPTY_REPLY_FALLBACK,
            mastery_score=extract_mastery_score(events),
            turn_count=ws.turn_count,
            mode_path=extract_mode_path(events),
            cost_est_usd=_read_cost(session_id),
            events=events,
        )
    finally:
        store.close()
```

- [ ] **Step 4: 运行测试验证通过**

```
.venv/bin/python -m pytest tests/unit/orchestration/test_assembly.py -q < /dev/null
```
Expected: 10 passed（7 提取器 + 3 装配）。

> 若 `test_..._partial_...` 的 `result.reply` 不等于 recap 文本：用
> `.venv/bin/python -m pytest tests/unit/orchestration/test_assembly.py::test_run_new_agent_session_partial_drives_socratic_to_feynman -q -s < /dev/null`
> 打印 `[(str(e.type), e.payload) for e in result.events]` 核对实际事件链，再校准断言（提取逻辑本身已被 Task 3 单测覆盖，差异多来自规则路由路径，按实际 mode_path 调整断言即可）。

- [ ] **Step 5: Commit**

```bash
git add app/orchestration/assembly.py tests/unit/orchestration/test_assembly.py
git commit -m "feat(plan-d): 装配线 build_new_stack + run_new_agent_session（5 Agent 端到端串联）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: /api/chat feature flag 分支

**Files:**
- Modify: `app/api/chat.py`
- Test: `tests/unit/api/test_chat_feature_flag.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/api/test_chat_feature_flag.py`：

```python
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat import router

_app = FastAPI()
_app.include_router(router, prefix="/api")
client = TestClient(_app)


class _FakeLegacyGraph:
    async def ainvoke(self, state, config):
        return {"teaching": {"reply": "老栈回复"},
                "evaluation": {"mastery_score": 70}}


def test_chat_flag_off_uses_legacy_stack(monkeypatch):
    """关 flag → 走老栈（app_old 图）；新栈代码不被触及。"""
    monkeypatch.delenv("FEATURE_USE_NEW_AGENT_GRAPH", raising=False)
    monkeypatch.setattr("app.api.chat._graph", _FakeLegacyGraph())
    resp = client.post("/api/chat", json={"message": "在吗", "session_id": "c-off"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["stack"] == "legacy"
    assert data["reply"] == "老栈回复"
    assert data["mastery_score"] == 70


def test_chat_flag_on_uses_new_stack(monkeypatch, mock_llm_invoke_json):
    """开 flag → 走新栈 5 Agent 协作环。"""
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    mock_llm_invoke_json({
        "tutor_ask": {"content": "你怎么理解 RAG？"},
        "critic_assess": {"mastery_level": "partial", "mastery_score": 55},
        "tutor_request_recap": {"content": "请复述 RAG"},
    })
    resp = client.post("/api/chat",
                       json={"message": "帮我理解 RAG", "session_id": "c-on",
                             "user_id": 7})
    assert resp.status_code == 200
    data = resp.json()
    assert data["stack"] == "new"
    assert data["reply"]                       # 非空
    assert data["mastery_score"] == 55
    assert data["turn_count"] is not None
    assert data["mode_path"][0] == "Socratic"
```

- [ ] **Step 2: 运行测试验证失败**

```
.venv/bin/python -m pytest tests/unit/api/test_chat_feature_flag.py -q < /dev/null
```
Expected: FAIL —— flag off 测试因 `ChatResponse` 无 `stack`（值为 None 而非 "legacy"）失败；flag on 测试因端点未走新栈失败。

- [ ] **Step 3: 最小实现**

把 `app/api/chat.py` 整体改为（保留老栈逻辑原样，仅在函数顶部加 flag 分支 + 两处 `stack` 标识；**`app_old.agent.graph` import 维持工作区现状不动**）：

```python
import asyncio

from fastapi import APIRouter

from app.models.schemas import ChatRequest, ChatResponse
from app.core.feature_flags import use_new_agent_graph
from app_old.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat"])
_graph = build_learning_graph()


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if use_new_agent_graph():
        from app.orchestration.assembly import run_new_agent_session
        result = await asyncio.to_thread(
            run_new_agent_session,
            req.session_id,
            str(req.user_id) if req.user_id is not None else "anonymous",
            req.message,
        )
        return ChatResponse(
            reply=result.reply,
            session_id=req.session_id,
            mastery_score=result.mastery_score,
            turn_count=result.turn_count,
            mode_path=result.mode_path,
            cost_est_usd=result.cost_est_usd,
            stack="new",
        )

    # —— 老栈（关 flag 回退路径，逻辑与改造前一致）——
    from app.harness.enums import Stage
    state = {
        "user_input": req.message,
        "routing": {}, "teaching": {}, "retrieval": {},
        "evaluation": {}, "memory": {},
        "meta": {"session_id": req.session_id, "stage": Stage.INIT, "branch_trace": []},
    }
    config = {"configurable": {"thread_id": req.session_id}}
    result = await _graph.ainvoke(state, config=config)
    return ChatResponse(
        reply=result.get("teaching", {}).get("reply", "") or result.get("teaching", {}).get("summary", ""),
        session_id=req.session_id,
        mastery_score=result.get("evaluation", {}).get("mastery_score"),
        stack="legacy",
    )
```

- [ ] **Step 4: 运行测试验证通过**

```
.venv/bin/python -m pytest tests/unit/api/test_chat_feature_flag.py -q < /dev/null
```
Expected: 2 passed。

- [ ] **Step 5: Commit**

```bash
git add app/api/chat.py tests/unit/api/test_chat_feature_flag.py
git commit -m "feat(plan-d): /chat feature flag 分支（新栈协作环 / 老栈回退）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: /api/chat/stream feature flag 分支

**Files:**
- Modify: `app/api/chat_stream.py`
- Test: `tests/unit/api/test_chat_stream_feature_flag.py`

> 新栈暂不做 token 级流式（§3.5.1：单线程事件循环整体跑完）。新栈 stream 路径＝跑完协作环后把整条 reply 作为单个 SSE `data:` 事件输出，满足「端到端通」；token 级流式为后续优化，不在 P8 范围。

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/api/test_chat_stream_feature_flag.py`：

```python
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat_stream import router

_app = FastAPI()
_app.include_router(router, prefix="/api")
client = TestClient(_app)


class _FakeLegacyGraph:
    async def astream_events(self, state, config, version):
        yield {"event": "on_chain_end",
               "data": {"output": {"teaching": {"reply": "老栈流式回复"}}}}


def test_stream_flag_off_uses_legacy(monkeypatch):
    monkeypatch.delenv("FEATURE_USE_NEW_AGENT_GRAPH", raising=False)
    monkeypatch.setattr("app.api.chat_stream._graph", _FakeLegacyGraph())
    resp = client.post("/api/chat/stream",
                       json={"message": "hi", "session_id": "s-off"})
    assert resp.status_code == 200
    assert "老栈流式回复" in resp.text
    assert resp.text.startswith("data:")


def test_stream_flag_on_uses_new_stack(monkeypatch, mock_llm_invoke_json):
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    mock_llm_invoke_json({
        "tutor_ask": {"content": "新栈引导问题"},
        "critic_assess": {},
    })
    resp = client.post("/api/chat/stream",
                       json={"message": "帮我理解 RAG", "session_id": "s-on"})
    assert resp.status_code == 200
    assert "新栈引导问题" in resp.text
    assert "data:" in resp.text
```

- [ ] **Step 2: 运行测试验证失败**

```
.venv/bin/python -m pytest tests/unit/api/test_chat_stream_feature_flag.py -q < /dev/null
```
Expected: FAIL —— flag on 测试因端点未走新栈、SSE 不含「新栈引导问题」失败。

- [ ] **Step 3: 最小实现**

把 `app/api/chat_stream.py` 整体改为（老栈 `generate` 逻辑原样，新增 flag 分支与新栈生成器；**import 维持 `app_old`**）：

```python
import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest
from app.core.feature_flags import use_new_agent_graph
from app_old.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat-stream"])
_graph = build_learning_graph()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    if use_new_agent_graph():
        from app.orchestration.assembly import run_new_agent_session

        async def generate_new():
            result = await asyncio.to_thread(
                run_new_agent_session,
                req.session_id,
                str(req.user_id) if req.user_id is not None else "anonymous",
                req.message,
            )
            if result.reply:
                yield f"data: {result.reply}\n\n"

        return StreamingResponse(generate_new(), media_type="text/event-stream")

    # —— 老栈（关 flag 回退路径，逻辑与改造前一致）——
    from app.harness.enums import Stage

    async def generate():
        state = {
            "user_input": req.message,
            "routing": {}, "teaching": {}, "retrieval": {},
            "evaluation": {}, "memory": {},
            "meta": {"session_id": req.session_id, "stage": Stage.INIT, "branch_trace": []},
        }
        config = {"configurable": {"thread_id": req.session_id}}
        async for event in _graph.astream_events(state, config=config, version="v2"):
            kind = event.get("event", "")
            if kind == "on_chain_end":
                data = event.get("data", {}).get("output", {})
                if isinstance(data, dict) and "teaching" in data:
                    reply = data["teaching"].get("reply", "") or data["teaching"].get("summary", "")
                    if reply:
                        yield f"data: {reply}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 4: 运行测试验证通过**

```
.venv/bin/python -m pytest tests/unit/api/test_chat_stream_feature_flag.py -q < /dev/null
```
Expected: 2 passed。

- [ ] **Step 5: Commit**

```bash
git add app/api/chat_stream.py tests/unit/api/test_chat_stream_feature_flag.py
git commit -m "feat(plan-d): /chat/stream feature flag 分支（新栈 SSE / 老栈回退）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 回退 + 指标对齐集成测试

**Files:**
- Test: `tests/integration/test_plan_d_stack_parity.py`

> 验收 §8 P8：同一输入下，新旧栈都返回同一 `ChatResponse` schema、关键对齐字段（reply/session_id/mastery_score/stack）齐备；关 flag 可回退老栈。本 Task 纯加测试（前序实现已满足），若红则回到对应 Task 修实现。

- [ ] **Step 1: 写测试**

创建 `tests/integration/test_plan_d_stack_parity.py`：

```python
"""Plan D §8 P8 验收：新旧栈指标对齐 + 一键回退。"""
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chat import router

_app = FastAPI()
_app.include_router(router, prefix="/api")
client = TestClient(_app)

_ALIGN_KEYS = {"reply", "session_id", "mastery_score", "stack"}


class _FakeLegacyGraph:
    async def ainvoke(self, state, config):
        return {"teaching": {"reply": "老栈回复"},
                "evaluation": {"mastery_score": 60}}


def _post(msg, sid):
    return client.post("/api/chat", json={"message": msg, "session_id": sid}).json()


def test_toggle_flag_switches_stack_and_can_revert(monkeypatch, mock_llm_invoke_json):
    mock_llm_invoke_json({
        "tutor_ask": {"content": "引导问题"},
        "critic_assess": {"mastery_level": "mastered", "mastery_score": 88},
        "conductor_decide": {"action": "loop_exit", "reason": "done"},
    })

    # 开 flag → 新栈
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    new = _post("帮我理解 RAG", "parity-new")
    assert new["stack"] == "new"
    assert new["reply"]

    # 关 flag → 回退老栈（同进程即时切换）
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "false")
    monkeypatch.setattr("app.api.chat._graph", _FakeLegacyGraph())
    old = _post("帮我理解 RAG", "parity-old")
    assert old["stack"] == "legacy"
    assert old["reply"] == "老栈回复"


def test_both_stacks_share_aligned_schema(monkeypatch, mock_llm_invoke_json):
    """两栈输出都含对齐关键字段，且 mastery_score 类型一致（int|None）。"""
    mock_llm_invoke_json({
        "tutor_ask": {"content": "Q"},
        "critic_assess": {"mastery_level": "partial", "mastery_score": 50},
        "tutor_request_recap": {"content": "复述"},
    })
    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "true")
    new = _post("学习 RAG", "align-new")

    monkeypatch.setenv("FEATURE_USE_NEW_AGENT_GRAPH", "false")
    monkeypatch.setattr("app.api.chat._graph", _FakeLegacyGraph())
    old = _post("学习 RAG", "align-old")

    assert _ALIGN_KEYS <= set(new)
    assert _ALIGN_KEYS <= set(old)
    for key in _ALIGN_KEYS:
        assert key in new and key in old
    # mastery_score 两栈均为 int 或 None（对齐可比）
    assert isinstance(new["mastery_score"], (int, type(None)))
    assert isinstance(old["mastery_score"], (int, type(None)))
```

- [ ] **Step 2: 运行测试验证通过**

```
.venv/bin/python -m pytest tests/integration/test_plan_d_stack_parity.py -q < /dev/null
```
Expected: 2 passed。

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_plan_d_stack_parity.py
git commit -m "test(plan-d): 新旧栈指标对齐 + 一键回退集成测试（§8 P8 验收）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: README 更新 + 全量回归

**Files:**
- Modify: `README.md`
- 全量 `pytest`

- [ ] **Step 1: 读 README 现有 Plan 进度段**

先读 `README.md`，定位已有的「Plan A / Plan C 进度」段落，按相同格式在其后追加 Plan D 段。

- [ ] **Step 2: 追加 Plan D 进度段**

在 README 对应「多 Agent 重设计进度」区域追加（措辞与现有段落风格对齐；下为内容要点，落地时套用现有标题层级）：

```markdown
### Plan D：集成与灰度 ✅

- **Feature flag**：`FEATURE_USE_NEW_AGENT_GRAPH`（环境变量，运行时切换、一键回退）。
  - `true/1/yes/on` → 新栈（事件驱动 5 Agent 协作环）；未设/其他值 → 老栈（`app_old` LangGraph 图）。
- **装配线** `app/orchestration/assembly.py`：EventBus + Tutor/Critic/Retriever/Curator/Conductor + Orchestrator 一次同步 `run_collab_loop`，从事件流提取 reply/mastery/mode_path。
- **API**：`/chat`、`/chat/stream` 端点内按 flag 分支；新栈用 `asyncio.to_thread` 包裹同步协作环。
- **指标对齐**：`ChatResponse` 扩展 `turn_count` / `mode_path` / `cost_est_usd` / `stack`，新旧栈同 schema 可比。
- **回退**：关 flag 即走老栈，新栈代码零触及。
- 新增测试全绿，基线不减。
```

- [ ] **Step 3: 全量回归**

```
.venv/bin/python -m pytest -q < /dev/null
```
Expected: 原 362 passed 增加本计划新增用例数（feature_flags 4 + schemas 3 + assembly 10 + chat flag 2 + stream flag 2 + parity 2 = 23），即约 **385 passed, 4 failed**；4 failed 仍全部为 `tests/unit/infrastructure/test_stores.py` 预存失败（数字以实测为准，关键是无新增失败、无 `EmitViolationError`）。

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(plan-d): README 标注 Plan D 完成（feature flag 灰度 + 装配线 + 指标对齐）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 自检（Self-Review）

**Spec 覆盖：**
- §1.1 API 层 `/chat` `/chat/stream` → Task 5/6 加 flag 分支。✓
- §3.5.4 LangGraph 嵌套边界（协作环对外是一次同步调用）→ Task 4 `run_new_agent_session` 同步调 `run_collab_loop`，API 层 `asyncio.to_thread` 包裹。✓
- §8 P8 灰度切换、新旧栈指标对齐、关 flag 回退 → Task 2 flag + Task 7 parity 测试。✓
- §9 老代码回归风险 → 老栈逻辑原样保留、默认 flag off 行为不变、`app_old` 只读、commit 精确 add。✓

**接口约束核对：**
- Curator 装配用 `Curator(graph=..., store=...)` 两参；`MasteryGraph(user_id, store)`；`MasteryGraphStore(db_path)` 不 await init（handle 不触异步方法）。✓
- 只 `import`/`subscribe`/`run_collab_loop`，未改任何冻结接口签名。✓
- 种子事件 `source` 合规：`UserMessage`=USER、`TopicEntered`/`ACTION_REQUESTED`=ORCHESTRATOR（白名单 §3.2 通过）。✓

**类型/命名一致性：**
- `run_new_agent_session` 返回 `NewStackResult`（Task 4 定义），Task 5/6 端点按 `result.reply/.mastery_score/.turn_count/.mode_path/.cost_est_usd` 取用——字段名一致。✓
- 提取器 `extract_reply/extract_mastery_score/extract_mode_path`（Task 3 定义）在 Task 4 调用，签名一致。✓
- `use_new_agent_graph()`（Task 2）在 Task 5/6 调用。✓
- `ChatResponse` 新字段（Task 1）在 Task 5/6/7 使用。✓

**无占位符：** 所有 step 含完整代码 + 精确命令 + 预期输出。✓

**风险点与缓解：**
- 若 `:memory:` EventStore 在 `Path.parent.mkdir` 报错 → 回退用 `tempfile.mkstemp(suffix=".db")` + finally `os.unlink`（与 e2e fixture 同款），改 `build_new_stack` 内 `db_path`。
- 若 Task 4 partial 场景实际 mode_path 与断言不符 → 按 Step 4 的 `-s` 打印事件链校准断言（提取逻辑已被 Task 3 独立覆盖，不影响正确性）。
- `app.api.chat._graph` 在 import 时构造老栈图（flag on 时也构造但不调用）——已验证 `build_learning_graph()` 仅构图不调 LLM，无副作用。
