# Plan 0 — 核心契约地基 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立事件驱动多 Agent 系统的核心契约地基——枚举、Event 模型、所有权白名单、WorkspaceState、EventStore、EventBus、AgentBase、协作环骨架、主图骨架，作为 Wave 1（Plan A/B/C）全部并行实施的接口前置。

**Architecture:** 严格自底向上、顺序 TDD：枚举 → 事件模型+优先级 → 所有权白名单 → 会话状态 → 事件存储 → 事件总线 → Agent 基类 → 协作环骨架 → 主图骨架。每个组件先写失败测试再最小实现，每 Task 末提交。协作环是**单线程同步事件循环**（§3.5），故 EventStore 用同步 `sqlite3`（标准库），不引入 async。

**Tech Stack:** Python 3.11（`StrEnum` / `dataclass`）· `sqlite3`（同步，标准库）· `langgraph`（主图骨架）· `pytest`（同步测试，沿用现有 `asyncio.run` 风格仅在需要时）。

**Design Specs:** `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md`
- §3.1 EventBus 数据模型 · §3.2 事件清单+所有权白名单 · §3.5 协作环执行模型 · §2.2 Agent 契约 · §6 核心数据结构 · §4.1 教学模式

---

## File Structure

```
Modify: app/harness/enums.py                       # 加 EventType / EventSource / TeachingMode / ActionKind
Create: app/harness/events.py                       # Event dataclass + new_event_id + EVENT_PRIORITY + 白名单 + EmitViolationError
Create: app/harness/workspace_state.py              # WorkspaceState dataclass（§6）
Create: app/infrastructure/storage/event_store.py   # EventStore（同步 sqlite3，append + replay）
Create: app/harness/eventbus.py                     # EventBus（publish[校验+持久化] / subscribe / subscribers_of / replay）
Create: app/agents/__init__.py                      # 新包
Create: app/agents/base.py                          # AgentBase（source/subscriptions/emittable_types/handle/emit/evaluate）
Create: app/orchestration/__init__.py               # 新包
Create: app/orchestration/collab_loop.py            # 协作环骨架（优先级队列 + 回合屏障钩子 + MAX_TURNS 熔断）
Create: app/orchestration/graph.py                  # 4 节点主图骨架（ingest/route/collab_loop/wrap_up）

Create: tests/unit/harness/test_events.py
Create: tests/unit/harness/test_workspace_state.py
Create: tests/unit/harness/test_eventbus.py
Create: tests/unit/infrastructure/test_event_store.py
Create: tests/unit/agents/__init__.py
Create: tests/unit/agents/test_agent_base.py
Create: tests/unit/orchestration/__init__.py
Create: tests/unit/orchestration/test_collab_loop.py
Create: tests/unit/orchestration/test_graph.py
Modify: tests/unit/harness/test_enums.py            # 追加新枚举断言
```

**依赖顺序**：Task 1（enums）→ Task 2（events 依赖 enums）→ Task 3（白名单依赖 events）→ Task 4（state）→ Task 5（event_store 依赖 events）→ Task 6（eventbus 依赖 events+event_store）→ Task 7（base 依赖 events+state+eventbus）→ Task 8（collab_loop 依赖全部）→ Task 9（graph）→ Task 10（回归）。

---

## Task 1: 枚举扩展 — EventType / EventSource / TeachingMode / ActionKind

**Files:**
- Modify: `app/harness/enums.py`（在文件末尾追加 4 个枚举）
- Test: `tests/unit/harness/test_enums.py`（追加断言）

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/harness/test_enums.py` 末尾追加：

```python
from app.harness.enums import EventType, EventSource, TeachingMode, ActionKind


def test_event_type_covers_whitelist():
    # §3.2 五类产出 + 控制类，逐一存在
    assert EventType.USER_MESSAGE == "UserMessage"
    assert EventType.TUTOR_ASKED == "TutorAsked"
    assert EventType.RETRIEVED_EVIDENCE == "RetrievedEvidence"
    assert EventType.MASTERY_ASSESSED == "MasteryAssessed"
    assert EventType.GRAPH_PREREQ_WEAK_DETECTED == "GraphPrereqWeakDetected"
    assert EventType.TOPIC_ENTERED == "TopicEntered"
    assert EventType.ORCHESTRATOR_TICK == "OrchestratorTick"
    assert EventType.CONDUCTOR_DECIDED == "ConductorDecided"


def test_event_source_seven_roles():
    # §3.1 source 七角色（含 orchestrator）
    roles = {s.value for s in EventSource}
    assert roles == {"user", "tutor", "retriever", "critic",
                     "curator", "conductor", "orchestrator"}


def test_teaching_mode_four():
    assert {m.value for m in TeachingMode} == {"Socratic", "Feynman", "Analogy", "Regress"}


def test_action_kind_has_probe_prereq():
    # §3.4 新增动作
    assert ActionKind.TUTOR_PROBE_PREREQ == "tutor_probe_prereq"
    assert ActionKind.REGRESS_TO_PREREQ == "regress_to_prereq"
    assert ActionKind.REQUEST_OBSERVATION == "request_observation"
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/unit/harness/test_enums.py -q`
Expected: FAIL — `ImportError: cannot import name 'EventType'`

- [ ] **Step 3: 在 `app/harness/enums.py` 末尾追加实现**

```python
class EventType(StrEnum):
    """事件类型（§3.2）— 值即 §3.2 白名单中的事件名"""
    # 用户输入类
    USER_MESSAGE = "UserMessage"
    USER_UPLOADED = "UserUploaded"
    # Tutor 产出类
    TUTOR_ASKED = "TutorAsked"
    TUTOR_EXPLAINED = "TutorExplained"
    TUTOR_REQUESTED_RECAP = "TutorRequestedRecap"
    TUTOR_OFFERED_ANALOGY = "TutorOfferedAnalogy"
    # Retriever 产出类
    RETRIEVED_EVIDENCE = "RetrievedEvidence"
    RETRIEVAL_FAILED = "RetrievalFailed"
    # Critic 产出类
    MASTERY_ASSESSED = "MasteryAssessed"
    CONFUSION_DETECTED = "ConfusionDetected"
    CONTRADICTION_DETECTED = "ContradictionDetected"
    LOW_CONFIDENCE_DETECTED = "LowConfidenceDetected"
    RAG_QUALITY_ASSESSED = "RAGQualityAssessed"
    # Curator 产出类
    PROFILE_UPDATED = "ProfileUpdated"
    GRAPH_NODE_STRENGTHENED = "GraphNodeStrengthened"
    GRAPH_PREREQ_WEAK_DETECTED = "GraphPrereqWeakDetected"
    # 控制类
    TOPIC_ENTERED = "TopicEntered"
    LOOP_EXIT = "LoopExit"
    POLICY_TRANSITION = "PolicyTransition"
    ACTION_REQUESTED = "ActionRequested"
    CONDUCTOR_REQUESTED = "ConductorRequested"
    CONDUCTOR_DECIDED = "ConductorDecided"
    ORCHESTRATOR_TICK = "OrchestratorTick"


class EventSource(StrEnum):
    """事件来源身份（§3.1 source）— 七角色"""
    USER = "user"
    TUTOR = "tutor"
    RETRIEVER = "retriever"
    CRITIC = "critic"
    CURATOR = "curator"
    CONDUCTOR = "conductor"
    ORCHESTRATOR = "orchestrator"


class TeachingMode(StrEnum):
    """融合式教学四模式（§4.1）"""
    SOCRATIC = "Socratic"
    FEYNMAN = "Feynman"
    ANALOGY = "Analogy"
    REGRESS = "Regress"


class ActionKind(StrEnum):
    """Orchestrator 可下达的动作（§3.4）"""
    RETRIEVER_SEARCH = "retriever_search"
    RETRIEVER_EXPAND_QUERY = "retriever_expand_query"
    TUTOR_ASK = "tutor_ask"
    TUTOR_EXPLAIN = "tutor_explain"
    TUTOR_RE_EXPLAIN = "tutor_re_explain"
    TUTOR_REQUEST_RECAP = "tutor_request_recap"
    TUTOR_OFFER_ANALOGY = "tutor_offer_analogy"
    TUTOR_CORRECT = "tutor_correct"
    TUTOR_PROBE_PREREQ = "tutor_probe_prereq"
    REGRESS_TO_PREREQ = "regress_to_prereq"
    CONDUCTOR_DECIDE = "conductor_decide"
    REQUEST_OBSERVATION = "request_observation"
    LOOP_EXIT = "loop_exit"
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/unit/harness/test_enums.py -q`
Expected: PASS（全部断言通过）

- [ ] **Step 5: 提交**

```bash
git add app/harness/enums.py tests/unit/harness/test_enums.py
git commit -m "feat(plan0): add EventType/EventSource/TeachingMode/ActionKind enums"
```

---

## Task 2: Event 数据模型 + 时序 ID + 出队优先级

**Files:**
- Create: `app/harness/events.py`
- Test: `tests/unit/harness/test_events.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/harness/test_events.py
import time
from app.harness.events import Event, new_event_id, EVENT_PRIORITY
from app.harness.enums import EventType, EventSource


def test_new_event_id_is_time_sortable():
    a = new_event_id(1000.0)
    b = new_event_id(2000.0)
    assert a < b                       # 字典序 == 时序
    assert len(a) == 25                # 13 位 ms + 12 位随机


def test_new_event_id_unique_same_ms():
    ids = {new_event_id(1000.0) for _ in range(100)}
    assert len(ids) == 100             # 同毫秒也唯一


def test_event_auto_id_and_ts():
    ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
               session_id="s1", payload={"text": "hi"})
    assert ev.id != ""                 # __post_init__ 自动生成
    assert ev.ts > 0
    assert ev.payload == {"text": "hi"}
    assert ev.parent_id is None
    assert ev.metadata == {}


def test_event_explicit_id_preserved():
    ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
               session_id="s1", id="fixed-id", ts=123.0)
    assert ev.id == "fixed-id"
    assert ev.ts == 123.0


def test_event_priority_observation_before_default():
    # 观察类优先级数值 < 默认（越小越先出）
    assert EVENT_PRIORITY[EventType.MASTERY_ASSESSED] < EVENT_PRIORITY.get(
        EventType.TUTOR_ASKED, 20)


def test_event_priority_tick_is_lowest():
    # OrchestratorTick 最后出队（实现回合屏障）
    tick = EVENT_PRIORITY[EventType.ORCHESTRATOR_TICK]
    assert tick > EVENT_PRIORITY[EventType.MASTERY_ASSESSED]
    assert tick > EVENT_PRIORITY.get(EventType.ACTION_REQUESTED, 20)


def test_loop_exit_is_high_priority():
    # LoopExit 尽快出队以快速退出/熔断
    assert EVENT_PRIORITY[EventType.LOOP_EXIT] < EVENT_PRIORITY[EventType.MASTERY_ASSESSED]
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/unit/harness/test_events.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.harness.events'`

- [ ] **Step 3: 实现 `app/harness/events.py`**

```python
import time
import uuid
from dataclasses import dataclass, field

from app.harness.enums import EventType, EventSource


def new_event_id(ts_ms: float | None = None) -> str:
    """生成时序可排的全局唯一 ID（§3.1 ULID 语义的轻量实现）。

    结构 = 13 位毫秒时间戳（零填充）+ 12 位随机十六进制。
    字典序 == 时序，同毫秒靠随机段保证唯一。无需第三方 ulid 库。
    """
    ms = int(ts_ms if ts_ms is not None else time.time() * 1000)
    return f"{ms:013d}{uuid.uuid4().hex[:12]}"


@dataclass
class Event:
    """事件总线上的统一消息（§3.1）。"""
    type: EventType
    source: EventSource
    session_id: str
    payload: dict = field(default_factory=dict)
    parent_id: str | None = None          # 因果链（§3.1，用于回放与协作评估）
    metadata: dict = field(default_factory=dict)  # node / intent / cost / latency_ms
    id: str = ""
    ts: float = 0.0                        # epoch ms

    def __post_init__(self):
        if self.ts == 0.0:
            self.ts = time.time() * 1000
        if not self.id:
            self.id = new_event_id(self.ts)


# 出队优先级（数值越小越先出；同值由队列入队序 FIFO 兜底，保证确定性回放 §3.5.2）
_OBSERVATION = 10   # Critic/Curator 观察类，先于决策处理 → 实现回合屏障
_DEFAULT = 20       # 用户输入 / Tutor / Retriever 产出 / 控制类动作
_LOOP_EXIT = 5      # 出环/熔断信号，尽快出队
_TICK = 100         # OrchestratorTick 决策哨兵，最后出队（观察处理完才决策）

EVENT_PRIORITY: dict[EventType, int] = {
    EventType.MASTERY_ASSESSED: _OBSERVATION,
    EventType.CONFUSION_DETECTED: _OBSERVATION,
    EventType.CONTRADICTION_DETECTED: _OBSERVATION,
    EventType.LOW_CONFIDENCE_DETECTED: _OBSERVATION,
    EventType.RAG_QUALITY_ASSESSED: _OBSERVATION,
    EventType.GRAPH_PREREQ_WEAK_DETECTED: _OBSERVATION,
    EventType.GRAPH_NODE_STRENGTHENED: _OBSERVATION,
    EventType.PROFILE_UPDATED: _OBSERVATION,
    EventType.LOOP_EXIT: _LOOP_EXIT,
    EventType.ORCHESTRATOR_TICK: _TICK,
}


def priority_of(event_type: EventType) -> int:
    """查事件出队优先级，未登记者取默认。"""
    return EVENT_PRIORITY.get(event_type, _DEFAULT)
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/unit/harness/test_events.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/harness/events.py tests/unit/harness/test_events.py
git commit -m "feat(plan0): add Event model, time-sortable id, dequeue priority"
```

---

## Task 3: 事件所有权白名单 + EmitViolationError

**Files:**
- Modify: `app/harness/events.py`（追加白名单 + 异常 + 校验函数）
- Test: `tests/unit/harness/test_events.py`（追加）

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/harness/test_events.py` 末尾追加：

```python
import pytest
from app.harness.events import EVENT_OWNERSHIP, EmitViolationError, check_ownership


def test_ownership_covers_all_event_types():
    # 白名单必须覆盖每一个 EventType（无遗漏，否则 publish 会误判越权）
    for et in EventType:
        assert et in EVENT_OWNERSHIP, f"{et} 未登记所有权"


def test_ownership_correct_source_passes():
    ev = Event(type=EventType.CONFUSION_DETECTED, source=EventSource.CRITIC,
               session_id="s1")
    check_ownership(ev)                # 不抛错


def test_ownership_violation_raises():
    # Tutor 越权发 Critic 的事件
    ev = Event(type=EventType.CONFUSION_DETECTED, source=EventSource.TUTOR,
               session_id="s1")
    with pytest.raises(EmitViolationError) as exc:
        check_ownership(ev)
    assert exc.value.source == EventSource.TUTOR
    assert exc.value.event_type == EventType.CONFUSION_DETECTED


def test_ownership_orchestrator_controls():
    for et in (EventType.ACTION_REQUESTED, EventType.LOOP_EXIT,
               EventType.POLICY_TRANSITION, EventType.TOPIC_ENTERED,
               EventType.ORCHESTRATOR_TICK, EventType.CONDUCTOR_REQUESTED):
        assert EVENT_OWNERSHIP[et] == EventSource.ORCHESTRATOR


def test_ownership_conductor_only_decided():
    assert EVENT_OWNERSHIP[EventType.CONDUCTOR_DECIDED] == EventSource.CONDUCTOR
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/unit/harness/test_events.py -q`
Expected: FAIL — `ImportError: cannot import name 'EVENT_OWNERSHIP'`

- [ ] **Step 3: 在 `app/harness/events.py` 末尾追加**

```python
# 事件所有权白名单（§3.2）：每个 EventType 仅有唯一合法 source
EVENT_OWNERSHIP: dict[EventType, EventSource] = {
    # 用户
    EventType.USER_MESSAGE: EventSource.USER,
    EventType.USER_UPLOADED: EventSource.USER,
    # Tutor
    EventType.TUTOR_ASKED: EventSource.TUTOR,
    EventType.TUTOR_EXPLAINED: EventSource.TUTOR,
    EventType.TUTOR_REQUESTED_RECAP: EventSource.TUTOR,
    EventType.TUTOR_OFFERED_ANALOGY: EventSource.TUTOR,
    # Retriever
    EventType.RETRIEVED_EVIDENCE: EventSource.RETRIEVER,
    EventType.RETRIEVAL_FAILED: EventSource.RETRIEVER,
    # Critic
    EventType.MASTERY_ASSESSED: EventSource.CRITIC,
    EventType.CONFUSION_DETECTED: EventSource.CRITIC,
    EventType.CONTRADICTION_DETECTED: EventSource.CRITIC,
    EventType.LOW_CONFIDENCE_DETECTED: EventSource.CRITIC,
    EventType.RAG_QUALITY_ASSESSED: EventSource.CRITIC,
    # Curator
    EventType.PROFILE_UPDATED: EventSource.CURATOR,
    EventType.GRAPH_NODE_STRENGTHENED: EventSource.CURATOR,
    EventType.GRAPH_PREREQ_WEAK_DETECTED: EventSource.CURATOR,
    # Conductor
    EventType.CONDUCTOR_DECIDED: EventSource.CONDUCTOR,
    # 控制类（Orchestrator）
    EventType.TOPIC_ENTERED: EventSource.ORCHESTRATOR,
    EventType.LOOP_EXIT: EventSource.ORCHESTRATOR,
    EventType.POLICY_TRANSITION: EventSource.ORCHESTRATOR,
    EventType.ACTION_REQUESTED: EventSource.ORCHESTRATOR,
    EventType.CONDUCTOR_REQUESTED: EventSource.ORCHESTRATOR,
    EventType.ORCHESTRATOR_TICK: EventSource.ORCHESTRATOR,
}


class EmitViolationError(Exception):
    """Agent 越权发出不属于其职能的事件（§2.2 / §3.2 运行时强制）。"""

    def __init__(self, source: EventSource, event_type: EventType):
        self.source = source
        self.event_type = event_type
        owner = EVENT_OWNERSHIP.get(event_type)
        super().__init__(
            f"职能越权：source='{source}' 无权 emit '{event_type}'，"
            f"该事件归 '{owner}'"
        )


def check_ownership(event: Event) -> None:
    """校验事件来源是否合法（§3.2）。越权抛 EmitViolationError。"""
    owner = EVENT_OWNERSHIP.get(event.type)
    if owner is None or event.source != owner:
        raise EmitViolationError(event.source, event.type)
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/unit/harness/test_events.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/harness/events.py tests/unit/harness/test_events.py
git commit -m "feat(plan0): add event ownership whitelist + EmitViolationError"
```

---

## Task 4: WorkspaceState 会话内共享状态

**Files:**
- Create: `app/harness/workspace_state.py`
- Test: `tests/unit/harness/test_workspace_state.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/harness/test_workspace_state.py
from app.harness.workspace_state import WorkspaceState
from app.harness.enums import TeachingMode


def test_workspace_state_defaults():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    assert ws.session_id == "s1"
    assert ws.user_id == "u1"
    assert ws.current_topic is None
    assert ws.current_mode == TeachingMode.SOCRATIC   # 默认进苏格拉底
    assert ws.turn_count == 0
    assert ws.event_ids == []
    assert ws.evidence_pool == []
    assert ws.critic_state == {}
    assert ws.profile_snapshot == {}


def test_workspace_state_independent_mutables():
    # 两个实例的可变默认字段不共享（dataclass field(default_factory)）
    a = WorkspaceState(session_id="s1", user_id="u1")
    b = WorkspaceState(session_id="s2", user_id="u2")
    a.event_ids.append("e1")
    assert b.event_ids == []


def test_workspace_state_records_event_ref():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    ws.event_ids.append("0000000001000abcdef012345")
    ws.current_mode = TeachingMode.FEYNMAN
    ws.turn_count = 3
    assert len(ws.event_ids) == 1
    assert ws.current_mode == "Feynman"
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/unit/harness/test_workspace_state.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.harness.workspace_state'`

- [ ] **Step 3: 实现 `app/harness/workspace_state.py`**

```python
from dataclasses import dataclass, field

from app.harness.enums import TeachingMode


@dataclass
class WorkspaceState:
    """会话内共享状态（§6）。事件正文存 EventStore，这里只持引用 id。

    注意：Agent 不直接写 WorkspaceState（§2.2），由协作环/Orchestrator 维护。
    evidence_pool / critic_state / profile_snapshot 在 Plan 0 用 dict 占位，
    Wave 1（Plan A/B）落地具体结构后可替换为强类型。
    """
    session_id: str
    user_id: str
    current_topic: str | None = None
    current_mode: TeachingMode = TeachingMode.SOCRATIC
    turn_count: int = 0
    event_ids: list[str] = field(default_factory=list)       # 仅引用，正文存 EventStore
    evidence_pool: list[dict] = field(default_factory=list)  # Retriever 最近输出
    critic_state: dict = field(default_factory=dict)         # Critic 最近一次评估
    profile_snapshot: dict = field(default_factory=dict)     # 进入会话时画像快照
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/unit/harness/test_workspace_state.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/harness/workspace_state.py tests/unit/harness/test_workspace_state.py
git commit -m "feat(plan0): add WorkspaceState session-shared state"
```

---

## Task 5: EventStore 事件持久化 + 全序回放（同步 sqlite3）

**Files:**
- Create: `app/infrastructure/storage/event_store.py`
- Test: `tests/unit/infrastructure/test_event_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/infrastructure/test_event_store.py
import os
import tempfile

from app.infrastructure.storage.event_store import EventStore
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


def _make_store() -> tuple[EventStore, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = EventStore(db_path=path)
    store.init()
    return store, path


def test_append_and_replay_roundtrip():
    store, path = _make_store()
    try:
        ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="s1", payload={"text": "hi"})
        store.append(ev)
        got = store.replay("s1")
        assert len(got) == 1
        assert got[0].id == ev.id
        assert got[0].type == EventType.USER_MESSAGE
        assert got[0].source == EventSource.USER
        assert got[0].payload == {"text": "hi"}
    finally:
        store.close()
        os.unlink(path)


def test_replay_is_total_order_by_id():
    store, path = _make_store()
    try:
        # 故意乱序 append，但 id 时序递增（ts 递增）
        e2 = Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR,
                   session_id="s1", ts=2000.0)
        e1 = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="s1", ts=1000.0)
        store.append(e2)
        store.append(e1)
        got = store.replay("s1")
        assert [e.ts for e in got] == [1000.0, 2000.0]   # 回放按 id(时序) 升序
    finally:
        store.close()
        os.unlink(path)


def test_replay_filters_by_session():
    store, path = _make_store()
    try:
        store.append(Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                           session_id="s1"))
        store.append(Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                           session_id="s2"))
        assert len(store.replay("s1")) == 1
        assert len(store.replay("s2")) == 1
        assert store.replay("nope") == []
    finally:
        store.close()
        os.unlink(path)


def test_append_preserves_parent_id_and_metadata():
    store, path = _make_store()
    try:
        ev = Event(type=EventType.CONFUSION_DETECTED, source=EventSource.CRITIC,
                   session_id="s1", parent_id="p1", metadata={"cost": 0.01})
        store.append(ev)
        got = store.replay("s1")[0]
        assert got.parent_id == "p1"
        assert got.metadata == {"cost": 0.01}
    finally:
        store.close()
        os.unlink(path)
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/unit/infrastructure/test_event_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.storage.event_store'`

- [ ] **Step 3: 实现 `app/infrastructure/storage/event_store.py`**

```python
import json
import sqlite3
from pathlib import Path

from app.harness.events import Event
from app.harness.enums import EventType, EventSource


class EventStore:
    """事件持久化 + 回放（§3.1）。

    用同步 sqlite3：协作环是单线程同步事件循环（§3.5），EventStore.append 在
    循环内被调用，同步实现最契合、零异步开销。回放按 id 升序 —— id 是时序可排
    ULID，故等价于全序时序回放（满足 §5 replay 需求）。
    """

    def __init__(self, db_path: str = "data/events.db"):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def init(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                ts REAL NOT NULL,
                session_id TEXT NOT NULL,
                source TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT DEFAULT '{}',
                parent_id TEXT,
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);
        """)
        self._conn.commit()

    def append(self, event: Event) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO events
               (id, ts, session_id, source, type, payload, parent_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.id, event.ts, event.session_id, str(event.source),
             str(event.type), json.dumps(event.payload), event.parent_id,
             json.dumps(event.metadata)),
        )
        self._conn.commit()

    def replay(self, session_id: str) -> list[Event]:
        rows = self._conn.execute(
            """SELECT id, ts, session_id, source, type, payload, parent_id, metadata
               FROM events WHERE session_id = ? ORDER BY id ASC""",
            (session_id,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row) -> Event:
        return Event(
            id=row[0], ts=row[1], session_id=row[2],
            source=EventSource(row[3]), type=EventType(row[4]),
            payload=json.loads(row[5]), parent_id=row[6],
            metadata=json.loads(row[7]),
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/unit/infrastructure/test_event_store.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/infrastructure/storage/event_store.py tests/unit/infrastructure/test_event_store.py
git commit -m "feat(plan0): add EventStore (sync sqlite3) with total-order replay"
```

---

## Task 6: EventBus — publish（白名单校验 + 持久化）/ subscribe / replay

**Files:**
- Create: `app/harness/eventbus.py`
- Test: `tests/unit/harness/test_eventbus.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/harness/test_eventbus.py
import os
import tempfile

import pytest

from app.harness.eventbus import EventBus
from app.infrastructure.storage.event_store import EventStore
from app.harness.events import Event, EmitViolationError
from app.harness.enums import EventType, EventSource


def _make_bus() -> tuple[EventBus, EventStore, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = EventStore(db_path=path)
    store.init()
    return EventBus(store=store), store, path


def test_publish_legal_event_persists():
    bus, store, path = _make_bus()
    try:
        ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="s1", payload={"text": "hi"})
        bus.publish(ev)
        assert len(bus.replay("s1")) == 1
    finally:
        store.close()
        os.unlink(path)


def test_publish_violation_raises_and_not_persisted():
    bus, store, path = _make_bus()
    try:
        bad = Event(type=EventType.CONFUSION_DETECTED, source=EventSource.TUTOR,
                    session_id="s1")
        with pytest.raises(EmitViolationError):
            bus.publish(bad)
        assert bus.replay("s1") == []      # 越权事件不落库
    finally:
        store.close()
        os.unlink(path)


def test_subscribe_and_subscribers_of():
    bus, store, path = _make_bus()
    try:
        agent_a, agent_b = object(), object()
        bus.subscribe(agent_a, [EventType.USER_MESSAGE, EventType.TUTOR_ASKED])
        bus.subscribe(agent_b, [EventType.USER_MESSAGE])
        subs = bus.subscribers_of(EventType.USER_MESSAGE)
        assert agent_a in subs and agent_b in subs
        assert bus.subscribers_of(EventType.TUTOR_ASKED) == [agent_a]
        assert bus.subscribers_of(EventType.LOOP_EXIT) == []
    finally:
        store.close()
        os.unlink(path)


def test_replay_without_store_returns_empty():
    bus = EventBus(store=None)
    assert bus.replay("s1") == []
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/unit/harness/test_eventbus.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.harness.eventbus'`

- [ ] **Step 3: 实现 `app/harness/eventbus.py`**

```python
from collections import defaultdict

from app.harness.events import Event, check_ownership
from app.harness.enums import EventType
from app.infrastructure.storage.event_store import EventStore


class EventBus:
    """发布/订阅 + 白名单校验 + 持久化（§3.1/§3.2）。

    publish 是唯一的写入口：先校验所有权（越权抛 EmitViolationError，事件不落库），
    再持久化到 EventStore。分发（按 type 找订阅者并调用 handle）由协作环（§3.5）
    用 subscribers_of 驱动，EventBus 本身不调用 Agent —— 保持单线程循环对控制流的
    完全掌控。
    """

    def __init__(self, store: EventStore | None = None):
        self._subscribers: dict[EventType, list] = defaultdict(list)
        self._store = store

    def subscribe(self, agent, event_types: list[EventType]) -> None:
        for et in event_types:
            self._subscribers[et].append(agent)

    def subscribers_of(self, event_type: EventType) -> list:
        return list(self._subscribers.get(event_type, []))

    def publish(self, event: Event) -> None:
        check_ownership(event)                 # §3.2 越权抛错（在持久化之前）
        if self._store is not None:
            self._store.append(event)

    def replay(self, session_id: str) -> list[Event]:
        if self._store is None:
            return []
        return self._store.replay(session_id)
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/unit/harness/test_eventbus.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/harness/eventbus.py tests/unit/harness/test_eventbus.py
git commit -m "feat(plan0): add EventBus with whitelist-checked publish + replay"
```

---

## Task 7: AgentBase 抽象基类

**Files:**
- Create: `app/agents/__init__.py`（空文件）
- Create: `app/agents/base.py`
- Create: `tests/unit/agents/__init__.py`（空文件）
- Create: `tests/unit/agents/test_agent_base.py`

- [ ] **Step 1: 创建空包文件**

```bash
mkdir -p app/agents tests/unit/agents
touch app/agents/__init__.py tests/unit/agents/__init__.py
```

- [ ] **Step 2: 写失败测试**

```python
# tests/unit/agents/test_agent_base.py
import pytest

from app.agents.base import AgentBase
from app.harness.events import Event, check_ownership
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState


class _EchoTutor(AgentBase):
    source = EventSource.TUTOR
    subscriptions = [EventType.USER_MESSAGE]
    emittable_types = {EventType.TUTOR_ASKED}

    def handle(self, event, ws):
        return [self.emit(EventType.TUTOR_ASKED, ws, payload={"q": "why?"},
                          parent_id=event.id)]


def test_handle_emits_event_with_own_source():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    trigger = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                    session_id="s1")
    out = _EchoTutor().handle(trigger, ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_ASKED
    assert out[0].source == EventSource.TUTOR
    assert out[0].session_id == "s1"
    assert out[0].parent_id == trigger.id        # 因果链


def test_emit_undeclared_type_raises():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    agent = _EchoTutor()
    with pytest.raises(ValueError):
        agent.emit(EventType.CONFUSION_DETECTED, ws)   # 未在 emittable_types


def test_emitted_event_passes_bus_ownership():
    # AgentBase.emit 出的事件应天然通过 §3.2 全局白名单
    ws = WorkspaceState(session_id="s1", user_id="u1")
    ev = _EchoTutor().emit(EventType.TUTOR_ASKED, ws)
    check_ownership(ev)                              # 不抛错


def test_evaluate_default_not_implemented():
    with pytest.raises(NotImplementedError):
        _EchoTutor().evaluate(test_case={})
```

- [ ] **Step 3: 运行验证失败**

Run: `pytest tests/unit/agents/test_agent_base.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.base'`

- [ ] **Step 4: 实现 `app/agents/base.py`**

```python
from abc import ABC, abstractmethod

from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState


class AgentBase(ABC):
    """所有 Agent 的统一契约（§2.2）。

    子类必须声明三个类属性：
      source           —— 该 Agent 的事件来源身份（EventSource）
      subscriptions    —— 订阅的事件类型（协作环据此分发）
      emittable_types  —— 允许 emit 的事件类型集合（声明即契约，§2.2）

    约束：Agent 不直接互相调用、不直接写 DB/LLM（经 Harness 接口）、不写
    WorkspaceState。emit 出的事件先过本地 emittable_types 校验，最终所有权
    由 EventBus.publish 的 check_ownership 把关（§3.2）。
    """

    source: EventSource
    subscriptions: list[EventType]
    emittable_types: set[EventType]

    @abstractmethod
    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """处理一个订阅到的事件，返回产出的新事件（可为空列表）。"""
        ...

    def emit(self, type: EventType, ws: WorkspaceState,
             payload: dict | None = None,
             parent_id: str | None = None) -> Event:
        """构造一个带本 Agent source 身份的事件。

        本地校验 type ∈ emittable_types（声明即契约），越界抛 ValueError。
        """
        if type not in self.emittable_types:
            raise ValueError(
                f"{self.source} 未声明可 emit {type}（不在 emittable_types）")
        return Event(type=type, source=self.source, session_id=ws.session_id,
                     payload=payload or {}, parent_id=parent_id)

    def evaluate(self, test_case) -> dict:
        """部件级评估接口（§5.2）。Plan E / Wave 1 各 Agent 自行实现。"""
        raise NotImplementedError(
            f"{type(self).__name__} 尚未实现 evaluate（见 §5.2）")
```

- [ ] **Step 5: 运行验证通过**

Run: `pytest tests/unit/agents/test_agent_base.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/agents/ tests/unit/agents/
git commit -m "feat(plan0): add AgentBase contract (source/subscriptions/emittable/emit)"
```

---

## Task 8: 协作环骨架 — 优先级队列 + MAX_TURNS 熔断 + Orchestrator 钩子

**Files:**
- Create: `app/orchestration/__init__.py`（空文件）
- Create: `app/orchestration/collab_loop.py`
- Create: `tests/unit/orchestration/__init__.py`（空文件）
- Create: `tests/unit/orchestration/test_collab_loop.py`

> **范围说明**：Plan 0 提供优先级队列 + 单线程循环 + MAX_TURNS 熔断 + LoopExit 退出 + 双种子注入 + Orchestrator 钩子接口。**回合屏障的完整决策语义（OrchestratorTick 哨兵收集完整观察集）由 Plan C 的 Orchestrator 实现**——Plan 0 只保证"观察类事件优先级高于默认、Tick 最低"的队列基础（§3.5.2/§3.5.3）。

- [ ] **Step 1: 创建空包文件**

```bash
mkdir -p app/orchestration tests/unit/orchestration
touch app/orchestration/__init__.py tests/unit/orchestration/__init__.py
```

- [ ] **Step 2: 写失败测试**

```python
# tests/unit/orchestration/test_collab_loop.py
import os
import tempfile

from app.orchestration.collab_loop import run_collab_loop, PriorityEventQueue
from app.harness.eventbus import EventBus
from app.infrastructure.storage.event_store import EventStore
from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState
from app.agents.base import AgentBase


def _bus():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = EventStore(db_path=path)
    store.init()
    return EventBus(store=store), store, path


class _AskOnce(AgentBase):
    source = EventSource.TUTOR
    subscriptions = [EventType.USER_MESSAGE]
    emittable_types = {EventType.TUTOR_ASKED}

    def handle(self, event, ws):
        return [self.emit(EventType.TUTOR_ASKED, ws, payload={"q": "why"})]


class _LoopForever(AgentBase):
    source = EventSource.TUTOR
    subscriptions = [EventType.USER_MESSAGE, EventType.TUTOR_ASKED]
    emittable_types = {EventType.TUTOR_ASKED}

    def handle(self, event, ws):
        return [self.emit(EventType.TUTOR_ASKED, ws)]


class _StubOrchestrator:
    def __init__(self):
        self.seen = []

    def on_event(self, event, ws):
        self.seen.append(event.type)
        if event.type == EventType.USER_MESSAGE:
            return [Event(type=EventType.LOOP_EXIT, source=EventSource.ORCHESTRATOR,
                          session_id=ws.session_id, payload={"reason": "done"})]
        return []


def test_priority_queue_observation_before_default():
    q = PriorityEventQueue()
    tutor = Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR, session_id="s")
    mastery = Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC, session_id="s")
    q.push(tutor)
    q.push(mastery)
    assert q.pop().type == EventType.MASTERY_ASSESSED   # 观察类先出（回合屏障基础）
    assert q.pop().type == EventType.TUTOR_ASKED


def test_priority_queue_same_priority_fifo():
    q = PriorityEventQueue()
    a = Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR, session_id="s", id="a")
    b = Event(type=EventType.TUTOR_EXPLAINED, source=EventSource.TUTOR, session_id="s", id="b")
    q.push(a)
    q.push(b)
    assert q.pop().id == "a"        # 同优先级 FIFO（确定性回放）
    assert q.pop().id == "b"


def test_loop_runs_until_queue_empty():
    bus, store, path = _bus()
    try:
        bus.subscribe(_AskOnce(), [EventType.USER_MESSAGE])
        ws = WorkspaceState(session_id="s1", user_id="u1")
        seed = Event(type=EventType.USER_MESSAGE, source=EventSource.USER, session_id="s1")
        run_collab_loop(bus, ws, [seed])
        types = [e.type for e in bus.replay("s1")]
        assert EventType.USER_MESSAGE in types
        assert EventType.TUTOR_ASKED in types
    finally:
        store.close()
        os.unlink(path)


def test_max_turns_fuse_stops_infinite_loop():
    bus, store, path = _bus()
    try:
        bus.subscribe(_LoopForever(), [EventType.USER_MESSAGE, EventType.TUTOR_ASKED])
        ws = WorkspaceState(session_id="s1", user_id="u1")
        seed = Event(type=EventType.USER_MESSAGE, source=EventSource.USER, session_id="s1")
        run_collab_loop(bus, ws, [seed], max_turns=5)
        assert ws.turn_count >= 5
        assert any(e.type == EventType.LOOP_EXIT for e in bus.replay("s1"))  # 熔断注入
    finally:
        store.close()
        os.unlink(path)


def test_dual_seed_both_persisted():
    bus, store, path = _bus()
    try:
        ws = WorkspaceState(session_id="s1", user_id="u1")
        seeds = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER, session_id="s1"),
            Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                  session_id="s1", payload={"topic": "RAG"}),
        ]
        run_collab_loop(bus, ws, seeds)
        types = {e.type for e in bus.replay("s1")}
        assert EventType.USER_MESSAGE in types
        assert EventType.TOPIC_ENTERED in types       # 双种子（§3.5.1）
    finally:
        store.close()
        os.unlink(path)


def test_orchestrator_hook_invoked_and_can_exit():
    bus, store, path = _bus()
    try:
        orch = _StubOrchestrator()
        ws = WorkspaceState(session_id="s1", user_id="u1")
        seed = Event(type=EventType.USER_MESSAGE, source=EventSource.USER, session_id="s1")
        run_collab_loop(bus, ws, [seed], orchestrator=orch)
        assert EventType.USER_MESSAGE in orch.seen
        assert any(e.type == EventType.LOOP_EXIT for e in bus.replay("s1"))
    finally:
        store.close()
        os.unlink(path)
```

- [ ] **Step 3: 运行验证失败**

Run: `pytest tests/unit/orchestration/test_collab_loop.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.orchestration.collab_loop'`

- [ ] **Step 4: 实现 `app/orchestration/collab_loop.py`**

```python
import heapq
import itertools

from app.harness.events import Event, priority_of
from app.harness.enums import EventType, EventSource
from app.harness.eventbus import EventBus
from app.harness.workspace_state import WorkspaceState

MAX_TURNS = 50


class PriorityEventQueue:
    """优先级队列（§3.5.2）：priority 小先出；同 priority 按入队序 FIFO，
    保证确定性回放。观察类(10) < 默认(20) < Tick(100)，LoopExit(5) 最先。
    """

    def __init__(self):
        self._heap: list = []
        self._seq = itertools.count()

    def push(self, event: Event) -> None:
        heapq.heappush(self._heap, (priority_of(event.type), next(self._seq), event))

    def pop(self) -> Event:
        return heapq.heappop(self._heap)[2]

    def empty(self) -> bool:
        return not self._heap


def run_collab_loop(bus: EventBus, ws: WorkspaceState, seed_events: list[Event],
                    orchestrator=None, max_turns: int = MAX_TURNS) -> WorkspaceState:
    """单线程事件循环（§3.5.1）。

    seed_events：协作环种子，通常是 UserMessage（+ 新主题时的 TopicEntered）。
    orchestrator：可选，提供 on_event(event, ws) -> list[Event] 钩子做路由决策；
                  Plan 0 骨架可不传（Plan C 接入真正的 Orchestrator + 回合屏障）。
    """
    queue = PriorityEventQueue()

    def _publish_and_enqueue(ev: Event) -> None:
        bus.publish(ev)                 # §3.2 白名单校验 + 持久化
        ws.event_ids.append(ev.id)
        queue.push(ev)

    for ev in seed_events:
        _publish_and_enqueue(ev)

    turn = 0
    fused = False
    while not queue.empty():
        turn += 1
        if turn > max_turns and not fused:        # 死循环熔断（§9）
            fused = True
            _publish_and_enqueue(Event(
                type=EventType.LOOP_EXIT, source=EventSource.ORCHESTRATOR,
                session_id=ws.session_id, payload={"reason": "max_turns"}))

        event = queue.pop()
        if event.type == EventType.LOOP_EXIT:     # 唯一出环信号（§3.5.4）
            break

        for agent in bus.subscribers_of(event.type):
            for new_ev in agent.handle(event, ws):
                _publish_and_enqueue(new_ev)

        if orchestrator is not None:
            for new_ev in orchestrator.on_event(event, ws):
                _publish_and_enqueue(new_ev)

    ws.turn_count = turn
    return ws
```

- [ ] **Step 5: 运行验证通过**

Run: `pytest tests/unit/orchestration/test_collab_loop.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/orchestration/ tests/unit/orchestration/test_collab_loop.py tests/unit/orchestration/__init__.py
git commit -m "feat(plan0): add collab loop skeleton (priority queue + fuse + hook)"
```

---

## Task 9: 4 节点主图骨架（LangGraph）

**Files:**
- Create: `app/orchestration/graph.py`
- Test: `tests/unit/orchestration/test_graph.py`

> **范围说明**：Plan 0 只验证主图**结构**（4 节点 + 进/不进环条件边 + compile 可跑）。`collab_loop` 节点是 pass-through 占位，**Plan C 将其替换为调用 `run_collab_loop`**；`route` 的真实意图识别复用现有 `intent_router`（Plan C 接入）。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/orchestration/test_graph.py
from app.orchestration.graph import build_main_graph

_CFG = {"configurable": {"thread_id": "t1"}}


def test_graph_compiles():
    assert build_main_graph() is not None


def test_enter_loop_path_visits_collab_loop():
    g = build_main_graph()
    out = g.invoke({"session_id": "s1", "user_id": "u1", "enter_loop": True}, config=_CFG)
    assert out["stage"] == "wrap_up"            # 终点
    assert "collab_loop" in out["visited"]      # 进环


def test_skip_loop_path_bypasses_collab_loop():
    g = build_main_graph()
    out = g.invoke({"session_id": "s2", "user_id": "u1", "enter_loop": False},
                   config={"configurable": {"thread_id": "t2"}})
    assert out["stage"] == "wrap_up"
    assert "collab_loop" not in out["visited"]  # 纯 FAQ 不进环（§3.5.4）
    assert out["visited"] == ["ingest", "route", "wrap_up"]
```

- [ ] **Step 2: 运行验证失败**

Run: `pytest tests/unit/orchestration/test_graph.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.orchestration.graph'`

- [ ] **Step 3: 实现 `app/orchestration/graph.py`**

```python
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver


class MainState(TypedDict, total=False):
    """主图骨架状态（Plan 0）。Wave 1 将以 WorkspaceState 承载真实会话状态。"""
    session_id: str
    user_id: str
    enter_loop: bool                              # route 决策：是否进协作环
    stage: str                                    # 当前阶段（覆盖写）
    visited: Annotated[list[str], operator.add]   # 经过的节点（累加）


def _ingest(state: MainState) -> dict:
    return {"visited": ["ingest"], "stage": "ingest"}


def _route(state: MainState) -> dict:
    return {"visited": ["route"], "stage": "route"}


def _route_decision(state: MainState) -> str:
    # 默认进环；纯 FAQ（enter_loop=False）直接收尾（§3.5.4）
    return "collab_loop" if state.get("enter_loop", True) else "wrap_up"


def _collab_loop_node(state: MainState) -> dict:
    # Plan 0 占位：Plan C 在此调用 run_collab_loop(bus, ws, seeds, orchestrator)
    return {"visited": ["collab_loop"], "stage": "collab_loop"}


def _wrap_up(state: MainState) -> dict:
    return {"visited": ["wrap_up"], "stage": "wrap_up"}


def build_main_graph():
    """4 节点骨架：ingest → route → [collab_loop] → wrap_up（§3.5.4）。"""
    g = StateGraph(MainState)
    g.add_node("ingest", _ingest)
    g.add_node("route", _route)
    g.add_node("collab_loop", _collab_loop_node)
    g.add_node("wrap_up", _wrap_up)
    g.set_entry_point("ingest")
    g.add_edge("ingest", "route")
    g.add_conditional_edges("route", _route_decision,
                            {"collab_loop": "collab_loop", "wrap_up": "wrap_up"})
    g.add_edge("collab_loop", "wrap_up")
    g.add_edge("wrap_up", END)
    return g.compile(checkpointer=MemorySaver())
```

- [ ] **Step 4: 运行验证通过**

Run: `pytest tests/unit/orchestration/test_graph.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/orchestration/graph.py tests/unit/orchestration/test_graph.py
git commit -m "feat(plan0): add 4-node main graph skeleton (ingest/route/collab_loop/wrap_up)"
```

---

## Task 10: Plan 0 全量回归

**Files:** 无新增代码——仅验证 gate。

- [ ] **Step 1: 跑全量测试**

Run: `pytest -q`
Expected: PASS，**无 failures / errors**。

- [ ] **Step 2: 确认基线未退化**

Run: `pytest --collect-only -q | tail -1`
Expected: 收集到的测试数 ≥ 155（原基线）+ Plan 0 新增（约 28 个）。现有 155 个旧测试必须全部仍在且通过——Plan 0 全为新增文件，未触碰老代码，理应零回归。

- [ ] **Step 3: 确认新模块可被导入（冒烟）**

Run:
```bash
python -c "from app.harness.events import Event, check_ownership, EVENT_OWNERSHIP; \
from app.harness.eventbus import EventBus; \
from app.harness.workspace_state import WorkspaceState; \
from app.infrastructure.storage.event_store import EventStore; \
from app.agents.base import AgentBase; \
from app.orchestration.collab_loop import run_collab_loop; \
from app.orchestration.graph import build_main_graph; \
print('plan0 imports ok')"
```
Expected: 输出 `plan0 imports ok`

- [ ] **Step 4: 回退判据自检（§8 P1）**

确认：EventStore.replay 返回严格时序（Task 5 `test_replay_is_total_order_by_id` 通过）；越权 emit 被 EventBus 拦截（Task 6 `test_publish_violation_raises_and_not_persisted` 通过）。若任一不满足 → 回退重审 §3.1/§3.2。

- [ ] **Step 5: 提交（若 Step 1-3 有任何 __init__.py 遗漏补充）**

```bash
git add -A && git commit -m "test(plan0): full regression green — core contracts ready for Wave 1" --allow-empty
```

---

## Self-Review

**1. Spec coverage（§11 Wave 0 = WorkspaceState/EventBus/AgentBase/EventStore/enums/骨架）**
- enums（EventType/EventSource/TeachingMode/ActionKind）→ Task 1 ✓
- Event 模型 + 时序 id + 优先级（§3.1）→ Task 2 ✓
- 所有权白名单 + EmitViolationError（§2.2/§3.2）→ Task 3 ✓
- WorkspaceState（§6）→ Task 4 ✓
- EventStore + 全序 replay（§3.1/§5）→ Task 5 ✓
- EventBus（§3.1/§3.2）→ Task 6 ✓
- AgentBase（§2.2）→ Task 7 ✓
- 协作环骨架（§3.5.1 单线程/优先级/熔断/双种子）→ Task 8 ✓
- 主图骨架（§3.5.4）→ Task 9 ✓
- **有意延后到 Plan C**（非遗漏）：回合屏障的 OrchestratorTick 完整决策语义（§3.5.3）、规则引擎（§3.4）、真实 Orchestrator——Plan 0 提供其全部依赖底座（优先级队列 + 钩子 + Tick 最低优先级）。Task 8 范围说明已注明。

**2. Placeholder scan**：collab_loop 的 orchestrator 钩子、graph 的 `_collab_loop_node` 是**有明确接口与 Plan C 衔接说明的分层占位**，非 "TODO/fill-in" 空洞占位；其余每步均含完整测试 + 实现代码。

**3. Type consistency**（跨 Task 核对）：
- `Event(type, source, session_id, payload, parent_id, metadata, id, ts)` 字段在 Task 2/5/6/7/8 一致
- `AgentBase.emit(type, ws, payload=None, parent_id=None)` 在 Task 7 定义、Task 8 测试用法一致
- `EventBus.publish/subscribe/subscribers_of/replay` 在 Task 6 定义、Task 8 使用一致
- `EventStore.init/append/replay/close` 在 Task 5 定义、Task 6/8 使用一致
- `priority_of` / `EVENT_PRIORITY` 在 Task 2 定义、Task 8 队列使用一致
- `EVENT_OWNERSHIP` / `check_ownership` 在 Task 3 定义、Task 6 使用一致

---

## 执行交接

**Plan complete and saved to `docs/superpowers/plans/2026-06-01-plan-0-core-contracts.md`. 两种执行方式：**

**1. Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，Task 间两阶段审查，快速迭代。REQUIRED SUB-SKILL: superpowers:subagent-driven-development

**2. Inline Execution** — 在当前会话用 superpowers:executing-plans 批量执行，带检查点审查。

**选哪种？** 选定后，Wave 1（Plan A 检索 / B 记忆画像 / C 教学编排）即可基于本 Plan 0 定稿的接口并行展开。
