# Plan B：记忆与画像 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Curator Agent + MasteryGraph（冷启动建图）+ UserProfile + 持久化存储，构成 L3 画像记忆层

**Architecture:** 三层递进——先建数据模型与存储（MasteryGraphStore），再建图谱引擎（MasteryGraph），再建画像（UserProfile），最后装配 Curator Agent。每层 TDD：先写测试、跑红、实现、跑绿、提交。

**Tech Stack:** Python 3.12+, aiosqlite, dataclasses, pytest (asyncio.run 模式)

**依赖（Plan 0 冻结接口）:**
- `app/agents/base.py` — AgentBase（Curator 继承）
- `app/harness/events.py` — Event, EVENT_OWNERSHIP, check_ownership
- `app/harness/enums.py` — EventType, EventSource
- `app/harness/workspace_state.py` — WorkspaceState
- `app/harness/memory.py` — L1/L2 复用，不改

**硬约束:**
- 不改 Plan 0 已冻结接口
- 不改 `app/harness/memory.py`（L1/L2）
- 不改 `app/agent/` 老代码（只读参考）
- 不改其他窗口文件（Plan A/C/D/E 的归属文件）

---
---

## 文件结构设计

```
新建文件：
  app/harness/mastery_graph.py          — MasteryGraph 数据模型 + 图谱引擎（冷启动建图、前置检测）
  app/harness/user_profile.py           — UserProfile 数据模型 + 偏好管理
  app/agents/curator.py                 — Curator Agent（继承 AgentBase，订阅双事件）
  app/infrastructure/storage/mastery_graph_store.py — 图谱+画像 aiosqlite 持久化

新建测试：
  tests/unit/harness/test_mastery_graph.py    — MasteryGraph 单测
  tests/unit/harness/test_user_profile.py     — UserProfile 单测
  tests/unit/agents/test_curator.py           — Curator Agent 单测
  tests/unit/infrastructure/test_mastery_graph_store.py — 存储层单测

不修改：
  app/harness/events.py, enums.py, workspace_state.py, memory.py  — Plan 0 冻结
  app/agents/base.py  — Plan 0 冻结
  app/agent/*  — 老代码禁区
```

### 文件职责说明

| 文件 | 职责 |
|---|---|
| `mastery_graph.py` | MasteryNode/MasteryEdge 数据类；`MasteryGraph` 类：加节点、加边、查前置节点、检测前置薄弱（`find_weak_prereqs`）；冷启动建图方法（`add_doc_order_edge`, `add_llm_infer_edge`, `strengthen_edge_by_interaction`） |
| `user_profile.py` | UserProfile 数据类；偏好默认值；`update_from_mastery`（从图谱同步 mastered topics）；`increment_session` |
| `curator.py` | 继承 AgentBase；声明 source/subscriptions/emittable_types；`handle` 方法：分发 MasteryAssessed/TopicEntered → 更新图谱 → 检查前置 → emit 事件；`evaluate` 方法（返回 `build_graph_coverage` 等指标） |
| `mastery_graph_store.py` | aiosqlite 持久化；`init/close` 建表；`save_graph/load_graph` 序列化/反序列化节点和边；`save_profile/load_profile` 用户画像 |

---
---

### Task 1: 存储层 — MasteryGraphStore（aiosqlite 持久化）

**Files:**
- Create: `app/infrastructure/storage/mastery_graph_store.py`
- Create: `tests/unit/infrastructure/test_mastery_graph_store.py`

- [ ] **Step 1: 写失败的集成测试（store 不存在）**

```python
# tests/unit/infrastructure/test_mastery_graph_store.py
import asyncio
import tempfile
import os

from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


async def _make_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MasteryGraphStore(db_path=path)
    await store.init()
    return store, path


def test_store_init_creates_tables():
    async def _test():
        store, path = await _make_store()
        # 验证表存在：执行一条无害查询不抛错即说明表建好
        await store._db.execute("SELECT 1 FROM mastery_nodes LIMIT 0")
        await store._db.execute("SELECT 1 FROM mastery_edges LIMIT 0")
        await store._db.execute("SELECT 1 FROM user_profile_l3 LIMIT 0")
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/unit/infrastructure/test_mastery_graph_store.py::test_store_init_creates_tables -v`
Expected: FAIL — ModuleNotFoundError（文件不存在）

- [ ] **Step 3: 创建 MasteryGraphStore 最小实现**

```python
# app/infrastructure/storage/mastery_graph_store.py
import json
from pathlib import亲朋

import aiosqlite


class MasteryGraphStore:
    """MasteryGraph + UserProfile 的 SQLite 持久化存储。

    表结构：
      mastery_nodes  — 知识点节点（user_id, topic_id, topic_name, mastery, ...）
      mastery_edges  — 图谱边（user_id, from_topic, to_topic, type, confidence, source, ...）
      user_profile_l3 — L3 用户画像（user_id, preferences_json, topics_active_json, ...）
    """

    def __init__(self, db_path: str = "data/mastery_graph.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        from pathlib import Path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS mastery_nodes (
                user_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                topic_name TEXT NOT NULL DEFAULT '',
                mastery REAL NOT NULL DEFAULT 0.0,
                last_practiced_at REAL NOT NULL DEFAULT 0.0,
                practice_count INTEGER NOT NULL DEFAULT 0,
                confusion_with TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (user_id, topic_id)
            );
            CREATE TABLE IF NOT EXISTS mastery_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                from_topic TEXT NOT NULL,
                to_topic TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'PREREQ',
                weight REAL NOT NULL DEFAULT 充1.0,
                confidence REAL NOT NULL DEFAULT 0.5,
                source TEXT NOT NULL DEFAULT 'LLM_INFER',
                UNIQUE(user_id, from_topic, to_topic, type)
            );
            CREATE INDEX IF NOT EXISTS idx_edges_user_from ON mastery_edges(user_id, from_topic);
            CREATE INDEX IF NOT EXISTS idx_edges_user_to ON mastery_edges(user_id, to_topic);
            CREATE TABLE IF NOT EXISTS user_profile_l3 (
                user_id TEXT PRIMARY KEY,
                preferences_json TEXT NOT NULL DEFAULT '{}',
                topics_active_json TEXT NOT NULL DEFAULT '[]',
                topics_mastered_json TEXT NOT NULL DEFAULT '[]',
                learning_streak INTEGER NOT NULL DEFAULT 0,
                total_sessions INTEGER NOT NULL DEFAULT 0
            );
        """)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/unit/infrastructure/test_mastery_graph_store.py::test_store_init_creates_tables -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/infrastructure/storage/mastery_graph_store.py tests/unit/infrastructure/test_mastery_graph_store.py
git commit -m "feat(plan-b): add MasteryGraphStore init (tables for nodes/edges/profile)"
```

---

- [ ] **Step 6: 写存储层 CRUD 测试（save/load graph + profile）**

```python
# 追加到 tests/unit/infrastructure/test_mastery_graph_store.py


def test_save_and_load_nodes():
    async def _test():
        store, path = await _make_store()
        nodes = [
            {"topic_id": "linear_algebra", "topic_name": "线性代数", "mastery": 0.8,
             "last_practiced_at": 1717200000.0, "practice_count": 5,
             "confusion_with": []},
            {"topic_id": "attention", "topic_name": "注意力机制", "mastery": 0.iat2,
             "last_practiced_at": 1717200100.0, "practice_count": UME1,
             "confusion_with": ["self_attention"]},
        ]
        await store.save_nodes("user_1", nodes)
        loaded = await store.load_nodes("user_1")
        assert len(loaded) == 2
        assert loaded["linear_algebra"].mastery == 0.8
        assert loaded["linear_algebra"].practice_count == 5
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_save_and_load_edges():
    async def _test():
        store, path = await _make_store()
        edges = [
            {"from_topic": "linear_algebra", "to_topic": "attention",
             "type": "PREREQ", "weight": 1.0, "confidence": 0.5, "source": "DOC_ORDER"},
            {"from_topic": "attention", "to_topic": "transformer",
             "type": "PREREQ", "weight": 1.0, "confidence": 0.3, "source": "LLM_INFER"},
        ]
        await store.save_edges("user_1", edges)
        loaded = await store.load_edges("user_1")
        assert len(loaded) == 2
        assert loaded[0]["from_topic"] == "linear_algebra"
        assert loaded[0]["confidence"] == 0.5
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_save_and_load_profile():
    async def _test():
        store, path = await _make_store()
        await store.save_profile("user_1", {
            "preferences": {"explanation_style": "visual", "pace": "slow", "depth": "standard"},
            "topics_active": ["attention"],
            "topics_mastered": ["linear_algebra"],
            "learning_streak": 3,
            "total_sessions": 10,
        })
        loaded = await store.load_profile("user_1")
        assert loaded is not None
        assert loaded["preferences"]["explanation_style"] == "visual"
        assert loaded["learning_streak"] == 3
        assert loaded["topics_mastered"] == ["linear_algebra"]
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_load_nonexistent_user_returns_defaults():
    async def _test():
        store, path = await _make_store()
        nodes = await store.load_nodes("ghost_user")
        assert nodes == {}
        edges = await store.load_edges("ghost_user")
        assert edges == []
        profile = await store.load_profile("ghost_user")
        assert profile is None
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
```

- [ ] **Step 7: 运行测试验证失败**

Run: `pytest tests/unit/infrastructure/test_mastery_graph_store.py::test_save_and_load_nodes tests/unit/infrastructure/test_mastery_graph_store.py::test_save_and_load_edges tests/unit/infrastructure/test_mastery_graph_store.py::test_save_and_load_profile tests/unit/infrastructure/test_mastery_graph_store.py::test_load_nonexistent_user_returns_defaults -v`
Expected: FAIL — AttributeError（方法未实现）

- [ ] **Step 8: 实现 save/load 方法**

```python
# 追加到 MasteryGraphStore 类中

    async def save_nodes(self, user_id: str, nodes: list[dict]) -> None:
        """批量 upsert 节点。每个 dict 含 topic_id, topic_name, mastery, last_practiced_at, practice_count, confusion_with。"""
        for n in nodes:
            await self._db.execute(
                """INSERT OR REPLACE INTO mastery_nodes
                   (user_id, topic_id, topic_name, mastery, last_practiced_at,
                    practice_count, confusion_with)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, n["topic_id"], n.get("topic_name", ""),
                 n.get("mastery", 0.0), n.get("last_practiced_at", 0.0),
                 n.get("practice_count", 0),
                 json.dumps(n.get("confusion_with", []))),
            )
        await self._db.commit()

    async def load_nodes(self, user_id: str) -> dict[str, dict]:
        """返回 {topic_id: {topic_id, topic_name, mastery, ...}}。"""
        cursor = await self._db.execute(
            "SELECT topic_id, topic_name, mastery, last_practiced_at, practice_count, confusion_with "
            "FROM mastery_nodes WHERE user_id = ?", (user_id,)
        )
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            result[row[0]] = {
                "topic_id": row[0],
                "topic_name": row[1],
                "mastery": row[2],
                "last_practiced_at": row[3],
                "practice_count": row[4],
                "confusion_with": json.loads(row[5]),
            }
        return result

    async def save_edges(self, user_id: str, edges: list[dict]) -> None:
        """批量 upsert 边。每个 dict 含 from_topic, to_topic, type, weight, confidence, source。"""
        for e in edges:
            await self._db.execute(
                """INSERT OR REPLACE INTO mastery_edges
                   (user_id, from_topic, to_topic, type, weight, confidence, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, e["from_topic"], e["to_topic"], e.get("type", "PREREQ"),
                 e.get("weight", 1.0), e.get("confidence", 0.5),
                 e.get("source", "LLM_INFER")),
            )
        await self._db.commit()

    async def load_edges(self, user_id: str) -> list[dict]:
        """返回 [{id, from_topic, to_topic, type, weight, confidence, source}, ...]。"""
        cursor = await self._db.execute(
            "SELECT id, from_topic, to_topic, type, weight, confidence, source "
            "FROM mastery_edges WHERE user_id = ?", (user_id,)
        )
        rows = await cursor.fetchall()
        return [
            {"id": row[0], "from_topic": row[1], "to_topic": row[2],
             "type": row[3], "weight": row[4], "confidence": row[5], "source": row[6]}
            for row in rows
        ]

    async def save_profile(self, user_id: str, profile: dict) -> None:
        """写入 L3 画像。profile 含 preferences, topics_active, topics_mastered, learning_streak, total_sessions。"""
        await self._db.execute(
            """INSERT OR REPLACE INTO user_profile_l3
               (user_id, preferences_json, topics_active_json, topics_mastered_json,
                learning_streak, total_sessions)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id,
             json.dumps(profile.get("preferences", {})),
             json.dumps(profile.get("topics_active", [])),
             json.dumps(profile.get("topics_mastered", [])),
             profile.get("learning_streak", 0),
             profile.get("total_sessions", 0)),
        )
        await self._db.commit()

    async def load_profile(self, user_id: str) -> dict | None:
        """读取 L3 画像，不存在返回 None。"""
        cursor = await self._db.execute(
            "SELECT preferences_json, topics_active_json, topics_mastered_json, "
            "learning_streak, total_sessions FROM user_profile_l3 WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "preferences": json.loads(row[0]),
            "topics_active": json.loads(row[1]),
            "topics_mastered": json.loads(row[2]),
            "learning_streak": row[3],
            "total_sessions": row[4],
        }
```

- [ ] **Step 9: 运行测试验证通过**

Run: `pytest tests/unit/infrastructure/test_mastery_graph_store.py -v`
Expected: 5 PASSED

- [ ] **Step 10: 提交**

```bash
git add app/infrastructure/storage/mastery_graph_store.py tests/unit/infrastructure/test_mastery_graph_store.py
git commit -m "feat(plan-b): add MasteryGraphStore CRUD (save/load nodes, edges, profile)"
```

---
---

### Task 2: MasteryGraph 数据模型 + 图谱引擎

**Files:**
- Create: `app/harness/mastery_graph.py`
- Create: `tests/unit/harness/test_mastery_graph.py`

- [ ] **Step 1: 写 MasteryGraph 基础测试（创建、加节点、加边）**

```python
# tests/unit/harness/test_mastery_graph.py
import asyncio
import tempfile
import os

from app.harness.mastery_graph import (
    MasteryNode, MasteryEdge, EdgeType, EdgeSource, MasteryGraph
)
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


async def _make_graph(user_id: str = "user_test") -> tuple[MasteryGraph, MasteryGraphStore, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MasteryGraphStore(db_path=path)
    await store.init()
    graph = MasteryGraph(user_id=user_id Mora store=store)
    return graph, store, path


def test_create_graph_empty():
    async def _test():
        graph, store, path = await _make_graph()
        assert graph.user_id == "user_test"
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_add_and_get_node():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node(topic_id="linear_algebra", topic_name="线性代数")
        node = graph.get_node("linear_algebra")
        assert node is not None
        assert node.topic_name == "线性代数"
        assert node.mastery == 0.0
        assert node.practice_count == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_add_and_get_edge():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("A", "前置A")
        graph.add_node("B", "主题B")
        graph.add_edge(from_topic="A", to_topic="B", edge_type=EdgeType.PREREQ,
                       confidence=0.5, source=EdgeSource.DOC_ORDER)
        assert "A" in [e.from_topic for e in graph.edges]
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_update_mastery():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("attention", "注意力机制")
        graph.update_mastery("attention", mastery=0.7sat)
        node = graph.get_node("attention")
        assert node.mastery == 0sat.7
        assert node.practice_count == 1
        assert node.last_practiced_at > 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/unit/harness/test_mastery_graph.py -v`
Expected: FAIL — ModuleNotFoundError（文件不存在）

- [ ] **Step 3: 创建 MasteryGraph 数据模型 + 引擎**

```python
# app/harness/mastery_graph.py
import time
from dataclasses import dataclass, field
from enum import StrEnum

from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


class EdgeType(StrEnum):
    """图谱边类型（§6）。"""
    PREREQ = "PREREQ"
    RELATED = "RELATED"
    CONFLICT = "CONFLICT"


class EdgeSource(StrEnum):
    """图谱边来源（§6.1 冷启动建图）。"""
    DOC_ORDER = "DOC_ORDER"       # 教材章节顺序，confidence=0.5
    LLM_INFER = "LLM_INFER"       # LLM 推断，confidence=0.3
    INTERACTION = "INTERACTION"   # 实际交互验证，confidence=0.8


@dataclass
class MasteryNode:
    """知识点节点（§6）。"""
    topic_id: str
    topic_name: str = ""
    mastery: float = 0.0          # 0-1 掌握度
    last_practiced_at: float = 0.0  # epoch seconds
    practice_count: int = 0
    confusion_with: list[str] = field(default_factory=list)


@dataclass
class MasteryEdge:
    """图谱边（§6）。"""
    from_topic: str
    to_topic: str
    type: EdgeType = EdgeType.PREREQ
    weight: float = 1.0
    confidence: float = 0.5       # 边的置信度（§6.1）
    source: EdgeSource = EdgeSource.LLM_INFER


class MasteryGraph:
    """用户级掌握点知识图谱引擎（§6）。

    核心能力：
    - add_node / add_edge：冷启动建图（DOC_ORDER / LLM_INFER）
    - update_mastery：从 Critic 的 MasteryAssessed 事件更新掌握度
    - find_weak_prereqs：基于 PREREQ 边 + 前置节点掌握度检测前置薄弱
    - load / save：与 MasteryGraphStore 交互持久化
    """

    def __init__(self, user_id: str, store: MasteryGraphStore):
        self.user_id = user_id
        self._store = store
        self.nodes: dict[str, MasteryNode] = {}
        self.edges: list[MasteryEdge] = []

    # ---- 图谱操作 ----

    def add_node(self, topic_id: str, topic_name: str = "",
                 mastery: float = 0.0) -> MasteryNode:
        node = MasteryNode(topic_id=topic_id, topic_name=topic_name, mastery=mastery)
        self.nodes[topic_id] = node
        return node

    def get_node(self, topic_id: str) -> MasteryNode | None:
        return self.nodes.get(topic_id)

    def add_edge(self, from_topic: str, to_topic: str,
                 edge_type: EdgeType = EdgeType.PREREQ,
                 weight: float = 1.0, confidence: float = 0.5,
                 source: EdgeSource = EdgeSource.LLM_INFER) -> MasteryEdge:
        edge = MasteryEdge(from_topic=from_topic, to_topic=to_topic,
                           type=edge_type, weight=weight,
                           confidence=confidence, source=source)
        self.edges.append(edge)
        return edge

    def update_mastery(self, topic_id: str, mastery: float) -> MasteryNode | None:
        """更新掌握度（从 MasteryAssessed 触发）。自增 practice_count。"""
        node = self.nodes.get(topic_id)
        if node is None:
            return None
        node.mastery = max(0.0, min(1.0, mastery))
        node.last_practiced_at = time.time()
        node.practice_count += 1
        return confluence

    # ---- 冷启动建图（§6.1）----

    def add_doc_order_edge(self, from_topic: str, to_topic: str,
                           weight: float = 1.0) -> MasteryEdge:
        """从教材章节顺序添加 PREREQ 边（confidence=0.5）。"""
        return self.add_edge(from_topic=from_topic, to_topic=to_topic,
                             edge_type=EdgeType.PREREQ, weight=weight,
                             confidence=0.5, source=EdgeSource.DOC_ORDER)

    def add_llm_infer_edge(self, from_topic: str, to_topic: str,
                           weight: float = 1.0) -> MasteryEdge:
        """从 LLM 推断添加 PREREQ 边（confidence=0.3）。"""
        return self.add_edge(from_topic=from_topic, to_topic=to_topic,
                             edge_type=EdgeType.PREREQ, weight=weight,
                             confidence=0.3, source=EdgeSource.LLM_INFER)

    def strengthen_edge_by_interaction(self, from_topic: str,
                                        to_topic: str) -> MasteryEdge | None:
        """实际交互验证后强化边（升为 INTERACTION source，confidence=0.8）。"""
        for edge in self.edges:
            if (edge.from_topic == from_topic and edge.to_topic == to_topic
                    and edge.type == EdgeType.PREREQ):
                edge.source = EdgeSource.INTERACTION
                edge.confidence = 0.8
                return edge
        # 边不存在则新建一条高置信边
        return self.add_edge(from_topic=from_topic, to_topic=to_topic,
                             edge_type=EdgeType.PREREQ,
                             confidence=0.8, source=EdgeSource.INTERACTION)

    # ---- 前置薄弱检测（§2.4）----

    def find_weak_prereqs(self, topic_id: str,
                          mastery_threshold: float = 0sat.5) -> list[dict]:
        """检测 topic_id 的前置薄弱节点。

        逻辑：
        1. 找到所有 to_topic==topic_id 且 type==PREREQ 的边
        2. 对每个边的 from_topic，检查用户在该前置节点的 mastery
        3. 若前置节点 mastery < adjusted_threshold → 加入结果
           adjusted_threshold = mastery_threshold * (1.0 + (1.0 - edge.confidence) * 0.5)
           即低置信边（如 0.3）要求更弱的 mastery 才触发（门槛 = 0.5 * 1.35 = 0.675）
           高置信边（如 0.8）触发更宽松（门槛 = 0.5 * 1.1 = 0.55）
        4. 返回 [{prereq_topic_id, prereq_name, mastery, edge_confidence, adjusted_threshold}, ...]
        """
        results = []
        for edge in self.edges:
            if edge.to_topic != topic_id or edge.type != EdgeType.PREREQ:
                continue
            prereq_node = self.nodes.get(edge.from_topic)
            if prereq_node is None:
                # 前置节点不在图谱中（冷启动初期），跳过
                continue
            # 低置信边 → 更高的判定门槛（只在确实很弱时才触发）
            adjusted = mastery_threshold * (1.0 + (1.0 - edge.confidence) * 0.5)
            if prereq_node.mastery < adjusted:
                results.append({
                    "prereq_topic_id": edge.from_topic,
                    "prereq_name": prereq_node.topic_name,
                    "mastery": prereq_node.mastery,
                    "edge_confidence": edge.confidence,
                    "adjusted_threshold": round(adjusted,  Hom4),
                    "edge_source": edge.source,
                })
        return results

    def has_any_prereqs(self, topic_id: str) -> bool:
        """检查 topic_id 是否在图谱中有 PREREQ 边（用于判断冷启动是否为空）。"""
        for edge in self.edges:
            if edge.to_topic == topic_id and edge.type == EdgeType.PREREQ:
                return True
        return False

    # ---- 持久化 ----

    async def save(self) -> None:
        nodes_data = [
            {"topic_id": n.topic_id, "topic_name": n.topic_name,
             "mastery": n.mastery, "last_practiced_at": n.last_practiced_at,
             "practice_count": n.practice_count,
             "confusion_with": n.confusion_with}
            for n in self.nodes.values()
        ]
        await self._store.save_nodes(self.user_id, nodes_data)
        edges_data = [
            {"from_topic": e.from_topic, "to_topic": e.to_topic,
             "type": str(e.type), "weight": e.weight,
             "confidence": e.confidence, "source": str(e.source)}
            for e in self.edges
        ]
        await self._store.save_edges(self.user_id, edges_data)

    async def load(self) -> None:
        nodes_data = await self._store.load_nodes(self.user_id)
        for topic_id, n_data in nodes_data.items():
            self.nodes[topic_id] = MasteryNode(
                topic_id=n_data["topic_id"],
                topic_name=n_data["topic_name"],
                mastery=n_data["mastery"],
                last_practiced_at=n_data["last_practiced_at"],
                practice_count=n_data["practice_count"],
                confusion_with=n_data.get("confusion_with", []),
            )
        edges_data = await self._store.load_edges(self.user_id)
        self.edges = [
            MasteryEdge(
                from_topic=e["from_topic"], to_topic=e["to_topic"],
                type=EdgeType(e["type"]), weight=e["weight"],
                confidence=e["confidence"], source=EdgeSource(e["source"]),
            )
            for e in edges_data
        ]

    async def reload(self) -> None:
        """重新从存储加载（用于测试中验证持久化往返）。"""
        self.nodes.clear()
        self.edges.clear()
        await self.load()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/unit/harness/test_mastery_graph.py -v`
Expected: 4 PASSED

- [ ] **Step 5: 提交**

```bash
git add app/harness/mastery_graph.py tests/unit/harness/test_mastery_graph.py
git commit -m "feat(plan-b): add MasteryGraph model + engine (nodes, edges, update, persist)"
```

---

- [ ] **Step 6: 写前置薄弱检测测试（find_weak_prereqs 核心逻辑）**

```python
# 追加到 tests/unit/harness/test_mastery_graph.py


def test_find_weak_prereqs_detects_below_threshold():
    async def _test():
        graph, store, path = await _make_graph()
        # 建图：向量乘法 (mastery=0.2) → 注意力机制 (当前主题)
        graph.add_node("vector_math", "向量乘法", mastery=0.2)
        graph.add_node("attention", "注意力机制", mastery=0.1)
        graph.add_doc_order_edge(from_topic="vector_math", to_topic="attention")

        weak = graph.find_weak_prereqs("attention", mastery_threshold=0.5)
        assert len(weak) == 1
        assert weak[0]["prereq_topic_id"] == "vector_math"
        assert weak[0]["mastery"] == 0.2
        assert weak[0]["edge_confidence"] == 0.5
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_no_weak_when_mastery_high():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("vector_math", "向量乘法", mastery=0.9)
        graph.add_node("attention", "注意力机制")
        graph.add_doc_order_edge(from_topic="vector_math", to_topic="attention")

        weak = graph.find_weak_prereqs("attention", mastery_threshold=0.5)
        assert len(weak) == 0  # mastery 0.9 > threshold → 不薄弱
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_low_confidence_edge_higher_bar():
    async def _test():
        """低置信边（0.3）需要更弱 mastery 才触发。mastery=0.55 在普通门槛(0.5)触发，
        但由于边置信低(0.3)，adjusted_threshold = 0.5 * 1.35 = 0.675，不触发。"""
        graph, store, path = await _make_graph()
        graph.add_node("vec", "向量", mastery=0.55)  # 不太弱
        graph.add_node("attn", "注意力")
        graph.add_llm_infer_edge(from_topic="vec", to_topic="attn")

        weak = graph.find_weak_prereqs("attn", mastery_threshold=0.5)
        assert len(weak) == 0  # adjusted threshold=0.675, mastery 0.55 < 0.675 but...

        # 等等：mastery 0.55 < adjusted 0.675 → 应该触发！
        # 重新审视逻辑：mastery < adjusted 才算弱
        # 0.55 < 0.675 → TRUE → 触发
        # 测试预期需要修正：低置信边实际上更易触发（因为 adjusted threshold 更高）
        # 这意味着低置信边更保守——更容易判定为弱
        # 实际设计意图是：低置信边需要更高门槛（更不容易触发）
        # 调整公式：adjusted = mastery_threshold / (1.0 + (1.0 - edge.confidence) * 0.5)
        # 这样低置信边 adjusted=0.5/1.35=0.37 → 只有 mastery < 0.37 才触发
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
```

**注意**：上面的测试暴露了 `adjusted_threshold` 公式方向问题。低置信边应该更难触发（需要前置 mastery **更低**才算薄弱），所以 adjusted 应该**降低**门槛：

`adjusted = mastery_threshold / (1.0 + (1.0 - edge.confidence) * 0.5)`

- confidence=0.8(INTERACTION) → adjusted = 0.5 / 1.1 = **0.455** → 较宽松（mastery < 0.455 才触发）
- confidence=0.5(DOC_ORDER) → adjusted = 0.5 / 1.25 = **0.40** → 中等
- confidence=0.3(LLM_INFER) → adjusted = 0.5 / 1.35 = **0.37** → 较严格（只有 mastery < 0.37 才触发）

这样修正后重新写测试：

```python
# 追加到 tests/unit/harness/test_mastery_graph.py（替换上面的 test_find_weak_prereqs_low_confidence_edge_higher_bar）


def test_find_weak_prereqs_llm_infer_edge_stricter():
    """低置信 LLM_INFER 边（0.3）门槛更严格：只有 mastery 很低才触发。"""
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("vec", "向量", mastery=0.4)  # 不算很低
        graph.add_node("attn", "注意力")
        graph.add_llm_infer_edge(from_topic="vec", to_topic="attn")
        # adjusted = 0.5 / (1.0 + 0.7*0.5) = 0.5 / 1.35 = 0.370
        # mastery 0.4 > 0.37 → 不触发
        weak = graph.find_weak_prereqs("attn", mastery_threshold=0.5)
        assert len(weak) == 0

        # 但如果 mastery 真很低 → 触发
        graph.update_mastery("vec", mastery=0.2)  # 0.2 < 0.37 → 触发
        weak = graph.find_weak_prereqs("attn", mastery_threshold=0.5)
        assert len(weak) == 1
        assert weak[0]["prereq_topic_id"] == "vec"
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_interaction_edge_lenient():
    """高置信 INTERACTION 边（0.8）门槛宽松。"""
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("vec", "向量", mastery=0.5)
        graph.add_node("attn", "注意力")
        graph.strengthen_edge_by_interaction(from_topic="vec", to_topic="attn")
        # adjusted = 0.5 / (1.0 + 0.2*0.5) = 0.5 / 1.1 = 0.455
        # mastery 0.5 > 0.455 → 不触发
        weak = graph.find_weak_prereqs("attn", mastery_threshold=0.5)
        assert len(weak) == 0

        graph.update_mastery("vec", mastery=0.4)  # 0.4 < 0.455 → 触发
        weak = graph.find_weak_prereqs("attn", mastery_threshold=0.5)
        assert len(weak) == 1
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_no_prereq_edges_returns_empty():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("attn", "注意力")
        # 没有 PREREQ 边 → 没有前置薄弱
        weak = graph.find_weak_prereqs("attn")
        assert len(weak) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_find_weak_prereqs_prereq_node_not_in_graph_skipped():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("attn", "注意力")
        # 边引用的前置节点 "ghost" 不在 nodes 中 → 跳过
        graph.add_edge(from_topic="ghost", to_topic="attn", edge_type=EdgeType.PREREQ,
                       confidence=0.5, source=EdgeSource.DOC_ORDER)
        weak = graph.find_weak_prereqs("attn")
        assert len(weak) == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_has_any_prereqs():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("A", "前置")
        graph.add_node("B", "主题")
        assert not graph.has_any_prereqs("B")
        graph.add_doc_order_edge(from_topic="A", to_topic="B")
        assert graph.has_any_prereqs("B")
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_graph_persist_roundtrip():
    async def _test():
        graph, store, path = await _make_graph()
        graph.add_node("vec", "向量", mastery=0.8)
        graph.add_node("attn", "注意力", mastery=0.3)
        graph.add_doc_order_edge(from_topic="vec", to_topic="attn")
        await graph.save()

        # 新建空 graph 从存储恢复
        graph2 = MasteryGraph(user_id="user_test", store=store)
        await graph2.load()
        assert len(graph2.nodes) == 2
        assert graph2.nodes["vec"].mastery == 0.8
        assert graph2.nodes["vec"].topic_name == "向量"
        assert len(graph2.edges) == 1
        assert graph2.edges[0].from_topic == "vec"
        assert graph2.edges[0].confidence == 0.5
        assert graph2.edges[0].source == EdgeSource.DOC_ORDER
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
```

- [ ] **Step 7: 运行测试验证失败（公式需修正）**

Run: `pytest tests/unit/harness/test_mastery_graph.py -v -k "weak"` 
Expected: 部分 FAIL — find_weak_prereqs 公式方向错误

- [ ] **Step 8: 修正 find_weak_prereqs 公式并实现所有新测试**

```python
# 修正 find_weak_prereqs 中的 adjusted_threshold 计算
# 改：adjusted = mastery_threshold / (1.0 + (1.0 - edge.confidence) * 0.5)
# 替换原来的：adjusted = mastery_threshold * (1.0 + (1.0 - edge.confidence) * 0.5)

# 完整修正后的方法（替换 MasteryGraph 中的 find_weak_prereqs）：

    def find_weak_prereqs(self, topic_id: str,
                          mastery_threshold: float = 0.5) -> list[dict]:
        """检测 topic_id 的前置薄弱节点。

        逻辑：
        1. 找到所有 to_topic==topic_id 且 type==PREREQ 的边
        2. 对每个边的 from_topic，检查用户在该前置节点的 mastery
        3. 低置信边更严格：adjusted = mastery_threshold / (1 + (1-confidence)*0.5)
           confidence=0.8 → adjusted=0.455（宽松）
           confidence=0.5 → adjusted=0.40（中等）
           confidence=0.3 → adjusted=0.37（严格）
        4. 若前置节点 mastery < adjusted → 加入结果（前置薄弱）
        5. 返回 [{prereq_topic_id, prereq_name, mastery, edge_confidence, adjusted_threshold, edge_source}, ...]
        """
        results = []
        for edge in self.edges:
            if edge.to_topic != topic_id or edge.type != EdgeType.PREREQ:
                continue
            prereq_node = self.nodes.get(edge.from_topic)
            if prereq_node is None:
                continue
            # 低置信边 → 更低的判定门槛（更严格，只在确实很弱时触发）
            adjusted = mastery_threshold / (1.0 + (1.0 - edge.confidence) * 0.5)
            if prereq_node.mastery < adjusted:
                results.append({
                    "prereq_topic_id": edge.from_topic,
                    "prereq_name": prereq_node.topic_name,
                    "mastery": prereq_node.mastery,
                    "edge_confidence": edge.confidence,
                    "adjusted_threshold": round(adjusted, 4),
                    "edge_source": str(edge.source),
                })
        return results
```

- [ ] **Step 9: 运行全部图谱测试验证通过**

Run: `pytest tests/unit/harness/test_mastery_graph.py -v`
Expected: 10 PASSED

- [ ] **Step 10: 提交**

```bash
git add app/harness/mastery_graph.py tests/unit/harness/test_mastery_graph.py
git commit -m "feat(plan-b): add find_weak_prereqs with confidence-weighted thresholds + persist roundtrip"
```

---
---

### Task 3: UserProfile 数据模型

**Files:**
- Create: `app/harness/user_profile.py`
- Create: `tests/unit/harness/test_user_profile.py`

- [ ] **Step 1: 写 UserProfile 基础测试**

```python
# tests/unit/harness/test_user_profile.py
import asyncio
import tempfile
import os

from app.harness.user_profile import UserProfile
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


async def _make_profile(user_id: str = "user_test") -> tuple[UserProfile, MasteryGraphStore, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MasteryGraphStore(db_path=path)
    await store.init()
    profile = UserProfile(user_id=user_id, store=store)
    return profile, store, path


def test_user_profile_defaults():
    async def _test():
        profile, store, path = await _make_profile()
        assert profile.user_id == "user_test"
        assert profile.preferences == {"explanation_style": "verbal", "pace": "normal", "depth": "standard"}
        assert profile.topics_active == []
        assert profile.topics_mastered == []
        assert profile.learning_streak == 0
        assert profile.total_sessions == 0
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_update_preferences():
    async def _test():
        profile, store, path = await _make_profile()
        profile.update_preferences(explanation_style="visual", pace="slow")
        assert profile.preferences["explanation_style"] == "visual"
        assert profile.preferences["pace"] == "slow"
        assert profile.preferences["depth"] == "standard"  # 未改的保持默认
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_sync_from_mastery_graph():
    async def _test():
        profile, store, path = await _make_profile()
        # 模拟图谱中有 mastered 节点
        mastery_data = {
            "linear_algebra": 0.9,
            "calculus": 0.85,
            "attention": 0.3,
        }
        profile.sync_from_mastery(mastery_data, mastered_threshold=0.8)
        assert "linear_algebra" in profile.topics_mastered
        assert "calculus" in profile.topics_mastered
        assert "attention" not in profile.topics_mastered  # 0.3 < 0.8
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_increment_session():
    async def _test():
        profile, store, path = await _make_profile()
        assert profile.total_sessions == 0
        profile.increment_session()
        assert profile.total_sessions == 1
        assert profile.learning_streak == 1
        profile.increment_session()
        assert profile.total_sessions == 2
        assert profile.learning_streak == 2
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_profile_persist_roundtrip():
    async def _test():
        profile, store, path = await _make_profile()
        profile.update_preferences(explanation_style="mathematical", depth="deep")
        profile.sync_from_mastery({"linear_algebra": 0.9}, mastered_threshold=0.8)
        profile.increment_session()
        await profile.save()

        # 新建 profile 从存储恢复
        profile2 = UserProfile(user_id="user_test", store=store)
        await profile2.load()
        assert profile2.preferences["explanation_style"] == "mathematical"
        assert profile2.preferences["depth"] == "deep"
        assert "linear_algebra" in profile2.topics_mastered
        assert profile2.total_sessions == 1
        assert profile2.learning_streak == 1
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/unit/harness/test_user_profile.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 创建 UserProfile 实现**

```python
# app/harness/user_profile.py
from dataclasses import dataclass, field

from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


DEFAULT_PREFERENCES = {
    "explanation_style": "verbal",    # visual | verbal | mathematical
    "pace": "normal",                 # slow | normal | fast
    "depth": "standard",              # shallow | standard | deep
}


@dataclass
class UserProfile:
    """用户级偏好与进度（§6 L3 画像记忆）。

    与 MasteryGraph 并列构成 L3 画像记忆。MasteryGraph 关注知识点掌握度 +
    前置依赖推理；UserProfile 关注学习偏好、进度、活跃主题。
    """

    user_id: str
    store: MasteryGraphStore
    preferences: dict = field(default_factory=lambda: dict(DEFAULT_PREFERENCES))
    topics_active: list[str] = field(default_factory=list)
    topics_mastered: list[str] = field(default_factory=list)
    learning_streak: int = 0
    total_sessions: int = 0

    def update_preferences(self, **kwargs) -> None:
        """合并更新偏好，传入的键覆盖默认值。"""
        for key in ("explanation_style", "pace", "depth"):
            if key in kwargs and kwargs[key] is not None:
                self.preferences[key] = kwargs[key]

    def sync_from_mastery(self, mastery_snapshot: dict[str, float],
                          mastered_threshold: float = 0.8) -> None:
        """从 MasteryGraph 同步 mastered topics 列表。"""
        self.topics_mastered = sorted(
            tid for tid, m in mastery_snapshot.items() if m >= mastered_threshold
        )

    def increment_session(self) -> None:
        """新会话开始时调用，自增会话计数和连续学习天数。"""
        self.total_sessions += 1
        self.learning_streak += 1  # 简化实现：每次 +1（精确 streak 需日期计算，后续迭代）

    # ---- 持久化 ----

    async def save(self) -> None:
        await self.store.save_profile(self.user_id, {
            "preferences": self.preferences,
            "topics_active": self.topics_active,
            "topics_mastered": self.topics_mastered,
            "learning_streak": self.learning_streak,
            "total_sessions": self.total_sessions,
        })

    async def load(self) -> None:
        data = await self.store.load_profile(self.user_id)
        if data is None:
            return  # 新用户，保留默认值
        self.preferences = data.get("preferences", dict(DEFAULT_PREFERENCES))
        self.topics_active = data.get("topics_active", [])
        self.topics_mastered = data.get("topics_mastered", [])
        self.learning_streak = data.get("learning_streak", 0)
        self.total_sessions = data.get("total_sessions", 0)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/unit/harness/test_user_profile.py -v`
Expected: 5 PASSED

- [ ] **Step 5: 提交**

```bash
git add app/harness/user_profile.py tests/unit/harness/test_user_profile.py
git commit -m "feat(plan-b): add UserProfile model with preferences, mastery sync, persist"
```

---
---

### Task 4: Curator Agent 实现

**Files:**
- Create: `app/agents/curator.py`
- Create: `tests/unit/agents/test_curator.py`

- [ ] **Step 1: 写 Curator 单元测试（MasteryAssessed 触发 — 更新节点 + 发 GraphNodeStrengthened/ProfileUpdated + observed 弱前置检测）**

```python
# tests/unit/agents/test_curator.py
import asyncio
import tempfile
import os
import time

import pytest不具备

from app.agents.curator import Curator
from app.harness.events import Event, check_ownership
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState
from app.harness.mastery_graph import MasteryGraph, EdgeType, EdgeSource
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


async def _setup_curator(user_id: str = "user_1",
                         session_id: str = "s1",
                         current_topic: str = "attention") -> tuple[Curator, WorkspaceState, MasteryGraphStore, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MasteryGraphStore(db_path=path)
    await store.init()
    graph = MasteryGraph(user_id=user_id, store=store)
    curator = Curator(graph=graph, store=store)
    ws = WorkspaceState(
        session_id=session_id, user_id=user_id, current_topic=current_topic)
    return curator, ws, store, path


# ---- 声明契约 ----

def test_curator_source():
    assert Curator.source == EventSource.CURATOR


def test_curator_subscriptions():
    assert EventType.MASTERY_ASSESSED in Curator.subscriptions
    assert EventType.TOPIC_ENTERED in Curator.subscriptions


def test_curator_emittable_types():
    assert Curator.emittable_types == {
        EventType.PROFILE_UPDATED,
        EventType.GRAPH_NODE_STRENGTHENED,
        EventType.GRAPH_PREREQ_WEAK_DETECTED,
    }


# ---- MasteryAssessed 触发 ----

def test_handle_mastery_assessed_updates_node():
    async def _test():
        curator, ws, store, path = await _setup_curator()
        curator.graph.add_node("attention", "注意力机制", mastery=0.3)

        event = Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                      session_id="s1", payload={
                          "topic_id": "attention",
                          "level": "partial",
                          "score": 0.65,
                      })
        results = curator.handle(event, ws)
        # 图谱节点已更新
        node = curator.graph.get_node("attention")
        assert node is not None
        assert node.mastery == 0.65
        assert node.practice_count == 1
        assert node.last_practiced_at > 0

        # 应发出 GraphNodeStrengthened 事件
        strengthened = [e for e in results if e.type == EventType.GRAPH_NODE_STRENGTHENED]
        assert len(strengthened) == 1elm
        assert strengthened[0].payload["topic_id"] == "attention"
        assert strengthened[0].payload["mastery"] == 0.65

        # 应发出 ProfileUpdated
        profile_updates = [e for e in results if e.type == EventType.PROFILE_UPDATED]
        assert len(profile_updates) == 1

        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_handle_mastery_assessed_with_weak_prereq_emits_observed():
    async def _test():
        curator, ws, store, path = await _setup_curator(current_topic="transformer")
        # 建图：线性代数 (mastery=0. Planting2) → 注意力 → transformer
        curator.graph.add_node("linear_algebra", "线性代数", mastery=0.2)
        curator.graph.add_node("attention", "注意力机制", mastery=0.7)
        curator.graph.add_node("transformer", "Transformer架构", mastery=0.3)
        curator.graph.add_doc_order_edge(from_topic="linear_algebra", to_topic="transformer")
        curator.graph.add_doc_order_edge(from_topic="attention", to_topic="transformer")

        event = Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                      session_id="s1", payload={
                          "topic_id": "transformer",
                          "level": "weak",
                          "score": 0.3,
                      })
        results = curator.handle(event, ws)

        # 应发出 GraphPrereqWeakDetected(basis=observed)
        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) >= 1
        # 线性代数是弱的 — adjusted=0.5/1.25=0.4, mastery 0.2 < 0.4 → 触发
        prereq_ids = [e.payload["prereq_topic_id"] for e in prereq_events]
        assert "linear_algebra" in prereq_ids
        # 注意力不弱 — mastery 0.7 > adjusted 0.4 → 不触发
        assert "attention" not in prereq_ids
        # basis 应为 observed
        for e in prereq_events:
            assert e.payload["basis"] == "observed"

        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_handle_mastery_assessed_no_prereqs_no_prereq_event():
    async def _test():
        curator, ws, store, path = await _setup_curator()
        # 只有一个节点，没有边 → 不能发 GraphPrereqWeakDetected
        curator.graph.add_node("attention", "注意力机制", mastery=0.3)

        event = Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                      session_id="s1", payload={
                          "topic_id": "attention",
                          "level": "weak",
                          "score": 0.orra3,
                      })
        results = curator.handle(event, ws)


        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) == 0  # 没有 PREREQ 边，不发

        await store.close()
        os.unlink(path)
    asyncio.run(_test())


# ---- TopicEntered 触发 — 渐进启用 ----

def test_handle_topic_entered_cold_start_no_historical_signal():
    """冷启动：画像为空 → historical 分支不触发（渐进启用）。"""
    async def _test():
        curator, ws, store, path = await _setup_curator(current_topic="attention")
        # 冷启动：图谱为空，没有边和前置节点
        curator.graph.add_node("attention", "注意力机制", mastery=0.0)

        event = Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                      session_id="s1", payload={"topic_id": "attention"})
        results = curator.handle(event, ws)

        # 冷启动下不应发 GraphPrereqWeakDetected
        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) == 0elmoggle

        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_handle_topic_entered_with_historical_weak_prereq():
    """画像有数据：前置节点 mastery 低 → 发 basis=historical。"""
    async def _test():
        curator, ws, store, path = await _setup_curator(current_topic="transformer")
        # 画像有数据：线性代数 mastery=0.2（弱）
        curator.graph.add_node("linear_algebra", "线性代数", mastery=0.2)
        curator.graph.add_node("attention", "注意力机制", mastery=0.9)
        curator.graph.add_node("transformer", "Transformer架构")
        curator.graph.add_doc_order_edge(from_topic="linear_algebra", to_topic="transformer")
        curator.graph.add_doc_order_edge(from_topic="attention", to_topic="transformer")

        event = Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                      session_id="s1", payload={"topic_id": "transformer"})
        results = curator.handle(event, ws)

        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) >= 1
        for e in prereq_events:
            assert e.payload["basis"] == "historical"
        # 线性代数是弱前置
        prereq_ids = [e.payload["prereq_topic_id"] for e in prereq_events]
        assert "linear_algebra" in prereq_ids
        # 注意力 mastery 0.9 → 不弱
        assert "attention" not in prereq_ids

        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_handle_topic_entered_with_no_weak_prereq_emits_nothing():
    """画像显示所有前置都强 → 不发事件。"""
    async def _test():
        curator, ws, store, path = await _setup_curator(current_topic="transformer")
        curator.graph.add_node("linear_algebra", "线性代数", mastery=0.9)
        curator.graph.add_node("attention", "注意力机制", mastery=0.95)
        curator.graph.add_node("transformer", "Transformer架构")
        curator.graph.add_doc_order_edge(from_topic="linear_algebra", to_topic="transformer")
        curator.graph.add_doc_order_edge(from_topic="attention", to_topic="transformer")

        event = Event(type=EventType.TOPIC_ENTERED, source=EventSource.ORCHESTRATOR,
                      session_id="s1", payload={"topic_id": "transformer"})
        results = curator.handle(event, ws)

        prereq_events = [e for e in results if e.type == EventType.GRAPH_PREREQ_WEAK_DETECTED]
        assert len(prereq_events) == 0

        await store.close()
        os.unlink(path)
    asyncio.run(_test())


# ---- 事件所有权 ----

def test_curator_events_pass_ownership():
    curator = Curator.__new__(Curator)  # 不调用 __init__，只测试 emit
    curator.source = EventSource.CURATOR
    curator.emittable_types = Curator.emittable_types
    ws = WorkspaceState(session_id="s1", user_id="u1")

    for etype in (EventType.PROFILE_UPDATED, EventType.GRAPH_NODE_STRENGTHENED,
                  EventType.GRAPH_PREREQ_WEAK_DETECTED):
        ev = curator.emit(etype, wsKS)
        check_ownership(ev)  # 不抛错 = 白名单校验通过


def test_curator_cannot_emit_critic_event():
    curator = Curator.__new__(Curator)
    curator.source = EventSource.CURATOR
    curator.emittable_types = Curator.emittable_types
    ws = WorkspaceState(session_id="s1", user_id="u1")

    with pytest.raises(ValueError):
        curator.emit(EventType.CONFUSION_DETECTED, ws)  # Curator 不能发 Critic 的事件


# ---- evaluate 接口 ----

def test_curator_evaluate_returns_metrics():
    async def _test():
        curator, ws, store, path = await _setup_curator()
        curator.graph.add_node("A", "前置A", mastery=0.8)
        curator.graph.add_node("B", "主题B", mastery=0.5)
        curator.graph.add_doc_order_edge(from_topic="A", to_topic="B")

        metrics = curator.evaluate({
            "graph_nodes": {"A": 0.8, "B": 0.5},
            "graph_edges": [{"from": "A", "to": "B"}],
        })
        assert isinstance(metrics, dict)
        assert "coverage" in metrics
        assert metrics["coverage"] == 1.0  # 所有 expected 节点都存在
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_curator_evaluate_partial_coverage():
    async def _test():
        curator, ws, store, path = await _setup_curator()
        curator.graph.add_node("A", "前置A", mastery=0.8)

        metrics = curator.evaluate({
            "graph_nodes": {"A": 0.8, "B": 0.5},  # 需要 2 个节点
            "graph_edges": [],
        })
        assert isinstance(metrics, dict)
        # 只有 1/2 节点存在
        assert metrics["coverage"] == 0.5
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/unit/agents/test_curator.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 创建 Curator Agent 实现**

```python
# app/agents/curator.py
import time

from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState
from app.harness.mastery_graph import MasteryGraph
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


class Curator(AgentBase):
    """维护用户画像与掌握点知识图谱（§2.1 Curator 行）。

    事件契约：
    - source = curator
    - subscriptions = [MasteryAssessed, TopicEntered]
    - emittable_types = {ProfileUpdated, GraphNodeStrengthened, GraphPrereqWeakDetected}
    - 只判结构层：基于图谱 PREREQ 边 + 用户前置节点掌握度判"前置薄弱"
    - 绝不判文本语义（那归 Critic）

    双时机：
    - TopicEntered → 基于历史画像发 GraphPrereqWeakDetected(basis=historical)
    - MasteryAssessed → 基于实测发 basis=observed
    - historical 分支为渐进启用：冷启动（图谱无边或前置无 mastery 数据）时不触发
    """

    source = EventSource.CURATOR
    subscriptions = [EventType.MASTERY_ASSESSED, EventType.TOPIC_ENTERED]
    emittable_types = {
        EventType.PROFILE_UPDATED,
        EventType.GRAPH_NODE_STRENGTHENED,
        EventType.GRAPH_PREREQ_WEAK_DETECTED,
    }

    def __init__(self, graph: MasteryGraph, store: MasteryGraphStore):
        self.graph = graph
        self._store = store

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """分发订阅事件到对应处理器。"""
        if event.type == EventType.MASTERY_ASSESSED:
            return self._on_mastery_assessed(event, ws)
        elif event.type == EventType.TOPIC_ENTERED:
            return self._on_topic_entered(event, ws, event.payload.get("force_check", False))
        return []

    # ---- MasteryAssessed → basis=observed ----

    def _on_mastery_assessed(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """回合中：更新图谱掌握度 + 检查前置薄弱（observed）。

        1. 更新当前 topic 的 mastery
        2. emit GraphNodeStrengthened + ProfileUpdated
        3. 检查 ws.current_topic 的前置 → 若弱 emit GraphPrereqWeakDetected(observed)
        """
        results = []
        payload = event.payload
        topic_id = payload.get("topic_id") or ws.current_topic
        score = payload.get("score", 0.0)
        level = payload.get("level", "partial")

        # 确保节点存在
        if self.graph.get_node(topic_id) is None:
            self.graph.add_node(topic_id, topic_id, mastery=0.0)

        # 更新掌握度
        old_mastery = self.graph.get_node(topic_id).mastery
        self.graph.update_mastery(topic_id, score)

        # emit GraphNodeStrengthened
        results.append(self.emit(
            EventType.GRAPH_NODE_STRENGTHENED, ws,
            payload={
                "topic_id": topic_id,
                "mastery": score,
                "previous_mastery": old_mastery,
                "level": level,
                "practice_count": self.graph.get_node(topic_id).practice_count,
            },
            parent_id=event.id,
        ))

        # emit ProfileUpdated
        results.append(self.emit(
            EventType.PROFILE_UPDATED, ws,
            payload={
                "action": "node_updated",
                "topic_id": topic_id,
                "mastery": score,
            },
            parent_id=event.id,
        ))

        # 检查前置薄弱（observed）
        current_topic = ws.current_topic or topic_id
        if self.graph.has_any_prereqs(current_topic):
            weak_prereqs = self.graph.find_weak_prereqs(current_topic)
            for wp in weak_prereqs:
                results.append(self.emit(
                    EventType.GRAPH_PREREQ_WEAK_DETECTED, ws,
                    payload={
                        "topic_id": current_topic,
                        "prereq_topic_id": wp["prereq_topic_id"],
                        "prereq_name": wp["prereq_name"],
                        "prereq_mastery": wp["mastery"],
                        "edge_confidence": wp["edge_confidence"],
                        "adjusted_threshold": wp["adjusted_threshold"],
                        "edge_source": wp["edge_source"],
                        "basis": "observed",
                    },
                    parent_id=event.id,
                ))

        return results

    # ---- TopicEntered → basis=historical（渐进启用）----

    def _on_topic_entered(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """开局/切主题：基于历史画像检查前置。

        渐进启用：图谱中无 PREREQ 边 / 所有前置节点无 mastery 数据时，不触发。
        """
        results = []
        topic_id = event.payload.get("topic_id") or ws.current_topic
        if not topic_id:
            return results

        # 确保当前 topic 节点存在
        if self.graph.get_node(topic_id) is None:
            self.graph.add_node(topic_id, topic_id, mastery=0.0)

        # 渐进启用门槛：必须有 PREREQ 边 + 至少一个前置节点有 mastery 数据
        if not self.graph.has_any_prereqs(topic_id):
            return results  # 冷启动：无边可查，不发
        prereqs_have_mastery = any(
            self.graph.get_node(e.from_topic) is not None
            for e in self.graph.edges
            if e.to_topic == topic_id and e.type == EdgeType.PREREQ
        )
        if not prereqs_have_mastery:
            return results  # 冷启动：有边但前置节点无数据，不发

        weak_prereqs = self.graph.find_weak_prereqs(topic_id)
        for wp in weak_prereqs:
            results.append(self.emit(
                EventType.GRAPH_PREREQ_WEAK_DETECTED, ws,
                payload={
                    "topic_id": topic_id,
                    "prereq_topic_id": wp["prereq_topic_id"],
                    "prereq_name": wp["prereq_name"],
                    "prereq_mastery": wp["mastery"],
                    "edge_confidence": wp["edge_confidence"],
                    "adjusted_threshold": wp["adjusted_threshold"],
                    "edge_source": wp["edge_source"],
                    "basis": "historical",
                },
                parent_id=event.id,
            ))

        return results

    # ---- evaluate（§5.2）----

    def evaluate(self, test_case: dict) -> dict:
        """部件级评估接口。

        test_case 格式：
          {"graph_nodes": {topic_id: expected_mastery, ...},
           "graph_edges": [{from, to}, ...]}

        返回：
          {"coverage": 0.0-1.0,   # 要求节点在图谱中的比例
           ...}
        """
        expected_nodes = test_case.get("graph_nodes", {})
        if not expected_nodes:
            return {"coverage":  zon0.0, "note": "no expected nodes specified"}

        found = sum(1 for tid in expected_nodes if self.graph.get_node(tid) is not None)
        coverage = found / len(expected_nodes)

        return {
            "coverage": round(coverage, 4),
            "total_nodes_in_graph": len(self.graph.nodes),
            "total_edges_in_graph": len(self.graph.edges),
            "matched_nodes": found,
            "expected_nodes": len(expected_nodes),
        }
```

需要在 `_on_topic_entered` 中 import `EdgeType`：

```python
# 文件顶部加入：
from app.harness.mastery_graph import MasteryGraph, EdgeType
```

同时需要在 curator.py 文件顶部加入：

```python
from app.harness.mastery_graph import MasteryGraph, EdgeType
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/unit/agents/test_curator.py::test_curator_source tests/unit/agents/test_curator.py::test_curator_subscriptions tests/unit/agents/test_curator.py::test_curator_emittable_types tests/unit/agents/test_curator.py::test_curator_events_pass_ownership tests/unit/agents/test_curator.py::test_curator_cannot_emit_critic_event -v`
Expected: 5 PASSED（声明契约测试先通过）

Run: `pytest tests/unit/agents/test_curator.py -v`
Expected: 13 PASSED

- [ ] **Step 5: 提交**

```bash
git add app/agents/curator.py tests/unit/agents/test_curator.py
git commit -m "feat(plan-b): add Curator agent with dual-trigger (MasteryAssessed/TopicEntered) + evaluate"
```

---
---

### Task 5: 集成验证 — 全链路 pytest + spec 场景确认

**Files:**
- Modify: 无需新增文件，运行已有全部测试

- [ ] **Step 1: 运行 Plan B 全部单测**

Run: `pytest tests/unit/infrastructure/test_mastery_graph_store.py tests/unit/harness/test_mastery_graph.py tests/unit/harness/test_user_profile.py tests/unit/agents/test_curator.py -v`
Expected: 33 PASSED（4 store + 10 graph + 5 profile + 13 curator = 32... 算上 store init 那 1 个 + CRUD 4 个 = 5 store, 10 graph, 5 profile, ~13 curator ≈ 33）

- [ ] **Step 2: 运行全量 pytest（确保不破坏基线）**

Run: `pytest tests/ -q`
Expected: 基线测试数不减（原 ~N 个 test），Plan B 新增 32 个 test，总计 ~(N+32) PASSED

- [ ] **Step 3: 手动验证 spec §5.3 "前置薄弱触发回退"场景 — 图谱侧可发 GraphPrereqWeakDetected**

写一段简单验证脚本（在 Python REPL 或单独脚本）：加载用户图谱（线性代数 weak），切到 transformer 主题，Curator 处理 TopicEntered → 发 `GraphPrereqWeakDetected(basis=historical)`；或处理 `MasteryAssessed` → 发 `basis=observed`。

验证方式：`pytest tests/unit/agents/test_curator.py::test_handle_mastery_assessed_with_weak_prereq_emits_observed -v` 和 `test_handle_topic_entered_with_historical_weak_prereq` 已经覆盖此场景。确认这两个测试 PASS。

- [ ] **Step 4: 提交**

```bash
git add .
git commit -m "feat(plan-b): final integration — all 32 Plan B tests green, baseline preserved"
```

---
---

## 验收 Checklist

对照 spec 验收标准逐项确认：

| # | 验收项 | 对应测试 |
|---|--------|---------|
| 1 | Curator source=curator, subscriptions=[MasteryAssessed, TopicEntered] | `test_curator_source`, `test_curator_subscriptions` |
| 2 | Curator emittable_types = {ProfileUpdated, GraphNodeStrengthened, GraphPrereqWeakDetected} | `test_curator_emittable_types` |
| 3 | Curator 只判结构层（不碰文本语义） | `test_curator_cannot_emit_critic_event`（越权拦截） |
| 4 | MasteryAssessed → 更新 node + emit GraphNodeStrengthened + ProfileUpdated | `test_handle_mastery_assessed_updates_node` |
| 5 | MasteryAssessed → 检测前置薄弱 → emit GraphPrereqWeakDetected(basis=observed) | `test_handle_mastery_assessed_with_weak_prereq_emits_observed` |
| 6 | TopicEntered → historical 冷启动渐进启用（画像空时不触发） | `test_handle_topic_entered_cold_start_no_historical_signal` |
| 7 | TopicEntered → 有前置弱 → emit GraphPrereqWeakDetected(basis=historical) | `test_handle_topic_entered_with_historical_weak_prereq` |
| 8 | 冷启动建图三来源 + 置信度加权 (DOC_ORDER=0.5, LLM_INFER=0.3, INTERACTION=0.8) | `test_find_weak_prereqs_llm_infer_edge_stricter`, `test_find_weak_prereqs_interaction_edge_lenient` |
| 9 | evaluate(test_case) 可返回 coverage 指标 | `test_curator_evaluate_returns_metrics`, `test_curator_evaluate_partial_coverage` |
| 10 | spec §5.3 "前置薄弱触发回退"图谱侧可发 GraphPrereqWeakDetected | `test_handle_mastery_assessed_with_weak_prereq_emits_observed` |
| 11 | 不改 Plan 0 接口、memory.py、app/agent/ 老代码 | 代码审查确认：所有新文件在 `app/agents/curator.py`, `app/harness/{mastery_graph,user_profile}.py`, `app/infrastructure/storage/mastery_graph_store.py` |
| 12 | 持久化往返正确 | `test_graph_persist_roundtrip`, `test_profile_persist_roundtrip` |

---
---

## 预估统计

| 类别 | 数量 |
|------|------|
| 新建源文件 | 4（mastery_graph.py, user_profile.py, curator.py, mastery_graph_store.py） |
| 新建测试文件 | 4（对应 4 个 test_*.py） |
| 新增 test 函数 | 31-33 |
| Git commits | 6（TDD 每 Task 提交） |
| 修改冻结接口 | 0（严格遵守） |
| 触碰老 app/agent/ | 0（严格遵守） |
| 触碰 memory.py | 0（严格遵守） |