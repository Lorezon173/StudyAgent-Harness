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
