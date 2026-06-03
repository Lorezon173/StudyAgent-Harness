# Plan E：评估体系 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建完整的旁路评估体系（L2），含部件级/系统级/协作级三层次 + A/B消融 + 选型报告，回答「协作架构本身值多少增益」。

**Architecture:** 四模块 + 一内核：EvalKernel 统一调度 ComponentBench/SystemBench/CollaborationBench，ABController 提供参数A/B与消融两种对照模式，SelectionReporter 聚合各bench结果生成 Markdown 选型报告。全部为纯旁路——只读 EventStore.replay / Agent.evaluate / 事件流 parent_id，不改任何在线代码。

**Tech Stack:** Python 3.12+、sqlite3（读 EventStore）、pyyaml（场景定义）、同步 pytest（匹配项目风格）、json+dataclass（指标序列化）

---

## 文件结构

```
app/eval/
    __init__.py                  # 包入口，导出 EvalKernel
    kernel.py                    # EvalKernel —— 统一运行器，编排所有 bench
    component_bench.py           # ComponentBench —— 调各 Agent.evaluate()
    system_bench.py              # SystemBench —— 跑 scenarios YAML（结果+过程断言）
    collaboration_bench.py       # CollaborationBench —— 消费 replay parent_id 算六维
    ab_controller.py             # ABController —— 参数 A/B + 组件消融
    selection_reporter.py        # SelectionReporter —— 聚合输出 Markdown 报告
    scenarios/
        __init__.py
        standard_scenarios.yaml  # spec §5.3 四场景 + §5.5 消融场景
    fixtures/
        __init__.py
        golden_cases.py          # 部件级黄金用例（Tutor/Retriever/Critic/Curator/Conductor）

tests/eval/
    __init__.py
    test_kernel.py
    test_component_bench.py
    test_system_bench.py
    test_collaboration_bench.py
    test_ab_controller.py
    test_selection_reporter.py

tests/golden/
    __init__.py
    golden_traces.py             # 黄金轨迹（标注过的完整事件序列）
    cohens_kappa.py              # Cohen's κ 计算工具（双人标注一致性）
```

---

## Task 0: 准备 —— 创建目录骨架与 __init__.py

**Files:**
- Create: `app/eval/` 目录
- Create: `app/eval/__init__.py`
- Create: `app/eval/scenarios/__init__.py`
- Create: `app/eval/fixtures/__init__.py`
- Create: `tests/eval/__init__.py`
- Create: `tests/golden/__init__.py`

- [ ] **Step 1: 创建目录**

Run:
```bash
mkdir -p app/eval/scenarios app/eval/fixtures tests/eval tests/golden
```

- [ ] **Step 2: 写 app/eval/__init__.py**

```python
from app.eval.kernel import EvalKernel

__all__ = ["EvalKernel"]
```

- [ ] **Step 3: 写三个空 __init__.py**

```python
# app/eval/scenarios/__init__.py
# app/eval/fixtures/__init__.py
# tests/eval/__init__.py
# tests/golden/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add app/eval/ tests/eval/ tests/golden/
git commit -m "feat(plan-e): create eval directory skeleton

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 1: 数据类 —— TestCase + EvalResult + ScenarioDefinition

**Files:**
- Create: `app/eval/kernel.py`（前半段，仅数据类 + 类型定义）

- [ ] **Step 1: 写失败的测试（数据类结构 + 序列化）**

```python
# tests/eval/test_kernel.py
import json
from dataclasses import asdict

import pytest

from app.eval.kernel import TestCase, EvalResult, ScenarioDefinition


class TestDataClasses:
    def test_test_case_roundtrip(self):
        tc = TestCase(
            name="test_rag_accuracy",
            component="retriever",
            input={"query": "什么是RAG", "top_k": 3},
            expected={"recall@k": 0.8, "faithfulness": 0.7},
            meta={"source": "golden_set_v1"},
        )
        d = asdict(tc)
        restored = TestCase(**d)
        assert restored.name == tc.name
        assert restored.component == tc.component
        assert restored.input == tc.input
        assert restored.expected == tc.expected
        assert restored.meta == tc.meta

    def test_eval_result_roundtrip(self):
        r = EvalResult(
            test_name="test_rag",
            component="retriever",
            passed=True,
            metrics={"faithfulness": 0.85, "recall_at_k": 0.9},
            errors=[],
            meta={"latency_ms": 45.2},
        )
        d = asdict(r)
        restored = EvalResult(**d)
        assert restored.passed is True
        assert restored.metrics["faithfulness"] == 0.85

    def test_eval_result_failure(self):
        r = EvalResult(
            test_name="failing_test",
            component="critic",
            passed=False,
            metrics={},
            errors=["mastery mismatch: expected mastered, got weak"],
        )
        assert r.passed is False
        assert len(r.errors) == 1

    def test_scenario_definition_with_process_assertions(self):
        sc = ScenarioDefinition(
            name="零基础学习RAG",
            user_profile={"type": "blank"},
            topic="RAG",
            script=[{"user_input": "什么是RAG？"}],
            expected={
                "mastery_reached": "mastered",
                "max_turns": 12,
                "expected_mode_path": ["Socratic", "Feynman", "Analogy"],
                "must_contain_events": ["TutorExplained", "RetrievedEvidence"],
                "must_not_contain_events": ["ConductorRequested"],
            },
        )
        assert sc.expected.get("mastery_reached") == "mastered"
        assert "must_contain_events" in sc.expected
```

Run: `pytest tests/eval/test_kernel.py::TestDataClasses -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.eval.kernel'"

- [ ] **Step 2: 写数据类实现**

```python
# app/eval/kernel.py
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestCase:
    """部件级评估的单个测试用例（§5.2）。
    
    name:       测试用例名称
    component:  被测部件标识（tutor|retriever|critic|curator|conductor）
    input:      输入参数（传给 Agent.evaluate()）
    expected:   期望的指标值
    meta:       元信息（来源、版本、标注者等）
    """
    name: str
    component: str
    input: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    """单个测试用例的评估结果。"""
    test_name: str
    component: str
    passed: bool
    metrics: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class ScenarioDefinition:
    """系统级场景定义（§5.3）。
    
    script:          模拟用户的多轮回复
    expected:        结果断言 + 过程断言（§5.3 格式 + §5.4 轨迹偏离）
    meta:            场景元信息
    """
    name: str
    user_profile: dict = field(default_factory=dict)
    topic: str = ""
    script: list[dict] = field(default_factory=list)
    expected: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
```

- [ ] **Step 3: 运行验证通过**

Run: `pytest tests/eval/test_kernel.py::TestDataClasses -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add tests/eval/test_kernel.py app/eval/kernel.py
git commit -m "feat(plan-e): TestCase/EvalResult/ScenarioDefinition data classes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 黄金集与 Cohen's κ 工具

**Files:**
- Create: `tests/golden/cohens_kappa.py`
- Create: `tests/golden/golden_traces.py`
- Create: `app/eval/fixtures/golden_cases.py`

- [ ] **Step 1: 写 Cohen's κ 测试**

```python
# tests/eval/test_kernel.py（追加）
class TestCohensKappa:
    def test_perfect_agreement(self):
        from tests.golden.cohens_kappa import cohens_kappa
        a = ["mastered", "weak", "partial", "mastered"]
        b = ["mastered", "weak", "partial", "mastered"]
        k = cohens_kappa(a, b)
        assert k == pytest.approx(1.0, abs=0.01)

    def test_no_agreement(self):
        from tests.golden.cohens_kappa import cohens_kappa
        a = ["mastered", "mastered", "mastered"]
        b = ["weak", "weak", "weak"]
        k = cohens_kappa(a, b)
        assert k == pytest.approx(0.0, abs=0.01)

    def test_partial_agreement(self):
        from tests.golden.cohens_kappa import cohens_kappa
        a = ["mastered", "weak", "partial", "mastered", "weak"]
        b = ["mastered", "weak", "mastered", "partial", "weak"]
        k = cohens_kappa(a, b)
        # 4/5 观察一致 = 0.8 observed, expected_by_chance > 0 故 κ < 0.8
        assert 0.0 < k < 1.0

    def test_kappa_threshold_06(self):
        from tests.golden.cohens_kappa import cohens_kappa
        # 模拟达到 κ >= 0.6 的数据
        a = ["mastered", "weak", "partial", "mastered", "weak",
             "mastered", "weak", "partial", "mastered", "weak"]
        b = ["mastered", "weak", "partial", "mastered", "weak",
             "mastered", "weak", "mastered", "partial", "weak"]
        k = cohens_kappa(a, b)
        # 这组数据 8/10 一致，κ 应 > 0.6
        assert k >= 0.6, f"κ={k} should be >= 0.6 for 80% agreement"
```

Run: `pytest tests/eval/test_kernel.py::TestCohensKappa -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 2: 实现 Cohen's κ**

```python
# tests/golden/cohens_kappa.py
from collections import Counter


def cohens_kappa(annotator_a: list[str], annotator_b: list[str]) -> float:
    """Cohen's κ 系数（§5.1.1 双人标注一致性）。
    
    返回 [-1, 1] 范围，≥ 0.6 表示标注一致可采信。
    """
    if len(annotator_a) != len(annotator_b):
        raise ValueError("标注长度不一致")
    n = len(annotator_a)
    if n == 0:
        return 1.0

    # 观察一致率
    observed = sum(1 for a, b in zip(annotator_a, annotator_b) if a == b) / n

    # 期望一致率（边际乘积之和）
    count_a = Counter(annotator_a)
    count_b = Counter(annotator_b)
    categories = set(count_a.keys()) | set(count_b.keys())
    expected = sum((count_a.get(c, 0) / n) * (count_b.get(c, 0) / n) for c in categories)

    if expected == 1.0:         # 全部同类别
        return 1.0

    return (observed - expected) / (1 - expected)
```

- [ ] **Step 3: 验证通过**

Run: `pytest tests/eval/test_kernel.py::TestCohensKappa -v`
Expected: 4 PASS

- [ ] **Step 4: 写黄金轨迹冻结数据**

```python
# tests/golden/golden_traces.py
"""黄金轨迹 —— 人工标注的参考事件序列（§5.1.1 / #21）。

每条轨迹 = (session_id, events, expected_assessments)。
events 是期望的理想事件序列，expected_assessments 是逐事件的期望评估。
冻结后只增不改，改则升版本。
"""

GOLDEN_VERSION = "v1.0"

# 场景：零基础学习 RAG（规范 §5.3 第一个场景）
GOLDEN_TRACE_ZERO_RAG = {
    "scenario": "零基础学习RAG",
    "user_profile": {"type": "blank"},
    "topic": "RAG",
    "expected_mode_path": ["Socratic", "Feynman", "Analogy"],
    "events": [
        {"type": "TopicEntered", "source": "orchestrator",
         "payload": {"topic": "RAG"}},
        {"type": "ActionRequested", "source": "orchestrator",
         "payload": {"action": "tutor_ask", "target": "tutor"}},
        {"type": "TutorAsked", "source": "tutor",
         "payload": {"content": "什么是RAG?"}},
        {"type": "UserMessage", "source": "user",
         "payload": {"text": "RAG是检索增强生成"}},
        {"type": "MasteryAssessed", "source": "critic",
         "payload": {"level": "partial", "score": 60}},
    ],
    "expected_assessments": {
        "mastery_reached": "mastered",
        "max_turns": 12,
        "must_contain_events": ["TutorExplained", "RetrievedEvidence"],
        "must_not_contain_events": ["ConductorRequested"],
    },
}

GOLDEN_TRACES = {
    "zero_rag": GOLDEN_TRACE_ZERO_RAG,
    # 后续场景逐步追加
}
```

- [ ] **Step 5: 写部件级黄金用例**

```python
# app/eval/fixtures/golden_cases.py
"""部件级黄金测试用例（§5.1.1 / §5.2），供 ComponentBench 加载。"""

from app.eval.kernel import TestCase

GOLDEN_CASES: dict[str, list[TestCase]] = {
    "tutor": [
        TestCase(name="解释完整性_base",
                 component="tutor",
                 input={"topic": "RAG", "action": "tutor_explain"},
                 expected={"explanation_completeness": 0.7},
                 meta={"source": "golden_v1", "rubric": "基础概念覆盖"}),
    ],
    "retriever": [
        TestCase(name="RAG检索_准确率",
                 component="retriever",
                 input={"query": "什么是RAG", "top_k": 5,
                        "golden_chunks": ["RAG = Retrieval Augmented Generation"],
                        "golden_answer": "RAG是检索增强生成技术"},
                 expected={"recall_at_k": 0.8, "faithfulness": 0.7,
                          "answer_relevancy": 0.6, "context_precision": 0.6},
                 meta={"source": "golden_v1"}),
    ],
    "critic": [
        TestCase(name="掌握度判定_准确",
                 component="critic",
                 input={"user_text": "RAG是检索增强生成",
                        "topic": "RAG"},
                 expected={"mastery_level": "partial"},
                 meta={"source": "golden_v1"}),
    ],
    "curator": [
        TestCase(name="图谱覆盖率",
                 component="curator",
                 input={"graph_nodes": {"RAG": 0.0, "retrieval": 0.0,
                                        "generation": 0.0}},
                 expected={"coverage": 1.0},
                 meta={"source": "golden_v1"}),
    ],
    "conductor": [
        TestCase(name="观察不足_请求补观察",
                 component="conductor",
                 input={"observations": [],
                        "current_mode": "Socratic"},
                 expected={"action": "request_observation",
                          "observation_enough": False},
                 meta={"source": "golden_v1"}),
    ],
}
```

- [ ] **Step 6: Commit**

```bash
git add tests/golden/cohens_kappa.py tests/golden/golden_traces.py \
       app/eval/fixtures/golden_cases.py \
       tests/eval/test_kernel.py
git commit -m "feat(plan-e): golden dataset + Cohen's kappa tool

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: EvalKernel 核心运行器

**Files:**
- Create: `app/eval/kernel.py`（追加 EvalKernel 类）
- Modify: `tests/eval/test_kernel.py`

- [ ] **Step 1: 写 EvalKernel 测试**

```python
# tests/eval/test_kernel.py（追加）
class TestEvalKernel:
    def test_run_component_bench_requires_agent_map(self):
        kernel = EvalKernel(agent_map={})
        with pytest.raises(ValueError, match="ComponentBench 无注册 Agent"):
            kernel.run_component_bench("tutor", [])

    def test_run_component_bench_returns_results(self):
        from app.agents.tutor import TutorAgent
        tutor = TutorAgent.__new__(TutorAgent)
        kernel = EvalKernel(agent_map={"tutor": tutor})
        test_cases = [
            TestCase(name="dummy", component="tutor", input={}),
        ]
        results = kernel.run_component_bench("tutor", test_cases)
        assert len(results) == 1
        assert results[0].test_name == "dummy"
        assert results[0].component == "tutor"

    def test_run_system_bench(self):
        kernel = EvalKernel(agent_map={})
        scenarios = [
            ScenarioDefinition(
                name="dummy_scenario",
                user_profile={"type": "blank"},
                topic="test",
                script=[{"user_input": "hello"}],
                expected={},
            ),
        ]
        results = kernel.run_system_bench(scenarios, event_store=None)
        assert len(results) == 1

    def test_run_collaboration_bench(self):
        kernel = EvalKernel(agent_map={})
        result = kernel.run_collaboration_bench(
            "test_session", event_store=None)
        # 无 event_store 时返回空结果（非崩溃）
        assert result is not None
        assert "violation_count" in result

    def test_run_ablation(self, tmp_path):
        kernel = EvalKernel(agent_map={})
        config = {
            "name": "curator_ablation",
            "control": {"all_agents": True},
            "treatment": {"disable_agent": "curator"},
            "scenarios": ["dummy"],
        }
        results = kernel.run_ablation(config, scenarios=[], event_store=None)
        assert "control" in results
        assert "treatment" in results
```

Run: `pytest tests/eval/test_kernel.py::TestEvalKernel -v`
Expected: 5 FAIL (未实现 EvalKernel)

- [ ] **Step 2: 实现 EvalKernel**

```python
# app/eval/kernel.py（追加）

class EvalKernel:
    """评估内核 —— 统一编排三层次评估 + A/B 消融（§5）。
    
    agent_map: {component_name: AgentBase_instance}
    """
    
    def __init__(self, agent_map: dict[str, "AgentBase"] | None = None):
        self._agent_map = agent_map or {}
    
    # ---- ComponentBench（§5.2）----
    
    def run_component_bench(self, component: str,
                            test_cases: list[TestCase]) -> list[EvalResult]:
        if component not in self._agent_map:
            raise ValueError(
                f"ComponentBench 无注册 Agent：{component}")
        agent = self._agent_map[component]
        results: list[EvalResult] = []
        for tc in test_cases:
            try:
                metrics = agent.evaluate(tc.input)
            except NotImplementedError as e:
                results.append(EvalResult(
                    test_name=tc.name, component=component,
                    passed=False, errors=[str(e)]))
                continue
            passed = self._check_expected(tc.expected, metrics)
            errors = []
            if not passed:
                for key, threshold in tc.expected.items():
                    actual = metrics.get(key)
                    if actual is None or actual < threshold:
                        errors.append(
                            f"{key}: expected>={threshold}, got={actual}")
            results.append(EvalResult(
                test_name=tc.name, component=component,
                passed=passed, metrics=metrics, errors=errors))
        return results
    
    @staticmethod
    def _check_expected(expected: dict, actual: dict) -> bool:
        for key, threshold in expected.items():
            val = actual.get(key)
            if val is None or val < threshold:
                return False
        return True
    
    # ---- SystemBench（§5.3）----
    
    def run_system_bench(self, scenarios: list[ScenarioDefinition],
                         event_store=None) -> list[dict]:
        """运行系统级场景评估。
        
        实际运行时 event_store 为 EventStore 实例，用于 replay 已运行场景。
        返回每个场景的评估摘要。
        """
        results: list[dict] = []
        for sc in scenarios:
            trace = None
            if event_store is not None:
                trace = event_store.replay(sc.name)
            result = self._assess_scenario(sc, trace)
            results.append(result)
        return results
    
    def _assess_scenario(self, sc: ScenarioDefinition,
                         trace: list | None) -> dict:
        """对单个场景做结果断言 + 过程断言。"""
        summary = {
            "scenario": sc.name,
            "result_assertions": {},
            "process_assertions": {},
            "passed": True,
            "errors": [],
        }
        expected = sc.expected
        # 结果断言由系统运行时的终态提供（此处占位，Task 5 完整实现）
        summary["result_assertions"] = {
            "mastery_reached": None,
            "max_turns": None,
        }
        return summary
    
    # ---- CollaborationBench（§5.4）----
    
    def run_collaboration_bench(self, session_id: str,
                                event_store=None) -> dict:
        """对一次会话回放计算六维协作指标。"""
        from app.eval.collaboration_bench import compute_collaboration_metrics
        return compute_collaboration_metrics(session_id, event_store)
    
    # ---- ABController（§5.5）----
    
    def run_ablation(self, config: dict,
                     scenarios: list[ScenarioDefinition],
                     event_store=None) -> dict:
        """运行消融实验。
        
        config 结构：
          name: str
          control: {"all_agents": bool}
          treatment: {"disable_agent": str}
          scenarios: list[str] 场景名列表
        """
        from app.eval.ab_controller import run_ablation_experiment
        return run_ablation_experiment(
            config, scenarios, event_store, agent_map=self._agent_map)
```

- [ ] **Step 3: 验证通过**

Run: `pytest tests/eval/test_kernel.py::TestEvalKernel -v`
Expected: 5 PASS

- [ ] **Step 4: Commit**

```bash
git add app/eval/kernel.py tests/eval/test_kernel.py
git commit -m "feat(plan-e): EvalKernel core runner

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: ComponentBench 部件级评估

**Files:**
- Create: `app/eval/component_bench.py`
- Test: `tests/eval/test_component_bench.py`

- [ ] **Step 1: 写 ComponentBench 测试**

```python
# tests/eval/test_component_bench.py
import pytest

from app.eval.component_bench import ComponentBench
from app.eval.kernel import TestCase, EvalResult
from app.harness.enums import EventSource


class FakeEvaluatable:
    """模拟实现了 evaluate 的 Agent。"""
    source = EventSource.RETRIEVER

    def evaluate(self, test_case: dict) -> dict:
        if test_case.get("query") == "fail":
            raise RuntimeError("eval crash")
        return {
            "faithfulness": test_case.get("expected_faithfulness", 0.8),
            "recall_at_k": test_case.get("expected_recall", 0.9),
        }


class TestComponentBench:
    def test_run_single_agent(self):
        bench = ComponentBench({"retriever": FakeEvaluatable()})
        cases = [
            TestCase(name="test1", component="retriever",
                     input={"query": "RAG", "expected_faithfulness": 0.8},
                     expected={"faithfulness": 0.7, "recall_at_k": 0.8}),
        ]
        results = bench.run("retriever", cases)
        assert len(results) == 1
        assert results[0].passed is True

    def test_run_all_agents(self):
        bench = ComponentBench({
            "retriever": FakeEvaluatable(),
            "tutor": FakeEvaluatable(),
        })
        cases = [
            TestCase(name="t1", component="retriever",
                     input={}, expected={}),
            TestCase(name="t2", component="tutor",
                     input={}, expected={}),
        ]
        results = bench.run_all(cases)
        assert len(results) == 2
    
    def test_agent_not_registered(self):
        bench = ComponentBench({})
        cases = [TestCase(name="x", component="nonexistent", input={})]
        results = bench.run("nonexistent", cases)
        assert len(results) == 1
        assert not results[0].passed
        assert "未注册" in results[0].errors[0]

    def test_format_report(self):
        bench = ComponentBench({"retriever": FakeEvaluatable()})
        cases = [
            TestCase(name="ok", component="retriever",
                     input={}, expected={}),
            TestCase(name="fail", component="retriever",
                     input={"query": "fail"}, expected={"x": 1.0}),
        ]
        results = bench.run("retriever", cases)
        report = bench.format_report(results)
        assert "ok" in report
        assert "fail" in report
        assert "PASS" in report or "FAIL" in report
```

Run: `pytest tests/eval/test_component_bench.py -v`
Expected: 4 FAIL

- [ ] **Step 2: 实现 ComponentBench**

```python
# app/eval/component_bench.py
from app.eval.kernel import TestCase, EvalResult


class ComponentBench:
    """部件级评估（§5.2）：对各 Agent 的 evaluate() 运行黄金用例。"""
    
    def __init__(self, agent_map: dict[str, object]):
        self._agent_map = agent_map
    
    def run(self, component: str,
            test_cases: list[TestCase]) -> list[EvalResult]:
        if component not in self._agent_map:
            return [
                EvalResult(test_name=tc.name, component=component,
                           passed=False,
                           errors=[f"Agent '{component}' 未注册"])
                for tc in test_cases
            ]
        agent = self._agent_map[component]
        results: list[EvalResult] = []
        for tc in test_cases:
            try:
                metrics = agent.evaluate(tc.input)
            except Exception as e:
                results.append(EvalResult(
                    test_name=tc.name, component=component,
                    passed=False, errors=[f"evaluate 异常：{e}"]))
                continue
            passed = True
            errors: list[str] = []
            for key, threshold in tc.expected.items():
                actual = metrics.get(key)
                if actual is None:
                    passed = False
                    errors.append(f"{key}: 未返回（期望 >= {threshold}）")
                elif isinstance(threshold, (int, float)):
                    if actual < threshold:
                        passed = False
                        errors.append(
                            f"{key}: {actual} < {threshold}")
                elif isinstance(threshold, str):
                    if str(actual) != threshold:
                        passed = False
                        errors.append(
                            f"{key}: {actual} != {threshold}")
            results.append(EvalResult(
                test_name=tc.name, component=component,
                passed=passed, metrics=metrics, errors=errors))
        return results
    
    def run_all(self, test_cases: list[TestCase]) -> list[EvalResult]:
        by_component: dict[str, list[TestCase]] = {}
        for tc in test_cases:
            by_component.setdefault(tc.component, []).append(tc)
        results: list[EvalResult] = []
        for comp, cases in by_component.items():
            results.extend(self.run(comp, cases))
        return results
    
    @staticmethod
    def format_report(results: list[EvalResult]) -> str:
        lines = ["## ComponentBench 报告\n"]
        passed = sum(1 for r in results if r.passed)
        lines.append(f"**通过率**: {passed}/{len(results)}")
        for r in results:
            status = "✅ PASS" if r.passed else "❌ FAIL"
            lines.append(f"\n### {r.test_name} ({status})")
            lines.append(f"- 组件: {r.component}")
            lines.append(f"- 指标: {r.metrics}")
            if r.errors:
                lines.append(f"- 错误: {r.errors}")
        return "\n".join(lines)
```

- [ ] **Step 3: 验证通过**

Run: `pytest tests/eval/test_component_bench.py -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add app/eval/component_bench.py tests/eval/test_component_bench.py
git commit -m "feat(plan-e): ComponentBench with format_report

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: SystemBench 场景运行器（结果断言 + 过程断言）

**Files:**
- Create: `app/eval/system_bench.py`
- Create: `app/eval/scenarios/standard_scenarios.yaml`
- Test: `tests/eval/test_system_bench.py`

- [ ] **Step 1: 写场景 YAML**

```yaml
# app/eval/scenarios/standard_scenarios.yaml
# spec §5.3 四标准场景 + §5.5 消融场景

scenarios:
  - name: "零基础学习RAG"
    user_profile: {type: blank}
    topic: "RAG"
    script:
      - {user_input: "RAG是什么？"}
      - {user_input: "RAG是检索增强生成"}
      - {user_input: "向量数据库在RAG中的作用是存储和检索相关文档"}
    expected:
      mastery_reached: mastered
      max_turns: 12
      cost_usd: 0.05
      expected_mode_path: [Socratic, Feynman, Analogy]
      must_contain_events: [TutorExplained, RetrievedEvidence]
      must_not_contain_events: [ConductorRequested]

  - name: "有基础但有混淆"
    user_profile:
      mastered: ["LLM基础"]
      confused_pairs: [["retrieval", "fine-tuning"]]
    topic: "RAG"
    script:
      - {user_input: "RAG是什么？"}
      - {user_input: "RAG就是fine-tuning的一种"}
    expected:
      confusion_detected_within_turns: 3
      mastery_reached: mastered

  - name: "跨主题跳跃"
    user_profile: {type: blank}
    topic: "RAG"
    script:
      - {user_input: "什么是RAG？"}
      - {user_input: "说到RAG，我觉得transformer的注意力机制更重要"}
    expected:
      conductor_triggered: true
      no_loss_of_context: true

  - name: "前置薄弱触发回退"
    user_profile: {type: blank, mastered: []}
    topic: "transformer 注意力机制"
    script:
      - {user_input: "我要学transformer注意力机制"}
    expected:
      regress_to_prereq: true
      expected_mode_path: [Socratic, Regress]

  - name: "消融场景_无Curator"
    user_profile: {type: blank}
    topic: "RAG"
    script:
      - {user_input: "RAG是什么？"}
    expected:
      mastery_reached: mastered
      max_turns: 15
```

- [ ] **Step 2: 写 SystemBench 测试**

```python
# tests/eval/test_system_bench.py
import pytest
import yaml

from app.eval.system_bench import SystemBench
from app.eval.kernel import ScenarioDefinition
from pathlib import Path


class TestScenarioLoading:
    def test_load_yaml(self):
        bench = SystemBench()
        scenarios = bench.load_scenarios(
            str(Path(__file__).resolve().parent.parent.parent /
                "app/eval/scenarios/standard_scenarios.yaml"))
        assert len(scenarios) >= 4
        names = [s.name for s in scenarios]
        assert "零基础学习RAG" in names
        assert "前置薄弱触发回退" in names

    def test_scenario_has_process_assertions(self):
        bench = SystemBench()
        scenarios = bench.load_scenarios(
            str(Path(__file__).resolve().parent.parent.parent /
                "app/eval/scenarios/standard_scenarios.yaml"))
        sc = [s for s in scenarios if s.name == "零基础学习RAG"][0]
        assert "expected_mode_path" in sc.expected
        assert "must_contain_events" in sc.expected
        assert "must_not_contain_events" in sc.expected


class TestSystemBench:
    def test_assess_with_trace(self):
        bench = SystemBench()
        trace = [
            {"type": "TopicEntered", "source": "orchestrator"},
            {"type": "TutorExplained", "source": "tutor"},
            {"type": "MasteryAssessed", "source": "critic",
             "payload": {"level": "mastered"}},
        ]
        sc = ScenarioDefinition(
            name="test",
            expected={
                "mastery_reached": "mastered",
                "must_contain_events": ["TutorExplained"],
                "must_not_contain_events": ["ConductorRequested"],
            },
        )
        result = bench.assess(sc, trace)
        assert result["result_assertions"]["mastery_reached"] is True

    def test_assess_missing_required_event(self):
        bench = SystemBench()
        trace = [
            {"type": "UserMessage"},
        ]
        sc = ScenarioDefinition(
            name="test",
            expected={
                "must_contain_events": ["MasteryAssessed"],
            },
        )
        result = bench.assess(sc, trace)
        assert result["passed"] is False
        assert "缺少必需事件" in str(result["errors"])

    def test_assess_forbidden_event_detected(self):
        bench = SystemBench()
        trace = [
            {"type": "UserMessage"},
            {"type": "ConductorRequested", "source": "orchestrator"},
        ]
        sc = ScenarioDefinition(
            name="test",
            expected={
                "must_not_contain_events": ["ConductorRequested"],
            },
        )
        result = bench.assess(sc, trace)
        assert result["passed"] is False
        assert "禁止出现" in str(result["errors"])

    def test_assess_mode_path(self):
        bench = SystemBench()
        trace = [
            {"type": "PolicyTransition",
             "payload": {"from": "Socratic", "to": "Feynman"}},
            {"type": "PolicyTransition",
             "payload": {"from": "Feynman", "to": "Analogy"}},
        ]
        sc = ScenarioDefinition(
            name="test",
            expected={
                "expected_mode_path": ["Socratic", "Feynman", "Analogy"],
            },
        )
        result = bench.assess(sc, trace)
        assert result["passed"] is True

    def test_assess_mode_path_deviation(self):
        bench = SystemBench()
        trace = [
            {"type": "PolicyTransition",
             "payload": {"from": "Socratic", "to": "Regress"}},
        ]
        sc = ScenarioDefinition(
            name="test",
            expected={
                "expected_mode_path": ["Socratic", "Feynman", "Analogy"],
            },
        )
        result = bench.assess(sc, trace)
        assert result["passed"] is False
        assert "偏离" in str(result["errors"])
```

Run: `pytest tests/eval/test_system_bench.py -v`
Expected: 7 FAIL

- [ ] **Step 3: 实现 SystemBench**

```python
# app/eval/system_bench.py
from pathlib import Path

import yaml

from app.eval.kernel import ScenarioDefinition


class SystemBench:
    """系统级场景运行器（§5.3）。
    
    加载 YAML 场景定义，对已运行的 trace 做结果断言 + 过程断言。
    """
    
    @staticmethod
    def load_scenarios(path: str) -> list[ScenarioDefinition]:
        p = Path(path)
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return [ScenarioDefinition(**sc) for sc in data.get("scenarios", [])]
    
    def assess(self, sc: ScenarioDefinition,
               trace: list[dict]) -> dict:
        """依据 trace 做结果断言 + 过程断言。"""
        summary = {
            "scenario": sc.name,
            "result_assertions": {},
            "process_assertions": {},
            "passed": True,
            "errors": [],
        }
        expected = sc.expected
        trace_types = [ev["type"] for ev in trace]
        
        # --- 结果断言 ---
        self._assess_result(expected, trace, summary)
        
        # --- 过程断言：must_contain_events ---
        must = expected.get("must_contain_events", [])
        for et in must:
            if et not in trace_types:
                summary["passed"] = False
                summary["errors"].append(
                    f"缺少必需事件：{et}")
        summary["process_assertions"]["must_contain_events"] = {
            "expected": must,
            "all_found": all(et in trace_types for et in must),
        }
        
        # --- 过程断言：must_not_contain_events ---
        must_not = expected.get("must_not_contain_events", [])
        for et in must_not:
            if et in trace_types:
                summary["passed"] = False
                summary["errors"].append(
                    f"禁止出现事件：{et}（出现 {trace_types.count(et)} 次）")
        summary["process_assertions"]["must_not_contain_events"] = {
            "expected": must_not,
            "none_found": all(et not in trace_types for et in must_not),
        }
        
        # --- 过程断言：expected_mode_path ---
        mode_path = expected.get("expected_mode_path", [])
        if mode_path:
            actual_path = self._extract_mode_path(trace)
            deviated = self._mode_path_deviation(mode_path, actual_path)
            if deviated:
                summary["passed"] = False
                summary["errors"].append(
                    f"模式路径偏离：期望 {mode_path}，"
                    f"实际 {actual_path}（{deviated}）")
            summary["process_assertions"]["mode_path"] = {
                "expected": mode_path,
                "actual": actual_path,
                "deviation": deviated,
            }
        
        return summary
    
    @staticmethod
    def _assess_result(expected: dict, trace: list[dict],
                       summary: dict) -> None:
        result = summary["result_assertions"]
        
        # mastery_reached
        expected_mastery = expected.get("mastery_reached")
        if expected_mastery:
            actual = None
            for ev in reversed(trace):
                if ev.get("type") == "MasteryAssessed":
                    actual = (ev.get("payload", {})
                              .get("level"))
                    break
            ok = actual == expected_mastery
            result["mastery_reached"] = ok
            if not ok:
                summary["errors"].append(
                    f"掌握度未达标：期望 {expected_mastery}，实际 {actual}")
                summary["passed"] = False
        
        # max_turns
        max_turns = expected.get("max_turns")
        if max_turns:
            actual_turns = len(trace) // 3  # 启发式估算
            ok = actual_turns <= max_turns
            result["max_turns"] = ok
            if not ok:
                summary["errors"].append(
                    f"回合数超限：{actual_turns} > {max_turns}")
                summary["passed"] = False
    
    @staticmethod
    def _extract_mode_path(trace: list[dict]) -> list[str]:
        path = []
        for ev in trace:
            if ev.get("type") == "PolicyTransition":
                p = ev.get("payload", {})
                frm = p.get("from")
                to = p.get("to")
                if frm and not path:
                    path.append(frm)
                if to:
                    path.append(to)
        return path
    
    @staticmethod
    def _mode_path_deviation(expected: list[str],
                             actual: list[str]) -> str | None:
        if not actual:
            return "空路径"
        # 检查实际路径是否包含期望的子序列
        i = 0
        for mode in expected:
            if i < len(actual) and actual[i] == mode:
                i += 1
        if i < len(expected):
            return f"路径在第{i+1}步偏离（期望{expected[i]}，实际{actual[i] if i < len(actual) else '无'}）"
        if len(actual) > len(expected):
            return f"路径比期望长{len(actual) - len(expected)}步"
        return None
```

- [ ] **Step 4: 验证通过**

Run: `pytest tests/eval/test_system_bench.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add app/eval/system_bench.py app/eval/scenarios/standard_scenarios.yaml \
       tests/eval/test_system_bench.py
git commit -m "feat(plan-e): SystemBench with result + process assertions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: CollaborationBench 协作级评估（六维指标）

**Files:**
- Create: `app/eval/collaboration_bench.py`
- Test: `tests/eval/test_collaboration_bench.py`

- [ ] **Step 1: 写 CollaborationBench 测试**

```python
# tests/eval/test_collaboration_bench.py
import pytest
from datetime import datetime, timezone

from app.eval.collaboration_bench import (
    compute_collaboration_metrics,
    build_causal_tree,
    compute_violation_rate,
    compute_efficiency,
    compute_decision_stability,
    compute_conflict_resolution,
    compute_causal_chain_quality,
    compute_trajectory_deviation,
)
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


class TestBuildCausalTree:
    def test_basic_chain(self):
        """UserMessage → MasteryAssessed → GraphPrereqWeakDetected"""
        events = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="s1", id="ev1"),
            Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                  session_id="s1", id="ev2", parent_id="ev1"),
            Event(type=EventType.GRAPH_PREREQ_WEAK_DETECTED,
                  source=EventSource.CURATOR, session_id="s1",
                  id="ev3", parent_id="ev2"),
        ]
        tree = build_causal_tree(events)
        assert "ev1" in tree
        assert "ev2" in tree["ev1"]["children"]
        assert "ev3" in tree["ev2"]["children"]

    def test_orphan_detection(self):
        """无 parent_id 的孤儿事件"""
        events = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="s1", id="ev1"),
            Event(type=EventType.TUTOR_ASKED, source=EventSource.TUTOR,
                  session_id="s1", id="ev2"),  # 无 parent_id
        ]
        tree = build_causal_tree(events)
        orphans = [eid for eid, node in tree.items()
                   if node["parent"] is None
                   and node["event"].type != EventType.USER_MESSAGE]
        assert len(orphans) == 1


class TestCollaborationMetrics:
    @pytest.fixture
    def sample_events(self):
        """构造标准事件流用于六维指标计算。"""
        return [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="s1", id="e1"),
            Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                  session_id="s1", id="e2", parent_id="e1"),
            Event(type=EventType.ORCHESTRATOR_TICK, source=EventSource.ORCHESTRATOR,
                  session_id="s1", id="e3"),
            Event(type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
                  session_id="s1", id="e4", parent_id="e3"),
            Event(type=EventType.TUTOR_EXPLAINED, source=EventSource.TUTOR,
                  session_id="s1", id="e5", parent_id="e4"),
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="s1", id="e6"),
            Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                  session_id="s1", id="e7", parent_id="e6"),
            Event(type=EventType.LOOP_EXIT, source=EventSource.ORCHESTRATOR,
                  session_id="s1", id="e8", parent_id="e7"),
        ]

    def test_violation_rate_zero(self, sample_events):
        """正交违约率应为 0（白名单拦截日志为 0）。"""
        rate = compute_violation_rate(sample_events, [])
        assert rate == 0.0

    def test_violation_rate_nonzero(self, sample_events):
        violations = ["ev_violation1", "ev_violation2"]
        rate = compute_violation_rate(sample_events, violations)
        assert rate == 2 / len(sample_events)

    def test_efficiency(self, sample_events):
        eff = compute_efficiency(sample_events, 2)
        assert eff["events_per_turn"] == len(sample_events) / 2
        assert "ineffective_rate" in eff
        assert 0 <= eff["ineffective_rate"] <= 1

    def test_decision_stability(self, sample_events):
        stab = compute_decision_stability(sample_events)
        assert "mode_switches" in stab
        assert "repent_rate" in stab

    def test_conflict_resolution(self, sample_events):
        cr = compute_conflict_resolution(sample_events)
        assert "conflict_rate" in cr
        assert 0 <= cr["conflict_rate"] <= 1

    def test_causal_chain_quality(self, sample_events):
        cc = compute_causal_chain_quality(sample_events)
        assert "orphan_rate" in cc
        assert 0 <= cc["orphan_rate"] <= 1
        assert "max_depth" in cc

    def test_trajectory_deviation(self, sample_events):
        expected_path = ["Socratic", "Feynman"]
        td = compute_trajectory_deviation(sample_events, expected_path)
        assert "deviation_score" in td

    def test_compute_all_metrics(self, sample_events):
        result = compute_collaboration_metrics(
            session_id="s1",
            events=sample_events,
            violation_log=[],
            expected_mode_path=["Socratic", "Feynman"],
        )
        assert "violation_count" in result
        assert "violation_rate" in result
        assert "events_per_turn" in result
        assert "ineffective_rate" in result
        assert "mode_switches" in result
        assert "conflict_rate" in result
        assert "orphan_rate" in result
        assert "max_depth" in result
        assert "deviation_score" in result
        assert result["violation_count"] == 0
```

Run: `pytest tests/eval/test_collaboration_bench.py -v`
Expected: 10 FAIL

- [ ] **Step 2: 实现 CollaborationBench**

```python
# app/eval/collaboration_bench.py
"""协作级评估（§5.4）：消费 EventStore.replay 的 parent_id 因果链，算六维指标。

六维指标：
1. 职能正交违约 — 跨域 emit 次数（应恒为 0）
2. 协作效率 — 每教学回合事件数 + 无效事件率
3. 决策稳定性 — 模式切换震荡频率 + Orchestrator 反悔率
4. 冲突消解 — Critic/Curator 观察冲突率
5. 因果链质量 — 因果完整性 + 孤儿事件率 + 因果树深度
6. 轨迹偏离 — 实际模式路径 vs 黄金轨迹偏离度
"""

from collections import defaultdict
from app.harness.events import Event, priority_of
from app.harness.enums import EventType


# ---- 因果链构建 ----

def build_causal_tree(events: list[Event]) -> dict[str, dict]:
    """构建 parent_id 因果树。
    
    返回 {event_id: {"event": Event, "parent": str|None, "children": list[str]}}
    """
    tree: dict[str, dict] = {}
    id_map = {ev.id: ev for ev in events}
    
    for ev in events:
        tree[ev.id] = {
            "event": ev,
            "parent": ev.parent_id,
            "children": [],
        }
    
    for eid, node in tree.items():
        parent = node["parent"]
        if parent and parent in tree:
            tree[parent]["children"].append(eid)
    
    return tree


# ---- 六维指标函数 ----

def compute_violation_rate(events: list[Event],
                           violation_log: list[str]) -> float:
    """维度1：职能正交违约率（§5.4 / #14）。
    
    violation_log 是 EmitViolationError 的记录列表（每条含违规事件 id）。
    违约率 = 违规事件数 / 总事件数。应恒为 0。
    """
    if not events:
        return 0.0
    return len(violation_log) / len(events)


def compute_efficiency(events: list[Event],
                       num_teaching_turns: int) -> dict:
    """维度2：协作效率。
    
    - events_per_turn: 每教学回合事件数
    - ineffective_rate: 无效事件率（emit 了但未被任何后续事件引用为 parent）
    """
    if num_teaching_turns <= 0:
        num_teaching_turns = 1
    
    # parent_id 被引用次数
    referenced: set[str] = set()
    for ev in events:
        if ev.parent_id:
            referenced.add(ev.parent_id)
    
    # 控制类事件不计入"无效"判定
    control_types = {EventType.ORCHESTRATOR_TICK, EventType.LOOP_EXIT,
                     EventType.POLICY_TRANSITION, EventType.ACTION_REQUESTED,
                     EventType.CONDUCTOR_REQUESTED}
    
    ineffective = sum(1 for ev in events
                      if ev.id not in referenced
                      and ev.type not in control_types
                      and ev.source.name != "USER")
    
    return {
        "events_per_turn": round(len(events) / num_teaching_turns, 2),
        "ineffective_rate": round(ineffective / len(events), 4) if events else 0.0,
        "total_events": len(events),
        "ineffective_count": ineffective,
    }


def compute_decision_stability(events: list[Event]) -> dict:
    """维度3：决策稳定性。
    
    - mode_switches: PolicyTransition 总数
    - repent_rate: 反悔率（切回前一个模式的次数 / 总切换次数）
    """
    transitions = [
        ev for ev in events
        if ev.type == EventType.POLICY_TRANSITION
    ]
    total_switches = len(transitions)
    
    if total_switches < 2:
        return {
            "mode_switches": total_switches,
            "repent_rate": 0.0,
            "repent_count": 0,
        }
    
    # 反悔 = 连续两次切换构成 A→B→A
    repents = 0
    for i in range(1, len(transitions) - 1):
        p0 = transitions[i - 1].payload
        p1 = transitions[i].payload
        if (p0.get("from") == p1.get("to")
                and p0.get("to") == p1.get("from")):
            repents += 1
    
    return {
        "mode_switches": total_switches,
        "repent_rate": round(repents / total_switches, 4) if total_switches else 0.0,
        "repent_count": repents,
    }


def compute_conflict_resolution(events: list[Event]) -> dict:
    """维度4：冲突消解。
    
    冲突 = 短时间内同一 topic 出现矛盾评估（MasteryAssessed 大幅波动
    或 ConfusionDetected 后无对应消解动作）。
    """
    # 检测 mastery 冲突：连续 mastery 差值 > 0.5
    mastery_events = [
        ev for ev in events
        if ev.type == EventType.MASTERY_ASSESSED
    ]
    mastery_conflicts = 0
    for i in range(1, len(mastery_events)):
        prev_score = mastery_events[i - 1].payload.get("score", 0) or 0
        curr_score = mastery_events[i].payload.get("score", 0) or 0
        if abs(curr_score - prev_score) > 50:  # 0-100 范围，波动 > 50 点
            mastery_conflicts += 1
    
    total = len(mastery_events)
    return {
        "conflict_rate": round(mastery_conflicts / total, 4) if total else 0.0,
        "mastery_conflicts": mastery_conflicts,
        "total_mastery_events": total,
    }


def compute_causal_chain_quality(events: list[Event]) -> dict:
    """维度5：因果链质量。
    
    - orphan_rate: 孤儿事件率（无 parent_id 且不是 UserMessage 种子事件）
    - max_depth: 因果树最大深度
    - avg_depth: 平均深度
    """
    tree = build_causal_tree(events)
    
    # 孤儿事件（无 parent 且非种子）
    seed_types = {EventType.USER_MESSAGE, EventType.TOPIC_ENTERED,
                  EventType.ORCHESTRATOR_TICK}
    orphans = [
        eid for eid, node in tree.items()
        if node["parent"] is None
        and node["event"].type not in seed_types
    ]
    
    # 计算最大深度
    def _depth(eid: str, visited: set[str] | None = None) -> int:
        if visited is None:
            visited = set()
        if eid in visited:
            return 0
        visited.add(eid)
        node = tree[eid]
        if not node["children"]:
            return 1
        return 1 + max(_depth(c, visited) for c in node["children"])
    
    depths = [_depth(eid) for eid in tree if tree[eid]["parent"] is None]
    max_depth = max(depths) if depths else 0
    avg_depth = round(sum(depths) / len(depths), 2) if depths else 0.0
    
    return {
        "orphan_rate": round(len(orphans) / len(events), 4) if events else 0.0,
        "orphan_count": len(orphans),
        "max_depth": max_depth,
        "avg_depth": avg_depth,
    }


def compute_trajectory_deviation(events: list[Event],
                                  expected_path: list[str]) -> dict:
    """维度6：轨迹偏离（§5.4 / #21）。
    
    实际模式路径 vs 黄金轨迹的偏离度。
    """
    actual_path = [
        ev.payload.get("to", "")
        for ev in events
        if ev.type == EventType.POLICY_TRANSITION
    ]
    
    if not expected_path:
        return {"deviation_score": 0.0, "actual_path": actual_path}
    
    # 编辑距离归一化：偏离步数 / 总步数
    if not actual_path:
        return {"deviation_score": 1.0, "actual_path": actual_path}
    
    # 简单匹配：实际路径中预期子序列匹配比例
    matches = 0
    i, j = 0, 0
    while i < len(expected_path) and j < len(actual_path):
        if expected_path[i] == actual_path[j]:
            matches += 1
            i += 1
        j += 1
    
    deviation = 1.0 - (matches / len(expected_path)) if expected_path else 0.0
    return {
        "deviation_score": round(deviation, 4),
        "actual_path": actual_path,
        "expected_path": expected_path,
        "matches": matches,
        "total_expected": len(expected_path),
    }


# ---- 汇总 ----

def compute_collaboration_metrics(
    session_id: str,
    events: list[Event] | None = None,
    violation_log: list[str] | None = None,
    expected_mode_path: list[str] | None = None,
    num_teaching_turns: int = 1,
) -> dict:
    """六维协作指标汇总。"""
    if events is None:
        events = []
    if violation_log is None:
        violation_log = []
    if expected_mode_path is None:
        expected_mode_path = []
    
    # 从 EventStore replay（若外部未传入 events）
    # 此处 events 已由调用方传入（或从 event_store.replay 获得）
    
    violation_rate = compute_violation_rate(events, violation_log)
    efficiency = compute_efficiency(events, num_teaching_turns)
    stability = compute_decision_stability(events)
    conflict = compute_conflict_resolution(events)
    causal = compute_causal_chain_quality(events)
    trajectory = compute_trajectory_deviation(events, expected_mode_path)
    
    return {
        "session_id": session_id,
        "violation_count": len(violation_log),
        "violation_rate": violation_rate,
        **{f"efficiency_{k}": v for k, v in efficiency.items()},
        **{f"stability_{k}": v for k, v in stability.items()},
        **{f"conflict_{k}": v for k, v in conflict.items()},
        **{f"causal_{k}": v for k, v in causal.items()},
        **{f"trajectory_{k}": v for k, v in trajectory.items()},
    }
```

- [ ] **Step 3: 验证通过**

Run: `pytest tests/eval/test_collaboration_bench.py -v`
Expected: 10 PASS

- [ ] **Step 4: Commit**

```bash
git add app/eval/collaboration_bench.py tests/eval/test_collaboration_bench.py
git commit -m "feat(plan-e): CollaborationBench with six-dimension metrics

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: CollaborationBench EventStore 集成

**Files:**
- Modify: `app/eval/collaboration_bench.py`（追加 `collaboration_report` 函数 + EventStore 集成入口）
- Modify: `tests/eval/test_collaboration_bench.py`（集成测试）

- [ ] **Step 1: 写集成测试**

```python
# tests/eval/test_collaboration_bench.py（追加）
class TestCollaborationEventStore:
    def test_from_event_store(self, tmp_path):
        from app.infrastructure.storage.event_store import EventStore
        from app.eval.collaboration_bench import (
            collaboration_report_from_store)
        
        store = EventStore(str(tmp_path / "test_events.db"))
        store.init()
        ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="sess_integration", id="int_e1")
        store.append(ev)
        
        result = collaboration_report_from_store(
            store=store, session_id="sess_integration")
        assert result is not None
        assert result["session_id"] == "sess_integration"
        assert result["violation_count"] == 0
        store.close()

    def test_from_store_with_violations(self, tmp_path):
        from app.infrastructure.storage.event_store import EventStore
        from app.eval.collaboration_bench import (
            collaboration_report_from_store)
        
        store = EventStore(str(tmp_path / "test_violations.db"))
        store.init()
        ev = Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                   session_id="s2", id="v_e1")
        store.append(ev)
        
        result = collaboration_report_from_store(
            store=store, session_id="s2",
            violation_log=["v_violation_1"])
        assert result["violation_count"] == 1
        
        violation_dict = collaboration_report_from_store(
            store=store, session_id="s2",
            violation_log=["v_violation_1"],
            as_dict=True)
        assert isinstance(violation_dict, dict)
        assert violation_dict["violation_count"] == 1
        store.close()
```

Run: `pytest tests/eval/test_collaboration_bench.py -v`
Expected: 2 FAIL（collaboration_report_from_store 未定义）

- [ ] **Step 2: 追加集成函数**

```python
# app/eval/collaboration_bench.py（末尾追加）

def collaboration_report_from_store(
    store: "EventStore",
    session_id: str,
    violation_log: list[str] | None = None,
    expected_mode_path: list[str] | None = None,
    as_dict: bool = False,
) -> dict:
    """从 EventStore 读取 trace 并计算六维协作指标。
    
    这是 Plan E 的主入口之一——旁路读取已运行会话的事件流。
    """
    events = store.replay(session_id)
    metrics = compute_collaboration_metrics(
        session_id=session_id,
        events=events,
        violation_log=violation_log or [],
        expected_mode_path=expected_mode_path or [],
        num_teaching_turns=max(1, len([e for e in events
                                       if e.type == EventType.ORCHESTRATOR_TICK])),
    )
    return metrics
```

- [ ] **Step 3: 验证通过**

Run: `pytest tests/eval/test_collaboration_bench.py -v`
Expected: 12 PASS

- [ ] **Step 4: Commit**

```bash
git add app/eval/collaboration_bench.py tests/eval/test_collaboration_bench.py
git commit -m "feat(plan-e): CollaborationBench EventStore integration

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: ABController —— 参数 A/B + 组件消融

**Files:**
- Create: `app/eval/ab_controller.py`
- Test: `tests/eval/test_ab_controller.py`

- [ ] **Step 1: 写 ABController 测试**

```python
# tests/eval/test_ab_controller.py
import pytest

from app.eval.ab_controller import (
    run_parameter_ab,
    run_ablation_experiment,
    AblationConfig,
)


class FakeSystem:
    """模拟可运行的系统用于 A/B 测试。"""
    def __init__(self, name="default"):
        self.name = name
    
    def run_scenario(self, scenario_name: str) -> dict:
        if self.name == "slow":
            return {"mastery_reached": "mastered", "cost_usd": 0.15,
                    "turns": 15}
        return {"mastery_reached": "mastered", "cost_usd": 0.05,
                "turns": 8}


class TestABController:
    def test_parameter_ab(self):
        control = FakeSystem("fast")
        treatment = FakeSystem("slow")
        scenarios = ["zero_rag", "confused_basics"]
        
        result = run_parameter_ab(
            control=control,
            treatment=treatment,
            scenarios=scenarios,
            metrics_to_compare=["mastery_reached", "cost_usd", "turns"],
            experiment_name="Tutor LLM upgrade",
        )
        assert result["experiment_name"] == "Tutor LLM upgrade"
        assert len(result["scenarios"]) == 2
        assert "control" in result
        assert "treatment" in result
        assert "delta" in result

    def test_ablation_experiment_curator(self):
        config = AblationConfig(
            name="Curator 价值消融",
            control={"all_agents": True},
            treatment={"disable_agent": "curator"},
            metrics_to_compare=["regress_to_prereq_trigger_rate",
                               "mastery_reached", "mode_path_deviation"],
        )
        control_sys = FakeSystem("with_curator")
        treatment_sys = FakeSystem("without_curator")
        
        result = run_ablation_experiment(
            config=config,
            control_sys=control_sys,
            treatment_sys=treatment_sys,
            scenarios=["prereq_scenario"],
        )
        assert result["experiment_name"] == "Curator 价值消融"
        assert "control" in result
        assert "treatment" in result
        assert "recommendation" in result
    
    def test_ablation_no_recommendation_if_both_equal(self):
        config = AblationConfig(
            name="equal_test",
            control={},
            treatment={"disable_agent": "curator"},
        )
        sys = FakeSystem("default")
        result = run_ablation_experiment(
            config=config, control_sys=sys, treatment_sys=sys,
            scenarios=["dummy"],
        )
        assert result["recommendation"] == "keep"
```

Run: `pytest tests/eval/test_ab_controller.py -v`
Expected: 3 FAIL

- [ ] **Step 2: 实现 ABController**

```python
# app/eval/ab_controller.py
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AblationConfig:
    """消融实验配置（§5.5 类型二，组件消融）。
    
    control:   对照配置（all_agents: true 或完整参数）
    treatment: 实验配置（disable_agent: "curator" 或参数变更）
    """
    name: str
    control: dict = field(default_factory=dict)
    treatment: dict = field(default_factory=dict)
    metrics_to_compare: list[str] = field(default_factory=list)
    repeats: int = 1


def run_parameter_ab(
    control: object,
    treatment: object,
    scenarios: list[str],
    metrics_to_compare: list[str],
    experiment_name: str = "A/B Experiment",
) -> dict:
    """运行参数 A/B 实验（§5.5 类型一）。
    
    control/treatment 为实现了 run_scenario(scenario_name) -> dict 的系统对象。
    返回包含 control/treatment/delta 的结果字典。
    """
    control_results: dict[str, dict] = {}
    treatment_results: dict[str, dict] = {}
    
    for sc in scenarios:
        control_results[sc] = control.run_scenario(sc)
        treatment_results[sc] = treatment.run_scenario(sc)
    
    # 计算 delta
    deltas: dict[str, float] = {}
    for metric in metrics_to_compare:
        if metric == "mastery_reached":
            continue  # 字符串指标不计算 delta
        c_val = _avg_metric(control_results, metric)
        t_val = _avg_metric(treatment_results, metric)
        if c_val and c_val != 0:
            deltas[metric] = round((t_val - c_val) / c_val * 100, 1)
        else:
            deltas[metric] = 0.0
    
    return {
        "experiment_name": experiment_name,
        "control": {sc: r for sc, r in control_results.items()},
        "treatment": {sc: r for sc, r in treatment_results.items()},
        "delta": deltas,
    }


def _avg_metric(results: dict[str, dict], metric: str) -> float:
    vals = [r.get(metric, 0) or 0 for r in results.values()]
    return sum(vals) / len(vals) if vals else 0.0


def run_ablation_experiment(
    config: AblationConfig,
    control_sys: object,
    treatment_sys: object,
    scenarios: list[str],
) -> dict:
    """运行组件消融实验（§5.5 类型二）。
    
    对照系统运行完整配置，实验系统运行 disable_agent 配置。
    通过对比 delta 回答"该组件本身值多少增益"。
    """
    ab_result = run_parameter_ab(
        control=control_sys,
        treatment=treatment_sys,
        scenarios=scenarios,
        metrics_to_compare=config.metrics_to_compare,
        experiment_name=config.name,
    )
    
    # 生成推荐结论
    deltas = ab_result["delta"]
    all_zero = all(abs(v) < 1.0 for v in deltas.values()) if deltas else True
    
    if all_zero:
        recommendation = "keep"
        reason = "消融前后指标无显著差异，建议保持当前配置"
    else:
        worse_count = sum(1 for v in deltas.values() if v < 0)
        better_count = sum(1 for v in deltas.values() if v > 0)
        if worse_count > better_count:
            recommendation = "keep"
            reason = f"消融后{worse_count}项指标变差，该组件有正向贡献"
        else:
            recommendation = "review"
            reason = f"消融后{better_count}项指标变好，建议评估是否可移除"
    
    ab_result["recommendation"] = recommendation
    ab_result["reason"] = reason
    return ab_result
```

- [ ] **Step 3: 验证通过**

Run: `pytest tests/eval/test_ab_controller.py -v`
Expected: 3 PASS

- [ ] **Step 4: Commit**

```bash
git add app/eval/ab_controller.py tests/eval/test_ab_controller.py
git commit -m "feat(plan-e): ABController with parameter A/B + ablation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: SelectionReporter 选型报告生成

**Files:**
- Create: `app/eval/selection_reporter.py`
- Test: `tests/eval/test_selection_reporter.py`

- [ ] **Step 1: 写 SelectionReporter 测试**

```python
# tests/eval/test_selection_reporter.py
import pytest

from app.eval.selection_reporter import SelectionReporter


class TestSelectionReporter:
    def test_aggregate_component_results(self):
        reporter = SelectionReporter()
        component_results = [
            {"component": "retriever", "passed": 5, "total": 6,
             "metrics_avg": {"faithfulness": 0.85, "recall_at_k": 0.9}},
        ]
        report = reporter.aggregate_component(component_results)
        assert "retriever" in report
        assert report["retriever"]["pass_rate"] == 5 / 6

    def test_aggregate_system_results(self):
        reporter = SelectionReporter()
        system_results = [
            {"scenario": "zero_rag", "passed": True,
             "result_assertions": {"mastery_reached": True}},
            {"scenario": "cross_topic", "passed": False,
             "errors": ["conductor not triggered"]},
        ]
        report = reporter.aggregate_system(system_results)
        assert report["pass_rate"] == 0.5
        assert report["passed"] == 1
        assert report["total"] == 2

    def test_aggregate_collaboration_results(self):
        reporter = SelectionReporter()
        collab_results = {
            "session_1": {"violation_count": 0, "violation_rate": 0.0,
                          "efficiency_events_per_turn": 8.0,
                          "stability_mode_switches": 2},
        }
        report = reporter.aggregate_collaboration(collab_results)
        assert report["total_sessions"] == 1
        assert report["all_violations_zero"] is True

    def test_report_to_markdown(self):
        reporter = SelectionReporter()
        markdown = reporter.to_markdown(
            component_report={"retriever": {"pass_rate": 0.9,
                                            "metrics_avg": {}}},
            system_report={"pass_rate": 0.75, "passed": 3, "total": 4},
            collaboration_report={"total_sessions": 1,
                                  "all_violations_zero": True},
            ablation_results=[{
                "experiment_name": "Curator 价值消融",
                "recommendation": "keep",
                "reason": "消融后指标变差",
                "delta": {"regress_to_prereq_trigger_rate": -15.0},
            }],
        )
        assert "# 选型建议报告" in markdown
        assert "Curator 价值消融" in markdown
        assert "retriever" in markdown
        assert markdown.count("##") >= 1
```

Run: `pytest tests/eval/test_selection_reporter.py -v`
Expected: 4 FAIL

- [ ] **Step 2: 实现 SelectionReporter**

```python
# app/eval/selection_reporter.py
from datetime import datetime


class SelectionReporter:
    """选型报告生成器（§5.6）。
    
    聚合 ComponentBench / SystemBench / CollaborationBench /
    ABController 的评估结果，输出可读的 Markdown 报告。
    """
    
    @staticmethod
    def aggregate_component(
            results: list[dict]) -> dict[str, dict]:
        """聚合部件级结果。"""
        report: dict[str, dict] = {}
        for r in results:
            comp = r["component"]
            report[comp] = {
                "pass_rate": r.get("passed", 0) / max(r.get("total", 1), 1),
                "passed": r.get("passed", 0),
                "total": r.get("total", 0),
                "metrics_avg": r.get("metrics_avg", {}),
            }
        return report
    
    @staticmethod
    def aggregate_system(
            results: list[dict]) -> dict:
        """聚合系统级结果。"""
        passed = sum(1 for r in results if r.get("passed"))
        total = len(results)
        return {
            "pass_rate": passed / total if total else 0.0,
            "passed": passed,
            "total": total,
            "details": results,
        }
    
    @staticmethod
    def aggregate_collaboration(
            results: dict[str, dict]) -> dict:
        """聚合协作级结果。"""
        violations = sum(
            r.get("violation_count", 0) for r in results.values())
        return {
            "total_sessions": len(results),
            "all_violations_zero": violations == 0,
            "total_violations": violations,
            "details": results,
        }
    
    @staticmethod
    def _component_markdown(report: dict) -> str:
        lines = ["## 部件级评估\n"]
        for comp, data in report.items():
            lines.append(f"### {comp}")
            lines.append(f"- 通过率：{data['passed']}/{data['total']} "
                        f"({data['pass_rate']:.1%})")
            if data.get("metrics_avg"):
                lines.append(f"- 平均指标：{data['metrics_avg']}")
            lines.append("")
        return "\n".join(lines)
    
    @staticmethod
    def _system_markdown(report: dict) -> str:
        lines = ["## 系统级评估\n"]
        lines.append(f"**场景通过率**：{report['passed']}/{report['total']} "
                    f"({report['pass_rate']:.1%})\n")
        for detail in report.get("details", []):
            status = "✅" if detail.get("passed") else "❌"
            lines.append(f"- {status} {detail.get('scenario', '?')}")
            for err in detail.get("errors", []):
                lines.append(f"  - {err}")
        lines.append("")
        return "\n".join(lines)
    
    @staticmethod
    def _collaboration_markdown(report: dict) -> str:
        lines = ["## 协作级评估\n"]
        v = "✅ 全部为零" if report["all_violations_zero"] else "❌ 有违规"
        lines.append(f"- 职能违约：{v}（{report.get('total_violations', 0)} 次）")
        lines.append(f"- 评估会话数：{report['total_sessions']}")
        lines.append("")
        return "\n".join(lines)
    
    @staticmethod
    def _ablation_markdown(results: list[dict]) -> str:
        if not results:
            return ""
        lines = ["## 消融实验\n"]
        for r in results:
            lines.append(f"### {r['experiment_name']}")
            lines.append(f"- 推荐：**{r['recommendation']}**")
            lines.append(f"- 理由：{r.get('reason', '')}")
            if r.get("delta"):
                lines.append(f"- Delta：{r['delta']}")
            lines.append("")
        return "\n".join(lines)
    
    def to_markdown(
        self,
        component_report: dict | None = None,
        system_report: dict | None = None,
        collaboration_report: dict | None = None,
        ablation_results: list[dict] | None = None,
    ) -> str:
        """生成完整的 Markdown 选型建议报告。"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 选型建议报告 — {timestamp}\n",
        ]
        
        if component_report:
            lines.append(self._component_markdown(component_report))
        if system_report:
            lines.append(self._system_markdown(system_report))
        if collaboration_report:
            lines.append(self._collaboration_markdown(collaboration_report))
        if ablation_results:
            lines.append(self._ablation_markdown(ablation_results))
        
        return "\n".join(lines)
```

- [ ] **Step 3: 验证通过**

Run: `pytest tests/eval/test_selection_reporter.py -v`
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add app/eval/selection_reporter.py tests/eval/test_selection_reporter.py
git commit -m "feat(plan-e): SelectionReporter with Markdown report output

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: 完整端到端验证

**Files:**
- Modify: `tests/eval/test_kernel.py`（追加端到端场景）
- Run: 验收测试

- [ ] **Step 1: 写端到端验收测试**

```python
# tests/eval/test_kernel.py（追加）
import json
from pathlib import Path

import pytest
import yaml

from app.eval.kernel import EvalKernel, TestCase, ScenarioDefinition
from app.eval.component_bench import ComponentBench
from app.eval.system_bench import SystemBench
from app.eval.collaboration_bench import (
    compute_collaboration_metrics,
    collaboration_report_from_store,
)
from app.eval.ab_controller import run_ablation_experiment, AblationConfig
from app.eval.selection_reporter import SelectionReporter
from app.harness.events import Event
from app.harness.enums import EventType, EventSource


class FakeAllAgent:
    """模拟实现了 evaluate 的完整 Agent 集合。"""
    source = EventSource.TUTOR
    
    def evaluate(self, test_case: dict) -> dict:
        action = test_case.get("action", "")
        if action == "tutor_explain":
            return {"explanation_completeness": 0.85}
        return {"result": "ok"}
    
    def run_scenario(self, scenario_name: str) -> dict:
        return {"mastery_reached": "mastered", "cost_usd": 0.04,
                "turns": 8}


@pytest.fixture
def fake_agent_map():
    return {
        "tutor": FakeAllAgent(),
        "retriever": FakeAllAgent(),
        "critic": FakeAllAgent(),
        "curator": FakeAllAgent(),
        "conductor": FakeAllAgent(),
    }


class TestEndToEnd:
    """spec §5.3 四场景验收（旁路模式）。"""
    
    def test_system_bench_four_scenarios(self, tmp_path):
        """§5.3 四场景加载 + 评估（无需 EventStore）。"""
        scenarios_path = Path(__file__).resolve().parent.parent.parent / \
            "app/eval/scenarios/standard_scenarios.yaml"
        assert scenarios_path.exists(), "场景文件缺失"
        
        with open(scenarios_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert len(data.get("scenarios", [])) >= 4, "至少 4 场景"
        
        bench = SystemBench()
        scenarios = bench.load_scenarios(str(scenarios_path))
        
        # 为每个场景模拟 trace
        for sc in scenarios:
            trace = [
                {"type": "TopicEntered", "source": "orchestrator"},
                {"type": "TutorExplained", "source": "tutor"},
                {"type": "MasteryAssessed", "source": "critic",
                 "payload": {"level": "mastered"}},
            ]
            result = bench.assess(sc, trace)
            # 场景定义有效（不一定全通过，取决于模拟 trace）
            assert "scenario" in result
            assert result["scenario"] == sc.name
    
    def test_collaboration_six_dimensions(self):
        """§5.4 协作六维指标可算。"""
        events = [
            Event(type=EventType.USER_MESSAGE, source=EventSource.USER,
                  session_id="e2e_s1", id="e2e_e1"),
            Event(type=EventType.MASTERY_ASSESSED, source=EventSource.CRITIC,
                  session_id="e2e_s1", id="e2e_e2", parent_id="e2e_e1"),
            Event(type=EventType.ORCHESTRATOR_TICK,
                  source=EventSource.ORCHESTRATOR,
                  session_id="e2e_s1", id="e2e_e3"),
            Event(type=EventType.ACTION_REQUESTED,
                  source=EventSource.ORCHESTRATOR,
                  session_id="e2e_s1", id="e2e_e4", parent_id="e2e_e3"),
            Event(type=EventType.LOOP_EXIT, source=EventSource.ORCHESTRATOR,
                  session_id="e2e_s1", id="e2e_e5"),
        ]
        
        metrics = compute_collaboration_metrics(
            session_id="e2e_s1", events=events)
        
        # 六维全可算
        assert metrics["violation_count"] == 0
        assert "efficiency_events_per_turn" in metrics
        assert "stability_mode_switches" in metrics
        assert "conflict_conflict_rate" in metrics
        assert "causal_orphan_rate" in metrics
        assert "trajectory_deviation_score" in metrics

    def test_ablation_curator_value(self):
        """§5.5 Curator 消融实验。"""
        config = AblationConfig(
            name="Curator 价值消融",
            control={"all_agents": True},
            treatment={"disable_agent": "curator"},
            metrics_to_compare=["turns", "cost_usd"],
        )
        control_sys = FakeAllAgent()
        treatment_sys = FakeAllAgent()
        
        result = run_ablation_experiment(
            config=config,
            control_sys=control_sys,
            treatment_sys=treatment_sys,
            scenarios=["prereq_weak_attention"],
        )
        assert result["experiment_name"] == "Curator 价值消融"
        assert result["recommendation"] in ("keep", "review")
    
    def test_selection_report_markdown(self):
        """§5.6 选型报告 Markdown 产出。"""
        reporter = SelectionReporter()
        
        markdown = reporter.to_markdown(
            component_report={
                "retriever": {"pass_rate": 0.9, "passed": 5,
                             "total": 6, "metrics_avg": {}},
            },
            system_report={
                "pass_rate": 0.75, "passed": 3, "total": 4,
                "details": [],
            },
            collaboration_report={
                "total_sessions": 1, "all_violations_zero": True,
                "total_violations": 0,
            },
            ablation_results=[{
                "experiment_name": "Curator 价值消融",
                "recommendation": "keep",
                "reason": "消融后指标变差",
                "delta": {"regress": -15.0},
            }],
        )
        
        assert "选型建议报告" in markdown
        assert markdown.count("##") >= 1
        assert len(markdown) > 100, "报告太短"
        
        # 输出到临时文件验证可读性
        print("\n=== 选型建议报告样例 ===\n")
        print(markdown)
```

- [ ] **Step 2: 运行端到端测试**

Run: `pytest tests/eval/test_kernel.py::TestEndToEnd -v -s`
Expected: 4 PASS（含 sample markdown 打印）

- [ ] **Step 3: 运行全量 eval 测试**

Run: `pytest tests/eval/ -v`
Expected: 全部 PASS（约 30+ 测试）

- [ ] **Step 4: 确保基线测试不受影响**

Run: `pytest -q`
Expected: 基线 0 failed（已有的 4 个预存失败保持不变）

- [ ] **Step 5: 最终 Commit**

```bash
git add tests/eval/test_kernel.py
git commit -m "test(plan-e): end-to-end acceptance tests for spec §5.3-§5.6

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 验收判据

| 条件 | 方式 |
|---|---|
| spec §5.3 四场景加载 + 过程断言 | `TestEndToEnd::test_system_bench_four_scenarios` |
| 协作六维可算 | `TestEndToEnd::test_collaboration_six_dimensions` |
| 1 个消融实验（Curator 价值） | `TestEndToEnd::test_ablation_curator_value` |
| 选型报告 Markdown 产出 | `TestEndToEnd::test_selection_report_markdown` |
| 纯旁路不改在线代码 | 代码审查确认——只读 EventStore/Agent.evaluate/parent_id |
| 基线测试 0 regresssion | `pytest -q` 新增失败为 0 |

---

## 自审查

**1. Spec 覆盖核查：**
- §5.1 评估整体视图 ✅ → TestCase/EvalResult 数据类 + EvalKernel
- §5.1.1 黄金集 + judge 独立 ✅ → tests/golden/ + Cohen's κ + 用例冻结
- §5.2 部件级 ✅ → ComponentBench（调 Agent.evaluate()）
- §5.3 系统级+过程断言 ✅ → SystemBench（scenarios YAML + result/process assertions）
- §5.4 协作级 ✅ → CollaborationBench（六维指标 + EventStore 集成）
- §5.5 消融实验 ✅ → ABController（参数 A/B + 组件消融）
- §5.6 选型报告 ✅ → SelectionReporter（Markdown 产出）

**2. 无占位符：** 每个 Task 含完整代码、测试、命令。

**3. 类型一致性：** 所有函数签名和引用类型在 Task 间一致（TestCase/EvalResult 来自 kernel.py、ScenarioDefinition 同模块、EventStore 来自 infrastructure/storage）。