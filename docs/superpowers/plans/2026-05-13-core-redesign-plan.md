# 核心模块重写实施计划（可观测 + 记忆 + LLM）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写 Observability / Memory / LLM 三个核心模块，从 stub 升级到生产就绪。

**Architecture:** 三阶段顺序执行（可观测→记忆→LLM），每阶段 TDD 驱动，阶段末全量回归测试。可观测为基础设施最先落地，记忆依赖 LLM 做摘要压缩，LLM 依赖可观测做追踪。

**Tech Stack:** Python 3.12 / Langfuse SDK / SQLite (aiosqlite + FTS5) / LangChain OpenAI / pytest

**Design Specs:**
- `docs/designs/2026-05-13-observability-redesign.md`
- `docs/designs/2026-05-13-memory-redesign.md`
- `docs/designs/2026-05-13-llm-redesign.md`

---

## File Structure

```
Phase 1 — Observability
  Rewrite: app/harness/observability.py
  Modify:  app/agent/node_wrapper.py
  Test:    tests/unit/harness/test_observability.py

Phase 2 — Memory
  Rewrite: app/harness/memory.py
  Modify:  app/harness/enums.py (add EPISODE)
  Rewrite: app/harness/state/memory.py
  Create:  app/infrastructure/storage/memory_store.py
  Test:    tests/unit/harness/test_memory.py
  Test:    tests/unit/infrastructure/test_memory_store.py

Phase 3 — LLM
  Rewrite: app/infrastructure/llm.py
  Modify:  app/agent/nodes/diagnose.py
  Modify:  app/agent/nodes/explain.py
  Modify:  app/agent/nodes/followup.py
  Modify:  app/agent/nodes/restate_check.py
  Modify:  app/agent/nodes/evaluate.py
  Modify:  app/agent/nodes/summarize.py
  Modify:  app/agent/nodes/answer_policy.py
  Test:    tests/unit/infrastructure/test_llm.py
```

---

## Phase 1: Observability System

### Task 1: Data Models — LLMSpan & SessionStats

**Files:**
- Rewrite: `app/harness/observability.py`
- Test: `tests/unit/harness/test_observability.py`

- [ ] **Step 1: Write failing tests for LLMSpan and SessionStats**

```python
# tests/unit/harness/test_observability.py

from app.harness.observability import LLMSpan, SessionStats


def test_llm_span_defaults():
    span = LLMSpan(model="gpt-4o-mini")
    assert span.model == "gpt-4o-mini"
    assert span.prompt_tokens == 0
    assert span.completion_tokens == 0
    assert span.total_tokens == 0
    assert span.latency_ms == 0.0
    assert span.cost_usd == 0.0
    assert span.metadata == {}


def test_session_stats_add_span():
    stats = SessionStats(session_id="s1")
    span = LLMSpan(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        latency_ms=200.0,
        cost_usd=0.0001,
        node="diagnose",
    )
    stats.add_span(span)
    assert stats.total_prompt_tokens == 100
    assert stats.total_completion_tokens == 50
    assert stats.total_tokens == 150
    assert stats.total_cost_usd == 0.0001
    assert stats.total_llm_calls == 1
    assert "diagnose" in stats.node_latencies
    assert stats.node_latencies["diagnose"] == [200.0]


def test_session_stats_multiple_spans():
    stats = SessionStats(session_id="s1")
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=100, node="a", latency_ms=100.0))
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=200, node="a", latency_ms=200.0))
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=50, node="b", latency_ms=50.0))
    assert stats.total_tokens == 350
    assert stats.total_llm_calls == 3
    assert stats.node_latencies["a"] == [100.0, 200.0]
    assert stats.node_latencies["b"] == [50.0]


def test_session_stats_summary():
    stats = SessionStats(session_id="s1")
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=100, cost_usd=0.01, node="x", latency_ms=100.0))
    stats.add_span(LLMSpan(model="gpt-4o", total_tokens=200, cost_usd=0.02, node="x", latency_ms=200.0))
    s = stats.summary()
    assert s["session_id"] == "s1"
    assert s["total_tokens"] == 300
    assert s["total_cost_usd"] == 0.03
    assert s["total_llm_calls"] == 2
    assert s["avg_node_latency_ms"]["x"] == 150.0


def test_session_stats_empty():
    stats = SessionStats(session_id="s1")
    s = stats.summary()
    assert s["total_tokens"] == 0
    assert s["total_llm_calls"] == 0
    assert s["avg_node_latency_ms"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/harness/test_observability.py -v`
Expected: FAIL — cannot import `LLMSpan` from `observability`

- [ ] **Step 3: Write implementation**

```python
# app/harness/observability.py

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

logger = logging.getLogger("learning_agent")


@dataclass
class LLMSpan:
    """单次 LLM 调用追踪数据"""
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    node: str = ""
    intent: str = ""
    session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionStats:
    """会话级汇总统计"""
    session_id: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_llm_calls: int = 0
    node_latencies: dict[str, list[float]] = field(default_factory=dict)

    def add_span(self, span: LLMSpan):
        self.total_prompt_tokens += span.prompt_tokens
        self.total_completion_tokens += span.completion_tokens
        self.total_tokens += span.total_tokens
        self.total_cost_usd += span.cost_usd
        self.total_llm_calls += 1
        node = span.node or "unknown"
        self.node_latencies.setdefault(node, []).append(span.latency_ms)

    def summary(self) -> dict:
        avg_latencies = {
            k: sum(v) / len(v) for k, v in self.node_latencies.items()
        }
        return {
            "session_id": self.session_id,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_llm_calls": self.total_llm_calls,
            "avg_node_latency_ms": avg_latencies,
        }


class Observability(ABC):
    """可观测性协议 — 所有实现必须满足"""

    @abstractmethod
    def start_trace(self, session_id: str, metadata: dict | None = None) -> str: ...

    @abstractmethod
    def end_trace(self, trace_id: str) -> None: ...

    @abstractmethod
    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None) -> None: ...

    @abstractmethod
    def llm_span(self, span: LLMSpan) -> None: ...

    @abstractmethod
    def metric(self, name: str, value: float, tags: dict | None = None) -> None: ...

    @abstractmethod
    def log(self, level: str, event: str, context: dict | None = None) -> None: ...

    @abstractmethod
    def session_summary(self, session_id: str) -> SessionStats | None: ...


class ConsoleObservability(Observability):
    """开发调试实现：结构化日志输出到 stdout"""

    def __init__(self):
        self._sessions: dict[str, SessionStats] = {}

    def start_trace(self, session_id: str, metadata: dict | None = None) -> str:
        import uuid
        trace_id = str(uuid.uuid4())
        self._sessions[session_id] = SessionStats(session_id=session_id)
        self._print("TRACE_START", session_id=session_id, metadata=metadata)
        return trace_id

    def end_trace(self, trace_id: str) -> None:
        self._print("TRACE_END", trace_id=trace_id)

    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None) -> None:
        self._print("SPAN", session_id=session_id, node=node, event=event, data=data)

    def llm_span(self, span: LLMSpan) -> None:
        self._print("LLM", model=span.model, tokens=span.total_tokens,
                    cost=span.cost_usd, latency_ms=span.latency_ms, node=span.node)
        stats = self._sessions.get(span.session_id)
        if stats:
            stats.add_span(span)

    def metric(self, name: str, value: float, tags: dict | None = None) -> None:
        self._print("METRIC", name=name, value=value, tags=tags)

    def log(self, level: str, event: str, context: dict | None = None) -> None:
        self._print(level.upper(), event=event, context=context)

    def session_summary(self, session_id: str) -> SessionStats | None:
        return self._sessions.get(session_id)

    def _print(self, tag: str, **kwargs):
        print(f"[{tag}] {json.dumps(kwargs, ensure_ascii=False, default=str)}")


class FakeObservability(Observability):
    """测试实现：记录所有调用，支持断言"""

    def __init__(self):
        self.calls: list[dict] = []
        self._sessions: dict[str, SessionStats] = {}

    def start_trace(self, session_id: str, metadata: dict | None = None) -> str:
        self.calls.append({"method": "start_trace", "session_id": session_id, "metadata": metadata})
        self._sessions[session_id] = SessionStats(session_id=session_id)
        return "fake-trace-id"

    def end_trace(self, trace_id: str) -> None:
        self.calls.append({"method": "end_trace", "trace_id": trace_id})

    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None) -> None:
        self.calls.append({"method": "trace", "session_id": session_id,
                           "node": node, "event": event, "data": data})

    def llm_span(self, span: LLMSpan) -> None:
        self.calls.append({"method": "llm_span", "span": span})
        stats = self._sessions.get(span.session_id)
        if stats:
            stats.add_span(span)

    def metric(self, name: str, value: float, tags: dict | None = None) -> None:
        self.calls.append({"method": "metric", "name": name, "value": value, "tags": tags})

    def log(self, level: str, event: str, context: dict | None = None) -> None:
        self.calls.append({"method": "log", "level": level, "event": event, "context": context})

    def session_summary(self, session_id: str) -> SessionStats | None:
        return self._sessions.get(session_id)

    def assert_traced(self, method: str, **kwargs):
        for call in self.calls:
            if call["method"] == method:
                if all(call.get(k) == v for k, v in kwargs.items()):
                    return
        raise AssertionError(f"未找到调用: {method} {kwargs}")


def get_observability() -> Observability:
    """根据环境变量自动选择实现"""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    if public_key and secret_key:
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        from langfuse import Langfuse
        client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        return _LangfuseObservability(client)
    return ConsoleObservability()


class _LangfuseObservability(Observability):
    """生产实现：通过 Langfuse SDK 写入追踪数据"""

    def __init__(self, client):
        self._client = client
        self._traces: dict[str, Any] = {}
        self._sessions: dict[str, SessionStats] = {}

    def start_trace(self, session_id: str, metadata: dict | None = None) -> str:
        trace = self._client.trace(
            name=f"session_{session_id}",
            session_id=session_id,
            metadata=metadata or {},
        )
        self._traces[session_id] = trace
        self._sessions[session_id] = SessionStats(session_id=session_id)
        return trace.id

    def end_trace(self, trace_id: str) -> None:
        pass

    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None) -> None:
        trace_obj = self._traces.get(session_id)
        if trace_obj:
            trace_obj.span(name=f"{node}.{event}", metadata=data or {})

    def llm_span(self, span: LLMSpan) -> None:
        trace_obj = self._traces.get(span.session_id)
        if trace_obj:
            trace_obj.generation(
                name=f"llm.{span.node}",
                model=span.model,
                metadata={
                    "intent": span.intent,
                    "prompt_tokens": span.prompt_tokens,
                    "completion_tokens": span.completion_tokens,
                    "total_tokens": span.total_tokens,
                    "latency_ms": span.latency_ms,
                    "cost_usd": span.cost_usd,
                    **span.metadata,
                },
            )
        stats = self._sessions.get(span.session_id)
        if stats:
            stats.add_span(span)

    def metric(self, name: str, value: float, tags: dict | None = None) -> None:
        pass

    def log(self, level: str, event: str, context: dict | None = None) -> None:
        log_fn = getattr(logger, level, logger.info)
        log_fn(json.dumps({"event": event, **(context or {})}))

    def session_summary(self, session_id: str) -> SessionStats | None:
        return self._sessions.get(session_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/harness/test_observability.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add app/harness/observability.py tests/unit/harness/test_observability.py
git commit -m "feat: rewrite observability with LLMSpan, SessionStats, ABC + 3 implementations"
```

---

### Task 2: FakeObservability Tests

**Files:**
- Test: `tests/unit/harness/test_observability.py` (append)

- [ ] **Step 1: Write failing tests for FakeObservability**

```python
# tests/unit/harness/test_observability.py (append)

from app.harness.observability import FakeObservability


def test_fake_obs_trace_records():
    obs = FakeObservability()
    obs.trace("s1", "diagnose", "start", {"key": "val"})
    obs.assert_traced("trace", node="diagnose", event="start")
    assert len(obs.calls) == 1


def test_fake_obs_llm_span_records():
    obs = FakeObservability()
    span = LLMSpan(model="gpt-4o", node="diagnose", session_id="s1")
    obs.llm_span(span)
    obs.assert_traced("llm_span")
    assert obs.calls[0]["span"].model == "gpt-4o"


def test_fake_obs_start_end_trace():
    obs = FakeObservability()
    tid = obs.start_trace("s1")
    assert tid == "fake-trace-id"
    obs.end_trace(tid)
    assert len(obs.calls) == 2
    assert obs.calls[0]["method"] == "start_trace"
    assert obs.calls[1]["method"] == "end_trace"


def test_fake_obs_session_summary():
    obs = FakeObservability()
    obs.start_trace("s1")
    obs.llm_span(LLMSpan(model="gpt-4o", total_tokens=100, session_id="s1"))
    stats = obs.session_summary("s1")
    assert stats is not None
    assert stats.total_tokens == 100


def test_fake_obs_session_summary_missing():
    obs = FakeObservability()
    assert obs.session_summary("nonexistent") is None


def test_fake_obs_assert_traced_failure():
    obs = FakeObservability()
    obs.trace("s1", "diagnose", "start")
    import pytest
    with pytest.raises(AssertionError, match="未找到调用"):
        obs.assert_traced("trace", node="nonexistent")


def test_fake_obs_metric_and_log():
    obs = FakeObservability()
    obs.metric("latency", 100.0, {"node": "x"})
    obs.log("info", "something_happened", {"detail": "test"})
    assert obs.calls[0]["method"] == "metric"
    assert obs.calls[1]["method"] == "log"
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/harness/test_observability.py -v`
Expected: 12 PASS (5 from Task 1 + 7 new)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/harness/test_observability.py
git commit -m "test: add FakeObservability coverage (7 tests)"
```

---

### Task 3: get_observability Factory Tests

**Files:**
- Test: `tests/unit/harness/test_observability.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/harness/test_observability.py (append)

from app.harness.observability import get_observability, ConsoleObservability


def test_factory_returns_console_by_default(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    obs = get_observability()
    assert isinstance(obs, ConsoleObservability)


def test_factory_returns_console_with_empty_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    obs = get_observability()
    assert isinstance(obs, ConsoleObservability)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/harness/test_observability.py -v`
Expected: 14 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/harness/test_observability.py
git commit -m "test: add factory function tests for get_observability"
```

---

### Task 4: Phase 1 Regression

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All existing tests pass (node_wrapper still calls `get_observability()` which returns ConsoleObservability — interface compatible)

- [ ] **Step 2: Fix any breakage if found**

Common issue: existing `test_get_observability_singleton` expects same instance returned. The new factory creates new instances each call. Update that test:

```python
# tests/unit/harness/test_observability.py — remove test_get_observability_singleton
# or update it to test ConsoleObservability interface
```

The old test file is fully replaced by Tasks 1-3, so no conflict.

---

## Phase 2: Memory System

### Task 5: MemoryScope Enum Extension

**Files:**
- Modify: `app/harness/enums.py`
- Test: `tests/unit/harness/test_enums.py` (append)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/harness/test_enums.py (append)

def test_episode_scope_exists():
    from app.harness.enums import MemoryScope
    assert hasattr(MemoryScope, "EPISODE")
    assert MemoryScope.EPISODE == "episode"


def test_memory_scope_has_5_values():
    from app.harness.enums import MemoryScope
    assert len(MemoryScope) == 5
    assert set(MemoryScope.__members__.keys()) == {
        "WORKING", "EPISODE", "SESSION", "USER", "GLOBAL"
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/harness/test_enums.py::test_episode_scope_exists -v`
Expected: FAIL — EPISODE not in MemoryScope

- [ ] **Step 3: Add EPISODE to MemoryScope**

在 `app/harness/enums.py` 的 `MemoryScope` 类中，在 `WORKING` 之后添加：

```python
class MemoryScope(StrEnum):
    """记忆作用域 — 5级"""
    WORKING = "working"
    EPISODE = "episode"        # 新增：一次教学循环
    SESSION = "session"
    USER = "user"
    GLOBAL = "global"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/harness/test_enums.py -v`
Expected: PASS (including existing enum tests)

- [ ] **Step 5: Commit**

```bash
git add app/harness/enums.py tests/unit/harness/test_enums.py
git commit -m "feat: add EPISODE to MemoryScope (5-level memory hierarchy)"
```

---

### Task 6: MemoryItem Dataclass

**Files:**
- Rewrite: `app/harness/memory.py` (partial — MemoryItem only first)
- Test: `tests/unit/harness/test_memory.py` (new tests)

- [ ] **Step 1: Write failing tests for MemoryItem**

```python
# tests/unit/harness/test_memory.py (new file, replace old)

import time
from datetime import datetime, timedelta
from app.harness.memory import MemoryItem
from app.harness.enums import MemoryScope


def test_memory_item_defaults():
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.WORKING, source="user_1")
    assert item.id == "t1"
    assert item.score == 0.0
    assert item.access_count == 0
    assert item.tags == []
    assert item.metadata == {}
    assert isinstance(item.created_at, datetime)


def test_memory_item_not_expired():
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.WORKING,
                      source="user_1", ttl_seconds=3600)
    assert item.is_expired is False


def test_memory_item_expired():
    past = datetime.now() - timedelta(seconds=100)
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.WORKING,
                      source="user_1", ttl_seconds=10, created_at=past)
    assert item.is_expired is True


def test_memory_item_no_ttl_never_expires():
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.USER, source="user_1")
    assert item.is_expired is False


def test_memory_item_touch():
    item = MemoryItem(id="t1", content="test", scope=MemoryScope.WORKING, source="user_1")
    old_accessed = item.accessed_at
    old_count = item.access_count
    time.sleep(0.01)
    item.touch()
    assert item.accessed_at > old_accessed
    assert item.access_count == old_count + 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/harness/test_memory.py -v`
Expected: FAIL — cannot import MemoryItem with new signature

- [ ] **Step 3: Write MemoryItem implementation**

Replace entire `app/harness/memory.py` with:

```python
# app/harness/memory.py

import json
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.harness.enums import MemoryScope


@dataclass
class MemoryItem:
    """记忆条目 — 统一数据模型"""
    id: str
    content: str
    scope: MemoryScope
    source: str
    score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    ttl_seconds: int | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        elapsed = (datetime.now() - self.created_at).total_seconds()
        return elapsed > self.ttl_seconds

    def touch(self):
        self.accessed_at = datetime.now()
        self.access_count += 1


class ShortTermStore:
    """短期记忆：LRU 缓存 + TTL 衰减"""

    DEFAULT_TTL = {
        MemoryScope.WORKING: 60,
        MemoryScope.EPISODE: 600,
        MemoryScope.SESSION: 3600,
    }

    def __init__(self, max_size: int = 200):
        self._cache: OrderedDict[str, MemoryItem] = OrderedDict()
        self._max_size = max_size

    def put(self, item: MemoryItem) -> str:
        if item.ttl_seconds is None:
            item.ttl_seconds = self.DEFAULT_TTL.get(item.scope, 3600)
        self._cache[item.id] = item
        self._cache.move_to_end(item.id)
        self._evict()
        return item.id

    def get(self, item_id: str) -> Optional[MemoryItem]:
        item = self._cache.get(item_id)
        if item is None:
            return None
        if item.is_expired:
            del self._cache[item_id]
            return None
        item.touch()
        self._cache.move_to_end(item_id)
        return item

    def recall(self, query: str, scopes: list[MemoryScope],
               top_k: int = 5) -> list[MemoryItem]:
        self._purge_expired()
        results = []
        query_lower = query.lower()
        for item in self._cache.values():
            if item.scope not in scopes:
                continue
            if query_lower in item.content.lower() or \
               any(t in query_lower for t in item.tags):
                relevance = item.score * (1 + item.access_count * 0.1)
                results.append((item, relevance))
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:top_k]]

    def remove(self, item_id: str) -> bool:
        if item_id in self._cache:
            del self._cache[item_id]
            return True
        return False

    def clear(self):
        self._cache.clear()

    def items_to_persist(self) -> list[MemoryItem]:
        return [
            item for item in self._cache.values()
            if item.scope in (MemoryScope.SESSION, MemoryScope.USER, MemoryScope.GLOBAL)
            and not item.is_expired
        ]

    def _evict(self):
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def _purge_expired(self):
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for k in expired:
            del self._cache[k]


class LongTermStore:
    """长期记忆：SQLite 持久化 + FTS5 检索 + LLM 摘要压缩"""

    def __init__(self, memory_store, llm=None):
        self._store = memory_store
        self._llm = llm

    async def recall(self, query: str, scopes: list[MemoryScope],
                     user_id: int | None = None, top_k: int = 5) -> list[MemoryItem]:
        return await self._store.search(query, scopes, user_id, top_k)

    async def memorize(self, item: MemoryItem, user_id: int | None = None) -> str:
        return await self._store.store(item, user_id)

    async def compress(self, user_id: int, session_id: str,
                       items: list[MemoryItem]) -> str | None:
        if not items or not self._llm:
            return None
        combined = "\n".join(f"[{i.scope}]{i.content}" for i in items)
        summary_text = self._llm.invoke(
            "你是一个学习记忆整理助手。请将以下学习记录压缩为简洁摘要，保留关键知识点和掌握程度。",
            combined,
        )
        source_ids = [i.id for i in items]
        return await self._store.store_summary(
            user_id, "session_compression", summary_text, source_ids
        )

    async def get_profile(self, user_id: int) -> dict | None:
        return await self._store.get_user_profile(user_id)

    async def update_profile(self, user_id: int, **fields) -> None:
        await self._store.update_user_profile(user_id, **fields)


class MemoryManager:
    """记忆管理门面 — 自动路由短期/长期，对节点透明"""

    def __init__(self, short_term: ShortTermStore,
                 long_term: LongTermStore | None = None):
        self._short = short_term
        self._long = long_term

    def recall(self, query: str, user_id: int | None,
               scopes: list[MemoryScope]) -> list[MemoryItem]:
        """同步查询：仅查短期记忆"""
        return self._short.recall(query, scopes)

    async def recall_async(self, query: str, user_id: int | None,
                           scopes: list[MemoryScope],
                           top_k: int = 5) -> list[MemoryItem]:
        """异步全量检索：短期 + 长期"""
        short_results = self._short.recall(query, scopes, top_k)
        long_results = []
        if self._long:
            long_scopes = [s for s in scopes
                           if s in (MemoryScope.USER, MemoryScope.GLOBAL)]
            if long_scopes:
                long_results = await self._long.recall(
                    query, long_scopes, user_id, top_k - len(short_results)
                )
        seen = {r.id for r in short_results}
        for r in long_results:
            if r.id not in seen:
                short_results.append(r)
                seen.add(r.id)
        return short_results

    def memorize(self, content: str, scope: MemoryScope,
                 user_id: int | None = None,
                 metadata: dict | None = None,
                 tags: list[str] | None = None) -> str:
        item = MemoryItem(
            id=f"{scope.value}_{uuid.uuid4().hex[:8]}",
            content=content,
            scope=scope,
            source=f"user_{user_id or 'anon'}",
            tags=tags or [],
            metadata=metadata or {},
        )
        return self._short.put(item)

    async def memorize_persistent(self, content: str, scope: MemoryScope,
                                  user_id: int | None = None,
                                  metadata: dict | None = None,
                                  tags: list[str] | None = None) -> str:
        item = MemoryItem(
            id=f"{scope.value}_{uuid.uuid4().hex[:8]}",
            content=content,
            scope=scope,
            source=f"user_{user_id or 'anon'}",
            tags=tags or [],
            metadata=metadata or {},
        )
        if self._long:
            return await self._long.memorize(item, user_id)
        return self._short.put(item)

    def forget(self, item_id: str) -> bool:
        return self._short.remove(item_id)

    async def flush_session(self, session_id: str, user_id: int | None = None):
        items = self._short.items_to_persist()
        if self._long and items and user_id:
            await self._long.compress(user_id, session_id, items)
        self._short.clear()

    async def summarize(self, user_id: int, session_id: str) -> str | None:
        items = self._short.items_to_persist()
        if self._long and items:
            return await self._long.compress(user_id, session_id, items)
        return None
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/harness/test_memory.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add app/harness/memory.py tests/unit/harness/test_memory.py
git commit -m "feat: rewrite memory system with MemoryItem, ShortTermStore, LongTermStore, MemoryManager"
```

---

### Task 7: ShortTermStore Tests

**Files:**
- Test: `tests/unit/harness/test_memory.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/harness/test_memory.py (append)

from app.harness.memory import ShortTermStore


def _make_item(item_id="t1", scope=MemoryScope.WORKING, content="test content",
               score=1.0, tags=None, ttl=None):
    return MemoryItem(id=item_id, content=content, scope=scope,
                      source="test", score=score, tags=tags or [], ttl_seconds=ttl)


def test_sts_put_and_get():
    store = ShortTermStore()
    item = _make_item()
    store.put(item)
    result = store.get("t1")
    assert result is not None
    assert result.content == "test content"


def test_sts_get_expired():
    store = ShortTermStore()
    item = _make_item(ttl=0)
    store.put(item)
    import time; time.sleep(0.01)
    assert store.get("t1") is None


def test_sts_lru_eviction():
    store = ShortTermStore(max_size=3)
    for i in range(5):
        store.put(_make_item(item_id=f"t{i}", scope=MemoryScope.SESSION))
    assert len(store._cache) == 3
    assert store.get("t0") is None
    assert store.get("t1") is None
    assert store.get("t4") is not None


def test_sts_recall_keyword_match():
    store = ShortTermStore()
    store.put(_make_item(item_id="t1", content="二分查找算法", scope=MemoryScope.SESSION))
    store.put(_make_item(item_id="t2", content="快速排序", scope=MemoryScope.SESSION))
    results = store.recall("二分", [MemoryScope.SESSION])
    assert len(results) == 1
    assert results[0].id == "t1"


def test_sts_recall_tag_match():
    store = ShortTermStore()
    store.put(_make_item(item_id="t1", content="算法分析", scope=MemoryScope.SESSION,
                         tags=["二分查找", "时间复杂度"]))
    results = store.recall("二分查找", [MemoryScope.SESSION])
    assert len(results) == 1


def test_sts_recall_scope_filter():
    store = ShortTermStore()
    store.put(_make_item(item_id="t1", content="global info", scope=MemoryScope.GLOBAL))
    store.put(_make_item(item_id="t2", content="session info", scope=MemoryScope.SESSION))
    results = store.recall("info", [MemoryScope.GLOBAL])
    assert len(results) == 1
    assert results[0].scope == MemoryScope.GLOBAL


def test_sts_items_to_persist_filters():
    store = ShortTermStore()
    store.put(_make_item(item_id="t1", content="working", scope=MemoryScope.WORKING))
    store.put(_make_item(item_id="t2", content="session", scope=MemoryScope.SESSION))
    store.put(_make_item(item_id="t3", content="global", scope=MemoryScope.GLOBAL))
    persistable = store.items_to_persist()
    ids = {i.id for i in persistable}
    assert "t2" in ids
    assert "t3" in ids
    assert "t1" not in ids


def test_sts_clear():
    store = ShortTermStore()
    store.put(_make_item())
    store.clear()
    assert len(store._cache) == 0
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/harness/test_memory.py -v`
Expected: 14 PASS (5 from Task 6 + 9 new)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/harness/test_memory.py
git commit -m "test: add ShortTermStore coverage (9 tests)"
```

---

### Task 8: MemoryManager Tests

**Files:**
- Test: `tests/unit/harness/test_memory.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/harness/test_memory.py (append)

from app.harness.memory import MemoryManager


def _make_manager():
    return MemoryManager(short_term=ShortTermStore())


def test_mgr_memorize_returns_id():
    mgr = _make_manager()
    mid = mgr.memorize("二分查找核心", MemoryScope.SESSION)
    assert mid.startswith("session_")


def test_mgr_memorize_with_tags():
    mgr = _make_manager()
    mid = mgr.memorize("test", MemoryScope.SESSION, tags=["算法"])
    results = mgr.recall("算法", None, [MemoryScope.SESSION])
    assert len(results) == 1


def test_mgr_recall_short_term_only():
    mgr = _make_manager()
    mgr.memorize("hello world", MemoryScope.SESSION)
    results = mgr.recall("hello", None, [MemoryScope.SESSION])
    assert len(results) == 1


def test_mgr_recall_empty():
    mgr = _make_manager()
    results = mgr.recall("nothing", None, [MemoryScope.SESSION])
    assert len(results) == 0


def test_mgr_forget():
    mgr = _make_manager()
    mid = mgr.memorize("to forget", MemoryScope.SESSION)
    assert mgr.forget(mid) is True
    assert mgr.forget("nonexistent") is False


def test_mgr_flush_clears():
    mgr = _make_manager()
    mgr.memorize("temp", MemoryScope.WORKING)
    mgr.memorize("persist", MemoryScope.SESSION)
    import asyncio
    asyncio.run(mgr.flush_session("s1"))
    results = mgr.recall("temp", None, [MemoryScope.WORKING])
    assert len(results) == 0
    results = mgr.recall("persist", None, [MemoryScope.SESSION])
    assert len(results) == 0
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/harness/test_memory.py -v`
Expected: 20 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/harness/test_memory.py
git commit -m "test: add MemoryManager coverage (6 tests)"
```

---

### Task 9: MemoryState Extension

**Files:**
- Modify: `app/harness/state/memory.py`

- [ ] **Step 1: Update MemoryState**

```python
# app/harness/state/memory.py

from typing import TypedDict, List, Optional


class MemoryState(TypedDict, total=False):
    # existing
    topic: Optional[str]
    topic_confidence: float
    topic_changed: bool
    topic_reason: str
    topic_context: str
    topic_segments: List[dict]
    comparison_mode: bool
    history: List[str]
    has_history: bool
    history_summary: str
    history_mastery: str
    # new
    short_term_ids: List[str]
    long_term_context: str
    user_profile_summary: str
    mastery_history: List[dict]
```

- [ ] **Step 2: Run full test suite to verify no breakage**

Run: `uv run pytest tests/ -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add app/harness/state/memory.py
git commit -m "feat: extend MemoryState with long_term_context, user_profile_summary, mastery_history"
```

---

### Task 10: MemoryStore (SQLite)

**Files:**
- Create: `app/infrastructure/storage/memory_store.py`
- Test: `tests/unit/infrastructure/test_memory_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/infrastructure/test_memory_store.py

import asyncio
import tempfile
import os
from app.infrastructure.storage.memory_store import MemoryStore
from app.harness.memory import MemoryItem
from app.harness.enums import MemoryScope


async def _make_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MemoryStore(db_path=path)
    await store.init()
    return store, path


def test_memory_store_crud():
    async def _test():
        store, path = await _make_store()
        item = MemoryItem(id="m1", content="二分查找", scope=MemoryScope.USER, source="test")
        mid = await store.store(item, user_id=1)
        assert mid == "m1"
        results = await store.search("二分", [MemoryScope.USER], user_id=1)
        assert len(results) == 1
        assert results[0].content == "二分查找"
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_memory_store_fts_search():
    async def _test():
        store, path = await _make_store()
        await store.store(MemoryItem(id="m1", content="二分查找算法", scope=MemoryScope.USER, source="test"), 1)
        await store.store(MemoryItem(id="m2", content="快速排序算法", scope=MemoryScope.USER, source="test"), 1)
        results = await store.search("二分", [MemoryScope.USER], user_id=1)
        assert len(results) == 1
        assert results[0].id == "m1"
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_memory_store_scope_filter():
    async def _test():
        store, path = await _make_store()
        await store.store(MemoryItem(id="m1", content="test", scope=MemoryScope.USER, source="test"), 1)
        await store.store(MemoryItem(id="m2", content="test", scope=MemoryScope.GLOBAL, source="test"), 1)
        results = await store.search("test", [MemoryScope.USER])
        assert all(r.scope == MemoryScope.USER for r in results)
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_memory_store_summary():
    async def _test():
        store, path = await _make_store()
        sid = await store.store_summary(1, "session", "学习了二分查找", ["m1"])
        assert sid is not None
        await store.close()
        os.unlink(path)
    asyncio.run(_test())


def test_memory_store_user_profile():
    async def _test():
        store, path = await _make_store()
        assert await store.get_user_profile(1) is None
        await store.update_user_profile(1, topics=["算法"], total_sessions=1)
        profile = await store.get_user_profile(1)
        assert profile is not None
        assert profile["topics"] == ["算法"]
        assert profile["total_sessions"] == 1
        await store.close()
        os.unlink(path)
    asyncio.run(_test())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/infrastructure/test_memory_store.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write MemoryStore**

```python
# app/infrastructure/storage/memory_store.py

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from app.harness.enums import MemoryScope
from app.harness.memory import MemoryItem


class MemoryStore:
    """SQLite 持久化存储 — 长期记忆"""

    def __init__(self, db_path: str = "data/memory.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                scope TEXT NOT NULL,
                source TEXT,
                score REAL DEFAULT 0,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                accessed_at TEXT,
                access_count INTEGER DEFAULT 0,
                user_id INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_scope ON memory_entries(scope);
            CREATE INDEX IF NOT EXISTS idx_user ON memory_entries(user_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                USING fts5(id, content, tags);
            CREATE TABLE IF NOT EXISTS memory_summaries (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                scope TEXT NOT NULL,
                summary TEXT NOT NULL,
                source_ids TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                topics TEXT DEFAULT '[]',
                mastery_summary TEXT DEFAULT '{}',
                learning_style TEXT DEFAULT '',
                total_sessions INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );
        """)
        await self._db.commit()

    async def store(self, item: MemoryItem, user_id: int | None = None) -> str:
        await self._db.execute(
            """INSERT OR REPLACE INTO memory_entries
               (id, content, scope, source, score, tags, metadata,
                created_at, accessed_at, access_count, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.id, item.content, item.scope, item.source, item.score,
             json.dumps(item.tags), json.dumps(item.metadata),
             item.created_at.isoformat(), item.accessed_at.isoformat(),
             item.access_count, user_id)
        )
        await self._db.execute(
            "INSERT OR REPLACE INTO memory_fts (id, content, tags) VALUES (?, ?, ?)",
            (item.id, item.content, " ".join(item.tags))
        )
        await self._db.commit()
        return item.id

    async def search(self, query: str, scopes: list[MemoryScope],
                     user_id: int | None = None, top_k: int = 5) -> list[MemoryItem]:
        scope_clause = ",".join("?" for _ in scopes)
        sql = f"""
            SELECT m.* FROM memory_entries m
            JOIN memory_fts f ON m.id = f.id
            WHERE m.scope IN ({scope_clause})
            AND memory_fts MATCH ?
        """
        params = [*scopes, query]
        if user_id is not None:
            sql += " AND m.user_id = ?"
            params.append(user_id)
        sql += " ORDER BY m.score DESC LIMIT ?"
        params.append(top_k)
        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._row_to_item(r, cursor) for r in rows]

    async def store_summary(self, user_id: int, scope: str,
                            summary: str, source_ids: list[str]) -> str:
        sid = str(uuid.uuid4())
        await self._db.execute(
            """INSERT INTO memory_summaries
               (id, user_id, scope, summary, source_ids, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sid, user_id, scope, summary, json.dumps(source_ids),
             datetime.now().isoformat())
        )
        await self._db.commit()
        return sid

    async def get_user_profile(self, user_id: int) -> dict | None:
        cursor = await self._db.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        result = dict(zip(cols, row))
        result["topics"] = json.loads(result.get("topics", "[]"))
        result["mastery_summary"] = json.loads(result.get("mastery_summary", "{}"))
        return result

    async def update_user_profile(self, user_id: int, **fields) -> None:
        sets, params = [], []
        for k, v in fields.items():
            sets.append(f"{k} = ?")
            params.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
        params.append(datetime.now().isoformat())
        params.append(user_id)
        sql = f"""INSERT INTO user_profiles (user_id, {', '.join(f'{k}' for k in fields)}, updated_at)
                   VALUES (?, {', '.join('?' for _ in fields)}, ?)
                   ON CONFLICT(user_id) DO UPDATE SET {', '.join(sets)}, updated_at = excluded.updated_at"""
        await self._db.execute(sql, params)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    def _row_to_item(self, row, cursor) -> MemoryItem:
        cols = [d[0] for d in cursor.description]
        r = dict(zip(cols, row))
        return MemoryItem(
            id=r["id"], content=r["content"], scope=MemoryScope(r["scope"]),
            source=r.get("source", "") or "", score=r.get("score", 0) or 0.0,
            tags=json.loads(r.get("tags", "[]") or "[]"),
            metadata=json.loads(r.get("metadata", "{}") or "{}"),
            created_at=datetime.fromisoformat(r["created_at"]),
            accessed_at=datetime.fromisoformat(r["accessed_at"]) if r.get("accessed_at") else datetime.now(),
            access_count=r.get("access_count", 0) or 0,
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/infrastructure/test_memory_store.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/storage/memory_store.py tests/unit/infrastructure/test_memory_store.py
git commit -m "feat: add MemoryStore with SQLite, FTS5, user profiles (5 tests)"
```

---

### Task 11: Phase 2 Regression

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All pass. Existing tests for memory (`test_memorize_and_recall`, `test_recall_filters_by_scope`, `test_recall_empty`, `test_memorize_returns_id`) are replaced by the new file — verify they are removed.

- [ ] **Step 2: Commit if any fixes needed**

---

## Phase 3: LLM Layer

### Task 12: LLMConfig & TokenBudgetExceeded

**Files:**
- Rewrite: `app/infrastructure/llm.py` (data classes first)
- Test: `tests/unit/infrastructure/test_llm.py` (new tests)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/infrastructure/test_llm.py

from app.infrastructure.llm import LLMConfig, TokenBudgetExceeded


def test_llm_config_defaults():
    cfg = LLMConfig()
    assert cfg.primary_model == "gpt-4o-mini"
    assert cfg.fallback_model == "gpt-4o-mini"
    assert cfg.max_retries == 2
    assert cfg.retry_delay == 1.0
    assert cfg.token_budget == 4096
    assert cfg.temperature == 0.7
    assert cfg.timeout == 30.0


def test_llm_config_custom():
    cfg = LLMConfig(primary_model="gpt-4o", max_retries=3, token_budget=8192)
    assert cfg.primary_model == "gpt-4o"
    assert cfg.max_retries == 3
    assert cfg.token_budget == 8192


def test_token_budget_exceeded():
    exc = TokenBudgetExceeded(budget=4096, requested=5000)
    assert exc.budget == 4096
    assert exc.requested == 5000
    assert "4096" in str(exc)
    assert "5000" in str(exc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/infrastructure/test_llm.py -v`
Expected: FAIL — cannot import

- [ ] **Step 3: Write data classes (replace entire llm.py)**

```python
# app/infrastructure/llm.py

import json
import time
import logging
from dataclasses import dataclass

logger = logging.getLogger("learning_agent")


@dataclass
class LLMConfig:
    """LLM 调用配置"""
    primary_model: str = "gpt-4o-mini"
    fallback_model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    max_retries: int = 2
    retry_delay: float = 1.0
    token_budget: int = 4096
    temperature: float = 0.7
    timeout: float = 30.0


class TokenBudgetExceeded(Exception):
    """Token 预算超限 — 当前作为软警告使用"""
    def __init__(self, budget: int, requested: int):
        self.budget = budget
        self.requested = requested
        super().__init__(f"Token 预算超限: 预算={budget}, 请求={requested}")


class FakeLLM:
    """测试替身"""

    RESPONSES = {
        "掌握度评估": '{"mastery_score": 65, "mastery_level": "partial", "mastery_rationale": "基本概念掌握，细节不足"}',
        "意图分类": '{"intent": "teach_loop", "confidence": 0.9}',
        "学习总结": "本次学习了二分查找的核心概念，掌握程度为中等。",
        "诊断": "用户对主题有基础了解，需要补充细节",
        "讲解": "知识点讲解内容...",
        "追问": "能否解释一下时间复杂度为什么是O(log n)？",
        "评估": "用户理解较为准确",
    }

    def __init__(self, responses: dict | None = None):
        self._responses = responses or self.RESPONSES.copy()
        self.call_history: list[dict] = []

    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        for keyword, response in self._responses.items():
            if keyword in user_prompt:
                self.call_history.append({
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response": response,
                    "kwargs": kwargs,
                })
                return response
        self.call_history.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response": "默认测试回复",
            "kwargs": kwargs,
        })
        return "默认测试回复"

    def invoke_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        return json.loads(self.invoke(system_prompt, user_prompt, **kwargs))

    def stream(self, system_prompt: str, user_prompt: str, **kwargs):
        response = self.invoke(system_prompt, user_prompt, **kwargs)
        for char in response:
            yield char

    def summarize_memories(self, memories: list[str]) -> str:
        return f"[摘要] 共{len(memories)}条记忆的压缩结果"

    def assert_called_with(self, keyword: str):
        for call in self.call_history:
            if keyword in call.get("user_prompt", ""):
                return
        raise AssertionError(f"未找到包含 '{keyword}' 的 LLM 调用")

    @property
    def call_count(self) -> int:
        return len(self.call_history)


class LLMService:
    """LLM 调用服务 — 连接复用 + 重试回退 + 可观测"""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._llm = None
        self._fallback_llm = None

    @property
    def llm(self):
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            self._llm = ChatOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url or None,
                model=self.config.primary_model,
                temperature=self.config.temperature,
                max_tokens=self.config.token_budget,
                timeout=self.config.timeout,
            )
        return self._llm

    @property
    def fallback_llm(self):
        if self._fallback_llm is None:
            from langchain_openai import ChatOpenAI
            self._fallback_llm = ChatOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url or None,
                model=self.config.fallback_model,
                temperature=self.config.temperature,
                max_tokens=self.config.token_budget,
                timeout=self.config.timeout,
            )
        return self._fallback_llm

    def invoke(self, system_prompt: str, user_prompt: str,
               session_id: str = "", node: str = "", intent: str = "",
               **kwargs) -> str:
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return self._call_with_span(
                    self.llm, system_prompt, user_prompt,
                    session_id, node, intent,
                )
            except Exception as e:
                last_error = e
                logger.warning(f"LLM 调用失败(尝试{attempt+1}): {e}")
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay * (2 ** attempt))

        if self.config.fallback_model != self.config.primary_model:
            logger.info(f"切换回退模型: {self.config.fallback_model}")
            try:
                return self._call_with_span(
                    self.fallback_llm, system_prompt, user_prompt,
                    session_id, node, intent,
                )
            except Exception as e:
                last_error = e

        raise last_error

    def invoke_json(self, system_prompt: str, user_prompt: str,
                    session_id: str = "", node: str = "", intent: str = "",
                    **kwargs) -> dict:
        text = self.invoke(system_prompt, user_prompt,
                           session_id, node, intent, **kwargs)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        return json.loads(cleaned)

    def stream(self, system_prompt: str, user_prompt: str,
               session_id: str = "", node: str = "", intent: str = "",
               **kwargs):
        from app.harness.observability import get_observability, LLMSpan
        obs = get_observability()
        start = time.monotonic()
        collected = []
        try:
            for chunk in self.llm.stream([
                {"type": "system", "content": system_prompt},
                {"type": "user", "content": user_prompt},
            ]):
                content = chunk.content
                collected.append(content)
                yield content
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            obs.llm_span(LLMSpan(
                model=self.config.primary_model,
                completion_tokens=len("".join(collected)) // 4,
                latency_ms=latency_ms,
                node=node, intent=intent, session_id=session_id,
                metadata={"streaming": True},
            ))

    def summarize_memories(self, memories: list[str]) -> str:
        combined = "\n".join(f"- {m}" for m in memories)
        return self.invoke(
            "你是一个学习记忆整理助手。请将以下学习记录压缩为简洁摘要，保留关键知识点和掌握程度。",
            combined,
        )

    def _call_with_span(self, llm, system_prompt: str, user_prompt: str,
                         session_id: str, node: str, intent: str) -> str:
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.harness.observability import get_observability, LLMSpan
        obs = get_observability()
        start = time.monotonic()
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        latency_ms = (time.monotonic() - start) * 1000
        usage = getattr(response, 'usage_metadata', None) or {}
        prompt_tokens = usage.get('input_tokens', 0)
        completion_tokens = usage.get('output_tokens', 0)
        total_tokens = prompt_tokens + completion_tokens
        if total_tokens > self.config.token_budget:
            logger.warning(f"Token 预算超限: {total_tokens} > {self.config.token_budget}")
        cost = self._calc_cost(llm.model_name, prompt_tokens, completion_tokens)
        obs.llm_span(LLMSpan(
            model=llm.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            node=node, intent=intent, session_id=session_id,
        ))
        return response.content

    @staticmethod
    def _calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        PRICING = {
            "gpt-4o-mini": (0.15 / 1e6, 0.60 / 1e6),
            "gpt-4o":      (2.50 / 1e6, 10.00 / 1e6),
            "gpt-4-turbo": (10.00 / 1e6, 30.00 / 1e6),
        }
        input_price, output_price = PRICING.get(model, (0.0, 0.0))
        return prompt_tokens * input_price + completion_tokens * output_price
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/infrastructure/test_llm.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/llm.py tests/unit/infrastructure/test_llm.py
git commit -m "feat: rewrite LLM layer with LLMConfig, TokenBudgetExceeded, retry/fallback, streaming"
```

---

### Task 13: FakeLLM Tests

**Files:**
- Test: `tests/unit/infrastructure/test_llm.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/infrastructure/test_llm.py (append)

from app.infrastructure.llm import FakeLLM


def test_fake_invoke_keyword_match():
    llm = FakeLLM()
    result = llm.invoke("system", "请诊断用户理解程度")
    assert "基础了解" in result


def test_fake_invoke_default():
    llm = FakeLLM()
    result = llm.invoke("system", "随机问题")
    assert result == "默认测试回复"


def test_fake_invoke_json():
    llm = FakeLLM()
    result = llm.invoke_json("system", "请输出意图分类意图")
    assert "intent" in result


def test_fake_call_history():
    llm = FakeLLM()
    llm.invoke("system", "诊断")
    llm.invoke("system", "讲解")
    assert llm.call_count == 2


def test_fake_assert_called_with():
    llm = FakeLLM()
    llm.invoke("system", "诊断用户")
    llm.assert_called_with("诊断")


def test_fake_assert_called_with_failure():
    import pytest
    llm = FakeLLM()
    with pytest.raises(AssertionError):
        llm.assert_called_with("不存在的关键词")


def test_fake_stream():
    llm = FakeLLM()
    chunks = list(llm.stream("system", "诊断"))
    assert len(chunks) > 0
    assert "".join(chunks) == llm.RESPONSES["诊断"]


def test_fake_custom_responses():
    llm = FakeLLM(responses={"自定义": "自定义回复"})
    result = llm.invoke("system", "自定义问题")
    assert result == "自定义回复"


def test_fake_summarize_memories():
    llm = FakeLLM()
    result = llm.summarize_memories(["记忆1", "记忆2"])
    assert "2条记忆" in result
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/infrastructure/test_llm.py -v`
Expected: 12 PASS (3 + 9 new)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/infrastructure/test_llm.py
git commit -m "test: add FakeLLM coverage (9 tests)"
```

---

### Task 14: Cost Calculation Tests

**Files:**
- Test: `tests/unit/infrastructure/test_llm.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/infrastructure/test_llm.py (append)

from app.infrastructure.llm import LLMService


def test_calc_cost_gpt4o_mini():
    cost = LLMService._calc_cost("gpt-4o-mini", 1000, 500)
    expected = 1000 * 0.15 / 1e6 + 500 * 0.60 / 1e6
    assert abs(cost - expected) < 1e-10


def test_calc_cost_gpt4o():
    cost = LLMService._calc_cost("gpt-4o", 1000, 500)
    expected = 1000 * 2.50 / 1e6 + 500 * 10.00 / 1e6
    assert abs(cost - expected) < 1e-10


def test_calc_cost_unknown_model():
    cost = LLMService._calc_cost("unknown-model", 1000, 500)
    assert cost == 0.0


def test_calc_cost_zero_tokens():
    cost = LLMService._calc_cost("gpt-4o-mini", 0, 0)
    assert cost == 0.0
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/infrastructure/test_llm.py -v`
Expected: 16 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/infrastructure/test_llm.py
git commit -m "test: add cost calculation tests (4 tests)"
```

---

### Task 15: Node Migration — Pass session_id/node/intent

**Files:**
- Modify: `app/agent/nodes/diagnose.py`
- Modify: `app/agent/nodes/explain.py`
- Modify: `app/agent/nodes/followup.py`
- Modify: `app/agent/nodes/restate_check.py`
- Modify: `app/agent/nodes/evaluate.py`
- Modify: `app/agent/nodes/summarize.py`
- Modify: `app/agent/nodes/answer_policy.py`

All 7 nodes follow the same pattern: extract `session_id` from state and pass `session_id`/`node`/`intent` to `_llm.invoke()`.

- [ ] **Step 1: Migrate all 7 nodes**

```python
# app/agent/nodes/diagnose.py
from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="diagnose")
def diagnose_node(state: LearningState) -> dict:
    system_prompt = state["_system_prompt"]
    topic = state.get("memory", {}).get("topic", "")
    user_input = state["user_input"]
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt, f"主题：{topic}\n用户：{user_input}",
        session_id=session_id, node="diagnose", intent="teach_loop",
    )
    return {"teaching": {"diagnosis": result}}
```

```python
# app/agent/nodes/explain.py
from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="explain")
def explain_node(state: LearningState) -> dict:
    system_prompt = state["_system_prompt"]
    topic = state.get("memory", {}).get("topic", "")
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt, f"主题：{topic}\n诊断：{diagnosis}\n请讲解",
        session_id=session_id, node="explain", intent="teach_loop",
    )
    return {"teaching": {"explanation": result, "reply": result}}
```

```python
# app/agent/nodes/followup.py
from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="followup")
def followup_node(state: LearningState) -> dict:
    system_prompt = state["_system_prompt"]
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    restatement_eval = state.get("teaching", {}).get("restatement_eval", "")
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt, f"诊断：{diagnosis}\n复述评估：{restatement_eval}",
        session_id=session_id, node="followup", intent="teach_loop",
    )
    return {
        "teaching": {"followup_question": result},
        "meta": {"stage": Stage.FOLLOWUP},
    }
```

```python
# app/agent/nodes/restate_check.py
from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="restate_check")
def restate_check_node(state: LearningState) -> dict:
    system_prompt = state["_system_prompt"]
    explanation = state.get("teaching", {}).get("explanation", "")
    user_input = state["user_input"]
    loop_count = state.get("teaching", {}).get("explain_loop_count", 0)
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt, f"讲解：{explanation}\n用户复述：{user_input}",
        session_id=session_id, node="restate_check", intent="teach_loop",
    )
    return {
        "teaching": {"restatement_eval": result, "explain_loop_count": loop_count},
        "meta": {"stage": Stage.RESTATE_CHECK},
    }
```

```python
# app/agent/nodes/evaluate.py
from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage, MasteryLevel
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="evaluate")
def evaluate_node(state: LearningState) -> dict:
    system_prompt = state["_system_prompt"]
    diagnosis = state.get("teaching", {}).get("diagnosis", "")
    restatement_eval = state.get("teaching", {}).get("restatement_eval", "")
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke_json(
        system_prompt,
        f"诊断：{diagnosis}\n复述评估：{restatement_eval}\n请输出掌握度评估",
        session_id=session_id, node="evaluate", intent="teach_loop",
    )
    mastery_score = result.get("mastery_score", 50)
    if mastery_score >= 80:
        level = MasteryLevel.MASTERED
    elif mastery_score >= 50:
        level = MasteryLevel.PARTIAL
    else:
        level = MasteryLevel.WEAK
    return {
        "evaluation": {
            "mastery_score": mastery_score,
            "mastery_level": level,
            "mastery_rationale": result.get("mastery_rationale", ""),
        },
        "meta": {"stage": Stage.EVALUATE},
    }
```

```python
# app/agent/nodes/summarize.py
from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="teach_loop", node="summarize")
def summarize_node(state: LearningState) -> dict:
    system_prompt = state["_system_prompt"]
    topic = state.get("memory", {}).get("topic", "")
    mastery = state.get("evaluation", {}).get("mastery_level", "")
    mastery_score = state.get("evaluation", {}).get("mastery_score", 0)
    rationale = state.get("evaluation", {}).get("mastery_rationale", "")
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt,
        f"主题：{topic}\n掌握等级：{mastery}\n掌握分数：{mastery_score}\n理由：{rationale}",
        session_id=session_id, node="summarize", intent="teach_loop",
    )
    return {
        "teaching": {"summary": result},
        "meta": {"stage": Stage.SUMMARIZE},
    }
```

```python
# app/agent/nodes/answer_policy.py
from app.harness.state import LearningState
from app.infrastructure.llm import FakeLLM
from app.harness.enums import Stage
from app.agent.spec_decorator import with_spec

_llm = FakeLLM()


@with_spec(intent="qa_direct", node="answer_policy")
def answer_policy_node(state: LearningState) -> dict:
    system_prompt = state["_system_prompt"]
    rag_context = state.get("retrieval", {}).get("rag_context", "")
    user_input = state["user_input"]
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt,
        f"知识：{rag_context}\n用户问题：{user_input}",
        session_id=session_id, node="answer_policy", intent="qa_direct",
    )
    return {
        "teaching": {"reply": result},
        "meta": {"stage": Stage.EXPLAINING},
    }
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All existing agent tests pass (FakeLLM accepts **kwargs, so session_id/node/intent are silently accepted)

- [ ] **Step 3: Commit**

```bash
git add app/agent/nodes/
git commit -m "feat: migrate 7 nodes to pass session_id/node/intent to LLM calls"
```

---

### Task 16: Phase 3 — Full Regression & Update README

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All pass

- [ ] **Step 2: Update README.md**

在 README.md 的技术栈表格中更新可观测性行：

```markdown
| 可观测性 | Langfuse（生产）/ Console（开发）+ SessionStats 汇总 |
```

在 README.md 的项目结构中更新：

```
├── harness/
│   ├── memory.py          # 短期(LRU+TTL) + 长期(SQLite) 双层记忆
│   ├── observability.py   # Observability ABC + Langfuse/Console/Fake
```

新增文件：
```
├── infrastructure/
│   ├── storage/
│   │   ├── memory_store.py   # SQLite + FTS5 长期记忆持久化
```

在测试部分更新测试数量。

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for observability, memory, and LLM redesign"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Each design spec section maps to a task
- [x] **Placeholder scan:** No TBD/TODO/fill-in-later found
- [x] **Type consistency:** MemoryItem, LLMSpan, MemoryScope types consistent across all tasks
- [x] **Import paths:** All imports reference correct modules
- [x] **Test isolation:** Each task's tests are self-contained
- [x] **Backward compatibility:** FakeLLM **kwargs accepts new params without breaking existing tests
