# DeepEval 落地 §5.2 部件级 LLM-judge 指标 — 设计文档

> **用途**：用 DeepEval 框架替换 ComponentBench 中 Retriever / Tutor 评估指标的「字符级启发式占位」，把母 spec §5.2 早已设计、§5.1.1 早已约束的 RAG 三件套与 LLM-judge 指标真正落地。
> **日期**：2026-06-22
> **技术栈**：DeepEval（LLM-as-judge 评估框架）+ 既有 `app/eval/` 框架（Plan E 已实现骨架）
> **重构策略**：纯替换部件级 `evaluate()` 的指标算法 + 新增 judge 适配层；不改 ComponentBench/EvalKernel 调度逻辑、不改在线 Agent 的 `handle()` 教学路径
> **母 spec**：`docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` §5.1.1 / §5.2
> **调研来源**：`Learned/DeepEval_测评方案.md`

---

## 0. 决策快照

| # | 维度 | 决策 |
|---|---|---|
| 1 | 落地范围 | Retriever 三件套（Faithfulness/AnswerRelevancy/ContextualRelevancy）+ Tutor G-Eval 教学指标（引导性/清晰度）；Critic/Curator/Conductor 本轮不动 |
| 2 | judge 模型 | 不绑定具体 provider，spec 留**可配置接口**；§5.1.1「judge 与被评 Agent 不同族」作为**配置校验规则**强制 |
| 3 | 替换对象 | 仅 `Retriever.evaluate()` 与 `Tutor.evaluate()` 的指标计算段；其余 evaluate 占位保持不变 |
| 4 | 框架边界 | DeepEval 只在 L2 旁路（`app/eval/` 与 Agent.evaluate）出现，**严禁进入在线 `handle()` 路径** |
| 5 | 降级策略 | judge 不可用（无 key / 不同族校验失败）时，evaluate 返回带 `degraded: true` 标记的占位指标，不崩溃 |
| 6 | 依赖管理 | DeepEval 作为**可选依赖**（eval extra），在线运行不强制安装 |
| 7 | 阈值归属 | 黄金用例的 expected 阈值留在 `golden_cases.py`，DeepEval metric 的 threshold 仅用于单测门槛，不与 ComponentBench 的 expected 重复 |

### 0.1 否决项及理由

| 被否方案 | 否决理由 |
|---|---|
| 新建独立评估体系 | 母 spec §5 + Plan E 已有完整三层框架与 ComponentBench 接口，DeepEval 只是填 §5.2 指标的实现，另起炉灶违背单一框架 |
| judge 写死 GPT-4o | 项目当前只配了 `openai_*`，但 §5.1.1 要求 judge 与被评不同族（Tutor 用 Claude），写死会绑死 provider 且无法校验不同族，故留可配置接口 |
| DeepEval 进在线 Agent.handle() | §5.1/§3.6 明确 L2 旁路与 L1 在线分层，在线评估归 Critic，DeepEval 入在线路径属越权 |
| 本轮一并做 CI/CD + baseline | 范围决策仅到 Retriever+Tutor；CI 依赖外部 secret、baseline 是独立关注点，拆后续 spec，避免本 spec 过长 |
| 保留字符级 Jaccard 作 fallback 指标 | 字符 Jaccard 与语义无关（`retriever.py:151` 自注「初期启发式」），保留会让降级结果误导选型，故降级显式标 `degraded` 而非伪装成真分数 |

---

## 1. 现状与缺口（写 spec 的事实依据）

| 事实 | 位置 |
|---|---|
| 母 spec §5.2 把 RAG 三件套写进 Retriever 指标、把「解释完整性 rubric-LLM-judge」写进 Tutor 指标 | `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md:562,561` |
| §5.1.1 规定 LLM-judge 必须与被评 Agent 不同族、盲评、judge 自身 κ≥0.6 才采信 | 同上 `:532-536` |
| Plan E 已实现 ComponentBench：调 `agent.evaluate(tc.input)`，按 `expected` 阈值判定 passed | `app/eval/component_bench.py:23` |
| `Retriever.evaluate()` 三件套是**字符级 Jaccard / token 重叠占位**，注释自承「后续可替换 ragas」 | `app/agents/retriever.py:151` |
| `Tutor.evaluate()` 解释完整性是**字符 Counter 交并比占位** | `app/agents/tutor.py:126-131` |
| 全 repo **零 LLM-judge 实现** | grep `as.judge / llm_judge` 无结果 |
| 项目 LLM 配置只有 `openai_*` 字段 | `app/core/config.py:9-11` |
| LLM Service 入口 | `app/infrastructure/llm.py` |

**缺口结论**：框架（调度）齐全，指标（语义评估）是占位。本 spec 只补「指标实现 + judge 适配 + 不同族校验」三件事。

---

## 2. 资产清单与三色血缘

| 名字 | 归属子系统 | 功能（干嘛） | 触发 / 入口 | 位置（file:line） | 血缘 |
|---|---|---|---|---|---|
| `ComponentBench` | L2 eval | 对 Agent.evaluate() 跑黄金用例、按 expected 判 passed | `EvalKernel.run_component_bench` | `app/eval/component_bench.py:23` | 🟢 保持现状（不改调度） |
| `Retriever.evaluate()` | Agent 部件 | 当前字符级 Jaccard 占位算三件套 | ComponentBench 调用 | `app/agents/retriever.py:105` | 🟡 改动（替换指标段） |
| `Tutor.evaluate()` | Agent 部件 | 当前字符 Counter 占位算解释完整性 | ComponentBench 调用 | `app/agents/tutor.py:99` | 🟡 改动（替换指标段） |
| `golden_cases.py` | eval fixtures | Retriever/Tutor 黄金用例 + expected 阈值 | ComponentBench 加载 | `app/eval/fixtures/golden_cases.py:19` | 🟡 改动（补 G-Eval 用例字段） |
| `app/core/config.py` | core | 全局配置；当前只有 openai_* | Settings 单例 | `app/core/config.py:9` | 🟡 改动（加 judge_* 配置） |
| `JudgeProvider` 适配层 | L2 eval | 把项目 LLM 配置包成 DeepEval 的 model 接口 + 不同族校验 | Retriever/Tutor.evaluate 内构造 | `app/eval/judge.py` | 🔴 新建 |
| `deepeval` 库 | 外部依赖 | LLM-as-judge 指标实现（Faithfulness/GEval 等） | judge.py import | pyproject eval extra | 🔴 新建（可选依赖） |
| `tests/eval/test_judge.py` | 测试 | judge 适配层 + 不同族校验 + 降级单测 | pytest | `tests/eval/test_judge.py` | 🔴 新建 |

---

## 3. 整体架构

### 3.1 分层边界（DeepEval 只在 L2）

```
L1 在线（handle 路径）          ← DeepEval 严禁进入（决策#4）
   Critic 发 RAGQualityAssessed
        │ 事件沉淀
        ▼
   EventStore
        │ replay
        ▼
L2 旁路 EvalKernel
   └─ ComponentBench（🟢 不改）
        └─ agent.evaluate(tc.input)
              ├─ Retriever.evaluate  🟡 ── 构造 ── ▶ JudgeProvider 🔴 ── ▶ deepeval 🔴
              └─ Tutor.evaluate      🟡 ── 构造 ── ▶ JudgeProvider 🔴 ── ▶ deepeval 🔴
```

**关键约束**：DeepEval 的 import 只出现在 `app/eval/judge.py` 与被它注入的 evaluate 指标段；在线 `handle()` 不 import deepeval，保证可选依赖缺席时在线运行零影响（决策#4/#6）。

### 3.2 三个子模块职责

| 子模块 | 职责 | 接口契约 |
|---|---|---|
| **JudgeProvider（新建）** | ① 读 config 的 judge_* 字段构造 DeepEval 可用的 model；② 执行 §5.1.1 不同族校验；③ judge 不可用时返回 `None` 触发降级 | `build_judge(target_family: str) -> JudgeHandle \| None` |
| **Retriever.evaluate 指标段（改）** | 把检索结果包成 `LLMTestCase`，调 DeepEval 三件套 metric，回填 score | 输入/输出 dict 结构**保持不变**，只换内部算法 |
| **Tutor.evaluate 指标段（改）** | 把教学输出包成 `LLMTestCase`，调 G-Eval 引导性/清晰度 metric | 同上，dict 结构不变 |

**为什么 evaluate 的输入输出 dict 结构不变**（对照决策）：

| | 本方案（保持 dict 契约） | 备选（改 evaluate 签名/返回结构） |
|---|---|---|
| 做法 | 只换 evaluate 内部指标算法，键名（faithfulness 等）不变 | 返回带 reason 的富对象 |
| 代价 / 收益 | ComponentBench（🟢）`_check_expected` 零改动；reason 走 meta 旁路带出 | 要同步改 ComponentBench 判定逻辑 + golden_cases |
| | **选它**：改动半径最小，reason 仍可经 EvalResult.meta 传出（见 §4.3） | 牵连 §5.2 接口契约，超范围 |

---

## 4. 核心接口设计

### 4.1 JudgeProvider 适配层（`app/eval/judge.py`）

```python
"""JudgeProvider — 把项目 LLM 配置包成 DeepEval model + §5.1.1 不同族校验。"""
from dataclasses import dataclass
from typing import Literal

# 可选依赖：deepeval 不存在时该模块 import 会 fail，由调用方 try-except 捕获降级
try:
    from deepeval.models.base_model import DeepEvalBaseLLM
except ImportError:
    DeepEvalBaseLLM = object  # 占位，避免模块加载失败

from app.core.config import settings


@dataclass
class JudgeHandle:
    """judge 的不透明句柄。"""
    model: DeepEvalBaseLLM
    family: str  # "openai" | "anthropic" | ...


ModelFamily = Literal["openai", "anthropic", "unknown"]


def infer_family(model_name: str) -> ModelFamily:
    """从模型名推断所属族。§5.1.1 不同族校验的基础。"""
    lower = model_name.lower()
    if "gpt" in lower or "o1" in lower or "davinci" in lower:
        return "openai"
    if "claude" in lower or "sonnet" in lower or "opus" in lower or "haiku" in lower:
        return "anthropic"
    return "unknown"


def build_judge(target_agent_family: ModelFamily) -> JudgeHandle | None:
    """构造 judge 并校验不同族（§5.1.1）。
    
    参数:
      target_agent_family: 被评 Agent 的模型族（如 Tutor 用 Claude → "anthropic"）
    
    返回:
      - JudgeHandle: judge 可用且不同族
      - None: judge 不可用（无 key）或同族（违背 §5.1.1），触发降级
    """
    # 当前项目只配了 openai，后续可扩展 judge_provider / judge_model 配置
    judge_key = getattr(settings, "openai_api_key", "")
    judge_model_name = getattr(settings, "openai_model", "gpt-4o-mini")
    
    if not judge_key:
        return None  # 无 key，降级
    
    judge_family = infer_family(judge_model_name)
    
    # §5.1.1 不同族校验
    if judge_family == target_agent_family:
        return None  # 同族，违背约束，降级
    if judge_family == "unknown" or target_agent_family == "unknown":
        return None  # 族不明，保守降级
    
    # 构造 DeepEval 的 model 接口（简化示例，实际需适配 generate 方法）
    from deepeval.models import OpenAIModel
    
    model = OpenAIModel(
        model=judge_model_name,
        api_key=judge_key,
    )
    
    return JudgeHandle(model=model, family=judge_family)
```

**配置扩展点（预留）**：后续可在 `config.py` 加 `judge_provider` / `judge_model` / `judge_api_key` 独立字段；当前直接复用 `openai_*`，因为项目 Tutor 用 Claude（Anthropic 族），OpenAI 恰好满足不同族。

### 4.2 Retriever.evaluate 指标替换（`app/agents/retriever.py`）

**改动范围**：`:151-165` 指标计算段，其余不动。

```python
# retriever.py:105 起的 evaluate 方法
def evaluate(self, test_case: dict) -> dict:
    """部件级评估接口（§5.2 RAG 三件套 + recall@k）。"""
    query = test_case.get("query", "")
    golden_chunks = test_case.get("golden_chunks", [])
    golden_answer = test_case.get("golden_answer", "")
    top_k = test_case.get("top_k", 5)

    # 执行检索（保持不变）
    t0 = time.time()
    result = self._coordinator.search(query, sources=None, top_k=top_k)
    latency_ms = (time.time() - t0) * 1000
    retrieved_contents = [c.content for c in result.chunks]

    # --- recall@k：保持原启发式（不依赖 LLM） ---
    if golden_chunks:
        hit = sum(1 for g in golden_chunks
                  if any(g in rc or rc in g for rc in retrieved_contents))
        recall_at_k = hit / len(golden_chunks)
    else:
        recall_at_k = 1.0

    # --- 🟡 替换段：三件套用 DeepEval ---
    try:
        from app.eval.judge import build_judge
        from deepeval.test_case import LLMTestCase
        from deepeval.metrics import (
            FaithfulnessMetric,
            AnswerRelevancyMetric,
            ContextualRelevancyMetric,
        )

        # 构造 judge（target 是 retriever 自己，但 retriever 不用 LLM 做推理，
        # 此处 judge 评估的是"检索+生成"组合质量，假设生成侧用项目默认 LLM）
        # 实际上 Retriever 评估的 faithfulness 是"检索内容能否支撑 golden_answer"，
        # 不涉及生成，故 target_family 取项目主 LLM 族（假设 Claude）
        judge_handle = build_judge(target_agent_family="anthropic")
        
        if judge_handle is None:
            # 降级：返回占位分数 + degraded 标记
            return {
                "recall_at_k": recall_at_k,
                "faithfulness": 0.0,
                "answer_relevancy": 0.0,
                "context_precision": 0.0,
                "latency_ms": latency_ms,
                "degraded": True,
                "degraded_reason": "judge 不可用或不同族校验失败",
            }

        # 包装为 LLMTestCase
        combined_context = " ".join(retrieved_contents)
        test_case_obj = LLMTestCase(
            input=query,
            actual_output=golden_answer,  # 评估检索是否支撑黄金答案
            retrieval_context=retrieved_contents,
        )

        # 计算三件套
        faithfulness_metric = FaithfulnessMetric(model=judge_handle.model)
        faithfulness_metric.measure(test_case_obj)
        faithfulness = faithfulness_metric.score

        relevancy_metric = AnswerRelevancyMetric(model=judge_handle.model)
        relevancy_metric.measure(test_case_obj)
        answer_relevancy = relevancy_metric.score

        context_metric = ContextualRelevancyMetric(model=judge_handle.model)
        context_metric.measure(test_case_obj)
        context_precision = context_metric.score

        return {
            "recall_at_k": recall_at_k,
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_precision": context_precision,
            "latency_ms": latency_ms,
            "degraded": False,
        }

    except ImportError:
        # DeepEval 未安装（可选依赖），降级
        return {
            "recall_at_k": recall_at_k,
            "faithfulness": 0.0,
            "answer_relevancy": 0.0,
            "context_precision": 0.0,
            "latency_ms": latency_ms,
            "degraded": True,
            "degraded_reason": "DeepEval 未安装（eval extra）",
        }
```

**关键点**：
- `degraded` 字段：降级时显式标记，ComponentBench 可检测并跳过该用例或警告
- 降级不抛异常：保证评估流程不中断
- recall@k 保持启发式：不依赖 LLM，成本低

### 4.3 Tutor.evaluate G-Eval 指标替换（`app/agents/tutor.py`）

**改动范围**：`:126-135` 指标计算段。

```python
# tutor.py:99 起的 evaluate 方法
def evaluate(self, test_case: dict) -> dict:
    """部件级评估（§5.2）：生成教学内容并计算质量指标。"""
    topic = test_case.get("topic", "")
    action = test_case.get("action", "tutor_explain")
    golden = test_case.get("golden_response", "")

    # 生成教学内容（保持不变）
    ws = WorkspaceState(session_id="__eval__", user_id="__eval__",
                        current_topic=topic)
    trigger = Event(
        type=EventType.ACTION_REQUESTED, source=EventSource.ORCHESTRATOR,
        session_id="__eval__",
        payload={"action": action, "target": str(EventSource.TUTOR)})
    produced = self.handle(trigger, ws)

    content = ""
    for ev in produced:
        content = ev.payload.get("content", "")
        if content:
            break

    response_length = len(content)

    # --- 🟡 替换段：G-Eval 教学指标 ---
    try:
        from app.eval.judge import build_judge
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams
        from deepeval.metrics import GEval

        # Tutor 用 Claude，judge 需不同族
        judge_handle = build_judge(target_agent_family="anthropic")
        
        if judge_handle is None or not content:
            return {
                "explanation_completeness": 0.0,
                "guidance_quality": 0.0,
                "clarity": 0.0,
                "response_length": response_length,
                "degraded": True,
                "degraded_reason": "judge 不可用或内容为空",
            }

        test_case_obj = LLMTestCase(
            input=f"请解释主题：{topic}",
            actual_output=content,
        )

        # G-Eval 引导性指标
        guidance_metric = GEval(
            name="Guidance Quality",
            criteria="评估答案是否通过提问、提示等方式引导学生自己思考，而非直接给出完整答案",
            evaluation_steps=[
                "检查是否包含启发性问题",
                "判断提示的程度是否适当（不能太明显也不能太隐晦）",
                "确认是否给学生留出了思考空间",
            ],
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=judge_handle.model,
        )
        guidance_metric.measure(test_case_obj)
        guidance_quality = guidance_metric.score

        # G-Eval 清晰度指标
        clarity_metric = GEval(
            name="Explanation Clarity",
            criteria="评估解释是否清晰、结构化、易于理解",
            evaluation_steps=[
                "检查是否使用了分步骤的解释",
                "确认是否包含了必要的例子",
                "评估术语使用是否适合学生水平",
            ],
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=judge_handle.model,
        )
        clarity_metric.measure(test_case_obj)
        clarity = clarity_metric.score

        # explanation_completeness 用 G-Eval 替代原 Counter
        completeness_metric = GEval(
            name="Explanation Completeness",
            criteria="评估解释是否覆盖了主题的核心概念",
            evaluation_steps=[
                "确认主题的关键要素是否被提及",
                "检查解释的完整性",
            ],
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=judge_handle.model,
        )
        completeness_metric.measure(test_case_obj)
        explanation_completeness = completeness_metric.score

        return {
            "explanation_completeness": explanation_completeness,
            "guidance_quality": guidance_quality,
            "clarity": clarity,
            "response_length": response_length,
            "degraded": False,
            # 可选：把 reasoning 带出到 meta
            "_reasoning": {
                "guidance": guidance_metric.reason,
                "clarity": clarity_metric.reason,
                "completeness": completeness_metric.reason,
            }
        }

    except ImportError:
        return {
            "explanation_completeness": 0.0,
            "guidance_quality": 0.0,
            "clarity": 0.0,
            "response_length": response_length,
            "degraded": True,
            "degraded_reason": "DeepEval 未安装",
        }
```

**reasoning 传出机制**：`_reasoning` 键（下划线前缀表内部）在 ComponentBench 的 `EvalResult.meta` 旁路传出，SelectionReporter 可展示（呼应改进点 5）。

### 4.4 配置扩展（`app/core/config.py`）

```python
# config.py 新增（预留，当前用既有 openai_* 字段）
class Settings(BaseSettings):
    # ... 既有字段 ...
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    
    # 🔴 新增：judge 专用配置（可选，未设置则复用 openai_*）
    judge_provider: str = ""  # "openai" | "anthropic" | ""（空表复用 openai）
    judge_model: str = ""      # 空表复用 openai_model
    judge_api_key: str = ""    # 空表复用 openai_api_key
```

**实施优先级**：首版直接用 `openai_*`（决策#2 满足当前不同族需求），预留字段待后续独立 judge 配置时再填充。

---

## 5. 降级策略与错误处理

| 降级场景 | 检测点 | 行为 | 影响半径 |
|---|---|---|---|
| DeepEval 未安装 | `import deepeval` 失败 | 返回 `degraded: true` + 0 分占位 | 单个 evaluate 调用 |
| judge key 缺失 | `build_judge` 读 config 无 key | 同上 | 单个 evaluate |
| 不同族校验失败 | `infer_family` 同族 | 同上 | 单个 evaluate（阻断自裁判） |
| DeepEval metric 抛异常 | measure 调用崩溃 | try-except 捕获 → degraded | 单个指标，不影响其他指标 |

**ComponentBench 对 degraded 的处理**（`component_bench.py` 增强）：

```python
# component_bench.py:23 处增加降级检测
def run(self, component: str, test_cases: list[TestCase]) -> list[EvalResult]:
    for tc in test_cases:
        try:
            metrics = agent.evaluate(tc.input)
        except Exception as e:
            # ... 既有逻辑 ...
        
        # 🔴 新增：降级检测
        if metrics.get("degraded"):
            errors.append(f"降级运行：{metrics.get('degraded_reason', '未知')}")
            # 降级用例标记为非关键失败，不计入 passed 统计
            results.append(EvalResult(
                test_name=tc.name, component=component,
                passed=False,  # 保守标记为失败，避免误判
                metrics=metrics,
                errors=errors,
                meta={"degraded": True}
            ))
            continue
        
        # 正常路径 ...
```

**为什么降级标 passed=False 而非跳过**：

| | 本方案（标 False） | 备选（跳过不计） |
|---|---|---|
| 做法 | degraded 用例算入 total 但 passed=False | 过滤 degraded 用例，不进统计 |
| 代价/收益 | 通过率下降暴露 judge 配置问题，促使修复 | 隐藏问题，可能误认为"全绿" |
| | **选它**：保守策略，防止降级被静默忽视 | 如果 degraded 占多数会让报告失真 |

---

## 6. 实施步骤（有序、可验证）

### Phase 1: Judge 适配层 + 单测（1-2 天）

**产出**：
- `app/eval/judge.py`（build_judge + infer_family + JudgeHandle）
- `tests/eval/test_judge.py`（不同族校验 + 降级场景单测）
- `pyproject.toml` 添加 `deepeval` 到 eval extra

**验收**：
```bash
pip install -e ".[eval]"
pytest tests/eval/test_judge.py -v
# 期望：不同族通过、同族返回 None、无 key 返回 None
```

### Phase 2: Retriever 三件套替换（1 天）

**产出**：
- 修改 `app/agents/retriever.py:151-165`
- 修改 `app/eval/fixtures/golden_cases.py` Retriever 用例（补 golden_answer 字段）
- 补充 `tests/unit/agents/test_retriever.py` 的 evaluate 单测

**验收**：
```bash
pytest tests/unit/agents/test_retriever.py::test_evaluate_with_deepeval -v
pytest tests/eval/test_component_bench.py -k retriever -v
# 期望：faithfulness/answer_relevancy/context_precision 非 0 分
```

### Phase 3: Tutor G-Eval 替换（1-2 天）

**产出**：
- 修改 `app/agents/tutor.py:126-135`
- 修改 `golden_cases.py` Tutor 用例（补 topic 字段）
- 补充 Tutor evaluate 单测

**验收**：
```bash
pytest tests/unit/agents/test_tutor.py::test_evaluate_geval -v
pytest tests/eval/test_component_bench.py -k tutor -v
# 期望：guidance_quality/clarity 非 0 分 + _reasoning 有内容
```

### Phase 4: ComponentBench 降级处理 + 端到端验收（0.5 天）

**产出**：
- 修改 `app/eval/component_bench.py:23` 增加 degraded 检测
- 端到端运行 ComponentBench

**验收**：
```bash
# 无 OPENAI_API_KEY 时触发降级
unset OPENAI_API_KEY
pytest tests/eval/test_component_bench.py -v
# 期望：所有 Retriever/Tutor 用例标 degraded=True，passed=False

# 有 key 时正常运行
export OPENAI_API_KEY=sk-...
pytest tests/eval/test_component_bench.py -v
# 期望：部分用例 passed=True，分数 > 0
```

---

## 7. 成本估算与优化预留

| 场景 | 调用次数 | 成本（GPT-4o-mini $0.15/1M in, $0.6/1M out） |
|---|---|---|
| 单个 Retriever 用例（3 指标） | 3 次 LLM 调用 | ~$0.003 |
| 单个 Tutor 用例（3 个 G-Eval） | 3 次 LLM 调用 | ~$0.003 |
| 完整 ComponentBench（Retriever 6 用例 + Tutor 1 用例） | 21 次调用 | ~$0.063 |

**优化预留**（后续 spec）：
- 模型分级：简单指标用 gpt-4o-mini，复杂指标（Faithfulness）用 gpt-4o
- 批量并行：DeepEval 的 `run_async=True`
- 采样：大黄金集分层采样

当前版本：**暂不优化**（决策#1 范围仅到指标落地，成本优化拆独立 spec）

---

## 8. 验收标准

| 条件 | 验证方式 |
|---|---|
| §5.1.1 不同族校验生效 | `test_judge.py::test_same_family_rejected` PASS |
| Retriever 三件套非启发式 | `test_retriever.py::test_evaluate_deepeval` 分数与字符 Jaccard 显著不同 |
| Tutor G-Eval 有 reasoning | `test_tutor.py::test_evaluate_geval` 返回的 `_reasoning` 非空 |
| 降级不崩溃 | 无 key 运行 ComponentBench，所有用例标 degraded，无异常 |
| 在线路径零影响 | `grep -r "import deepeval" app/agents/` 仅在 evaluate 方法内出现 |
| 可选依赖隔离 | 不装 eval extra 时 `python -c "from app.agents.retriever import RetrieverAgent"` 成功 |

---

## 9. 后续扩展点（不在本 spec 范围）

1. **Critic/Curator/Conductor 的 LLM-judge 指标**：母 spec §5.2 已设计（掌握度一致率 κ / 图谱连接合理性 / Conductor 决策合理性），待本轮验证 DeepEval 可行后逐个落地
2. **CI/CD 集成**：GitHub Actions + pytest marker critical，阈值门槛（见前述改进点 4）
3. **baseline 版本对比**：`EvalKernel.save_baseline` + delta 追踪（改进点 6）
4. **成本优化**：模型分级 + 批量并行（改进点 3）
5. **SelectionReporter reasoning 展示**：从 EvalResult.meta 提取 `_reasoning` 渲染到 Markdown（改进点 5）

---

## 10. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| DeepEval API 变更 | 中 | 中 | 锁定版本 `deepeval==1.x`，升级前跑回归测试 |
| judge 成本超预算 | 低 | 中 | 当前仅 Retriever+Tutor 少量用例，Phase 4 验收时实测成本，超限则触发优化 spec |
| 不同族校验漏判（新模型名未识别） | 中 | 高 | `infer_family` 返回 `unknown` 保守降级；补充单测覆盖新模型名 |
| G-Eval 分数不稳定（幻觉/主观） | 高 | 中 | §5.1.1 要求 judge 自身 κ≥0.6，Phase 3 验收时人工抽查 20 个 Tutor 输出，κ 不达标则细化 criteria/evaluation_steps |
| 降级用例过多导致报告失真 | 低 | 中 | ComponentBench 统计 degraded 占比，>50% 时报告顶部警告"评估不可信" |

---

## 附录 A：与 DeepEval 调研笔记的映射

| `Learned/DeepEval_测评方案.md` 章节 | 本 spec 落地位置 |
|---|---|
| §3.1 RAG Triad（Faithfulness/AnswerRelevancy/ContextualRelevancy） | §4.2 Retriever.evaluate |
| §3.3 G-Eval 自定义指标 | §4.3 Tutor.evaluate（引导性/清晰度） |
| §5.1.1 judge 模型独立性 | §4.1 JudgeProvider 不同族校验 |
| §6.1 成本优化（模型分级） | §9 后续扩展点 #4 |
| §7.3 失败案例 reasoning | §4.3 `_reasoning` 旁路传出 |

---

**文档状态**：✅ 设计完成，待评审后进入实施 Phase 1

