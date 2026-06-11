# 子项目② 实时协作流 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/chat/stream` 改成逐 Agent 事件实时 SSE、掌握度落库 SQLAlchemy/PG、修回合数语义、profile 读真实数据。

**Architecture:** collab_loop 加同步 `on_event` 回调；chat_stream 在主协程用 `asyncio.Queue` + `loop.call_soon_threadsafe` 桥接工作线程内的同步事件；掌握度新建 SQLAlchemy 表 + store（复刻旧 store 4 方法契约），主协程 `graph.load()`/`graph.save()`；抽 `persist_turn` 共享落库函数（会话+消息+掌握度原子提交）供 chat 与 chat_stream 复用。

**Tech Stack:** FastAPI、SQLAlchemy async（aiosqlite/asyncpg 双模）、asyncio、pytest（跑测试必须 `< /dev/null`）。

**上游 spec:** `docs/designs/2026-06-11-realtime-collab-stream-design.md`（含 §8.1/§8.2 两轮 review 修订）。

---

## 文件结构

| 文件 | 责任 | 动作 |
|---|---|---|
| `app/orchestration/collab_loop.py` | 加 `on_event` 回调钩子 | 改 |
| `app/orchestration/assembly.py` | `build_new_stack`/`run_new_agent_session` 加可选 `graph`/`on_event` | 改 |
| `app/models/tables.py` | 新增 `MasteryNodeTable`/`MasteryEdgeTable` | 改 |
| `app/infrastructure/storage/sqlalchemy_mastery_store.py` | SQLAlchemy 版掌握度 store（复刻 4 方法） | 新建 |
| `app/harness/mastery_graph.py` | `__init__` store 类型标注放宽 | 改 |
| `app/api/_sse_projection.py` | `project_event` 语义事件过滤+投影 | 新建 |
| `app/api/_persist.py` | `persist_turn` 共享落库（返回 turn_index） | 新建 |
| `app/api/chat.py` | 改调 `persist_turn`，接掌握度 | 改 |
| `app/api/chat_stream.py` | 重写真流式 + 自开 session | 改 |
| `app/api/profile.py` | 读真实 sessions + mastery 均值 | 改 |
| `tests/unit/...` / `tests/api/...` | 各任务对应测试 | 新建 |

任务顺序：Infra/Orchestration 底座（Task 1-4）→ API 投影/落库（Task 5-6）→ 端点改造（Task 7-9）→ profile（Task 10）→ 回归确认（Task 11）。

---

### Task 1: collab_loop 加 on_event 回调钩子

**Files:**
- Modify: `app/orchestration/collab_loop.py:31`（`run_collab_loop` 签名）、`:41-44`（`_publish_and_enqueue`）
- Test: `tests/unit/orchestration/test_collab_loop.py`

- [ ] **Step 1: 写失败测试**

加到 `tests/unit/orchestration/test_collab_loop.py` 末尾：

```python
def test_on_event_callback_receives_every_published_event():
    from app.orchestration.collab_loop import run_collab_loop
    from app.harness.eventbus import EventBus
    from app.harness.workspace_state import WorkspaceState
    from app.harness.events import Event
    from app.harness.enums import EventType, EventSource

    bus = EventBus(store=None)
    ws = WorkspaceState(session_id="s", user_id="u")
    seen = []
    seeds = [Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="s", payload={"text": "hi"})]
    run_collab_loop(bus, ws, seeds, orchestrator=None, on_event=seen.append)
    # 至少收到种子事件；回调次数 == 发布事件数
    assert len(seen) >= 1
    assert seen[0].type == EventType.USER_MESSAGE


def test_on_event_none_is_noop():
    # on_event 缺省为 None 时不报错、行为不变
    from app.orchestration.collab_loop import run_collab_loop
    from app.harness.eventbus import EventBus
    from app.harness.workspace_state import WorkspaceState
    from app.harness.events import Event
    from app.harness.enums import EventType, EventSource

    bus = EventBus(store=None)
    ws = WorkspaceState(session_id="s", user_id="u")
    seeds = [Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="s", payload={"text": "hi"})]
    out = run_collab_loop(bus, ws, seeds, orchestrator=None)
    assert out is ws
```

- [ ] **Step 2: 跑测试看失败**

Run: `pytest tests/unit/orchestration/test_collab_loop.py::test_on_event_callback_receives_every_published_event -v < /dev/null`
Expected: FAIL（`run_collab_loop() got an unexpected keyword argument 'on_event'`）

- [ ] **Step 3: 实现**

改 `app/orchestration/collab_loop.py`。签名加 `on_event` 参数（在 `max_turns` 之后）：

```python
def run_collab_loop(bus: EventBus, ws: WorkspaceState, seed_events: list[Event],
                    orchestrator=None, max_turns: int = MAX_TURNS,
                    on_event=None) -> WorkspaceState:
```

`_publish_and_enqueue` 内 `bus.publish(ev)` 之后加回调（保持其余不变）：

```python
    def _publish_and_enqueue(ev: Event) -> None:
        bus.publish(ev)                 # §3.2 白名单校验 + 持久化
        if on_event is not None:        # 子模块A：透出已落库的合法事件
            on_event(ev)
        ws.event_ids.append(ev.id)
        queue.push(ev)
```

- [ ] **Step 4: 跑测试看通过**

Run: `pytest tests/unit/orchestration/test_collab_loop.py -v < /dev/null`
Expected: 全部 PASS（含原有用例）

- [ ] **Step 5: Commit**

```bash
git add app/orchestration/collab_loop.py tests/unit/orchestration/test_collab_loop.py
git commit -m "feat: add on_event callback hook to run_collab_loop"
```

---

### Task 2: assembly 透传 graph / on_event

**Files:**
- Modify: `app/orchestration/assembly.py:100`（`build_new_stack`）、`:131`（`run_new_agent_session`）
- Test: `tests/unit/orchestration/test_assembly.py`

- [ ] **Step 1: 写失败测试**

加到 `tests/unit/orchestration/test_assembly.py` 末尾：

```python
def test_run_new_agent_session_invokes_on_event(mock_llm_invoke_json):
    mock_llm_invoke_json({})
    seen = []
    result = run_new_agent_session(
        "sess-onev", "u-onev", "什么是二分查找",
        on_event=lambda ev: seen.append(ev.type),
    )
    assert isinstance(result, NewStackResult)
    assert len(seen) >= 1  # 回调被逐事件调用


def test_run_new_agent_session_accepts_external_graph(mock_llm_invoke_json):
    mock_llm_invoke_json({})
    from app.harness.mastery_graph import MasteryGraph
    from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore
    graph = MasteryGraph(user_id="u-ext", store=MasteryGraphStore(db_path=":memory:"))
    result = run_new_agent_session(
        "sess-ext", "u-ext", "二分查找", graph=graph,
    )
    assert isinstance(result, NewStackResult)
```

- [ ] **Step 2: 跑测试看失败**

Run: `pytest tests/unit/orchestration/test_assembly.py::test_run_new_agent_session_invokes_on_event -v < /dev/null`
Expected: FAIL（`unexpected keyword argument 'on_event'`）

- [ ] **Step 3: 实现**

改 `app/orchestration/assembly.py`。`build_new_stack` 加可选 `graph`：

```python
def build_new_stack(user_id: str, graph=None):
    store = EventStore(db_path=":memory:")
    store.init()
    bus = EventBus(store=store)

    if graph is None:
        mg_store = MasteryGraphStore(db_path=":memory:")
        graph = MasteryGraph(user_id=user_id, store=mg_store)

    agents = [
        TutorAgent(),
        CriticAgent(),
        RetrieverAgent(),
        ConductorAgent(),
        Curator(graph=graph, store=graph._store),
    ]
    for agent in agents:
        bus.subscribe(agent, agent.subscriptions)

    orchestrator = Orchestrator(policy=TeachingPolicy())
    return bus, orchestrator, store
```

`run_new_agent_session` 加 `graph`/`on_event` 并透传：

```python
def run_new_agent_session(session_id: str, user_id: str, user_message: str,
                          current_topic: str | None = None,
                          graph=None, on_event=None) -> NewStackResult:
    topic = current_topic or user_message
    bus, orchestrator, store = build_new_stack(user_id, graph=graph)
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
        run_collab_loop(bus, ws, seeds, orchestrator=orchestrator, on_event=on_event)
        events = _events_in_runtime_order(bus.replay(session_id), ws.event_ids)
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

> 注：`Curator(graph=graph, store=graph._store)` 复用 graph 自带 store，使外部传入与内部自造两路一致。

- [ ] **Step 4: 跑测试看通过**

Run: `pytest tests/unit/orchestration/test_assembly.py -v < /dev/null`
Expected: 全部 PASS（含原有 3 个 run_new_agent_session 用例）

- [ ] **Step 5: Commit**

```bash
git add app/orchestration/assembly.py tests/unit/orchestration/test_assembly.py
git commit -m "feat: assembly passes optional graph/on_event through to collab loop"
```

---

### Task 3: 新增掌握度 SQLAlchemy 表 + 放宽 MasteryGraph store 标注

**Files:**
- Modify: `app/models/tables.py`（文件末尾追加两表）
- Modify: `app/harness/mastery_graph.py:54`（`__init__` 标注）
- Test: `tests/unit/models/test_mastery_tables.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/models/test_mastery_tables.py`：

```python
def test_mastery_tables_importable_and_named():
    from app.models.tables import MasteryNodeTable, MasteryEdgeTable
    assert MasteryNodeTable.__tablename__ == "mastery_nodes"
    assert MasteryEdgeTable.__tablename__ == "mastery_edges"
    # 复合主键 (user_id, topic_id)
    pk_cols = {c.name for c in MasteryNodeTable.__table__.primary_key.columns}
    assert pk_cols == {"user_id", "topic_id"}
    # topic_id 列宽够长（容纳整条用户消息，R2-A）
    assert MasteryNodeTable.__table__.c.topic_id.type.length >= 512
```

- [ ] **Step 2: 跑测试看失败**

Run: `pytest tests/unit/models/test_mastery_tables.py -v < /dev/null`
Expected: FAIL（`cannot import name 'MasteryNodeTable'`）

- [ ] **Step 3: 实现**

在 `app/models/tables.py` 末尾追加（import 已含 `UniqueConstraint` 需补）。先把首行 import 改为：

```python
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON, ForeignKey, UniqueConstraint
```

末尾追加两表：

```python
class MasteryNodeTable(Base):
    __tablename__ = "mastery_nodes"
    user_id = Column(String(64), primary_key=True)
    topic_id = Column(String(512), primary_key=True)
    topic_name = Column(String(512), nullable=False, default="")
    mastery = Column(Float, nullable=False, default=0.0)
    last_practiced_at = Column(Float, nullable=False, default=0.0)
    practice_count = Column(Integer, nullable=False, default=0)
    confusion_with = Column(JSON, nullable=False, default=list)
    rationale = Column(Text, nullable=False, default="")


class MasteryEdgeTable(Base):
    __tablename__ = "mastery_edges"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    from_topic = Column(String(512), nullable=False)
    to_topic = Column(String(512), nullable=False)
    type = Column(String(16), nullable=False, default="PREREQ")
    weight = Column(Float, nullable=False, default=1.0)
    confidence = Column(Float, nullable=False, default=0.5)
    source = Column(String(16), nullable=False, default="LLM_INFER")
    __table_args__ = (
        UniqueConstraint("user_id", "from_topic", "to_topic", "type",
                         name="uq_mastery_edge"),
    )
```

放宽 `app/harness/mastery_graph.py:54` 标注（去掉硬 `MasteryGraphStore`，避免实现层耦合具体 store 类型）：

```python
    def __init__(self, user_id: str, store):
```

并删除该文件顶部不再需要的 `from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore`（仅当该 import 在文件内无其他用处时；若有 docstring 引用可保留 import 不动——core 行为不依赖它）。**保守做法：保留 import 不删，仅去掉参数标注**，避免连带破坏。

- [ ] **Step 4: 跑测试看通过**

Run: `pytest tests/unit/models/test_mastery_tables.py tests/unit/harness/test_mastery_graph.py -v < /dev/null`
Expected: 全部 PASS（含旧 mastery_graph 测试，标注放宽不影响运行时）

- [ ] **Step 5: Commit**

```bash
git add app/models/tables.py app/harness/mastery_graph.py tests/unit/models/test_mastery_tables.py
git commit -m "feat: add MasteryNode/Edge SQLAlchemy tables, loosen MasteryGraph store annotation"
```

---

### Task 4: SQLAlchemyMasteryStore（复刻旧 store 4 方法契约）

**Files:**
- Create: `app/infrastructure/storage/sqlalchemy_mastery_store.py`
- Test: `tests/unit/infrastructure/test_sqlalchemy_mastery_store.py`（新建）

契约（必须与旧 `MasteryGraphStore` 逐字一致，使 `MasteryGraph.save/load` 无需改）：
- `save_nodes(user_id: str, nodes: list[dict])`：每个 dict 含 `topic_id/topic_name/mastery/last_practiced_at/practice_count/confusion_with/rationale`。
- `load_nodes(user_id: str) -> dict[str, dict]`：key=topic_id，value 含上述全部键。
- `save_edges(user_id: str, edges: list[dict])`：每个 dict 含 `from_topic/to_topic/type/weight/confidence/source`。
- `load_edges(user_id: str) -> list[dict]`。
- save 方法**不 commit**（C3：调用方提交）。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/infrastructure/test_sqlalchemy_mastery_store.py`：

```python
def test_save_load_nodes_roundtrip(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                store = SQLAlchemyMasteryStore(db)
                await store.save_nodes("u1", [{
                    "topic_id": "二分查找", "topic_name": "二分查找",
                    "mastery": 75.0, "last_practiced_at": 1.5,
                    "practice_count": 2, "confusion_with": ["排序"],
                    "rationale": "答对核心问题",
                }])
                await db.commit()
                loaded = await store.load_nodes("u1")
            assert loaded["二分查找"]["mastery"] == 75.0
            assert loaded["二分查找"]["rationale"] == "答对核心问题"
            assert loaded["二分查找"]["confusion_with"] == ["排序"]
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_save_nodes_upsert_updates(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                store = SQLAlchemyMasteryStore(db)
                await store.save_nodes("u1", [{"topic_id": "t", "topic_name": "t",
                    "mastery": 10.0, "last_practiced_at": 0, "practice_count": 1,
                    "confusion_with": [], "rationale": ""}])
                await db.commit()
                await store.save_nodes("u1", [{"topic_id": "t", "topic_name": "t",
                    "mastery": 90.0, "last_practiced_at": 0, "practice_count": 2,
                    "confusion_with": [], "rationale": ""}])
                await db.commit()
                loaded = await store.load_nodes("u1")
            assert loaded["t"]["mastery"] == 90.0  # 同 PK 覆盖而非重复
            assert loaded["t"]["practice_count"] == 2
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_save_load_edges_roundtrip(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                store = SQLAlchemyMasteryStore(db)
                await store.save_edges("u1", [{
                    "from_topic": "a", "to_topic": "b", "type": "PREREQ",
                    "weight": 1.0, "confidence": 0.8, "source": "INTERACTION",
                }])
                await db.commit()
                loaded = await store.load_edges("u1")
            assert len(loaded) == 1
            assert loaded[0]["from_topic"] == "a" and loaded[0]["confidence"] == 0.8
        finally:
            await engine.dispose()
    db_fixture.run(_test())
```

- [ ] **Step 2: 跑测试看失败**

Run: `pytest tests/unit/infrastructure/test_sqlalchemy_mastery_store.py -v < /dev/null`
Expected: FAIL（`No module named '...sqlalchemy_mastery_store'`）

- [ ] **Step 3: 实现**

新建 `app/infrastructure/storage/sqlalchemy_mastery_store.py`：

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import MasteryNodeTable, MasteryEdgeTable


class SQLAlchemyMasteryStore:
    """掌握度图谱的 SQLAlchemy 持久化（PG/SQLite 双模）。

    复刻旧 MasteryGraphStore 的 save_nodes/load_nodes/save_edges/load_edges
    四方法契约，使 MasteryGraph.save/load 无需改内部调用。save 不 commit（C3）。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_nodes(self, user_id: str, nodes: list[dict]) -> None:
        for n in nodes:
            row = await self.db.get(MasteryNodeTable, (user_id, n["topic_id"]))
            if row is None:
                self.db.add(MasteryNodeTable(
                    user_id=user_id, topic_id=n["topic_id"],
                    topic_name=n.get("topic_name", ""),
                    mastery=n.get("mastery", 0.0),
                    last_practiced_at=n.get("last_practiced_at", 0.0),
                    practice_count=n.get("practice_count", 0),
                    confusion_with=n.get("confusion_with", []),
                    rationale=n.get("rationale", ""),
                ))
            else:
                row.topic_name = n.get("topic_name", "")
                row.mastery = n.get("mastery", 0.0)
                row.last_practiced_at = n.get("last_practiced_at", 0.0)
                row.practice_count = n.get("practice_count", 0)
                row.confusion_with = n.get("confusion_with", [])
                row.rationale = n.get("rationale", "")

    async def load_nodes(self, user_id: str) -> dict[str, dict]:
        result = await self.db.execute(
            select(MasteryNodeTable).where(MasteryNodeTable.user_id == user_id)
        )
        out: dict[str, dict] = {}
        for r in result.scalars().all():
            out[r.topic_id] = {
                "topic_id": r.topic_id,
                "topic_name": r.topic_name,
                "mastery": r.mastery,
                "last_practiced_at": r.last_practiced_at,
                "practice_count": r.practice_count,
                "confusion_with": r.confusion_with or [],
                "rationale": r.rationale or "",
            }
        return out

    async def save_edges(self, user_id: str, edges: list[dict]) -> None:
        for e in edges:
            result = await self.db.execute(
                select(MasteryEdgeTable).where(
                    MasteryEdgeTable.user_id == user_id,
                    MasteryEdgeTable.from_topic == e["from_topic"],
                    MasteryEdgeTable.to_topic == e["to_topic"],
                    MasteryEdgeTable.type == e.get("type", "PREREQ"),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                self.db.add(MasteryEdgeTable(
                    user_id=user_id, from_topic=e["from_topic"],
                    to_topic=e["to_topic"], type=e.get("type", "PREREQ"),
                    weight=e.get("weight", 1.0),
                    confidence=e.get("confidence", 0.5),
                    source=e.get("source", "LLM_INFER"),
                ))
            else:
                row.weight = e.get("weight", 1.0)
                row.confidence = e.get("confidence", 0.5)
                row.source = e.get("source", "LLM_INFER")

    async def load_edges(self, user_id: str) -> list[dict]:
        result = await self.db.execute(
            select(MasteryEdgeTable).where(MasteryEdgeTable.user_id == user_id)
        )
        return [
            {"from_topic": r.from_topic, "to_topic": r.to_topic,
             "type": r.type, "weight": r.weight,
             "confidence": r.confidence, "source": r.source}
            for r in result.scalars().all()
        ]
```

- [ ] **Step 4: 跑测试看通过**

Run: `pytest tests/unit/infrastructure/test_sqlalchemy_mastery_store.py -v < /dev/null`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/storage/sqlalchemy_mastery_store.py tests/unit/infrastructure/test_sqlalchemy_mastery_store.py
git commit -m "feat: add SQLAlchemyMasteryStore replicating MasteryGraphStore contract"
```

---

### Task 5: SSE 事件投影函数 project_event

**Files:**
- Create: `app/api/_sse_projection.py`
- Test: `tests/api/test_sse_projection.py`（新建）

白名单 15 个 EventType（已对 enums.py 核实存在）：Tutor 4（ASKED/EXPLAINED/REQUESTED_RECAP/OFFERED_ANALOGY）+ MASTERY_ASSESSED/CONFUSION_DETECTED/CONTRADICTION_DETECTED/LOW_CONFIDENCE_DETECTED/RAG_QUALITY_ASSESSED + RETRIEVED_EVIDENCE/RETRIEVAL_FAILED + GRAPH_NODE_STRENGTHENED/GRAPH_PREREQ_WEAK_DETECTED + CONDUCTOR_DECIDED + POLICY_TRANSITION。

- [ ] **Step 1: 写失败测试**

新建 `tests/api/test_sse_projection.py`：

```python
from app.api._sse_projection import project_event
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


def _ev(t, source, payload):
    return Event(type=t, source=source, session_id="s", payload=payload)


def test_tutor_event_projected():
    out = project_event(_ev(EventType.TUTOR_ASKED, EventSource.TUTOR, {"content": "Q1"}))
    assert out["type"] == "agent_event"
    assert out["agent"] == "tutor"
    assert out["event"] == "TutorAsked"
    assert out["content"] == "Q1"


def test_mastery_assessed_carries_eval():
    out = project_event(_ev(EventType.MASTERY_ASSESSED, EventSource.CRITIC,
                            {"score": 80, "level": "good"}))
    assert out["agent"] == "critic"
    assert out["eval"]["score"] == 80
    assert out["eval"]["level"] == "good"


def test_control_event_filtered():
    assert project_event(_ev(EventType.ORCHESTRATOR_TICK, EventSource.ORCHESTRATOR, {})) is None
    assert project_event(_ev(EventType.USER_MESSAGE, EventSource.USER, {"text": "hi"})) is None
    assert project_event(_ev(EventType.LOOP_EXIT, EventSource.ORCHESTRATOR, {})) is None


def test_policy_transition_projected():
    out = project_event(_ev(EventType.POLICY_TRANSITION, EventSource.ORCHESTRATOR,
                            {"to": "feynman"}))
    assert out["event"] == "PolicyTransition"
    assert out["content"] == "feynman"
```

- [ ] **Step 2: 跑测试看失败**

Run: `pytest tests/api/test_sse_projection.py -v < /dev/null`
Expected: FAIL（`No module named 'app.api._sse_projection'`）

- [ ] **Step 3: 实现**

新建 `app/api/_sse_projection.py`：

```python
from app.harness.events import Event
from app.harness.enums import EventType

# 语义事件白名单（15 个）→ content 提取方式
_TUTOR = (EventType.TUTOR_ASKED, EventType.TUTOR_EXPLAINED,
          EventType.TUTOR_REQUESTED_RECAP, EventType.TUTOR_OFFERED_ANALOGY)
_CRITIC_EVAL = (EventType.MASTERY_ASSESSED, EventType.CONFUSION_DETECTED,
                EventType.CONTRADICTION_DETECTED, EventType.LOW_CONFIDENCE_DETECTED,
                EventType.RAG_QUALITY_ASSESSED)
_CURATOR = (EventType.GRAPH_NODE_STRENGTHENED, EventType.GRAPH_PREREQ_WEAK_DETECTED)
_RETRIEVER = (EventType.RETRIEVED_EVIDENCE, EventType.RETRIEVAL_FAILED)

_WHITELIST = set(_TUTOR) | set(_CRITIC_EVAL) | set(_CURATOR) | set(_RETRIEVER) | {
    EventType.CONDUCTOR_DECIDED, EventType.POLICY_TRANSITION,
}


def project_event(ev: Event) -> dict | None:
    """语义事件 → 前端友好 SSE payload；控制信号返回 None（生成器跳过）。"""
    if ev.type not in _WHITELIST:
        return None

    p = ev.payload or dict()
    out = {
        "type": "agent_event",
        "agent": str(ev.source),
        "event": str(ev.type),
        "content": "",
    }

    if ev.type in _TUTOR:
        out["content"] = p.get("content", "")
    elif ev.type in _CRITIC_EVAL:
        out["content"] = p.get("rationale", "") or p.get("content", "")
        out["eval"] = {k: p[k] for k in ("score", "level", "basis") if k in p}
    elif ev.type in _CURATOR:
        out["content"] = p.get("topic_id", "")
        out["eval"] = {k: p[k] for k in ("mastery", "prereq_topic_id") if k in p}
    elif ev.type in _RETRIEVER:
        out["content"] = p.get("summary", "") or str(p.get("count", ""))
    elif ev.type == EventType.POLICY_TRANSITION:
        out["content"] = p.get("to", "")
    elif ev.type == EventType.CONDUCTOR_DECIDED:
        out["content"] = p.get("decision", "") or p.get("action", "")

    return out
```

- [ ] **Step 4: 跑测试看通过**

Run: `pytest tests/api/test_sse_projection.py -v < /dev/null`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/_sse_projection.py tests/api/test_sse_projection.py
git commit -m "feat: add project_event SSE whitelist projection"
```

---

### Task 6: persist_turn 共享落库函数（返回 turn_index）

**Files:**
- Create: `app/api/_persist.py`
- Test: `tests/api/test_persist_turn.py`（新建）

抽 chat.py:29-62 落库逻辑成共享函数，加可选 graph.save()，返回 turn_index。

- [ ] **Step 1: 写失败测试**

新建 `tests/api/test_persist_turn.py`：

```python
def test_persist_turn_writes_session_messages_and_returns_turn_index(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api._persist import persist_turn
            from app.infrastructure.storage.message_store import MessageStore
            async with session_factory() as db:
                ti = await persist_turn(db, session_id="s1", user_id=1,
                                        user_message="你好", reply="回应", graph=None)
                msgs = await MessageStore(db).list_by_session("s1")
            assert ti == 0  # 首轮 turn_index
            assert len(msgs) == 2
            assert msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant"
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_persist_turn_saves_graph(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api._persist import persist_turn
            from app.harness.mastery_graph import MasteryGraph
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                graph = MasteryGraph(user_id="1", store=SQLAlchemyMasteryStore(db))
                graph.add_node("二分查找", "二分查找", mastery=70.0)
                await persist_turn(db, session_id="s2", user_id=1,
                                   user_message="二分", reply="r", graph=graph)
                # 重新载入验证落库
                graph2 = MasteryGraph(user_id="1", store=SQLAlchemyMasteryStore(db))
                await graph2.load()
            assert graph2.get_node("二分查找").mastery == 70.0
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_persist_turn_rolls_back_and_returns_none_on_error(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api._persist import persist_turn

            class BoomGraph:
                async def save(self):
                    raise RuntimeError("boom")
            async with session_factory() as db:
                ti = await persist_turn(db, session_id="s3", user_id=1,
                                        user_message="x", reply="y", graph=BoomGraph())
                from app.infrastructure.storage.message_store import MessageStore
                msgs = await MessageStore(db).list_by_session("s3")
            assert ti is None          # 失败返回 None
            assert len(msgs) == 0      # 整体回滚，不半落库
        finally:
            await engine.dispose()
    db_fixture.run(_test())
```

- [ ] **Step 2: 跑测试看失败**

Run: `pytest tests/api/test_persist_turn.py -v < /dev/null`
Expected: FAIL（`No module named 'app.api._persist'`）

- [ ] **Step 3: 实现**

新建 `app/api/_persist.py`：

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.storage.session_store import SessionStore
from app.infrastructure.storage.message_store import MessageStore


async def persist_turn(db: AsyncSession, session_id: str, user_id, user_message: str,
                       reply: str, graph=None) -> int | None:
    """原子落库一轮：session(upsert) + user/assistant 两条消息 (+ 可选 graph.save())。

    返回算出的 turn_index（供 API 回填 turn_count=turn_index+1）；失败 rollback 返回 None。
    成功一次 commit（C3）。
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
        return turn_index
    except Exception as e:
        await db.rollback()
        try:
            from app.harness.observability import get_observability
            get_observability().log_event("persist_error",
                                          {"session_id": session_id, "error": str(e)})
        except Exception:
            pass
        return None
```

- [ ] **Step 4: 跑测试看通过**

Run: `pytest tests/api/test_persist_turn.py -v < /dev/null`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/_persist.py tests/api/test_persist_turn.py
git commit -m "feat: add shared persist_turn (session+messages+optional graph, atomic)"
```

---

### Task 7: chat.py 改调 persist_turn + 接掌握度 + turn_count

**Files:**
- Modify: `app/api/chat.py:17-72`（新栈分支）
- Test: `tests/unit/api/test_chat_persist.py`（已存在，需补掌握度断言；先确认现有不破）

- [ ] **Step 1: 写失败测试**

加到 `tests/unit/api/test_chat_persist.py` 末尾（沿用其现有 mock 风格——文件已 mock `run_new_agent_session`）：

```python
def test_chat_turn_count_is_teaching_round(db_fixture, monkeypatch):
    # 第一轮 turn_count 应为 1（turn_index 0 + 1），非事件循环次数
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.orchestration.assembly import NewStackResult
            import app.api.chat as chat_mod
            from app.api.chat import chat
            from app.models.schemas import ChatRequest

            def fake_run(session_id, user_id, message, **kw):
                return NewStackResult(reply="R", mastery_score=80, turn_count=11,
                                      mode_path=["socratic"], cost_est_usd=None, events=[])
            monkeypatch.setattr("app.orchestration.assembly.run_new_agent_session", fake_run)
            monkeypatch.setattr(chat_mod, "use_new_agent_graph", lambda: True)

            async with session_factory() as db:
                resp = await chat(ChatRequest(message="hi", session_id="sc1", user_id=1), db=db)
            assert resp.turn_count == 1   # 不是 11
        finally:
            await engine.dispose()
    db_fixture.run(_test())
```

- [ ] **Step 2: 跑测试看失败**

Run: `pytest tests/unit/api/test_chat_persist.py::test_chat_turn_count_is_teaching_round -v < /dev/null`
Expected: FAIL（当前 turn_count 透传 result.turn_count=11）

- [ ] **Step 3: 实现**

将 `app/api/chat.py` 新栈分支（17-72 行）改为构造 graph、调 persist_turn、用其返回值算 turn_count。替换 import 段并重写新栈分支：

```python
import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ChatRequest, ChatResponse
from app.core.feature_flags import use_new_agent_graph
from app.core.database import get_db
from app.api._persist import persist_turn
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
from app_old.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat"])
_graph = build_learning_graph()


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    if use_new_agent_graph():
        from app.orchestration.assembly import run_new_agent_session
        uid_str = str(req.user_id) if req.user_id is not None else "anonymous"

        graph = MasteryGraph(user_id=uid_str, store=SQLAlchemyMasteryStore(db))
        await graph.load()

        result = await asyncio.to_thread(
            run_new_agent_session, req.session_id, uid_str, req.message,
            None, graph,        # current_topic=None, graph=graph
        )

        turn_index = await persist_turn(
            db, session_id=req.session_id, user_id=req.user_id,
            user_message=req.message, reply=result.reply, graph=graph,
        )
        turn_count = (turn_index + 1) if turn_index is not None else None

        return ChatResponse(
            reply=result.reply,
            session_id=req.session_id,
            mastery_score=result.mastery_score,
            turn_count=turn_count,
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

> 注：`run_new_agent_session` 位置参数顺序 `(session_id, user_id, user_message, current_topic, graph)`，与 Task 2 签名一致。

- [ ] **Step 4: 跑测试看通过**

Run: `pytest tests/unit/api/test_chat_persist.py -v < /dev/null`
Expected: 全部 PASS（含原有持久化用例 + 新 turn_count 用例）

- [ ] **Step 5: Commit**

```bash
git add app/api/chat.py tests/unit/api/test_chat_persist.py
git commit -m "feat: chat.py uses persist_turn + mastery load/save + teaching turn_count"
```

---

### Task 8: chat_stream 真流式（队列桥接 + 自开 session + persist_turn）

**Files:**
- Modify: `app/api/chat_stream.py:14-29`（新栈分支）
- Test: `tests/api/test_chat_stream_realtime.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `tests/api/test_chat_stream_realtime.py`（用 FastAPI TestClient 跑流式；mock run_new_agent_session 让它通过 on_event 推几个事件）：

```python
import json
import pytest


def test_chat_stream_emits_incremental_agent_events(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.api.chat_stream as cs
    from app.orchestration.assembly import NewStackResult
    from app.harness.events import Event
    from app.harness.enums import EventType, EventSource

    monkeypatch.setattr(cs, "use_new_agent_graph", lambda: True)

    def fake_run(session_id, user_id, message, current_topic=None, graph=None, on_event=None):
        # 模拟协作环逐事件回调
        if on_event:
            on_event(Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR,
                           session_id=session_id, payload={"content": "Q?"}))
            on_event(Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                           session_id=session_id, payload={"score": 80, "level": "good"}))
        return NewStackResult(reply="最终回答", mastery_score=80, turn_count=11,
                              mode_path=["socratic"], cost_est_usd=None, events=[])

    monkeypatch.setattr("app.orchestration.assembly.run_new_agent_session", fake_run)

    client = TestClient(app)
    with client.stream("POST", "/api/chat/stream",
                       json={"message": "hi", "session_id": "st1", "user_id": 1}) as r:
        body = "".join(chunk for chunk in r.iter_text())

    # 逐事件：至少一个 agent_event + 一个 final
    assert "agent_event" in body
    assert "TutorAsked" in body
    final_lines = [l for l in body.splitlines() if l.startswith("data:") and "final" in l]
    assert final_lines, "应有 final 事件"
    payload = json.loads(final_lines[-1][len("data:"):].strip())
    assert payload["reply"] == "最终回答"
    assert payload["turn_count"] == 1   # 教学回合，非 11
```

> 注：mount 前缀以 `app/main.py` 实际注册为准（chat_stream router prefix=`/chat`，若 main 挂在 `/api` 下则路径为 `/api/chat/stream`）。执行前先 `grep -n "chat_stream\|include_router" app/main.py` 确认实际前缀，必要时调整测试 URL。

- [ ] **Step 2: 跑测试看失败**

Run: `pytest tests/api/test_chat_stream_realtime.py -v < /dev/null`
Expected: FAIL（当前假流式只 yield 一次 reply 文本，无 agent_event/final）

- [ ] **Step 3: 实现**

重写 `app/api/chat_stream.py` 新栈分支（保留老栈回退不动）：

```python
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest
from app.core.feature_flags import use_new_agent_graph
from app.core.database import async_session
from app.api._sse_projection import project_event
from app.api._persist import persist_turn
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
from app_old.agent.graph import build_learning_graph

router = APIRouter(prefix="/chat", tags=["chat-stream"])
_graph = build_learning_graph()

_SENTINEL = object()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    if use_new_agent_graph():
        from app.orchestration.assembly import run_new_agent_session
        uid_str = str(req.user_id) if req.user_id is not None else "anonymous"

        async def generate_new():
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()

            # 自开独立 session，生命周期贯穿整个流（R2-E：不依赖 Depends(get_db)）
            async with async_session() as db:
                graph = MasteryGraph(user_id=uid_str, store=SQLAlchemyMasteryStore(db))
                await graph.load()

                def cb(ev):  # 工作线程内执行 → 跨线程投递
                    loop.call_soon_threadsafe(queue.put_nowait, ev)

                task = asyncio.create_task(asyncio.to_thread(
                    run_new_agent_session, req.session_id, uid_str, req.message,
                    None, graph, cb,
                ))
                task.add_done_callback(
                    lambda _: loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL))

                while True:
                    item = await queue.get()
                    if item is _SENTINEL:
                        break
                    sse = project_event(item)
                    if sse is not None:
                        yield f"data: {json.dumps(sse, ensure_ascii=False)}\n\n"

                result = await task   # 取结果 + re-raise 工作线程异常

                turn_index = await persist_turn(
                    db, session_id=req.session_id, user_id=req.user_id,
                    user_message=req.message, reply=result.reply, graph=graph,
                )
                turn_count = (turn_index + 1) if turn_index is not None else None

                final = {
                    "type": "final",
                    "reply": result.reply,
                    "turn_count": turn_count,
                    "mastery_score": result.mastery_score,
                    "mode_path": result.mode_path,
                }
                yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"

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

> `run_new_agent_session` 位置参数：`(session_id, user_id, user_message, current_topic=None, graph, on_event)` → 调用传 `(req.session_id, uid_str, req.message, None, graph, cb)`。

- [ ] **Step 4: 跑测试看通过**

Run: `pytest tests/api/test_chat_stream_realtime.py -v < /dev/null`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/chat_stream.py tests/api/test_chat_stream_realtime.py
git commit -m "feat: chat_stream real per-event SSE via thread-safe queue bridge + persist"
```

---

> **关于子模块 F（turn_count）**：回合数修复已在 Task 7（chat.py）与 Task 8（chat_stream）中内联落地——两处都用 `persist_turn` 返回的 `turn_index + 1` 作为 `turn_count`，不再透传 `result.turn_count`（事件循环次数）。无需独立任务。

### Task 9: profile 读真实数据

**Files:**
- Modify: `app/api/profile.py`
- Test: `tests/api/test_profile_real.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `tests/api/test_profile_real.py`：

```python
def test_profile_reads_real_sessions_and_avg_mastery(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api.profile import get_profile
            from app.infrastructure.storage.session_store import SessionStore
            from app.infrastructure.storage.sqlalchemy_mastery_store import SQLAlchemyMasteryStore
            async with session_factory() as db:
                # 两个会话 + 两个掌握度节点（70、90 → 均值 80）
                await SessionStore(db).save("s1", state={}, user_id=1, title="t1")
                await SessionStore(db).save("s2", state={}, user_id=1, title="t2")
                store = SQLAlchemyMasteryStore(db)
                await store.save_nodes("1", [
                    {"topic_id": "a", "topic_name": "a", "mastery": 70.0,
                     "last_practiced_at": 0, "practice_count": 1,
                     "confusion_with": [], "rationale": ""},
                    {"topic_id": "b", "topic_name": "b", "mastery": 90.0,
                     "last_practiced_at": 0, "practice_count": 1,
                     "confusion_with": [], "rationale": ""},
                ])
                await db.commit()
                resp = await get_profile(1, db=db)
            assert resp["stats"]["sessions"] == 2
            assert resp["stats"]["avg_mastery"] == 80   # int，非 80.0，非 8000
        finally:
            await engine.dispose()
    db_fixture.run(_test())


def test_profile_empty_returns_zero(db_fixture):
    async def _test():
        engine, session_factory = await db_fixture.setup_db()
        try:
            from app.api.profile import get_profile
            async with session_factory() as db:
                resp = await get_profile(999, db=db)
            assert resp["stats"]["sessions"] == 0
            assert resp["stats"]["avg_mastery"] == 0
        finally:
            await engine.dispose()
    db_fixture.run(_test())
```

- [ ] **Step 2: 跑测试看失败**

Run: `pytest tests/api/test_profile_real.py -v < /dev/null`
Expected: FAIL（当前 `get_profile` 无 db 参数，且写死返回 0）

- [ ] **Step 3: 实现**

重写 `app/api/profile.py`：

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.tables import SessionTable, MasteryNodeTable

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{user_id}")
async def get_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    sessions = await db.scalar(
        select(func.count()).select_from(SessionTable)
        .where(SessionTable.user_id == user_id)
    ) or 0

    avg = await db.scalar(
        select(func.avg(MasteryNodeTable.mastery))
        .where(MasteryNodeTable.user_id == str(user_id))
    )
    avg_mastery = int(round(avg)) if avg is not None else 0  # mastery 本就是 0-100，不×100

    return {"user_id": user_id, "stats": {"sessions": sessions, "avg_mastery": avg_mastery}}
```

- [ ] **Step 4: 跑测试看通过**

Run: `pytest tests/api/test_profile_real.py -v < /dev/null`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/profile.py tests/api/test_profile_real.py
git commit -m "feat: profile reads real session count + avg mastery (0-100 int)"
```

---

### Task 10: 全量回归 + 验收确认

**Files:** 无新增，仅运行验证。

- [ ] **Step 1: 跑全量测试套件**

Run: `pytest < /dev/null`
Expected: 全部 PASS。**重点确认回归保护**：
- 旧 `MasteryGraphStore` 4 个测试（test_curator / test_user_profile / test_mastery_graph / test_mastery_graph_store）全绿——证实 P2「旧 store 不删不改」成立。
- `test_assembly` 原有 3 个 run_new_agent_session 用例全绿——证实 P3「graph/on_event 可选向后兼容」成立。
- `test_chat_persist` 原有持久化用例全绿——证实 persist_turn 抽取未改变 chat.py 落库行为。

- [ ] **Step 2: 验收标准逐条核对（对照 spec §6）**

逐条确认（人工/测试）：
1. `/chat/stream` 逐事件 + final → `test_chat_stream_realtime` ✓
2. 掌握度落库 → `test_persist_turn_saves_graph` ✓
3. profile 真实数据 0-100 → `test_profile_real` ✓
4. turn_count=1/2 非 11 → `test_chat_turn_count_is_teaching_round` ✓
5. stream 跑完 messages 落 2 行 → `test_chat_stream_realtime`（可补断言）/ `test_persist_turn` ✓
6. 写库失败仍返回 → `test_persist_turn_rolls_back...` ✓
7. on_event=None + 旧测试全绿 → Step 1 ✓

- [ ] **Step 3: 更新 README**

按 README 维护规范，更新根 `README.md`：新增 `/chat/stream` 真流式 SSE 事件格式说明、profile 真实数据、掌握度落库、测试数变化。

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for subproject ② realtime stream + mastery persistence"
```

---

## 已知过渡态（不在本计划修复，④ 收口）

- `/chat/stream` 返回结构化 JSON SSE，但前端 `Chat.tsx` 仍按纯文本解析且仍走 `/chat`（非流式）。本计划交付到子项目④ 之间前端 SSE 解析错位是**已知过渡态**，非 bug。本计划的流式正确性由 `test_chat_stream_realtime` 验证，不依赖前端。

## PG 部署提示

- 本计划新增 `mastery_nodes`/`mastery_edges` 两张 SQLAlchemy 表。PG 模式（M1：alembic 为唯一建表源）需补一版 alembic migration 建这两表；SQLite 走 `init_db` 的 `create_all` 自动包含。生成迁移：`alembic revision --autogenerate -m "add mastery tables"`，检查后 `alembic upgrade head`。
