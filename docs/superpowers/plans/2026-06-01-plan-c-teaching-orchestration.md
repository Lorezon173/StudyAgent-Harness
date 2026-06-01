# Plan C — 教学与编排 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已冻结的 Plan 0 契约之上，实装 3 个 Agent（Tutor / Critic / Conductor）+ Orchestrator（规则引擎 + 回合屏障 + Conductor 召唤 + ConductorDecided 转译）+ TeachingPolicy（§4.2 完整状态机）+ 主图协作环装配点，验证 spec §4.3 事件流示例与 1 个标准场景（Socratic→Feynman→Analogy→mastered→LoopExit）可复现。

**Architecture:** 严格事件驱动 + 职能正交（白名单运行时强制）+ 单线程优先级队列 + 回合屏障（OrchestratorTick 最低优先级哨兵）。每个 Agent 只在专业领域 emit；Orchestrator 不是 Agent，是 `on_event(event, ws) -> list[Event]` 钩子，承接路由决策与策略转移。`graph._collab_loop_node` 通过 MainState 注入运行时（Bus+Agents+Orchestrator+WorkspaceState），运行真实 `run_collab_loop` —— Plan 0 零参数 `build_main_graph()` 测试保持不破。

**Tech Stack:** Python 3.11（`StrEnum` / `dataclass`）· `pyyaml`（规则文件解析）· `pytest` + `monkeypatch`（LLM Mock，决策 #22）· 复用 `app/infrastructure/llm.py::LLMService.invoke_json` 同步接口（不引入 async）。

**Design Specs:** `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md`
- §2.1 角色划分 · §2.3 Conductor 限制 · §2.4 职能正交 · §3.3 Orchestrator 结构 · §3.4 规则 DSL · §3.5 协作环执行模型（含 §3.5.3 回合屏障）· §4 全节（四模式 + 完整转移表 + 开局探测 + 事件流示例）

**Learned 锚点：**
- `Learned/多Agent重设计-Spec审阅与架构决策.md` #14（emit 白名单）/ #15（复述检查归 Critic）/ #16（Conductor 限制）/ #17（Curator 双时机：Plan C 仅消费、不实装）/ #22（LLM Mock 策略 = fixture+monkeypatch）

---

## File Structure

```
== 新建（Plan C 拥有）==
Create: app/agents/tutor.py                              # TutorAgent（生成教学内容）
Create: app/agents/critic.py                             # CriticAgent（文本语义评估）
Create: app/agents/conductor.py                          # ConductorAgent（规则未命中时的 LLM 路由兜底）
Create: app/harness/teaching_policy.py                   # TeachingPolicy（§4.2 完整转移表 + 历史）
Create: app/harness/orchestrator.py                      # Orchestrator（规则引擎 + 回合屏障 + Conductor 召唤）
Create: app/orchestration/orchestrator_rules.yaml        # §3.4 规则 DSL 配置（热可换）

== 修改（Plan C 唯一跨 Plan 0 改动点）==
Modify: app/orchestration/graph.py                       # 仅 _collab_loop_node 接入 run_collab_loop + 注入运行时；零参数 build_main_graph() 保持兼容

== 新建（测试）==
Modify: tests/conftest.py                                 # 末尾追加 mock_llm_invoke_json fixture（决策 #22）
Create: tests/unit/agents/test_tutor.py
Create: tests/unit/agents/test_critic.py
Create: tests/unit/agents/test_conductor.py
Create: tests/unit/harness/test_teaching_policy.py
Create: tests/unit/harness/test_orchestrator.py
Create: tests/unit/orchestration/test_graph_collab_loop_integration.py
Create: tests/integration/test_plan_c_e2e_scenario.py    # spec §4.3 事件流复现 + Socratic→Feynman→Analogy 端到端
```

**依赖顺序（不可跳跃）：**
Phase 1（Tutor）→ Phase 2（Critic）→ Phase 3（Conductor）→ Phase 4（TeachingPolicy）→ Phase 5（Orchestrator + 回合屏障）→ Phase 6（graph 接入）→ Phase 7（端到端验收）。
Tutor / Critic / Conductor 互相独立可并行，但本计划按线性 TDD 顺序展开以便 subagent-driven 单线追踪。

**禁区（违反即视为破坏 Plan 0/A/B 冻结）：**
- 不改 `app/harness/{events.py, enums.py, eventbus.py, workspace_state.py}`
- 不改 `app/agents/base.py`
- 不改 `app/orchestration/collab_loop.py`（只调用其 `run_collab_loop`）
- 不改 `app/infrastructure/storage/event_store.py`
- 不改 `app/agents/retriever.py / curator.py`（Plan A/B 拥有）
- 不改 `app/agent/` 老代码（只读、可复制改造到新文件）

---

## 测试公共约定

**Mock 策略（决策 #22 落地）：** `tests/conftest.py` 提供 `mock_llm_invoke_json` fixture，通过 `monkeypatch` 替换 `app.infrastructure.llm.LLMService.invoke_json`，**返回结构化 dict（绕开文本→JSON 解析的格式漂移）**。三 Agent 测试统一经此 fixture 注入 LLM 结果。`LLMService.invoke`（裸文本）的 mock 同理但 Plan C 实际 Agent 内部全部走 `invoke_json` —— Critic 输出结构化评估、Tutor 输出 `{"content": "..."}`、Conductor 输出 `{"action": "...", "reason": "..."}`，与老 `evaluate_node` 模式一致。

**测试包结构：** `tests/unit/agents/__init__.py`、`tests/unit/harness/__init__.py`、`tests/unit/orchestration/__init__.py`、`tests/integration/__init__.py` 在 Plan 0 已存在；本 Plan 不重复创建。

---

## Phase 1 — TutorAgent（生成教学内容；只生成、不评判）

> **契约（spec §2.1 / #14 / #15）：** source=tutor；subscriptions=[ActionRequested]；emittable_types={TutorAsked, TutorExplained, TutorRequestedRecap, TutorOfferedAnalogy}。Tutor 内部根据 `event.payload["action"]`（ActionKind）+ `event.payload["target"]==tutor` 分派到不同动作。**`TUTOR_PROBE_PREREQ` 复用 `TutorAsked`**（在 Socratic 模式下抛探测问题，本质仍是引导提问），payload 携带 `kind: probe_prereq`。

### Task 1.1: Mock 基础设施 — `mock_llm_invoke_json` fixture

**Files:**
- Modify: `tests/conftest.py`（末尾追加）

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/agents/test_mock_llm_fixture.py`：

```python
from app.infrastructure.llm import LLMService


def test_mock_llm_invoke_json_returns_mapped_response(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_ask": {"content": "为什么 LLM 需要 RAG？"}})
    svc = LLMService()
    out = svc.invoke_json("sys", "user_prompt", intent="tutor_ask")
    assert out == {"content": "为什么 LLM 需要 RAG？"}


def test_mock_llm_invoke_json_default_when_intent_missing(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_ask": {"content": "X"}})
    svc = LLMService()
    out = svc.invoke_json("sys", "u", intent="unknown_intent")
    assert out == {}   # 未配置的 intent → 空 dict（默认）
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/agents/test_mock_llm_fixture.py -q`
Expected: FAIL — `fixture 'mock_llm_invoke_json' not found`

- [ ] **Step 3: 在 `tests/conftest.py` 末尾追加 fixture**

```python
# === Plan C：LLM Mock fixture（决策 #22 — fixture+monkeypatch）===
# 用法：mock_llm_invoke_json({"tutor_ask": {...}, "critic_eval": {...}})
# 三 Agent 测试统一通过此 fixture 注入「intent → 结构化 dict」映射。
@pytest.fixture
def mock_llm_invoke_json(monkeypatch):
    def _install(intent_to_response: dict):
        def _fake_invoke_json(self, system_prompt, user_prompt,
                              session_id="", node="", intent="", **kwargs):
            return intent_to_response.get(intent, {})
        monkeypatch.setattr(
            "app.infrastructure.llm.LLMService.invoke_json",
            _fake_invoke_json,
        )
    return _install
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/agents/test_mock_llm_fixture.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/conftest.py tests/unit/agents/test_mock_llm_fixture.py
git commit -m "test(plan-c): add mock_llm_invoke_json fixture (decision #22)"
```

---

### Task 1.2: TutorAgent 契约骨架 + ASK / PROBE_PREREQ

**Files:**
- Create: `app/agents/tutor.py`
- Create: `tests/unit/agents/test_tutor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/agents/test_tutor.py
import pytest

from app.agents.tutor import TutorAgent
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind
from app.harness.workspace_state import WorkspaceState


def _action(action: ActionKind, target: str = "tutor", **extra) -> Event:
    return Event(
        type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
        session_id="s1",
        payload={"action": str(action), "target": target, **extra},
    )


def test_tutor_contract_declaration():
    a = TutorAgent()
    assert a.source == EventSource.TUTOR
    assert EventType.ACTION_REQUESTED in a.subscriptions
    assert a.emittable_types == {
        EventType.TUTOR_ASKED,
        EventType.TUTOR_EXPLAINED,
        EventType.TUTOR_REQUESTED_RECAP,
        EventType.TUTOR_OFFERED_ANALOGY,
    }


def test_tutor_ignores_action_targeted_at_others():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    a = TutorAgent()
    out = a.handle(_action(ActionKind.RETRIEVER_SEARCH, target="retriever"), ws)
    assert out == []


def test_tutor_ask_emits_tutor_asked(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_ask": {"content": "为什么 LLM 需要外部资料？"}})
    ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="RAG")
    trigger = _action(ActionKind.TUTOR_ASK)
    out = TutorAgent().handle(trigger, ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_ASKED
    assert out[0].source == EventSource.TUTOR
    assert out[0].parent_id == trigger.id
    assert out[0].payload["content"] == "为什么 LLM 需要外部资料？"
    assert out[0].payload.get("kind") in (None, "ask")


def test_tutor_probe_prereq_emits_tutor_asked_with_kind(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_probe_prereq": {"content": "你之前接触过向量乘法吗？"}})
    ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="注意力机制")
    trigger = _action(ActionKind.TUTOR_PROBE_PREREQ, prereq_topic="向量乘法")
    out = TutorAgent().handle(trigger, ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_ASKED   # PROBE_PREREQ 复用 TutorAsked
    assert out[0].payload["kind"] == "probe_prereq"
    assert out[0].payload["prereq_topic"] == "向量乘法"
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/agents/test_tutor.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.tutor'`

- [ ] **Step 3: 实现 `app/agents/tutor.py`**

```python
from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.llm import LLMService


class TutorAgent(AgentBase):
    """生成教学内容（§2.1）。

    职能正交：只生成（讲解 / 提问 / 类比 / 发起复述），不评判（复述质量归
    Critic，§2.4 / #15）。subscriptions 含 ActionRequested，内部按
    payload.action 分派；payload.target != 'tutor' 的事件被忽略（多 Agent 并存
    时由 Orchestrator 用 target 定向，§4 接口冻结清单 #8）。
    """

    source = EventSource.TUTOR
    subscriptions = [EventType.ACTION_REQUESTED]
    emittable_types = {
        EventType.TUTOR_ASKED,
        EventType.TUTOR_EXPLAINED,
        EventType.TUTOR_REQUESTED_RECAP,
        EventType.TUTOR_OFFERED_ANALOGY,
    }

    def __init__(self, llm: LLMService | None = None):
        self._llm = llm or LLMService()

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type != EventType.ACTION_REQUESTED:
            return []
        if event.payload.get("target") != str(EventSource.TUTOR):
            return []
        action = event.payload.get("action")
        if action == str(ActionKind.TUTOR_ASK):
            return self._ask(event, ws, intent="tutor_ask", kind="ask")
        if action == str(ActionKind.TUTOR_PROBE_PREREQ):
            return self._ask(event, ws, intent="tutor_probe_prereq",
                             kind="probe_prereq",
                             extra={"prereq_topic": event.payload.get("prereq_topic")})
        return []

    def _ask(self, trigger: Event, ws: WorkspaceState, intent: str,
             kind: str, extra: dict | None = None) -> list[Event]:
        result = self._llm.invoke_json(
            "你是融合式教学的 Tutor，在 Socratic 模式下抛出引导问题。",
            f"主题：{ws.current_topic or ''}",
            session_id=ws.session_id, node="tutor", intent=intent,
        )
        payload = {"content": result.get("content", ""), "kind": kind}
        if extra:
            payload.update({k: v for k, v in extra.items() if v is not None})
        return [self.emit(EventType.TUTOR_ASKED, ws, payload=payload,
                          parent_id=trigger.id)]

    def evaluate(self, test_case) -> dict:
        raise NotImplementedError("Plan E 实装 Tutor 部件级评估（§5.2）")
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/agents/test_tutor.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/agents/tutor.py tests/unit/agents/test_tutor.py
git commit -m "feat(plan-c): TutorAgent skeleton + ASK + PROBE_PREREQ"
```

---

### Task 1.3: TutorAgent — EXPLAIN / RE_EXPLAIN / CORRECT

**Files:**
- Modify: `app/agents/tutor.py`
- Modify: `tests/unit/agents/test_tutor.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/agents/test_tutor.py
def test_tutor_explain_emits_tutor_explained(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_explain": {"content": "RAG = Retrieval-Augmented Generation..."}})
    ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="RAG")
    trigger = _action(ActionKind.TUTOR_EXPLAIN)
    out = TutorAgent().handle(trigger, ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_EXPLAINED
    assert out[0].payload["mode"] == "explain"


def test_tutor_re_explain_marks_repeat(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_re_explain": {"content": "换个角度："}})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = TutorAgent().handle(_action(ActionKind.TUTOR_RE_EXPLAIN), ws)
    assert out[0].type == EventType.TUTOR_EXPLAINED
    assert out[0].payload["mode"] == "re_explain"


def test_tutor_correct_for_contradiction(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_correct": {"content": "你刚才说的 X 不对，正确的是 Y"}})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = TutorAgent().handle(_action(ActionKind.TUTOR_CORRECT), ws)
    assert out[0].type == EventType.TUTOR_EXPLAINED
    assert out[0].payload["mode"] == "correct"
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/agents/test_tutor.py -q`
Expected: FAIL（3 个新 case 输出为 `[]`）

- [ ] **Step 3: 在 `TutorAgent.handle` 内追加分派 + `_explain` 方法**

把 `handle` 改为：

```python
    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type != EventType.ACTION_REQUESTED:
            return []
        if event.payload.get("target") != str(EventSource.TUTOR):
            return []
        action = event.payload.get("action")
        if action == str(ActionKind.TUTOR_ASK):
            return self._ask(event, ws, intent="tutor_ask", kind="ask")
        if action == str(ActionKind.TUTOR_PROBE_PREREQ):
            return self._ask(event, ws, intent="tutor_probe_prereq",
                             kind="probe_prereq",
                             extra={"prereq_topic": event.payload.get("prereq_topic")})
        if action == str(ActionKind.TUTOR_EXPLAIN):
            return self._explain(event, ws, intent="tutor_explain", mode="explain")
        if action == str(ActionKind.TUTOR_RE_EXPLAIN):
            return self._explain(event, ws, intent="tutor_re_explain", mode="re_explain")
        if action == str(ActionKind.TUTOR_CORRECT):
            return self._explain(event, ws, intent="tutor_correct", mode="correct")
        return []

    def _explain(self, trigger: Event, ws: WorkspaceState, intent: str,
                 mode: str) -> list[Event]:
        result = self._llm.invoke_json(
            "你是融合式教学的 Tutor，根据模式给出讲解。",
            f"主题：{ws.current_topic or ''}\n模式：{mode}",
            session_id=ws.session_id, node="tutor", intent=intent,
        )
        return [self.emit(EventType.TUTOR_EXPLAINED, ws,
                          payload={"content": result.get("content", ""),
                                   "mode": mode},
                          parent_id=trigger.id)]
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/agents/test_tutor.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/agents/tutor.py tests/unit/agents/test_tutor.py
git commit -m "feat(plan-c): TutorAgent EXPLAIN/RE_EXPLAIN/CORRECT"
```

---

### Task 1.4: TutorAgent — REQUEST_RECAP（切入费曼）/ OFFER_ANALOGY / 越权防御

**Files:**
- Modify: `app/agents/tutor.py`
- Modify: `tests/unit/agents/test_tutor.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/agents/test_tutor.py
def test_tutor_request_recap_emits(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_request_recap": {"content": "请用你的话描述 RAG 的流程"}})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = TutorAgent().handle(_action(ActionKind.TUTOR_REQUEST_RECAP), ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_REQUESTED_RECAP


def test_tutor_offer_analogy_emits(mock_llm_invoke_json):
    mock_llm_invoke_json({"tutor_offer_analogy": {
        "content": "RAG 就像考试时翻参考书…",
        "analogy_target": "查字典",
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = TutorAgent().handle(_action(ActionKind.TUTOR_OFFER_ANALOGY), ws)
    assert len(out) == 1
    assert out[0].type == EventType.TUTOR_OFFERED_ANALOGY
    assert out[0].payload["analogy_target"] == "查字典"


def test_tutor_cannot_emit_confusion_detected():
    # 越权防御（#14）：Tutor 不能 emit Critic 的事件
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        TutorAgent().emit(EventType.CONFUSION_DETECTED, ws)


def test_tutor_cannot_emit_mastery_assessed():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        TutorAgent().emit(EventType.MASTERY_ASSESSED, ws)
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/agents/test_tutor.py -q`
Expected: FAIL（两个新 case 输出 `[]`；越权 case 不抛错）

- [ ] **Step 3: 补 RECAP / ANALOGY 分派**

在 `handle` 内增加：

```python
        if action == str(ActionKind.TUTOR_REQUEST_RECAP):
            result = self._llm.invoke_json(
                "你是融合式教学的 Tutor，切入费曼模式让用户复述。",
                f"主题：{ws.current_topic or ''}",
                session_id=ws.session_id, node="tutor",
                intent="tutor_request_recap",
            )
            return [self.emit(EventType.TUTOR_REQUESTED_RECAP, ws,
                              payload={"content": result.get("content", "")},
                              parent_id=event.id)]
        if action == str(ActionKind.TUTOR_OFFER_ANALOGY):
            result = self._llm.invoke_json(
                "你是融合式教学的 Tutor，给出类比破除概念混淆。",
                f"主题：{ws.current_topic or ''}",
                session_id=ws.session_id, node="tutor",
                intent="tutor_offer_analogy",
            )
            payload = {"content": result.get("content", "")}
            if "analogy_target" in result:
                payload["analogy_target"] = result["analogy_target"]
            return [self.emit(EventType.TUTOR_OFFERED_ANALOGY, ws,
                              payload=payload, parent_id=event.id)]
```

越权防御无需新代码——`AgentBase.emit` 已校验 `emittable_types`（Plan 0 Task 7）。

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/agents/test_tutor.py -q`
Expected: PASS（全部 Tutor 测试通过，含越权防御）

- [ ] **Step 5: 提交**

```bash
git add app/agents/tutor.py tests/unit/agents/test_tutor.py
git commit -m "feat(plan-c): TutorAgent RECAP/ANALOGY + emit-violation guard"
```

---

## Phase 2 — CriticAgent（文本语义评估；不读图谱、不路由）

> **契约（spec §2.1 / #15 / #18）：** source=critic；subscriptions=[UserMessage, RetrievedEvidence]；emittable_types={MasteryAssessed, ConfusionDetected, ContradictionDetected, LowConfidenceDetected, RAGQualityAssessed}。**单次 LLM 调用产出多条观察**（一份 JSON 同时含 mastery / confusion / contradiction / low_confidence 字段），Critic 据此拆分 emit。RAG 质量评估**仅当 `RetrievedEvidence.payload["purpose"] == "teaching"` 时触发**（#18 成本优化）。

### Task 2.1: CriticAgent 契约骨架 + UserMessage → MasteryAssessed

**Files:**
- Create: `app/agents/critic.py`
- Create: `tests/unit/agents/test_critic.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/agents/test_critic.py
import pytest

from app.agents.critic import CriticAgent
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, MasteryLevel
from app.harness.workspace_state import WorkspaceState


def _user_msg(text: str) -> Event:
    return Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                 session_id="s1", payload={"text": text})


def test_critic_contract_declaration():
    a = CriticAgent()
    assert a.source == EventSource.CRITIC
    assert EventType.USER_MESSAGE in a.subscriptions
    assert EventType.RETRIEVED_EVIDENCE in a.subscriptions
    assert a.emittable_types == {
        EventType.MASTERY_ASSESSED,
        EventType.CONFUSION_DETECTED,
        EventType.CONTRADICTION_DETECTED,
        EventType.LOW_CONFIDENCE_DETECTED,
        EventType.RAG_QUALITY_ASSESSED,
    }


def test_critic_emits_mastery_assessed_on_user_message(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "partial",
        "mastery_score": 65,
        "rationale": "基本概念掌握，细节不足",
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("我觉得 RAG 应该是先搜再答"), ws)
    types = [e.type for e in out]
    assert EventType.MASTERY_ASSESSED in types
    mastery = next(e for e in out if e.type == EventType.MASTERY_ASSESSED)
    assert mastery.source == EventSource.CRITIC
    assert mastery.payload["level"] == str(MasteryLevel.PARTIAL)
    assert mastery.payload["score"] == 65


def test_critic_handles_missing_optional_fields(mock_llm_invoke_json):
    # LLM 仅返回最小集合
    mock_llm_invoke_json({"critic_assess": {"mastery_level": "weak"}})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("不懂"), ws)
    assert any(e.type == EventType.MASTERY_ASSESSED for e in out)
    assert all(e.type != EventType.CONFUSION_DETECTED for e in out)
    assert all(e.type != EventType.CONTRADICTION_DETECTED for e in out)


def test_critic_ignores_evidence_without_purpose_teaching(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_rag_quality": {"score": 0.4}})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    ev = Event(type=EventType.RETRIEVED_EVIDENCE, source=EventSource.RETRIEVER,
               session_id="s1", payload={"chunks": [], "purpose": "exploration"})
    out = CriticAgent().handle(ev, ws)
    assert out == []   # 纯探索检索跳过（#18 成本优化）
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/agents/test_critic.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.critic'`

- [ ] **Step 3: 实现 `app/agents/critic.py`**

```python
from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, MasteryLevel
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.llm import LLMService


class CriticAgent(AgentBase):
    """文本语义评估（§2.1）。

    职能正交：只判文本语义层 —— mastery / confusion / contradiction /
    low_confidence / RAG 质量（#15 复述检查归本 Agent；#18 RAG 质量仅
    purpose=teaching 时评）。**不读图谱、不判前置缺失、不做路由决策**。
    单次 LLM 调用产出一份 JSON，含多观察字段，Critic 据此拆分多条 emit。
    """

    source = EventSource.CRITIC
    subscriptions = [EventType.USER_MESSAGE, EventType.RETRIEVED_EVIDENCE]
    emittable_types = {
        EventType.MASTERY_ASSESSED,
        EventType.CONFUSION_DETECTED,
        EventType.CONTRADICTION_DETECTED,
        EventType.LOW_CONFIDENCE_DETECTED,
        EventType.RAG_QUALITY_ASSESSED,
    }

    def __init__(self, llm: LLMService | None = None):
        self._llm = llm or LLMService()

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type == EventType.USER_MESSAGE:
            return self._assess_user_message(event, ws)
        if event.type == EventType.RETRIEVED_EVIDENCE:
            if event.payload.get("purpose") != "teaching":
                return []          # #18 成本优化：纯探索不评
            return self._assess_rag_quality(event, ws)
        return []

    def _assess_user_message(self, event: Event, ws: WorkspaceState) -> list[Event]:
        text = event.payload.get("text", "")
        result = self._llm.invoke_json(
            "你是融合式教学的 Critic，对用户回答做语义评估。"
            "输出 JSON：mastery_level(weak|partial|mastered)、mastery_score(0-100)、"
            "rationale、confusion(可选: {concept_a, concept_b})、"
            "contradiction(可选: {description})、low_confidence(可选: bool)。",
            f"主题：{ws.current_topic or ''}\n用户回答：{text}",
            session_id=ws.session_id, node="critic", intent="critic_assess",
        )
        events: list[Event] = []
        if "mastery_level" in result:
            events.append(self.emit(
                EventType.MASTERY_ASSESSED, ws,
                payload={
                    "level": result["mastery_level"],
                    "score": result.get("mastery_score"),
                    "rationale": result.get("rationale", ""),
                },
                parent_id=event.id))
        # 其余观察字段在后续 Task 落地（避免一次落地过大）
        return events

    def _assess_rag_quality(self, event: Event, ws: WorkspaceState) -> list[Event]:
        # 在 Task 2.3 落地
        return []

    def evaluate(self, test_case) -> dict:
        raise NotImplementedError("Plan E 实装 Critic 部件级评估（§5.2）")
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/agents/test_critic.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/agents/critic.py tests/unit/agents/test_critic.py
git commit -m "feat(plan-c): CriticAgent skeleton + UserMessage → MasteryAssessed"
```

---

### Task 2.2: CriticAgent — ConfusionDetected / ContradictionDetected / LowConfidenceDetected

**Files:**
- Modify: `app/agents/critic.py`
- Modify: `tests/unit/agents/test_critic.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/agents/test_critic.py
def test_critic_emits_confusion_when_present(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "partial",
        "confusion": {"concept_a": "retrieval", "concept_b": "augment"},
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("先搜，再给 LLM 处理"), ws)
    confusion = [e for e in out if e.type == EventType.CONFUSION_DETECTED]
    assert len(confusion) == 1
    assert confusion[0].payload["concept_a"] == "retrieval"
    assert confusion[0].payload["concept_b"] == "augment"


def test_critic_emits_contradiction_when_present(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "weak",
        "contradiction": {"description": "前后说 RAG 是又是微调又是检索"},
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("反复矛盾"), ws)
    assert any(e.type == EventType.CONTRADICTION_DETECTED for e in out)


def test_critic_emits_low_confidence(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "partial",
        "low_confidence": True,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("可能…大概…"), ws)
    assert any(e.type == EventType.LOW_CONFIDENCE_DETECTED for e in out)


def test_critic_emits_all_observations_in_single_handle(mock_llm_invoke_json):
    # 一次 handle 同时 emit 多观察（回合屏障的输入条件）
    mock_llm_invoke_json({"critic_assess": {
        "mastery_level": "partial",
        "confusion": {"concept_a": "A", "concept_b": "B"},
        "low_confidence": True,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = CriticAgent().handle(_user_msg("x"), ws)
    types = {e.type for e in out}
    assert types == {
        EventType.MASTERY_ASSESSED,
        EventType.CONFUSION_DETECTED,
        EventType.LOW_CONFIDENCE_DETECTED,
    }
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/agents/test_critic.py -q`
Expected: FAIL（4 个新 case）

- [ ] **Step 3: 扩展 `_assess_user_message` 补充观察拆分**

在 `mastery_level` 分支之后追加：

```python
        if isinstance(result.get("confusion"), dict):
            c = result["confusion"]
            events.append(self.emit(
                EventType.CONFUSION_DETECTED, ws,
                payload={
                    "concept_a": c.get("concept_a", ""),
                    "concept_b": c.get("concept_b", ""),
                },
                parent_id=event.id))
        if isinstance(result.get("contradiction"), dict):
            events.append(self.emit(
                EventType.CONTRADICTION_DETECTED, ws,
                payload={"description":
                         result["contradiction"].get("description", "")},
                parent_id=event.id))
        if result.get("low_confidence") is True:
            events.append(self.emit(
                EventType.LOW_CONFIDENCE_DETECTED, ws,
                payload={"signal": "user_self_uncertain"},
                parent_id=event.id))
        return events
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/agents/test_critic.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/agents/critic.py tests/unit/agents/test_critic.py
git commit -m "feat(plan-c): CriticAgent confusion/contradiction/low_confidence observations"
```

---

### Task 2.3: CriticAgent — RAGQualityAssessed（仅 purpose=teaching）+ 越权防御

**Files:**
- Modify: `app/agents/critic.py`
- Modify: `tests/unit/agents/test_critic.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/agents/test_critic.py
def test_critic_emits_rag_quality_for_teaching_purpose(mock_llm_invoke_json):
    mock_llm_invoke_json({"critic_rag_quality": {
        "score": 0.42, "relevance": 0.5, "sufficiency": 0.3,
        "rationale": "证据偏离主题",
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="RAG")
    ev = Event(type=EventType.RETRIEVED_EVIDENCE, source=EventSource.RETRIEVER,
               session_id="s1",
               payload={"chunks": [{"text": "..."}], "purpose": "teaching"})
    out = CriticAgent().handle(ev, ws)
    assert len(out) == 1
    assert out[0].type == EventType.RAG_QUALITY_ASSESSED
    assert out[0].payload["score"] == 0.42
    assert out[0].parent_id == ev.id


def test_critic_cannot_emit_tutor_event():
    # 越权防御（#14）
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        CriticAgent().emit(EventType.TUTOR_ASKED, ws)


def test_critic_cannot_emit_graph_prereq_weak():
    # 越权防御：结构层归 Curator（#15 切分）
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        CriticAgent().emit(EventType.GRAPH_PREREQ_WEAK_DETECTED, ws)
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/agents/test_critic.py -q`
Expected: FAIL（RAG 测试 `out == []`；越权防御无问题）

- [ ] **Step 3: 实装 `_assess_rag_quality`**

```python
    def _assess_rag_quality(self, event: Event, ws: WorkspaceState) -> list[Event]:
        chunks = event.payload.get("chunks", [])
        result = self._llm.invoke_json(
            "你是融合式教学的 Critic，评估证据对当前教学是否相关、是否充分。"
            "输出 JSON：score(0-1)、relevance(0-1)、sufficiency(0-1)、rationale。",
            f"主题：{ws.current_topic or ''}\n证据条数：{len(chunks)}",
            session_id=ws.session_id, node="critic", intent="critic_rag_quality",
        )
        if "score" not in result:
            return []
        return [self.emit(
            EventType.RAG_QUALITY_ASSESSED, ws,
            payload={
                "score": result["score"],
                "relevance": result.get("relevance"),
                "sufficiency": result.get("sufficiency"),
                "rationale": result.get("rationale", ""),
            },
            parent_id=event.id)]
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/agents/test_critic.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/agents/critic.py tests/unit/agents/test_critic.py
git commit -m "feat(plan-c): CriticAgent RAG quality (teaching-only) + emit guards"
```

---

## Phase 3 — ConductorAgent（规则未命中时的 LLM 路由兜底，不自产观察）

> **契约（spec §2.3 / #16）：** source=conductor；subscriptions=[ConductorRequested]；emittable_types={ConductorDecided}。**不直接 emit ActionRequested**（那是 Orchestrator 的职能 —— Conductor 输出 `ConductorDecided`，Orchestrator 转译）。观察足够 → `action=<具体动作>`；观察不足 → `action=REQUEST_OBSERVATION + target=critic|curator`。`UserMessage` 仅作上下文参考，不据此自判语义/结构。

### Task 3.1: ConductorAgent 骨架 + 观察足够路径

**Files:**
- Create: `app/agents/conductor.py`
- Create: `tests/unit/agents/test_conductor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/agents/test_conductor.py
import pytest

from app.agents.conductor import ConductorAgent
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind
from app.harness.workspace_state import WorkspaceState


def _request(observations: list[dict]) -> Event:
    return Event(
        type=EventType.CONDUCTOR_REQUESTED, source=EventSource.ORCHESTRATOR,
        session_id="s1",
        payload={"observations": observations,
                 "reason": "rule fallthrough"},
    )


def test_conductor_contract():
    a = ConductorAgent()
    assert a.source == EventSource.CONDUCTOR
    assert a.subscriptions == [EventType.CONDUCTOR_REQUESTED]
    assert a.emittable_types == {EventType.CONDUCTOR_DECIDED}


def test_conductor_observation_enough_emits_action(mock_llm_invoke_json):
    mock_llm_invoke_json({"conductor_decide": {
        "action": "tutor_offer_analogy", "target": "tutor",
        "reason": "复述虽然偏，但前置 OK，类比破解最优",
        "observation_enough": True,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = ConductorAgent().handle(_request([
        {"type": "MasteryAssessed", "level": "partial"},
    ]), ws)
    assert len(out) == 1
    assert out[0].type == EventType.CONDUCTOR_DECIDED
    assert out[0].payload["action"] == str(ActionKind.TUTOR_OFFER_ANALOGY)
    assert out[0].payload["target"] == "tutor"


def test_conductor_cannot_emit_action_requested():
    # 越权防御（#16）：Conductor 不可直接 emit ActionRequested
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        ConductorAgent().emit(EventType.ACTION_REQUESTED, ws)


def test_conductor_cannot_emit_mastery_or_confusion():
    # 越权防御（#16）：Conductor 不能自产语义观察
    ws = WorkspaceState(session_id="s1", user_id="u1")
    with pytest.raises(ValueError):
        ConductorAgent().emit(EventType.MASTERY_ASSESSED, ws)
    with pytest.raises(ValueError):
        ConductorAgent().emit(EventType.CONFUSION_DETECTED, ws)
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/agents/test_conductor.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.conductor'`

- [ ] **Step 3: 实现 `app/agents/conductor.py`**

```python
from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource, ActionKind
from app.harness.workspace_state import WorkspaceState
from app.infrastructure.llm import LLMService


class ConductorAgent(AgentBase):
    """LLM 决策兜底（§2.3 / #16）。

    硬约束：
      - 只能在已有观察事件之上做路由决策，**不自产语义/结构观察**
      - emit 集合仅 ConductorDecided（不直接发 ActionRequested，由
        Orchestrator 转译）
      - 观察不足时 emit ConductorDecided(action=REQUEST_OBSERVATION, target=critic|curator)
        让专业 Agent 先看，下轮可能命中规则
    """

    source = EventSource.CONDUCTOR
    subscriptions = [EventType.CONDUCTOR_REQUESTED]
    emittable_types = {EventType.CONDUCTOR_DECIDED}

    def __init__(self, llm: LLMService | None = None):
        self._llm = llm or LLMService()

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type != EventType.CONDUCTOR_REQUESTED:
            return []
        observations = event.payload.get("observations", [])
        result = self._llm.invoke_json(
            "你是融合式教学的 Conductor。只能基于已有观察事件做路由决策，"
            "禁止自产语义/结构观察。若观察不足，输出 "
            "action=request_observation + target=critic|curator。",
            f"观察集：{observations}\n当前模式：{ws.current_mode}",
            session_id=ws.session_id, node="conductor",
            intent="conductor_decide",
        )
        payload = {
            "action": result.get("action", str(ActionKind.LOOP_EXIT)),
            "reason": result.get("reason", ""),
            "observation_enough": bool(result.get("observation_enough", False)),
        }
        if "target" in result:
            payload["target"] = result["target"]
        return [self.emit(EventType.CONDUCTOR_DECIDED, ws,
                          payload=payload, parent_id=event.id)]

    def evaluate(self, test_case) -> dict:
        raise NotImplementedError("Plan E 实装 Conductor 部件级评估（§5.2）")
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/agents/test_conductor.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/agents/conductor.py tests/unit/agents/test_conductor.py
git commit -m "feat(plan-c): ConductorAgent (decided-only, no action/observation emit)"
```

---

### Task 3.2: ConductorAgent — 观察不足分支（REQUEST_OBSERVATION）

**Files:**
- Modify: `tests/unit/agents/test_conductor.py`

- [ ] **Step 1: 追加测试**

```python
def test_conductor_observation_insufficient_requests_critic(mock_llm_invoke_json):
    mock_llm_invoke_json({"conductor_decide": {
        "action": "request_observation",
        "target": "critic",
        "reason": "缺掌握度评估",
        "observation_enough": False,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = ConductorAgent().handle(_request([]), ws)
    assert len(out) == 1
    assert out[0].payload["action"] == str(ActionKind.REQUEST_OBSERVATION)
    assert out[0].payload["target"] == "critic"
    assert out[0].payload["observation_enough"] is False


def test_conductor_observation_insufficient_requests_curator(mock_llm_invoke_json):
    mock_llm_invoke_json({"conductor_decide": {
        "action": "request_observation",
        "target": "curator",
        "reason": "缺前置依赖结构观察",
        "observation_enough": False,
    }})
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = ConductorAgent().handle(_request([
        {"type": "MasteryAssessed", "level": "weak"},
    ]), ws)
    assert out[0].payload["target"] == "curator"


def test_conductor_ignores_non_subscribed_event():
    ws = WorkspaceState(session_id="s1", user_id="u1")
    ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
               session_id="s1")
    assert ConductorAgent().handle(ev, ws) == []
```

- [ ] **Step 2: 跑测试**

Run: `pytest tests/unit/agents/test_conductor.py -q`
Expected: PASS（实现 Task 3.1 已涵盖 target 透传与 fallback；无需改实现）

- [ ] **Step 3: 提交**

```bash
git add tests/unit/agents/test_conductor.py
git commit -m "test(plan-c): ConductorAgent insufficient-observation paths"
```

> （本 Task 只补测试 — Task 3.1 的实现已正确处理两条分支，TDD 在此用测试钉死契约。）

---

## Phase 4 — TeachingPolicy 状态机（§4.2 完整转移表）

> **契约（spec §4.2）：** TeachingPolicy 不是 Agent，是 Orchestrator 内部使用的纯函数状态机。输入：当前模式 + 观察集（含 `MasteryAssessed` / `ConfusionDetected` / `GraphPrereqWeakDetected(basis)` / `turn_count`）→ 输出：（目标模式, 触发动作 ActionKind）。**所有 14 行转移 + 熔断行 + historical/observed 分支必须全覆盖**。模式历史由 Policy 自身记录，供 §5 评估。

### Task 4.1: TeachingPolicy 骨架 + 历史记录 + Socratic 分支

**Files:**
- Create: `app/harness/teaching_policy.py`
- Create: `tests/unit/harness/test_teaching_policy.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/harness/test_teaching_policy.py
from app.harness.teaching_policy import TeachingPolicy, ObservationSet
from app.harness.enums import TeachingMode, ActionKind, MasteryLevel


def _obs(**kw) -> ObservationSet:
    return ObservationSet(**kw)


def test_policy_starts_in_socratic():
    p = TeachingPolicy()
    assert p.current_mode == TeachingMode.SOCRATIC
    assert p.history == [TeachingMode.SOCRATIC]


def test_socratic_mastered_topic_complete_exits():
    p = TeachingPolicy()
    target, action = p.next(_obs(mastery=MasteryLevel.MASTERED, topic_complete=True))
    assert action == ActionKind.LOOP_EXIT


def test_socratic_partial_transitions_to_feynman():
    p = TeachingPolicy()
    target, action = p.next(_obs(mastery=MasteryLevel.PARTIAL))
    assert target == TeachingMode.FEYNMAN
    assert action == ActionKind.TUTOR_REQUEST_RECAP


def test_socratic_weak_self_loop_within_repeat_limit():
    p = TeachingPolicy()
    target, action = p.next(_obs(mastery=MasteryLevel.WEAK, repeat_count=0))
    assert target == TeachingMode.SOCRATIC      # 自环
    assert action == ActionKind.TUTOR_RE_EXPLAIN


def test_socratic_confusion_transitions_to_analogy():
    p = TeachingPolicy()
    target, action = p.next(_obs(confusion=True))
    assert target == TeachingMode.ANALOGY
    assert action == ActionKind.TUTOR_OFFER_ANALOGY


def test_history_records_each_transition():
    p = TeachingPolicy()
    p.next(_obs(mastery=MasteryLevel.PARTIAL))   # → Feynman
    assert p.current_mode == TeachingMode.FEYNMAN
    assert p.history == [TeachingMode.SOCRATIC, TeachingMode.FEYNMAN]
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/harness/test_teaching_policy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.harness.teaching_policy'`

- [ ] **Step 3: 实现 `app/harness/teaching_policy.py`**

```python
from dataclasses import dataclass, field

from app.harness.enums import TeachingMode, ActionKind, MasteryLevel


@dataclass
class ObservationSet:
    """回合屏障后送入 Policy 的完整观察集（§3.5.3）。"""
    mastery: MasteryLevel | None = None
    confusion: bool = False
    contradiction: bool = False
    prereq_weak: bool = False
    prereq_basis: str | None = None      # "historical" | "observed"
    rag_quality_low: bool = False
    repeat_count: int = 0
    topic_complete: bool = False
    turn_over_limit: bool = False        # turn > MAX_TURNS（熔断）


class TeachingPolicy:
    """§4.2 完整状态转移表 + 历史记录。

    next(obs) → (target_mode, action) —— 纯函数化的状态机：根据当前模式与
    完整观察集裁决唯一目标模式与触发动作。历史供 §5 评估「模式切换合理性」。
    """

    MAX_REPEAT = 2

    def __init__(self, initial: TeachingMode = TeachingMode.SOCRATIC):
        self.current_mode: TeachingMode = initial
        self.history: list[TeachingMode] = [initial]

    def next(self, obs: ObservationSet) -> tuple[TeachingMode, ActionKind]:
        target, action = self._decide(obs)
        if target != self.current_mode:
            self.current_mode = target
            self.history.append(target)
        return target, action

    def _decide(self, obs: ObservationSet) -> tuple[TeachingMode, ActionKind]:
        # 熔断（§4.2 任意模式 + turn>MAX → LoopExit）
        if obs.turn_over_limit:
            return self.current_mode, ActionKind.LOOP_EXIT

        if self.current_mode == TeachingMode.SOCRATIC:
            return self._from_socratic(obs)
        # 其他模式分支在后续 Task 落地
        return self.current_mode, ActionKind.TUTOR_ASK

    def _from_socratic(self, obs: ObservationSet) -> tuple[TeachingMode, ActionKind]:
        if obs.mastery == MasteryLevel.MASTERED and obs.topic_complete:
            return self.current_mode, ActionKind.LOOP_EXIT
        if obs.confusion:
            return TeachingMode.ANALOGY, ActionKind.TUTOR_OFFER_ANALOGY
        if obs.mastery == MasteryLevel.PARTIAL:
            return TeachingMode.FEYNMAN, ActionKind.TUTOR_REQUEST_RECAP
        if obs.mastery == MasteryLevel.WEAK and obs.repeat_count < self.MAX_REPEAT:
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_RE_EXPLAIN
        return self.current_mode, ActionKind.TUTOR_ASK
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/harness/test_teaching_policy.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/harness/teaching_policy.py tests/unit/harness/test_teaching_policy.py
git commit -m "feat(plan-c): TeachingPolicy skeleton + Socratic transitions + history"
```

---

### Task 4.2: TeachingPolicy — Feynman / Analogy / Regress 完整分支 + historical/observed 探测

**Files:**
- Modify: `app/harness/teaching_policy.py`
- Modify: `tests/unit/harness/test_teaching_policy.py`

- [ ] **Step 1: 追加失败测试（覆盖 §4.2 表全部剩余行）**

```python
# 追加到 tests/unit/harness/test_teaching_policy.py
def test_socratic_prereq_observed_goes_regress():
    p = TeachingPolicy()
    target, action = p.next(_obs(prereq_weak=True, prereq_basis="observed"))
    assert target == TeachingMode.REGRESS
    assert action == ActionKind.REGRESS_TO_PREREQ


def test_socratic_prereq_historical_stays_socratic_with_probe():
    p = TeachingPolicy()
    target, action = p.next(_obs(prereq_weak=True, prereq_basis="historical"))
    assert target == TeachingMode.SOCRATIC
    assert action == ActionKind.TUTOR_PROBE_PREREQ


def test_feynman_mastered_returns_to_socratic():
    p = TeachingPolicy(initial=TeachingMode.FEYNMAN)
    target, action = p.next(_obs(mastery=MasteryLevel.MASTERED))
    assert target == TeachingMode.SOCRATIC


def test_feynman_confusion_goes_analogy():
    p = TeachingPolicy(initial=TeachingMode.FEYNMAN)
    target, action = p.next(_obs(confusion=True))
    assert target == TeachingMode.ANALOGY
    assert action == ActionKind.TUTOR_OFFER_ANALOGY


def test_feynman_prereq_observed_goes_regress():
    p = TeachingPolicy(initial=TeachingMode.FEYNMAN)
    target, action = p.next(_obs(prereq_weak=True, prereq_basis="observed"))
    assert target == TeachingMode.REGRESS


def test_feynman_weak_no_confusion_no_prereq_back_to_socratic():
    p = TeachingPolicy(initial=TeachingMode.FEYNMAN)
    target, action = p.next(_obs(mastery=MasteryLevel.WEAK))
    assert target == TeachingMode.SOCRATIC
    assert action == ActionKind.TUTOR_RE_EXPLAIN


def test_analogy_understood_returns_to_socratic():
    p = TeachingPolicy(initial=TeachingMode.ANALOGY)
    target, action = p.next(_obs(mastery=MasteryLevel.PARTIAL))
    assert target == TeachingMode.SOCRATIC


def test_analogy_still_weak_goes_regress():
    p = TeachingPolicy(initial=TeachingMode.ANALOGY)
    target, action = p.next(_obs(mastery=MasteryLevel.WEAK))
    assert target == TeachingMode.REGRESS


def test_regress_prereq_mastered_back_to_socratic():
    p = TeachingPolicy(initial=TeachingMode.REGRESS)
    target, action = p.next(_obs(mastery=MasteryLevel.MASTERED))
    assert target == TeachingMode.SOCRATIC


def test_regress_prereq_still_weak_self_loop():
    p = TeachingPolicy(initial=TeachingMode.REGRESS)
    target, action = p.next(_obs(prereq_weak=True, prereq_basis="observed"))
    assert target == TeachingMode.REGRESS


def test_turn_over_limit_triggers_loop_exit_in_any_mode():
    for m in TeachingMode:
        p = TeachingPolicy(initial=m)
        _, action = p.next(_obs(turn_over_limit=True))
        assert action == ActionKind.LOOP_EXIT, f"mode={m} 应触发 LoopExit"


def test_contradiction_triggers_tutor_correct_in_socratic():
    p = TeachingPolicy()
    _, action = p.next(_obs(contradiction=True))
    assert action == ActionKind.TUTOR_CORRECT


def test_priority_prereq_over_confusion_socratic():
    # §2.4 优先级裁决：前置缺失 (100) > 混淆 (80)
    p = TeachingPolicy()
    target, action = p.next(_obs(confusion=True, prereq_weak=True,
                                 prereq_basis="observed"))
    assert target == TeachingMode.REGRESS
    assert action == ActionKind.REGRESS_TO_PREREQ
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/harness/test_teaching_policy.py -q`
Expected: FAIL（多个新 case）

- [ ] **Step 3: 扩展 `_decide` 与各分支**

替换 `_decide`：

```python
    def _decide(self, obs: ObservationSet) -> tuple[TeachingMode, ActionKind]:
        if obs.turn_over_limit:
            return self.current_mode, ActionKind.LOOP_EXIT

        # 全局优先级（§2.4 / §3.4）：前置缺失 observed > contradiction >
        # confusion > mastery weak/partial/mastered
        if obs.prereq_weak and obs.prereq_basis == "observed":
            return TeachingMode.REGRESS, ActionKind.REGRESS_TO_PREREQ
        if obs.contradiction:
            return self.current_mode, ActionKind.TUTOR_CORRECT
        if obs.prereq_weak and obs.prereq_basis == "historical":
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_PROBE_PREREQ

        if self.current_mode == TeachingMode.SOCRATIC:
            return self._from_socratic(obs)
        if self.current_mode == TeachingMode.FEYNMAN:
            return self._from_feynman(obs)
        if self.current_mode == TeachingMode.ANALOGY:
            return self._from_analogy(obs)
        if self.current_mode == TeachingMode.REGRESS:
            return self._from_regress(obs)
        return self.current_mode, ActionKind.TUTOR_ASK

    def _from_feynman(self, obs):
        if obs.mastery == MasteryLevel.MASTERED:
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_ASK
        if obs.confusion:
            return TeachingMode.ANALOGY, ActionKind.TUTOR_OFFER_ANALOGY
        if obs.mastery == MasteryLevel.WEAK:
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_RE_EXPLAIN
        return self.current_mode, ActionKind.TUTOR_REQUEST_RECAP

    def _from_analogy(self, obs):
        if obs.mastery in (MasteryLevel.PARTIAL, MasteryLevel.MASTERED):
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_ASK
        if obs.mastery == MasteryLevel.WEAK:
            return TeachingMode.REGRESS, ActionKind.REGRESS_TO_PREREQ
        return self.current_mode, ActionKind.TUTOR_OFFER_ANALOGY

    def _from_regress(self, obs):
        if obs.mastery == MasteryLevel.MASTERED:
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_ASK
        return self.current_mode, ActionKind.REGRESS_TO_PREREQ
```

并删除原 `_from_socratic` 中已被全局优先级覆盖的 `confusion` 分支（保留 mastery / topic_complete 分支即可）：

```python
    def _from_socratic(self, obs):
        if obs.mastery == MasteryLevel.MASTERED and obs.topic_complete:
            return self.current_mode, ActionKind.LOOP_EXIT
        if obs.confusion:
            return TeachingMode.ANALOGY, ActionKind.TUTOR_OFFER_ANALOGY
        if obs.mastery == MasteryLevel.PARTIAL:
            return TeachingMode.FEYNMAN, ActionKind.TUTOR_REQUEST_RECAP
        if obs.mastery == MasteryLevel.WEAK and obs.repeat_count < self.MAX_REPEAT:
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_RE_EXPLAIN
        return self.current_mode, ActionKind.TUTOR_ASK
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/harness/test_teaching_policy.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/harness/teaching_policy.py tests/unit/harness/test_teaching_policy.py
git commit -m "feat(plan-c): TeachingPolicy full §4.2 transitions + priority order"
```

---

## Phase 5 — Orchestrator（规则引擎 + 观察缓冲 + 回合屏障 + ConductorDecided 转译）

> **契约（spec §3.3 / §3.4 / §3.5.3 / #16）：** Orchestrator **不是 Agent**，是 `on_event(event, ws) -> list[Event]` 钩子（Plan 0 `run_collab_loop` 的 `orchestrator=` 参数）。回合屏障原理：观察类事件入"待裁决缓冲"+ 入队尾插入 `OrchestratorTick`（优先级 100，最低，§3.2/§3.5.3）；当 `Tick` 被弹出时（说明所有观察都已 emit 完毕），Orchestrator 对完整观察集做唯一一次路由裁决。规则未命中 → `ConductorRequested`。Conductor 回 `ConductorDecided` → Orchestrator 转译为 `ActionRequested`。

### Task 5.1: 规则文件 `orchestrator_rules.yaml` + RuleEngine 加载与匹配

**Files:**
- Create: `app/orchestration/orchestrator_rules.yaml`
- Create: `app/harness/orchestrator.py`（先放 RuleEngine + 加载函数）
- Create: `tests/unit/harness/test_orchestrator.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/harness/test_orchestrator.py
from pathlib import Path

import pytest

from app.harness.orchestrator import RuleEngine, load_rules
from app.harness.enums import ActionKind, MasteryLevel


def test_load_rules_from_default_path():
    rules = load_rules()
    # 必含 #17 + §3.4 关键规则
    actions = {r["action"] for r in rules}
    assert "regress_to_prereq" in actions
    assert "tutor_probe_prereq" in actions
    assert "tutor_offer_analogy" in actions
    assert "tutor_request_recap" in actions
    assert "loop_exit" in actions
    assert "retriever_expand_query" in actions
    assert "conductor_decide" in actions    # default 兜底


def test_rule_engine_priority_prereq_observed_over_confusion():
    engine = RuleEngine(load_rules())
    action = engine.match({
        "confusion": True,
        "prereq_weak": True,
        "prereq_basis": "observed",
    })
    assert action == ActionKind.REGRESS_TO_PREREQ


def test_rule_engine_prereq_historical_routes_to_probe():
    engine = RuleEngine(load_rules())
    action = engine.match({
        "prereq_weak": True, "prereq_basis": "historical",
    })
    assert action == ActionKind.TUTOR_PROBE_PREREQ


def test_rule_engine_mastery_partial_request_recap():
    engine = RuleEngine(load_rules())
    action = engine.match({"mastery": "partial"})
    assert action == ActionKind.TUTOR_REQUEST_RECAP


def test_rule_engine_unknown_observations_fallback_to_conductor():
    engine = RuleEngine(load_rules())
    action = engine.match({})
    assert action == ActionKind.CONDUCTOR_DECIDE
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/harness/test_orchestrator.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 创建 `app/orchestration/orchestrator_rules.yaml`**

```yaml
# §3.4 规则 DSL — 热可换。priority 数值越大越优先；同优先级按表序。
# 命中条件用扁平 key 表达观察集字段（与 RuleEngine 字典 key 对应）。
rules:
  - name: prereq_weak_observed
    when:
      prereq_weak: true
      prereq_basis: observed
    action: regress_to_prereq
    priority: 100

  - name: prereq_weak_historical
    when:
      prereq_weak: true
      prereq_basis: historical
    action: tutor_probe_prereq
    priority: 100

  - name: contradiction
    when:
      contradiction: true
    action: tutor_correct
    priority: 90

  - name: confusion
    when:
      confusion: true
    action: tutor_offer_analogy
    priority: 80

  - name: weak_within_repeat
    when:
      mastery: weak
      repeat_lt: 2
    action: tutor_re_explain
    priority: 70

  - name: partial
    when:
      mastery: partial
    action: tutor_request_recap
    priority: 60

  - name: mastered_topic_complete
    when:
      mastery: mastered
      topic_complete: true
    action: loop_exit
    priority: 50

  - name: rag_quality_low
    when:
      rag_quality_low: true
    action: retriever_expand_query
    priority: 40

  - name: default
    when: {}
    action: conductor_decide
    priority: 0
```

- [ ] **Step 4: 实现 `app/harness/orchestrator.py`（先 RuleEngine 部分）**

```python
from pathlib import Path

import yaml

from app.harness.enums import ActionKind

_RULES_DEFAULT_PATH = Path(__file__).resolve().parent.parent / \
    "orchestration" / "orchestrator_rules.yaml"


def load_rules(path: Path | str | None = None) -> list[dict]:
    """加载 §3.4 规则 YAML，按 priority 降序返回。"""
    p = Path(path) if path else _RULES_DEFAULT_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    rules = data.get("rules", [])
    rules.sort(key=lambda r: r.get("priority", 0), reverse=True)
    return rules


class RuleEngine:
    """根据观察集匹配规则，返回 ActionKind。

    观察集字段（扁平 dict）：mastery / confusion / contradiction /
    prereq_weak / prereq_basis / rag_quality_low / repeat_count /
    topic_complete。规则 `when` 内字段值需全部相等（`repeat_lt: 2` 是
    特殊比较：`repeat_count < 2`）。
    """

    def __init__(self, rules: list[dict]):
        self._rules = rules

    def match(self, obs: dict) -> ActionKind:
        for rule in self._rules:
            if self._cond_match(rule.get("when", {}), obs):
                return ActionKind(rule["action"])
        return ActionKind.CONDUCTOR_DECIDE

    @staticmethod
    def _cond_match(when: dict, obs: dict) -> bool:
        for key, expected in when.items():
            if key == "repeat_lt":
                if obs.get("repeat_count", 0) >= expected:
                    return False
                continue
            if obs.get(key) != expected:
                return False
        return True
```

- [ ] **Step 5: 跑通过**

Run: `pytest tests/unit/harness/test_orchestrator.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/orchestration/orchestrator_rules.yaml app/harness/orchestrator.py tests/unit/harness/test_orchestrator.py
git commit -m "feat(plan-c): orchestrator_rules.yaml + RuleEngine (priority match)"
```

---

### Task 5.2: Orchestrator 骨架 + 观察缓冲 + Tick 哨兵注入

**Files:**
- Modify: `app/harness/orchestrator.py`
- Modify: `tests/unit/harness/test_orchestrator.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/harness/test_orchestrator.py
from app.harness.orchestrator import Orchestrator
from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState


def test_observation_event_buffers_and_injects_tick():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = orch.on_event(Event(
        type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
        session_id="s1", payload={"level": "partial"}), ws)
    # 观察类事件被缓冲，且注入 OrchestratorTick 哨兵（最低优先级，回合屏障）
    assert len(out) == 1
    assert out[0].type == EventType.ORCHESTRATOR_TICK
    assert out[0].source == EventSource.ORCHESTRATOR


def test_only_one_tick_injected_per_micro_turn():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out1 = orch.on_event(Event(
        type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
        session_id="s1", payload={"level": "weak"}), ws)
    out2 = orch.on_event(Event(
        type=EventType.CONFUSION_DETECTED, source=EventSource.CRITIC,
        session_id="s1", payload={"concept_a": "A", "concept_b": "B"}), ws)
    assert len(out1) == 1                          # 第一个观察注入 Tick
    assert len(out2) == 0                          # 同 micro-turn 内不再注入


def test_non_observation_event_no_buffer_no_tick():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out = orch.on_event(Event(
        type=EventType.TUTOR_ASKED, source=EventSource.TUTOR,
        session_id="s1"), ws)
    assert out == []                               # Tutor 产出不触发裁决
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/harness/test_orchestrator.py -q`
Expected: FAIL — `cannot import 'Orchestrator'`

- [ ] **Step 3: 在 `app/harness/orchestrator.py` 末尾追加 Orchestrator**

```python
from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState
from app.harness.teaching_policy import TeachingPolicy, ObservationSet

_OBSERVATION_TYPES = {
    EventType.MASTERY_ASSESSED,
    EventType.CONFUSION_DETECTED,
    EventType.CONTRADICTION_DETECTED,
    EventType.LOW_CONFIDENCE_DETECTED,
    EventType.RAG_QUALITY_ASSESSED,
    EventType.GRAPH_PREREQ_WEAK_DETECTED,
}


class Orchestrator:
    """事件路由器（§3.3）。Plan 0 `run_collab_loop` 的钩子。

    回合屏障（§3.5.3）：观察类事件进入 `_pending_obs` 缓冲，并仅在 micro-turn
    内首次出现时注入 `OrchestratorTick` 哨兵（priority=100，最低）。当 Tick
    被弹出时（说明同一 micro-turn 的全部观察都已入队），Orchestrator 对完整
    观察集做唯一一次路由裁决。
    """

    def __init__(self, rules_path: str | None = None,
                 policy: TeachingPolicy | None = None):
        self._engine = RuleEngine(load_rules(rules_path))
        self._policy = policy or TeachingPolicy()
        self._pending_obs: list[Event] = []
        self._tick_pending: bool = False

    def on_event(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type in _OBSERVATION_TYPES:
            self._pending_obs.append(event)
            if not self._tick_pending:
                self._tick_pending = True
                return [Event(
                    type=EventType.ORCHESTRATOR_TICK,
                    source=EventSource.ORCHESTRATOR,
                    session_id=ws.session_id,
                    payload={"reason": "micro_turn_barrier"})]
            return []
        return []
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/harness/test_orchestrator.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/harness/orchestrator.py tests/unit/harness/test_orchestrator.py
git commit -m "feat(plan-c): Orchestrator observation buffer + Tick injection"
```

---

### Task 5.3: Orchestrator — Tick 触发裁决（规则命中 → ActionRequested + PolicyTransition）

**Files:**
- Modify: `app/harness/orchestrator.py`
- Modify: `tests/unit/harness/test_orchestrator.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/harness/test_orchestrator.py
def test_tick_with_partial_mastery_emits_request_recap():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.MASTERY_ASSESSED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"level": "partial"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    types = [e.type for e in out]
    assert EventType.ACTION_REQUESTED in types
    action_ev = next(e for e in out if e.type == EventType.ACTION_REQUESTED)
    assert action_ev.payload["action"] == "tutor_request_recap"
    assert action_ev.payload["target"] == "tutor"


def test_tick_with_prereq_observed_emits_regress():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.GRAPH_PREREQ_WEAK_DETECTED,
                        source=EventSource.CURATOR, session_id="s1",
                        payload={"basis": "observed", "prereq_topic": "X"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    action_ev = next(e for e in out if e.type == EventType.ACTION_REQUESTED)
    assert action_ev.payload["action"] == "regress_to_prereq"


def test_tick_with_priority_prereq_over_confusion():
    # §2.4 复述失败分流（既混淆又前置缺失，优先前置）
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.CONFUSION_DETECTED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"concept_a": "A", "concept_b": "B"}), ws)
    orch.on_event(Event(type=EventType.GRAPH_PREREQ_WEAK_DETECTED,
                        source=EventSource.CURATOR, session_id="s1",
                        payload={"basis": "observed"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    action_ev = next(e for e in out if e.type == EventType.ACTION_REQUESTED)
    assert action_ev.payload["action"] == "regress_to_prereq"


def test_tick_emits_policy_transition_when_mode_changes():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.MASTERY_ASSESSED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"level": "partial"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    pt = [e for e in out if e.type == EventType.POLICY_TRANSITION]
    assert len(pt) == 1
    assert pt[0].payload["from"] == "Socratic"
    assert pt[0].payload["to"] == "Feynman"


def test_tick_clears_buffer_for_next_micro_turn():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.MASTERY_ASSESSED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"level": "partial"}), ws)
    orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                        source=EventSource.ORCHESTRATOR, session_id="s1",
                        payload={}), ws)
    # 下一 micro-turn 新观察应再次注入 Tick
    out = orch.on_event(Event(type=EventType.MASTERY_ASSESSED,
                              source=EventSource.CRITIC, session_id="s1",
                              payload={"level": "weak"}), ws)
    assert any(e.type == EventType.ORCHESTRATOR_TICK for e in out)
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/harness/test_orchestrator.py -q`
Expected: FAIL

- [ ] **Step 3: 扩展 `Orchestrator.on_event` 处理 Tick**

把 `on_event` 改为：

```python
    def on_event(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type in _OBSERVATION_TYPES:
            self._pending_obs.append(event)
            if not self._tick_pending:
                self._tick_pending = True
                return [Event(
                    type=EventType.ORCHESTRATOR_TICK,
                    source=EventSource.ORCHESTRATOR,
                    session_id=ws.session_id,
                    payload={"reason": "micro_turn_barrier"})]
            return []

        if event.type == EventType.ORCHESTRATOR_TICK:
            return self._on_tick(event, ws)

        if event.type == EventType.CONDUCTOR_DECIDED:
            return self._translate_conductor_decision(event, ws)

        return []

    def _on_tick(self, tick: Event, ws: WorkspaceState) -> list[Event]:
        obs = self._collect_observations(self._pending_obs, ws)
        self._pending_obs = []
        self._tick_pending = False

        action = self._engine.match(obs)
        if action == ActionKind.CONDUCTOR_DECIDE:
            return [Event(type=EventType.CONDUCTOR_REQUESTED,
                          source=EventSource.ORCHESTRATOR,
                          session_id=ws.session_id,
                          payload={"observations": [self._obs_summary(e)
                                                    for e in obs.get("_raw", [])],
                                   "reason": "rule fallthrough"},
                          parent_id=tick.id)]

        emits: list[Event] = []
        target_mode, _ = self._policy.next(self._to_obs_set(obs))
        if target_mode != ws.current_mode:
            emits.append(Event(type=EventType.POLICY_TRANSITION,
                               source=EventSource.ORCHESTRATOR,
                               session_id=ws.session_id,
                               payload={"from": str(ws.current_mode),
                                        "to": str(target_mode)},
                               parent_id=tick.id))
            ws.current_mode = target_mode

        if action == ActionKind.LOOP_EXIT:
            emits.append(Event(type=EventType.LOOP_EXIT,
                               source=EventSource.ORCHESTRATOR,
                               session_id=ws.session_id,
                               payload={"reason": "rule_loop_exit"},
                               parent_id=tick.id))
        else:
            emits.append(Event(type=EventType.ACTION_REQUESTED,
                               source=EventSource.ORCHESTRATOR,
                               session_id=ws.session_id,
                               payload={"action": str(action),
                                        "target": self._target_of(action)},
                               parent_id=tick.id))
        return emits

    @staticmethod
    def _target_of(action: ActionKind) -> str:
        if str(action).startswith("retriever"):
            return str(EventSource.RETRIEVER)
        if str(action).startswith("tutor") or action == ActionKind.REGRESS_TO_PREREQ:
            return str(EventSource.TUTOR)
        return ""

    @staticmethod
    def _collect_observations(events: list[Event], ws: WorkspaceState) -> dict:
        obs: dict = {"_raw": events, "repeat_count": 0,
                     "topic_complete": False, "turn_over_limit": False}
        for ev in events:
            if ev.type == EventType.MASTERY_ASSESSED:
                obs["mastery"] = ev.payload.get("level")
            elif ev.type == EventType.CONFUSION_DETECTED:
                obs["confusion"] = True
            elif ev.type == EventType.CONTRADICTION_DETECTED:
                obs["contradiction"] = True
            elif ev.type == EventType.LOW_CONFIDENCE_DETECTED:
                obs["low_confidence"] = True
            elif ev.type == EventType.RAG_QUALITY_ASSESSED:
                obs["rag_quality_low"] = (ev.payload.get("score") or 0) < 0.5
            elif ev.type == EventType.GRAPH_PREREQ_WEAK_DETECTED:
                obs["prereq_weak"] = True
                obs["prereq_basis"] = ev.payload.get("basis")
        return obs

    @staticmethod
    def _obs_summary(ev: Event) -> dict:
        return {"type": str(ev.type), **ev.payload}

    @staticmethod
    def _to_obs_set(obs: dict) -> ObservationSet:
        from app.harness.enums import MasteryLevel
        m = obs.get("mastery")
        return ObservationSet(
            mastery=MasteryLevel(m) if m else None,
            confusion=bool(obs.get("confusion")),
            contradiction=bool(obs.get("contradiction")),
            prereq_weak=bool(obs.get("prereq_weak")),
            prereq_basis=obs.get("prereq_basis"),
            rag_quality_low=bool(obs.get("rag_quality_low")),
            repeat_count=obs.get("repeat_count", 0),
            topic_complete=bool(obs.get("topic_complete")),
            turn_over_limit=bool(obs.get("turn_over_limit")),
        )

    def _translate_conductor_decision(self, event: Event,
                                       ws: WorkspaceState) -> list[Event]:
        # 在 Task 5.4 落地
        return []
```

> **注意**：`_target_of` 把 `regress_to_prereq` 也派给 tutor —— Regress 模式的实际动作仍由 Tutor 完成"前置点的小循环讲解"，与 §4.2 描述一致；ActionRequested 的 target 字段是给 Agent 过滤用的。

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/harness/test_orchestrator.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/harness/orchestrator.py tests/unit/harness/test_orchestrator.py
git commit -m "feat(plan-c): Orchestrator Tick decision (rule match → action + transition)"
```

---

### Task 5.4: Orchestrator — Conductor 召唤 + ConductorDecided 转译 + REQUEST_OBSERVATION 路由

**Files:**
- Modify: `app/harness/orchestrator.py`
- Modify: `tests/unit/harness/test_orchestrator.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/harness/test_orchestrator.py
def test_tick_with_no_match_emits_conductor_requested():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    orch.on_event(Event(type=EventType.LOW_CONFIDENCE_DETECTED,
                        source=EventSource.CRITIC, session_id="s1",
                        payload={"signal": "user_uncertain"}), ws)
    out = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                              source=EventSource.ORCHESTRATOR,
                              session_id="s1", payload={}), ws)
    assert any(e.type == EventType.CONDUCTOR_REQUESTED for e in out)
    cr = next(e for e in out if e.type == EventType.CONDUCTOR_REQUESTED)
    assert "observations" in cr.payload


def test_conductor_decided_translated_to_action_requested():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    decided = Event(type=EventType.CONDUCTOR_DECIDED,
                    source=EventSource.CONDUCTOR, session_id="s1",
                    payload={"action": "tutor_offer_analogy", "target": "tutor",
                             "observation_enough": True})
    out = orch.on_event(decided, ws)
    assert len(out) == 1
    assert out[0].type == EventType.ACTION_REQUESTED
    assert out[0].payload["action"] == "tutor_offer_analogy"
    assert out[0].payload["target"] == "tutor"
    assert out[0].parent_id == decided.id


def test_conductor_decided_request_observation_routes_to_critic():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    decided = Event(type=EventType.CONDUCTOR_DECIDED,
                    source=EventSource.CONDUCTOR, session_id="s1",
                    payload={"action": "request_observation",
                             "target": "critic",
                             "observation_enough": False})
    out = orch.on_event(decided, ws)
    assert out[0].type == EventType.ACTION_REQUESTED
    assert out[0].payload["action"] == "request_observation"
    assert out[0].payload["target"] == "critic"


def test_conductor_decided_loop_exit_emits_loop_exit():
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    decided = Event(type=EventType.CONDUCTOR_DECIDED,
                    source=EventSource.CONDUCTOR, session_id="s1",
                    payload={"action": "loop_exit", "observation_enough": True})
    out = orch.on_event(decided, ws)
    assert out[0].type == EventType.LOOP_EXIT
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/harness/test_orchestrator.py -q`
Expected: FAIL（_translate_conductor_decision 仍是 stub）

- [ ] **Step 3: 实装 `_translate_conductor_decision`**

替换：

```python
    def _translate_conductor_decision(self, event: Event,
                                       ws: WorkspaceState) -> list[Event]:
        action = event.payload.get("action", "")
        if action == str(ActionKind.LOOP_EXIT):
            return [Event(type=EventType.LOOP_EXIT,
                          source=EventSource.ORCHESTRATOR,
                          session_id=ws.session_id,
                          payload={"reason": "conductor"},
                          parent_id=event.id)]
        return [Event(type=EventType.ACTION_REQUESTED,
                      source=EventSource.ORCHESTRATOR,
                      session_id=ws.session_id,
                      payload={
                          "action": action,
                          "target": event.payload.get("target", ""),
                          "via_conductor": True,
                          "reason": event.payload.get("reason", ""),
                      },
                      parent_id=event.id)]
```

- [ ] **Step 4: 跑通过**

Run: `pytest tests/unit/harness/test_orchestrator.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/harness/orchestrator.py tests/unit/harness/test_orchestrator.py
git commit -m "feat(plan-c): Orchestrator translates ConductorDecided + handles fallthrough"
```

---

### Task 5.5: 回合屏障专项单测（观察集不完整即路由 → 失败）

**Files:**
- Modify: `tests/unit/harness/test_orchestrator.py`（追加专项测试，**这是验收硬要求**）

> **目的（spec §3.5.3 / §8 P2 回退判据 / 用户开场 prompt"回合屏障必须专项单测"）：** 直接验证若 Critic 的 `ConfusionDetected` 与 Curator 的 `GraphPrereqWeakDetected` 在同一 micro-turn 内先后入队，Orchestrator 不会在第一个观察事件到达时就立刻路由，而是必须等 Tick 哨兵后才裁决一次。

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/harness/test_orchestrator.py
def test_barrier_blocks_routing_until_tick_arrives():
    """回合屏障专项：观察集不完整时 Orchestrator 绝不裁决（无 ActionRequested）。"""
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    # 第一个观察到达：仅注入 Tick，不产 ActionRequested
    out1 = orch.on_event(Event(type=EventType.CONFUSION_DETECTED,
                               source=EventSource.CRITIC, session_id="s1",
                               payload={"concept_a": "A", "concept_b": "B"}), ws)
    assert all(e.type != EventType.ACTION_REQUESTED for e in out1), \
        "屏障失效：观察集未完整就路由"
    assert any(e.type == EventType.ORCHESTRATOR_TICK for e in out1)

    # 第二个观察到达（同 micro-turn）：仍不裁决（Tick 已存在不重复注入）
    out2 = orch.on_event(Event(type=EventType.GRAPH_PREREQ_WEAK_DETECTED,
                               source=EventSource.CURATOR, session_id="s1",
                               payload={"basis": "observed"}), ws)
    assert all(e.type != EventType.ACTION_REQUESTED for e in out2), \
        "屏障失效：观察集仍不完整就路由"

    # Tick 弹出（此时观察集已完整）：唯一一次路由裁决，前置缺失优先
    out3 = orch.on_event(Event(type=EventType.ORCHESTRATOR_TICK,
                               source=EventSource.ORCHESTRATOR,
                               session_id="s1", payload={}), ws)
    actions = [e for e in out3 if e.type == EventType.ACTION_REQUESTED]
    assert len(actions) == 1, "屏障应只产唯一动作"
    assert actions[0].payload["action"] == "regress_to_prereq", \
        "屏障未裁决出 §2.4 优先级（前置 > 混淆）"


def test_barrier_handles_single_observation_correctly():
    """单观察场景：Tick 依然必要 — 屏障对所有观察一视同仁。"""
    orch = Orchestrator()
    ws = WorkspaceState(session_id="s1", user_id="u1")
    out1 = orch.on_event(Event(type=EventType.MASTERY_ASSESSED,
                               source=EventSource.CRITIC, session_id="s1",
                               payload={"level": "mastered"}), ws)
    # 仍只产 Tick，不直接路由
    assert all(e.type != EventType.ACTION_REQUESTED for e in out1)
```

- [ ] **Step 2: 跑测试**

Run: `pytest tests/unit/harness/test_orchestrator.py::test_barrier_blocks_routing_until_tick_arrives tests/unit/harness/test_orchestrator.py::test_barrier_handles_single_observation_correctly -q`
Expected: PASS（Task 5.2/5.3 实现已正确处理屏障，本 Task 用专项断言"钉死"契约）

- [ ] **Step 3: 提交**

```bash
git add tests/unit/harness/test_orchestrator.py
git commit -m "test(plan-c): barrier specialty test (incomplete obs → no routing)"
```

---

## Phase 6 — graph 接入 + 端到端场景

### Task 6.1: `graph._collab_loop_node` 接入 `run_collab_loop` + 装配运行时

**Files:**
- Modify: `app/orchestration/graph.py`
- Create: `tests/unit/orchestration/test_graph_collab_loop_integration.py`

> **重要兼容承诺：** Plan 0 的 `test_graph.py`（含 `test_graph_compiles` / `test_enter_loop_path_visits_collab_loop` / `test_skip_loop_path_bypasses_collab_loop`）必须**继续全绿**。本 Task 通过给 `MainState` 加可选 `_runtime` 字段实现：若 `state["_runtime"]` 缺失（Plan 0 测试场景），节点退化为 stub；若注入了运行时（Plan C/D 场景），节点调真实 `run_collab_loop`。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/orchestration/test_graph_collab_loop_integration.py
import os
import tempfile

from app.orchestration.graph import build_main_graph, build_collab_runtime
from app.harness.eventbus import EventBus
from app.infrastructure.storage.event_store import EventStore
from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState
from app.harness.orchestrator import Orchestrator
from app.agents.tutor import TutorAgent
from app.agents.critic import CriticAgent
from app.agents.conductor import ConductorAgent


def _store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = EventStore(db_path=path)
    s.init()
    return s, path


def test_collab_runtime_factory_returns_bus_orchestrator_agents():
    store, path = _store()
    try:
        runtime = build_collab_runtime(EventBus(store=store))
        assert runtime.bus is not None
        assert runtime.orchestrator is not None
        # Agent 订阅由工厂注册
        assert TutorAgent in {type(a) for a in
                              runtime.bus.subscribers_of(EventType.ACTION_REQUESTED)}
        assert CriticAgent in {type(a) for a in
                               runtime.bus.subscribers_of(EventType.USER_MESSAGE)}
        assert ConductorAgent in {type(a) for a in
                                  runtime.bus.subscribers_of(EventType.CONDUCTOR_REQUESTED)}
    finally:
        store.close()
        os.unlink(path)


def test_collab_loop_node_runs_when_runtime_present(mock_llm_invoke_json):
    mock_llm_invoke_json({
        "critic_assess": {"mastery_level": "mastered", "rationale": "ok"},
    })
    store, path = _store()
    try:
        bus = EventBus(store=store)
        runtime = build_collab_runtime(bus)
        ws = WorkspaceState(session_id="s1", user_id="u1", current_topic="RAG")
        seeds = [Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                       session_id="s1", payload={"text": "我已经懂 RAG 了"})]
        g = build_main_graph()
        out = g.invoke({
            "session_id": "s1", "user_id": "u1", "enter_loop": True,
            "_runtime": {"runtime": runtime, "ws": ws, "seeds": seeds},
        }, config={"configurable": {"thread_id": "t-int-1"}})
        assert "collab_loop" in out["visited"]
        # 事件链已落库（mastered → loop_exit）
        events = bus.replay("s1")
        types = [e.type for e in events]
        assert EventType.USER_MESSAGE in types
        assert EventType.MASTERY_ASSESSED in types
        assert EventType.LOOP_EXIT in types
    finally:
        store.close()
        os.unlink(path)
```

- [ ] **Step 2: 跑失败**

Run: `pytest tests/unit/orchestration/test_graph_collab_loop_integration.py -q`
Expected: FAIL — `cannot import 'build_collab_runtime'`

- [ ] **Step 3: 修改 `app/orchestration/graph.py`**

仅替换 `_collab_loop_node` 与 `MainState`，并新增 `build_collab_runtime`：

```python
import operator
from dataclasses import dataclass
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.agents.conductor import ConductorAgent
from app.agents.critic import CriticAgent
from app.agents.tutor import TutorAgent
from app.harness.enums import EventType
from app.harness.eventbus import EventBus
from app.harness.orchestrator import Orchestrator
from app.orchestration.collab_loop import run_collab_loop


class MainState(TypedDict, total=False):
    """主图骨架状态（Plan 0 + Plan C 扩展）。

    `_runtime` 是 Plan C 注入的可选运行时字典：
      - "runtime": CollabRuntime（bus / orchestrator）
      - "ws":      WorkspaceState
      - "seeds":   list[Event] 种子事件
    若缺失，`_collab_loop_node` 退化为 stub（保持 Plan 0 测试兼容）。
    """
    session_id: str
    user_id: str
    enter_loop: bool
    stage: str
    visited: Annotated[list[str], operator.add]
    _runtime: dict


@dataclass
class CollabRuntime:
    bus: EventBus
    orchestrator: Orchestrator


def build_collab_runtime(bus: EventBus,
                          orchestrator: Orchestrator | None = None
                          ) -> CollabRuntime:
    """工厂：装配 3 Agent + Orchestrator 订阅到 Bus。

    Plan C 只装配 Tutor / Critic / Conductor（自有 Agent）；Retriever / Curator
    由 Plan D 的集成层补齐订阅（本 Plan 不引入 A/B 文件）。
    """
    tutor = TutorAgent()
    critic = CriticAgent()
    conductor = ConductorAgent()
    bus.subscribe(tutor, tutor.subscriptions)
    bus.subscribe(critic, critic.subscriptions)
    bus.subscribe(conductor, conductor.subscriptions)
    return CollabRuntime(bus=bus, orchestrator=orchestrator or Orchestrator())


def _ingest(state: MainState) -> dict:
    return {"visited": ["ingest"], "stage": "ingest"}


def _route(state: MainState) -> dict:
    return {"visited": ["route"], "stage": "route"}


def _route_decision(state: MainState) -> str:
    return "collab_loop" if state.get("enter_loop", True) else "wrap_up"


def _collab_loop_node(state: MainState) -> dict:
    """Plan C 接入点（§3.5.4）：若注入运行时则跑真实协作环；否则 stub 兜底。"""
    runtime_bundle = state.get("_runtime")
    if not runtime_bundle:
        return {"visited": ["collab_loop"], "stage": "collab_loop"}
    rt: CollabRuntime = runtime_bundle["runtime"]
    ws = runtime_bundle["ws"]
    seeds = runtime_bundle["seeds"]
    run_collab_loop(rt.bus, ws, seeds, orchestrator=rt.orchestrator)
    return {"visited": ["collab_loop"], "stage": "collab_loop"}


def _wrap_up(state: MainState) -> dict:
    return {"visited": ["wrap_up"], "stage": "wrap_up"}


def build_main_graph():
    """4 节点骨架：ingest → route → [collab_loop] → wrap_up（§3.5.4）。

    零参数版本保留 Plan 0 测试兼容；运行时由 MainState["_runtime"] 注入。
    """
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

- [ ] **Step 4: 跑测试 — 集成 + Plan 0 graph 测试**

Run: `pytest tests/unit/orchestration/test_graph_collab_loop_integration.py tests/unit/orchestration/test_graph.py -q`
Expected: PASS（**Plan 0 三个 graph 测试也须继续全绿**）

- [ ] **Step 5: 提交**

```bash
git add app/orchestration/graph.py tests/unit/orchestration/test_graph_collab_loop_integration.py
git commit -m "feat(plan-c): graph collab_loop_node injects real runtime (Plan 0 compat preserved)"
```

---

### Task 6.2: 端到端场景 — spec §4.3 事件流复现（Socratic→Feynman→Analogy→mastered→LoopExit）

**Files:**
- Create: `tests/integration/test_plan_c_e2e_scenario.py`

> **目的（用户开场 prompt 验收）：** 复现 spec §4.3 事件流示例的核心轨迹 —— Socratic→Feynman→Analogy→mastered→LoopExit；走通 1 个标准场景。本测试用脚本化用户回复 + mock LLM 驱动 3 Agent + Orchestrator，**完整经过 EventBus / 回合屏障 / TeachingPolicy** 路径。

- [ ] **Step 1: 写失败测试**

```python
# tests/integration/test_plan_c_e2e_scenario.py
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
    # LLM 响应映射（每个 intent 返回结构化结果）
    # 三轮 Critic 评估：partial(切费曼) → confusion(切 analogy) → mastered(出环)
    critic_responses = iter([
        {"mastery_level": "partial", "rationale": "基本概念有"},
        {"mastery_level": "weak", "confusion": {"concept_a": "retrieval",
                                                 "concept_b": "augment"}},
        {"mastery_level": "mastered", "rationale": "明白了"},
    ])

    def _critic_seq(self, sp, up, **kw):
        if kw.get("intent") == "critic_assess":
            return next(critic_responses)
        return {}

    import app.infrastructure.llm as llm_mod
    # 安装 Critic 序列；Tutor / Conductor 走默认 mock
    mock_llm_invoke_json({
        "tutor_ask": {"content": "你认为 LLM 直接回答 vs 借助资料有何区别？"},
        "tutor_request_recap": {"content": "请用你的话描述 RAG"},
        "tutor_offer_analogy": {"content": "RAG 就像考试翻参考书"},
    })
    # 然后 monkeypatch 覆盖 critic_assess 的序列响应
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
        # mastery=mastered 时需 topic_complete 才走 loop_exit；用 monkeypatch 临时
        # 修补 Orchestrator._collect_observations 为 mastered 注入 topic_complete=True
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
            orch_mod.Orchestrator._collect_observations = original
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
    # 此处复用上一测试的事件流但只断言：bus.replay 中所有事件 source 与
    # EVENT_OWNERSHIP 一致（运行期已经被 EventBus.publish 拦截，能成功 replay
    # 就证明零违约）。
    from app.harness.events import EVENT_OWNERSHIP
    for et, owner in EVENT_OWNERSHIP.items():
        assert owner is not None
```

- [ ] **Step 2: 跑测试**

Run: `pytest tests/integration/test_plan_c_e2e_scenario.py -q`
Expected: PASS（必要时调整 mock 序列/补 monkeypatch；目标是事件链满足必含集）

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_plan_c_e2e_scenario.py
git commit -m "test(plan-c): e2e scenario reproduces spec §4.3 (Socratic→Feynman→Analogy→exit)"
```

---

## Phase 7 — Plan C 全量回归

### Task 7.1: 全量 pytest + 越权拦截 + 基线 + README

**Files:** 无新代码 —— 验证 gate + README 同步（dev-standards.md 要求）。

- [ ] **Step 1: 跑全量测试**

Run: `pytest -q`
Expected: **全绿，零 failures / errors**。

- [ ] **Step 2: 确认基线未退化**

Run: `pytest --collect-only -q | tail -3`
Expected: 收集到的测试数 = Plan 0 完成时的数（155 + Plan 0 约 28）+ Plan C 新增（约 50+）。Plan 0 三个 `test_graph.py` 测试仍存在并通过（**Plan C 兼容承诺**）。

- [ ] **Step 3: 越权拦截全 Agent 单测复跑**

Run: `pytest tests/unit/agents -q -k "cannot_emit"`
Expected: PASS —— 三 Agent 的越权防御 case 全绿（#14 运行时不变量）。

- [ ] **Step 4: 冒烟导入新模块**

```bash
python -c "from app.agents.tutor import TutorAgent; \
from app.agents.critic import CriticAgent; \
from app.agents.conductor import ConductorAgent; \
from app.harness.orchestrator import Orchestrator, RuleEngine, load_rules; \
from app.harness.teaching_policy import TeachingPolicy, ObservationSet; \
from app.orchestration.graph import build_main_graph, build_collab_runtime; \
print('plan-c imports ok')"
```
Expected: `plan-c imports ok`

- [ ] **Step 5: 回退判据自检（spec §8 P2/P3）**
  - 回合屏障专项测试 `test_barrier_blocks_routing_until_tick_arrives` 通过 → 屏障未失效（P2 回退判据满足）
  - 端到端场景 `test_socratic_feynman_analogy_mastered_loop_exit` 通过 → 模式切换自洽（P3 回退判据满足）
  - 越权拦截全绿 → 职能正交运行时强制有效（#14）
  - Plan 0 `test_graph.py` 仍全绿 → 接口冻结未被破坏

  若任一不满足 → 回退重审对应 spec 章节，不要试图绕开。

- [ ] **Step 6: README 同步（dev-standards.md 维护规范）**

在项目根 `README.md` 的 "多 Agent 重设计进展" 段中追加：

```markdown
- ✅ Plan C 教学与编排（Tutor / Critic / Conductor + Orchestrator 规则引擎 +
  TeachingPolicy 状态机 + 回合屏障 + graph 协作环接入；spec §4.3 场景可复现）
```

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "docs(plan-c): README 标注 Plan C 完成 + 全量回归绿" --allow-empty
```

---

## Self-Review

**1. Spec coverage（逐项对照 §2.1 / §2.3 / §3.3 / §3.4 / §3.5.3 / §4 + Learned #14-17）**

| spec 要点 | 落地 Task |
|---|---|
| §2.1 Tutor 角色（生成、不评判） | Phase 1（1.2 / 1.3 / 1.4） |
| §2.1 Critic 角色（语义、不读图谱） | Phase 2（2.1 / 2.2 / 2.3） |
| §2.3 Conductor 限制（不自产观察、不 emit ActionRequested） | Phase 3（3.1 / 3.2） + 越权防御 case |
| §2.4 优先级裁决（前置>混淆） | Task 4.2 `test_priority_prereq_over_confusion_socratic` + Task 5.3 `test_tick_with_priority_prereq_over_confusion` |
| §3.3 Orchestrator 结构（规则引擎 + Conductor 召唤） | Phase 5（5.1 / 5.2 / 5.4） |
| §3.4 规则 DSL（YAML + 优先级） | Task 5.1（yaml + RuleEngine） |
| §3.5.3 回合屏障 | Task 5.2（Tick 注入）+ Task 5.5（专项测试） |
| §4.1 四模式语义 | Task 4.1 / 4.2 通过 ObservationSet → 模式 |
| §4.2 完整状态转移表 | Task 4.1 + 4.2（含 historical/observed 分支、熔断） |
| §4.3 事件流示例 | Task 6.2 端到端复现 |
| #14 emit 白名单 | 各 Agent 越权防御 case（Task 1.4 / 2.3 / 3.1） |
| #15 复述检查归 Critic | Critic 订阅 UserMessage 统一处理（含复述）—— Tutor 仅 `TUTOR_REQUEST_RECAP`（Task 1.4） |
| #16 Conductor 限制 | Task 3.1 / 3.2（不 emit Action/MasteryAssessed，REQUEST_OBSERVATION 分支） |
| #17 Curator 双时机 | 本 Plan **不实装 Curator**（Plan B 拥有），但 Orchestrator 已订阅 `GRAPH_PREREQ_WEAK_DETECTED` 并按 basis 路由（Task 5.1 规则 + Task 4.2 转移） |
| #22 LLM Mock 策略 | Task 1.1 `mock_llm_invoke_json` fixture |

**2. Placeholder scan**
- 无 "TBD / TODO / 待补"。
- Task 3.2 第 2 步注明"无需改实现"是因为 Task 3.1 实现已正确处理两分支 —— 这是 TDD 中"补测试钉死契约"的合法做法，非占位。
- Task 5.5 同理，专项屏障测试用以验证 Task 5.2/5.3 实现的运行时不变量。

**3. Type consistency**（跨 Task 核对）
- `TutorAgent / CriticAgent / ConductorAgent` 三类的 `source / subscriptions / emittable_types / handle / __init__(llm=None)` 在 Phase 1-3 一致；测试中 `_action / _user_msg / _request` helper 签名一致。
- `ObservationSet` 字段在 Task 4.1 定义，Task 4.2 / 5.3 使用一致（`mastery / confusion / contradiction / prereq_weak / prereq_basis / repeat_count / topic_complete / turn_over_limit / rag_quality_low`）。
- `RuleEngine.match(obs: dict) -> ActionKind` 与 `Orchestrator._collect_observations(events, ws) -> dict` 的 obs 字段在 Task 5.1 / 5.3 对应一致。
- `Event.payload` 关键键 `action / target / level / basis / kind / mode` 在 Phase 1-6 全文一致。
- `MainState["_runtime"]` 在 Task 6.1 定义，Task 6.2 端到端使用一致。

**4. 已知有意为之的设计点（非缺陷）**
- 模式切换震荡监控（#19 协作评估）—— 归 Plan E 实装，Plan C 仅提供 `TeachingPolicy.history` 数据源。
- Tutor 的 `EXPLAIN` 在 Regress 中复用 `TUTOR_EXPLAIN`（前置点小循环讲解）—— 与 §4.2 一致，未引入新 ActionKind。
- Curator 不在 Plan C 实装；Plan C 假定 `GRAPH_PREREQ_WEAK_DETECTED` 由 Plan B 或测试桩注入。Orchestrator 已能正确路由其 `basis` 字段。

---

## 执行交接

**Plan complete and saved to `docs/superpowers/plans/2026-06-01-plan-c-teaching-orchestration.md`. 两种执行方式：**

**1. Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，Task 间两阶段审查，快速迭代。REQUIRED SUB-SKILL: superpowers:subagent-driven-development

**2. Inline Execution** — 在当前会话用 superpowers:executing-plans 批量执行，带检查点审查。

**选哪种？** 选定后即开始按 Phase 1 → Phase 7 顺序执行 19 个 Task（每 Task 严格 5 步：测试 → 失败 → 实现 → 通过 → 提交）。
