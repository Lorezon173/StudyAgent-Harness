import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("study_agent")


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
