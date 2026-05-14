# 可观测系统重写 — 三层设计文档

> 日期：2026-05-13
> 方案：方案B — 核心一次性重写（Observability + Memory + LLM 联动）
> 优先级：最高（第一阶段）

---

## 第一层：总览

```
目标：将 Observability 从 JSON logger 升级为 Langfuse 深度集成，
      实现 LLM 调用全链路追踪、token/成本统计、会话级汇总。

改动范围：
  - 重写 app/harness/observability.py
  - 修改 app/agent/node_wrapper.py（接入新 API）
  - 修改 app/infrastructure/llm.py（调用 llm_span）
  - 新增 app/core/config.py 中 Langfuse 配置项
  - 新增 tests/unit/harness/test_observability.py（重写）

不动：
  - specs/ 规范文件、state/ 状态模型、其他节点代码

注意：
  - 本文档 3.7 节的 LLMService 仅为说明 llm_span 接入点，
    完整 LLMService 重写以 llm-redesign.md 3.3 为准
  - get_observability() 采用工厂模式（非全局单例），
    通过 os.getenv 自动选择实现，各实现自身无全局状态
```

## 第二层：概述

| 组件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `Observability` (ABC) | 定义可观测协议 | — | — |
| `LangfuseObservability` | 生产实现：Langfuse SDK 追踪 | 配置(3个env) | Trace/Span 写入 Langfuse |
| `ConsoleObservability` | 开发调试：结构化日志到 stdout | 无需配置 | 彩色结构化日志 |
| `FakeObservability` | 测试：记录所有调用供断言 | 无需配置 | `calls` 列表 |
| `LLMSpan` (dataclass) | 单次 LLM 调用的追踪数据 | model, prompt, tokens... | 传递给 Observability |
| `SessionStats` (dataclass) | 会话级汇总统计 | 多个 LLMSpan | 总token/总成本/节点耗时 |
| `get_observability()` | 工厂函数 | env/config | 返回对应实现实例 |

## 第三层：详细实施计划

### 3.1 Observability 协议定义

```python
# app/harness/observability.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

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
    def start_trace(self, session_id: str, metadata: dict | None = None) -> str:
        """开始一个 Trace，返回 trace_id"""

    @abstractmethod
    def end_trace(self, trace_id: str) -> None:
        """结束一个 Trace"""

    @abstractmethod
    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None) -> None:
        """记录节点级事件（兼容现有 safe_node 调用）"""

    @abstractmethod
    def llm_span(self, span: LLMSpan) -> None:
        """记录一次 LLM 调用的完整追踪数据"""

    @abstractmethod
    def metric(self, name: str, value: float, tags: dict | None = None) -> None:
        """记录自定义指标"""

    @abstractmethod
    def log(self, level: str, event: str, context: dict | None = None) -> None:
        """记录日志"""

    @abstractmethod
    def session_summary(self, session_id: str) -> SessionStats | None:
        """获取会话级汇总统计"""
```

### 3.2 LangfuseObservability 实现

```python
class LangfuseObservability(Observability):
    """生产实现：通过 Langfuse SDK 写入追踪数据"""

    def __init__(self, public_key: str, secret_key: str,
                 host: str = "https://cloud.langfuse.com"):
        from langfuse import Langfuse
        self._client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        self._traces: dict[str, Any] = {}
        self._spans: dict[str, Any] = {}
        self._sessions: dict[str, SessionStats] = {}

    def start_trace(self, session_id: str, metadata: dict | None = None) -> str:
        trace = self._client.trace(
            name=f"session_{session_id}",
            session_id=session_id,
            metadata=metadata or {},
        )
        self._traces[trace.id] = trace
        self._sessions[session_id] = SessionStats(session_id=session_id)
        return trace.id

    def end_trace(self, trace_id: str) -> None:
        self._traces.pop(trace_id, None)

    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None) -> None:
        trace_obj = self._find_trace_by_session(session_id)
        if trace_obj:
            trace_obj.span(
                name=f"{node}.{event}",
                metadata=data or {},
            )

    def llm_span(self, span: LLMSpan) -> None:
        trace_obj = self._find_trace_by_session(span.session_id)
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
        pass  # Langfuse 无原生 metric，后续可加 Prometheus export

    def log(self, level: str, event: str, context: dict | None = None) -> None:
        import logging
        logger = logging.getLogger("learning_agent")
        log_fn = getattr(logger, level, logger.info)
        log_fn({"event": event, **(context or {})})

    def session_summary(self, session_id: str) -> SessionStats | None:
        return self._sessions.get(session_id)

    def _find_trace_by_session(self, session_id: str):
        for trace in self._traces.values():
            if getattr(trace, 'session_id', None) == session_id:
                return trace
        return None
```

### 3.3 ConsoleObservability 实现

```python
class ConsoleObservability(Observability):
    """开发调试实现：结构化彩色日志输出到 stdout"""

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
        import json
        print(f"[{tag}] {json.dumps(kwargs, ensure_ascii=False, default=str)}")
```

### 3.4 FakeObservability 实现

```python
class FakeObservability(Observability):
    """测试实现：记录所有调用，支持断言"""

    def __init__(self):
        self.calls: list[dict] = []
        self._sessions: dict[str, SessionStats] = {}

    def start_trace(self, session_id: str, metadata: dict | None = None) -> str:
        self.calls.append({"method": "start_trace", "session_id": session_id})
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
        self.calls.append({"method": "metric", "name": name, "value": value})

    def log(self, level: str, event: str, context: dict | None = None) -> None:
        self.calls.append({"method": "log", "level": level, "event": event})

    def session_summary(self, session_id: str) -> SessionStats | None:
        return self._sessions.get(session_id)

    def assert_traced(self, method: str, **kwargs):
        """断言某次调用存在"""
        for call in self.calls:
            if call["method"] == method:
                if all(call.get(k) == v for k, v in kwargs.items()):
                    return
        raise AssertionError(f"未找到调用: {method} {kwargs}")
```

### 3.5 工厂函数改造

```python
def get_observability() -> Observability:
    """根据环境变量自动选择实现"""
    import os
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    if public_key and secret_key:
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        return LangfuseObservability(public_key, secret_key, host)
    return ConsoleObservability()
```

### 3.6 safe_node 改造

```python
# app/agent/node_wrapper.py — 改造后
# import 路径不变（仍从 observability 模块导入），但底层实现自动切换
# safe_node 自身逻辑不变，Observability 子类多态替代了原来的全局单例

from app.harness.error_handler import get_error_handler
from app.harness.observability import get_observability
from app.harness.state import LearningState

def safe_node(func):
    def wrapper(state: LearningState) -> dict:
        obs = get_observability()
        handler = get_error_handler()
        session_id = state.get("meta", {}).get("session_id", "")
        try:
            obs.trace(session_id, func.__name__, "start")
            result = func(state)
            obs.trace(session_id, func.__name__, "end")
            return result
        except Exception as e:
            obs.trace(session_id, func.__name__, "error", {"error": str(e)})
            return handler.handle(e, state)
    wrapper.__name__ = func.__name__
    return wrapper
```

### 3.7 LLMService 接入 llm_span（要点说明）

> 本节仅说明 llm_span 的接入点。LLMService 完整重写以 llm-redesign.md 3.3 为准。

接入方式：LLMService 的 `_call_with_span` 方法内部，在每次 LLM 调用完成后，
提取 `usage_metadata` 中的 token 用量，计算延迟和成本，构造 `LLMSpan` 传入 `obs.llm_span()`。
```

### 3.8 配置项

```python
# app/core/config.py 新增项

LANGFUSE_PUBLIC_KEY: str = ""
LANGFUSE_SECRET_KEY: str = ""
LANGFUSE_HOST: str = "https://cloud.langfuse.com"
```

### 3.9 测试计划

| 测试文件 | 覆盖内容 | 用例数 |
|----------|----------|--------|
| `test_observability.py` | FakeObservability 全方法断言 | 8 |
| `test_observability.py` | SessionStats 累加与 summary() | 4 |
| `test_observability.py` | ConsoleObservability 不报错 | 3 |
| `test_observability.py` | get_observability() 工厂选择逻辑 | 3 |
| `test_llm.py` | LLMService.invoke 写入 llm_span | 3 |
| `test_llm.py` | _calc_cost 各模型定价 | 3 |

合计：24 个测试用例
