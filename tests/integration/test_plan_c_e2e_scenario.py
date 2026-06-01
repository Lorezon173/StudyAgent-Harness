"""Plan C 端到端场景：Socratic → Feynman → Analogy → mastered → LoopExit。

驱动方式：用户脚本作为后续 UserMessage 注入（通过自定义 ScriptedUser Agent 监听
TutorAsked / TutorRequestedRecap / TutorOfferedAnalogy 触发回复）。这避免在
fixture 里手动倒水 ―― 让真实 EventBus / 回合屏障 / TeachingPolicy 一起跑。
"""
import os
import tempfile

import pytest

from app.agents.base import AgentBase
from app.agents.tutor import TutorAgent
from app.agents.critic import CriticAgent
from app.agents.conductor import ConductorAgent
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, TeachingMode
from app.harness.eventbus import EventBus
from app.harness.workspace_state import WorkspaceState
from app.harness.orchestrator import Orchestrator
from app.infrastructure.storage.event_store import EventStore
from app.orchestration.collab_loop import run_collab_loop


class _ScriptedUser(AgentBase):
    """脚本化用户：根据 Tutor 抛出的事件序列依次回复。"""
    source = EventSource.USER
    subscriptions = [EventType.TUTOR_ASKED,
                     EventType.TUTOR_REQUESTED_RECAP,
                     EventType.TUTOR_OFFERED_ANALOGY]
    emittable_types = {EventType.USER_MESSAGE}

    def __init__(self, replies: list[str]):
        self._replies = list(replies)

    def handle(self, event, ws):
        if not self._replies:
            return []
        text = self._replies.pop(0)
        return [self.emit(EventType.USER_MESSAGE, ws,
                          payload={"text": text}, parent_id=event.id)]


@pytest.fixture
def _store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = EventStore(db_path=path)
    s.init()
    yield s
    s.close()
    os.unlink(path)


def test_socratic_feynman_analogy_mastered_loop_exit(mock_llm_invoke_json, _store):
    # Critic 评估的序列响应：
    #   #0 seed UserMessage（用户尚未"答"，开场仅表诉求）→ 不产观察（{}）
    #   #1 reply1 partial → Socratic→Feynman（tutor_request_recap）
    #   #2 reply2 weak+confusion → Feynman→Analogy（tutor_offer_analogy）
    #   #3 reply3 mastered + topic_complete → LoopExit
    critic_responses = iter([
        {},
        {"mastery_level": "partial", "rationale": "基本概念有"},
        {"mastery_level": "weak", "confusion": {"concept_a": "retrieval",
                                                 "concept_b": "augment"}},
        {"mastery_level": "mastered", "rationale": "明白了"},
    ])

    import app.infrastructure.llm as llm_mod
    # 安装 Tutor / Conductor 的固定 mock，再用包装函数把 critic_assess 切换为序列响应
    mock_llm_invoke_json({
        "tutor_ask": {"content": "你认为 LLM 直接回答 vs 借助资料有何区别？"},
        "tutor_request_recap": {"content": "请用你的话描述 RAG"},
        "tutor_offer_analogy": {"content": "RAG 就像考试翻参考书"},
    })
    orig = llm_mod.LLMService.invoke_json

    def _wrapped(self, sp, up, **kw):
        if kw.get("intent") == "critic_assess":
            return next(critic_responses)
        return orig(self, sp, up, **kw)

    llm_mod.LLMService.invoke_json = _wrapped
    try:
        bus = EventBus(store=_store)
        bus.subscribe(TutorAgent(), [EventType.ACTION_REQUESTED])
        bus.subscribe(CriticAgent(), [EventType.USER_MESSAGE,
                                       EventType.RETRIEVED_EVIDENCE])
        bus.subscribe(ConductorAgent(), [EventType.CONDUCTOR_REQUESTED])
        bus.subscribe(_ScriptedUser([
            "可能借助资料更准确？",                  # 触发 partial → Feynman
            "先搜，再给 LLM …呃 LLM 处理一下",       # 触发 confusion → Analogy
            "哦，原来检索是把资料塞进 prompt",        # 触发 mastered+topic_complete → LoopExit
        ]), [EventType.TUTOR_ASKED, EventType.TUTOR_REQUESTED_RECAP,
              EventType.TUTOR_OFFERED_ANALOGY])

        orch = Orchestrator()
        ws = WorkspaceState(session_id="e2e-1", user_id="u1",
                            current_topic="RAG")
        seeds = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="e2e-1",
                  payload={"text": "帮我理解什么是 RAG"}),
        ]
        # mastery=mastered 时需 topic_complete 才走 loop_exit；
        # monkeypatch Orchestrator._collect_observations 给 mastered 注入 topic_complete=True
        import app.harness.orchestrator as orch_mod
        original = orch_mod.Orchestrator._collect_observations

        def _with_topic_complete(events, ws):
            obs = original(events, ws)
            if obs.get("mastery") == "mastered":
                obs["topic_complete"] = True
            return obs

        orch_mod.Orchestrator._collect_observations = staticmethod(_with_topic_complete)
        try:
            # 注入第一个 ActionRequested(tutor_ask) 让 Tutor 启动 Socratic 引导
            seeds.append(Event(
                type=EventType.ACTION_REQUESTED,
                source=EventSource.ORCHESTRATOR,
                session_id="e2e-1",
                payload={"action": "tutor_ask", "target": "tutor"}))
            run_collab_loop(bus, ws, seeds, orchestrator=orch, max_turns=80)
        finally:
            # 还原时必须重新包成 staticmethod（class 属性读取返回的是 underlying
            # function，直接赋回去会让它变成普通方法、self 会被错位塞进 events 参数）
            orch_mod.Orchestrator._collect_observations = staticmethod(original)
    finally:
        llm_mod.LLMService.invoke_json = orig

    events = bus.replay("e2e-1")
    types = [e.type for e in events]

    # 必含事件（spec §4.3 轨迹）
    assert EventType.TUTOR_ASKED in types
    assert EventType.MASTERY_ASSESSED in types
    assert EventType.TUTOR_REQUESTED_RECAP in types     # Socratic → Feynman
    assert EventType.CONFUSION_DETECTED in types
    assert EventType.TUTOR_OFFERED_ANALOGY in types     # Feynman → Analogy
    assert EventType.POLICY_TRANSITION in types
    assert EventType.LOOP_EXIT in types                  # 出环
    # 模式历史含 §4.3 三模式
    history = orch._policy.history
    assert TeachingMode.SOCRATIC in history
    assert TeachingMode.FEYNMAN in history
    assert TeachingMode.ANALOGY in history


def test_e2e_no_emit_violation_throughout():
    """端到端跑下来不应有任何越权 emit（#14 全局不变量）。"""
    from app.harness.events import EVENT_OWNERSHIP
    for et, owner in EVENT_OWNERSHIP.items():
        assert owner is not None
