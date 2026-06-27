# 混合评估方案（RAGAS for Retriever + DeepEval for Tutor）— 设计文档

> **用途**：把母 spec §5.2 设计的 RAG 三件套与教学 LLM-judge 指标真正落地，替换 ComponentBench 中 Retriever / Tutor 的「字符级启发式占位」。本文档是**实际执行方案**（混合架构）的统一设计，整合此前两份文档的决策。
> **日期**：2026-06-22
> **状态**：Phase 1 已落地（RAGAS Retriever + judge 适配层已实现并合入 main `fc210d4`）；Phase 2/3 待实施。
> **技术栈**：RAGAS 0.4.3（检索质量）+ DeepEval（教学质量，Phase 3）+ 既有 `app/eval/` 框架（Plan E 骨架）
> **母 spec**：`docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` §5.1.1 / §5.2
> **决策依据**：`docs/research/2026-06-22-deepeval-vs-ragas-adoption-report.md`（对比报告，混合方案的论证）
> **备选方案**：`docs/designs/2026-06-22-deepeval-component-metrics.md`（纯 DeepEval，RAGAS 受阻时回退）

---

## 0. 决策快照

| # | 维度 | 决策 |
|---|---|---|
| 1 | 框架分工 | Retriever 检索质量 → **RAGAS**；Tutor 教学质量 → **DeepEval G-Eval**；Critic/Curator/Conductor 本轮不动 |
| 2 | judge 模型 | 复用既有 `openai_*` 配置；§5.1.1「judge 与被评 Agent 不同族」作为**构造期校验**强制（Tutor=Claude/anthropic → judge=OpenAI 恰好不同族） |
| 3 | 替换对象 | 仅 `Retriever.evaluate()`（Phase 1 已替换）与 `Tutor.evaluate()`（Phase 3）的指标计算段；evaluate 的输入/输出 dict 契约不变 |
| 4 | 框架边界 | RAGAS/DeepEval 只在 L2 旁路（`app/eval/` 与 `Agent.evaluate`）出现，**严禁进入在线 `handle()` 路径** |
| 5 | 降级策略 | judge 不可用 / 缺 golden_answer / 库未装 / 评估异常 → 返回带 `degraded: true` 的结果，保留启发式分数，不崩溃 |
| 6 | 依赖管理 | RAGAS 已在 `pyproject.toml`（零新增）；DeepEval 作为可选 eval extra（Phase 3 引入），在线运行不强制安装 |
| 7 | 数据落库 | 复用 `EvalTable` 既有 `ragas_*` 三列 + 补 `ragas_context_recall` 列；Tutor 指标走 `eval_data` JSON 列，不新建列 |

### 0.1 否决项及理由

| 被否方案 | 否决理由 |
|---|---|
| 纯 DeepEval（原 spec） | 浪费 RAGAS 既有铺垫（依赖+字段+注释意图），且无合成测试集与分阶段诊断 |
| 纯 RAGAS（含 Tutor） | RAGAS Rubrics 需预定义 score1-5 分档，不如 G-Eval 自然语言 criteria 灵活，教学抽象维度（引导性/清晰度）表达力弱 |
| judge 写死 GPT-4o | §5.1.1 要求不同族校验，写死无法校验且绑死 provider；改为 `infer_family` 运行时推断 |
| 保留字符 Jaccard 作降级分数 | 字符重叠与语义无关，伪装成真分数会误导选型；降级显式标 `degraded` 而非掩盖 |
| RAGAS/DeepEval 进在线 handle() | §5.1/§3.6 明确 L2 旁路与 L1 在线分层，在线评估归 Critic，越权 |

---

## 1. 资产清单与三色血缘

字段含义见 `.claude/rules/solution-presentation.md`。本次方案涉及的产物：

| 名字 | 归属子系统 | 功能（干嘛） | 触发 / 入口 | 位置（file:line） | 血缘 |
|---|---|---|---|---|---|
| `Retriever.evaluate()` | Agent 部件 | 跑检索 + 算 recall@k/redundancy（启发式）+ RAGAS 三件套 | ComponentBench 调用 | `app/agents/retriever.py:105` | 🟡 已改（Phase 1） |
| `app/eval/judge.py` | L2 eval | 构造 judge（llm+embeddings）+ §5.1.1 不同族校验，同族/无 key 返回 None | Retriever/Tutor.evaluate 内调 | `app/eval/judge.py:36`（`build_judge`；`infer_family` 在 `:17`） | 🔴 已建（Phase 1） |
| `EvalTable.ragas_context_recall` | Infrastructure | 补齐枚举有定义但表缺的 context_recall 列 | ORM | `app/models/tables.py` | 🔴 已建（Phase 1） |
| `tests/eval/test_judge.py` | 测试 | infer_family + build_judge 不同族/降级单测（7 例） | pytest | `tests/eval/test_judge.py` | 🔴 已建（Phase 1） |
| `ComponentBench` | L2 eval | 跑黄金用例、按 expected 阈值判 passed | `EvalKernel` | `app/eval/component_bench.py:23` | 🟢 保持（Phase 1）/ 🟡 改（Phase 3 加分阶段诊断） |
| `Tutor.evaluate()` | Agent 部件 | 当前字符 Counter 占位算解释完整性 | ComponentBench 调用 | `app/agents/tutor.py:99` | 🟡 待改（Phase 3） |
| `golden_cases.py` | eval fixtures | Retriever/Tutor 黄金用例 + expected 阈值 | ComponentBench 加载 | `app/eval/fixtures/golden_cases.py:19` | 🟡 待改（Phase 2 扩充 + 补 ground_truth/topic） |
| `ragas` 库 | 外部依赖 | RAG 专用评估（三件套 + 合成测试集） | judge.py / retriever import | `pyproject.toml`（已声明） | 🟢 已有 |
| `deepeval` 库 | 外部依赖 | G-Eval 自定义教学指标 | Tutor.evaluate import | pyproject eval extra（待加） | 🔴 待建（Phase 3） |
| `scripts/generate_ragas_testset.py` | scripts | 从知识库文档演化生成合成测试集 | 手动运行 | 待建 | 🔴 待建（Phase 2） |
| `scripts/refine_testset.py` | scripts | 人工筛选 + 双标注 + Cohen's κ 校验 | 手动运行 | 待建 | 🔴 待建（Phase 2） |

---

## 2. 现状与缺口（事实依据）

| 事实 | 位置 |
|---|---|
| 母 spec §5.2 把 RAG 三件套写进 Retriever 指标、把「解释完整性 rubric-LLM-judge」写进 Tutor 指标 | 母 spec `:562,561` |
| §5.1.1 规定 LLM-judge 必须与被评 Agent 不同族、盲评、judge 自身 κ≥0.6 才采信 | 母 spec `:532-536` |
| Phase 1 已落地：Retriever 三件套走 RAGAS，judge 适配层完成 | `app/agents/retriever.py:169`、`app/eval/judge.py:36` |
| `Tutor.evaluate()` 解释完整性仍是字符 Counter 交并比占位 | `app/agents/tutor.py:99` |
| `golden_cases.py` 黄金用例数量不足（远少于 §5.1.1 可信评估所需） | `app/eval/fixtures/golden_cases.py:19` |
| context_recall 列已建但 evaluate 未算（缺 ground_truth） | `app/models/tables.py` |

**缺口结论**：Phase 1 已让 Retriever 检索质量从字符占位升级为 RAGAS 语义评估。剩余缺口是 ① 黄金集数量（Phase 2 合成测试集）；② Tutor 教学指标仍是占位（Phase 3 DeepEval G-Eval）；③ context_recall 逻辑（依赖 Phase 2 补 ground_truth）。

---

## 3. 整体架构

```
L1 在线（handle 路径）          ← RAGAS/DeepEval 严禁进入
   Critic 发 RAGQualityAssessed
        │ 事件沉淀
        ▼
   EventStore
        │ replay
        ▼
L2 旁路 EvalKernel
   └─ ComponentBench（🟢 不改调度）
        └─ agent.evaluate(tc.input)
              ├─ Retriever.evaluate  🟡 ── build_judge() ──▶ judge.py 🔴 ──▶ RAGAS 🟢
              └─ Tutor.evaluate      🟡（Phase 3）── build_judge() ──▶ judge.py 🔴 ──▶ DeepEval 🔴
```

**judge 适配层统一**：`app/eval/judge.py` 的 `build_judge()` 是两条评估路径的共享入口，负责 §5.1.1 不同族校验与 LLM/embeddings 构造。RAGAS 需要 `llm` + `embeddings`；DeepEval 需要 `DeepEvalBaseLLM` 包装。两者通过返回的 `judge_handle` dict 分别取用。

### 3.1 三层指标体系

| 层 | 指标 | 框架 | 状态 |
|---|---|---|---|
| 检索阶段 | context_precision（检索排序质量）| RAGAS | ✅ Phase 1 已落地 |
| 检索阶段 | context_recall（漏检率，需 ground_truth）| RAGAS | ⏳ Phase 2 补数据后补实现 |
| 生成阶段 | faithfulness（幻觉检测）| RAGAS | ✅ Phase 1 已落地 |
| 生成阶段 | answer_relevancy（答案切题度）| RAGAS | ✅ Phase 1 已落地 |
| 教学质量 | explanation_completeness（核心概念覆盖）| DeepEval G-Eval | ⏳ Phase 3 |
| 教学质量 | guidance_quality（引导性而非直给答案）| DeepEval G-Eval | ⏳ Phase 3 |
| 教学质量 | clarity（清晰度与结构化）| DeepEval G-Eval | ⏳ Phase 3 |
| 启发式 | recall_at_k、redundancy | 无 LLM（成本为零）| ✅ 始终保留 |

### 3.2 faithfulness/answer_relevancy 的评估语义（重要澄清）

RAGAS 的 `faithfulness`/`answer_relevancy` 原始定义针对**被评模型实际生成的回答**。但 Retriever 是检索部件，本身不生成回答，且 evaluate 须保持部件独立（不引入 Tutor 依赖，§0 决策 3）。当前实现把 `golden_answer`（人工标注的理想答案）填入 `response` 字段，实际语义如下：

| 指标 | 字面名 | 当前实现的真实语义 |
|---|---|---|
| faithfulness | 幻觉检测 | **检索内容能否支撑理想答案**的各陈述（检索完整性代理）|
| answer_relevancy | 答案切题度 | 理想答案与 query 的相关性（信息量低，几乎恒高）|
| context_precision | 检索排序质量 | 用 reference=golden_answer 判断检索块排序（**语义正确**）|

**待 Phase 3 决策**：若要评字面意义的「Tutor 生成是否忠实于检索」，须在 SystemBench 串 Retriever→Tutor 真实生成后再评。两种定位各有用途；当前选「检索完整性代理」定位，Phase 3 视 SystemBench 需求决定是否补真实生成路径。

### 3.3 RAGAS 0.4.3 API 适配（已知约束，避免重蹈 Phase 1 bug）

Phase 1 review 发现并已修复三处 API 误用，后续实施须遵守：

| 约束 | 正确做法 | 错误做法（已修） |
|---|---|---|
| metric 对象 | `from ragas.metrics import faithfulness as m_faithfulness`（小写，已实例化 `Metric`）| `from ragas.metrics.collections import faithfulness`（是子模块，非实例）|
| Dataset 列名 | `user_input` / `response` / `retrieved_contexts` / `reference` | `question` / `answer` / `contexts`（0.1.x 旧名）|
| 结果提取 | `result._scores_dict["faithfulness"][0]`（`List[float]`）| `result["faithfulness"].iloc[0]`（EvaluationResult 无 `.columns`）|
| import 别名 | metric 用 `m_` 前缀，避免遮蔽同名启发式浮点变量 | 裸名 import 覆盖局部变量→降级分支崩 |

**已知权衡**：`ragas.metrics` 小写实例在 0.4.3 有 `DeprecationWarning`（v1.0 移除），但 collections 新 `BaseMetric` 需要 `InstructorBaseRagasLLM` 而非 LangChain LLM，当前不兼容。升级到 collections API 触发条件：升 ragas ≥ 1.0 或 deprecation 移除时再迁移。

---

## 4. 分期实施计划

### Phase 1：RAGAS Retriever + judge 适配层 ✅ 已完成

**完成提交**：`fc210d4`（合入 main）

**实际产出**：
- `app/eval/judge.py` — `infer_family()` + `build_judge()` + §5.1.1 不同族校验。构造返回 dict `{"llm": ChatOpenAI, "embeddings": EmbeddingService, "family": str}`
- `app/agents/retriever.py:169-250` — RAGAS 三件套替换字符 Jaccard；recall_at_k/redundancy 保留启发式；4 层降级（judge=None → 无 golden_answer → ImportError → Exception）
- `app/models/tables.py` — 补 `ragas_context_recall = Column(Float, nullable=True)`
- `alembic/versions/20260623_add_ragas_context_recall.py` — 对应迁移
- 兼容性修复：`langchain-google-vertexai==3.2.4` + venv shim（解决 ragas 0.4.3 的 langchain_community.chat_models.vertexai 路径变更）
- `tests/eval/test_judge.py` — 7 例单测；`tests/unit/agents/test_retriever.py` — 25 例（含降级分支覆盖）

**验收结果**：初版 32 tests passed，但**全部走降级分支**（CI 无 API key → judge=None），RAGAS 真实调用从未执行，掩盖了 §3.3 的三处 API bug。Review 后已修 bug + 补 happy-path 提取测试（mock ragas_eval 但执行真实 import/Dataset/提取链路）+ integration 测试（真实 key，默认 deselect）。现 33 tests passed。

---

### Phase 2：RAGAS 合成测试集生成（待实施）

**目的**：黄金集当前数量不足，无法支撑 §5.1.1 可信评估。RAGAS 演化式生成可节省 90% 人工出题时间。

**子模块职责**：

**2-A `scripts/generate_ragas_testset.py`**
- 职责：从项目知识库文档自动演化生成候选测试用例
- 输入：**从 pgvector `VectorChunkTable` 取已索引 chunk**（`content` 列），包成 langchain `Document(page_content=chunk.content, metadata={...})`。**不依赖文件目录**——项目知识库存在 pgvector，不在文件系统（问题修正：原 `./knowledge_base/` 目录不存在）。
- 输出：`ragas_generated_candidates.csv`（100 条候选，含 `user_input`/`reference`/`reference_contexts` 列——0.4.3 Testset 列名，详见验证状态表）
- 问题类型分布：用 `query_distribution` 参数（0.4.3 用 `default_query_distribution` 或自定义 synthesizer 权重），按学习场景配单跳/多跳/抽象问题比例
- 关键函数（基于 ragas 0.4.3 **实测** API）：
  - `load_chunks_as_documents() -> list[Document]`：查 `VectorChunkTable.content`，包成 langchain Document
  - `build_generator() -> TestsetGenerator`：`TestsetGenerator(llm=LangchainLLMWrapper(judge_llm), embedding_model=LangchainEmbeddingsWrapper(embeddings))`（`knowledge_graph` 参数可选，缺省时由 `generate_with_langchain_docs` 内部从 documents 构建——是否显式传待 spike 确认，见验证表）
  - `generate(generator, documents) -> Testset`：`generator.generate_with_langchain_docs(documents, testset_size=100, query_distribution=...)`
  - `export_csv(testset, path)`：`testset.to_pandas().to_csv(path)`

> **⚠️ 0.4.3 API 适配（已 spike 实测，见验证状态表）**：原 spec 写的 `configure_generator(gen_llm, critic_llm, embeddings)` / `generate(documents, test_size, distributions)` 是 ragas **0.1.x** 签名，0.4.3 已重构——无 `critic_llm` 概念（改 `KnowledgeGraph` + transforms），构造器签名为 `TestsetGenerator(llm, embedding_model, knowledge_graph=...)`，生成方法为 `generate_with_langchain_docs(documents, testset_size, query_distribution=...)`。照旧签名写必报 `AttributeError`/`TypeError`。

**Phase 2 验证状态表**（应用 third-party-integration skill）：

| 代码片段 | 验证状态 | 依据 |
|---|---|---|
| `from ragas.testset import TestsetGenerator` | ✅ 实测 0.4.3 | import 成功 |
| `TestsetGenerator(llm=, embedding_model=, knowledge_graph=)` | ⚠️ 仅 inspect 签名 | `__init__` 签名确认存在该参数，但**未端到端跑通**——降级标 ⏳，见下 |
| `generate_with_langchain_docs(documents, testset_size, query_distribution=)` | ⏳ 待 spike | 仅 inspect 到方法签名；**未实测端到端生成**。R6：inspect≠实测，实施前必须最小 spike 跑通一次 |
| `Document(page_content=...)` | ✅ 实测 | `langchain_core.documents.Document` |
| `VectorChunkTable.content` 作文档源 | ✅ 实测 | `tables.py:102` content 列 |
| `query_distribution` 具体配比 API | ⏳ 待 spike | 实施前确认 0.4.3 default_query_distribution 结构 |
| 是否需显式传 `knowledge_graph` | ⏳ 待 spike | 与 generate_with_langchain_docs 端到端 spike 一并确认 |

> **⚠️ R6 红线**：上表 ⏳ 项均为**未来 Phase 的外部库调用**，不能因「是未来」就放过。`generate_with_langchain_docs` 是 0.4.3 相对 0.1.x 重构的核心方法（无 `critic_llm`、改 KnowledgeGraph），仅凭 inspect 签名进入实施 = 重蹈 Phase 1「3 个 API bug 骗过 32 测试」覆辙。**Phase 2 启动第一步：跑通最小 spike（真实 key + 几个 chunk → 生成 1-2 条用例），再写实施代码。**

**2-B `scripts/refine_testset.py`**
- 职责：人工筛选候选集 + 双人标注 + Cohen's κ 校验 + 输出最终 golden_cases 格式
- 输入：`ragas_generated_candidates.csv`（100 条）
- 输出：筛选后 50 条 + κ 报告 + `golden_cases_v2.py` 追加块
- 关键步骤：
  1. 人工删除质量差行（问题模糊、上下文缺失、答案不合逻辑）
  2. 双人各自独立标注 `ground_truth` 列
  3. 计算 Cohen's κ；κ < 0.6 时打印警告、输出冲突行列表供仲裁
  4. 冲突仲裁后合并，生成 `golden_cases_v2.py` TestCase 列表（含 ground_truth 字段，供 context_recall 使用）
- 关键函数：`compute_kappa(a_labels, b_labels) -> float` → `print_conflicts(df)` → `export_golden_cases(df_refined, output_path)`

**配套改动**：
- `app/agents/retriever.py` 补 context_recall 计算（依赖 golden_answer 中的 ground_truth，Phase 2 数据就绪后补）
- `app/eval/fixtures/golden_cases.py` 追加 v2 用例（retriever 用例从当前少量扩充到 50+）

**验收标准**：
- `generate_ragas_testset.py` 运行完成，输出 100 行 CSV
- `refine_testset.py` 计算出 κ 值并打印；κ ≥ 0.6 时生成 `golden_cases_v2.py`
- pytest retriever 用例数量 ≥ 20（原有用例 + v2 新增）

---

### Phase 3：ComponentBench 分阶段诊断 + DeepEval Tutor（待实施）

**目的**：① ComponentBench 报告从「只看分数」升级为「可执行优化建议」；② Tutor 教学指标替换字符 Counter 占位。

**子模块职责**：

**3-A `app/eval/component_bench.py` 分阶段诊断（改动）**
- 职责：在 `format_report()` 中追加 Retriever 分阶段诊断，将检索召回/排序/幻觉/跑题分开分析并给出优化建议
- 改动范围：`format_report()` 末尾追加诊断段；不改判定逻辑（`_check_expected` 保持不变）
- 诊断逻辑：对非 degraded 的 retriever 结果取平均分；依次检查 context_recall < 0.8（建议加 top_k/优化分块）/ context_precision < 0.8（建议加 reranking）/ faithfulness < 0.9（建议强化 Tutor prompt）/ **answer_relevancy < 0.8（建议检查 user_input 理解）**
  - ⚠️ **answer_relevancy 判定待 Phase 3 实施时重新评估**：§3.2 已指出当前实现中该指标为「理想答案与 query 相关性」（几乎恒高、信息量低）。Phase 3 落地 `_rag_diagnosis` 时，需根据实际数据决定是否保留此维度判定、降权、或移除。若保留，建议阈值提高到 0.95（恒高指标用低阈值无意义）。此决策点在 Phase 3 启动时明确，当前先保留原设计占位。
  - ⚠️ **§3.2 语义修正的影响传播（不止诊断阈值一处）**：answer_relevancy「恒高、信息量低」这一修正，下游有**两个独立使用点**，Phase 3 须一并处理：
    - **诊断阈值**（本 3-A）：`_rag_diagnosis` 内的 `< 0.8` 判定，见上。
    - **passed 判定阈值**（易漏）：`golden_cases.py:19-20` retriever 用例的 `expected={"answer_relevancy": 0.6, ...}`，是 `ComponentBench.run()` 的 **通过/失败判定**依据（`component_bench.py:31-39` 逐项比 `actual < threshold`），与诊断阈值是两处独立代码路径。恒高指标配 0.6 阈值 → 永远 pass、丧失判别力。Phase 3 调整 answer_relevancy 时，**必须同步改/移除此 expected 阈值**，否则诊断改了、判定仍失真。
- 输出格式：分析结论每条附「建议操作」（可执行，非泛泛而谈）
- 关键函数：`_rag_diagnosis(retriever_results) -> list[str]`（纯文本诊断行列表，由 format_report 拼入报告）

**3-B `app/agents/tutor.py` G-Eval 替换（改动）**
- 职责：替换 `:99` 起的 `evaluate()` 方法的指标计算段，用 DeepEval G-Eval 算教学三维度
- 改动范围：指标计算段（生成教学内容的代码保持不变，只换算分逻辑）
- 指标定义（三个 G-Eval，每个含 criteria + evaluation_steps）：
  - `guidance_quality`：评估是否通过提问/提示引导学生自己思考（不直给答案）
  - `clarity`：评估解释是否清晰、分步骤、有例子、适合学生水平
  - `explanation_completeness`：评估是否覆盖主题核心概念
- 降级路径：judge=None 或 content 为空 → 返回 degraded；ImportError → 返回 degraded
- reasoning 旁路：三个 metric 的 reason 字段写入返回 dict 的 `_reasoning` key，供 SelectionReporter 展示
- 关键函数：`_build_geval_metrics(judge_handle) -> tuple[GEval, GEval, GEval]`（构造三个 metric 对象，criteria 与 evaluation_steps 在此定义，集中管理）

**3-C 依赖与数据表**：
- `pyproject.toml` eval extra 新增 `deepeval>=1.4.0`（Phase 3 开始前确认当前稳定版本）
- Tutor 指标走 `EvalTable.eval_data`（JSON 列，`tables.py:55`），不新建列
- `golden_cases.py` Tutor 用例补 `topic` 字段（G-Eval 的 input 需要 topic）

**验收标准**：
- `pytest tests/unit/agents/test_tutor.py -k evaluate` — guidance_quality/clarity/completeness 非 0 分，`_reasoning` 非空
- `pytest tests/eval/test_component_bench.py` — Retriever 报告含分阶段诊断文本
- `grep -r "import deepeval" app/agents/` — 只在 `tutor.py` 的 `evaluate` 方法体内出现
- 不装 eval extra 时 `from app.agents.tutor import TutorAgent` 无报错

---

### Phase 4：API 集成 + 落库验证（待实施）

**目的**：`api/eval.py` 的 `rerun_eval` 当前是 stub（返回全 0），让它真正调用 ComponentBench 并把结果落库、可查回。

**⚠️ 前提事实修正（经代码核查，2026-06-26 review）**：原 §4-A 把 `EvalStore.save()` 当成已有的「落 `EvalTable`」入口，框定 Phase 4 工作为「加一个 key 映射字典」。实际不成立：

| 声称（修正前） | 代码事实 | 位置 |
|---|---|---|
| `EvalStore.save()` 把结果落 `EvalTable` | `EvalStore` 是**纯内存实现**，`save()` 写进 `self._evals` dict，不碰 ORM/DB | `app/infrastructure/storage/eval_store.py:11-15` |
| GET 端点从 `EvalTable` 查 | GET 从 `EvalStore` 内存读 | `app/api/eval.py:11-27` |
| `EvalTable` 已有读写路径 | `EvalTable` **全项目仅类定义，零读写代码**（`grep EvalTable` 只命中 tables.py） | `app/models/tables.py:46` |

因此 Phase 4 真实工作量不是「加映射字典」，而是分两件独立子模块：**4-A 评估执行接线** + **4-B 落库改造**。是否把内存 stub 升级为真正落 DB，是一个需明确的范围决策（见 4-B）。

**子模块职责**：

**4-A `app/api/eval.py:30` rerun_eval 评估执行（改动）**
- 职责：接收 session_id → 构造 `EvalKernel` → 解析黄金用例 → 跑 ComponentBench → **聚合多条结果为单个 EvalResponse** → 经映射写入 `EvalStore.save()`，返回非全 0 的 EvalResponse
- **依赖构造（易漏，经核查 `api/eval.py` 当前无 EvalKernel 实例）**：4-A 需自建评估栈——
  - 构造 `agent_map = {"retriever": RetrieverAgent(...)}`（RetrieverAgent 需注入 RAGCoordinator，与在线一致）
  - `kernel = EvalKernel(agent_map)`；调 `kernel.run_component_bench("retriever", test_cases)`（内部委托 `ComponentBench.run`，返回 `list[EvalResult]`，签名已确认 `kernel.py:63` / `component_bench.py:10-11`）
- 依赖现状：`EvalKernel.run_component_bench`（✅ 已存在 `kernel.py:63`）、`golden_cases.GOLDEN_CASES`（✅ 已存在）、`EventStore`（✅ 已存在 `app/infrastructure/storage/event_store.py`，4-A 是否需要它取决于"用例来源"决策，见下）
- **聚合逻辑（决策：选 1 求平均）**：`run_component_bench` 返回 `list[EvalResult]`（每条黄金用例一个），但 `rerun_eval` 的 `response_model` 是**单个** `EvalResponse`（`api/eval.py:30`）。聚合规则：
  - 对**非 degraded** 的 EvalResult，按 ragas 字段（faithfulness/answer_relevancy/context_precision/context_recall）分别取**算术平均**
  - degraded 的结果**排除出平均**（与 §5「degraded 不伪装真分数」一致），但计入 degraded 占比统计
  - 全部 degraded 时：返回各 ragas 字段为 None 的 EvalResponse + `degraded` 标记（不返回 0，0 会被误读为真实低分）
  - 关键函数：`_aggregate_results(results: list[EvalResult]) -> dict`（取非 degraded 子集求均值，返回映射前的指标 dict）
- 用例来源决策（待定，不可臆测）：

  | 选项 | 做法 | 代价 |
  |---|---|---|
  | A: 固定黄金集 | 直接用 `GOLDEN_CASES["retriever"]`，忽略 session_id 内容 | 简单，但 rerun 与具体 session 无关，session_id 仅作存储键 |
  | B: 从 EventStore 重建用例 | replay session 事件，提取真实 query/检索结果做 test_case | 贴合"重跑这次会话的评估"语义，但需定义事件→TestCase 的映射，工作量大 |

  → 默认选 A（与当前 stub 的 session_id 用法一致、最小改动）；B 留待 SystemBench（§3.2 已提）一并做。实施前与用户确认。
- 关键函数：`_resolve_test_cases(session_id) -> list[TestCase]`（选项 A 下直接返回 `GOLDEN_CASES["retriever"]`）→ `_aggregate_results(results) -> dict`（求平均）→ 映射字典转 key → `EvalStore.save()`

**4-B `EvalStore` 落库改造（范围决策，可能拆独立 spec）**
- 现状：`EvalStore` 内存 dict，进程重启即丢；`EvalTable` ORM 定义好但无人读写
- 待决策：本期是否把 `EvalStore.save()/list_by_session()` 改为真正读写 `EvalTable`（经 `app/core/database` 的 session）
  - 若**做**：4-B 实现 ORM 读写 + 复用已有 `evals` 表迁移（`d48d7137f57f` 已建表 + `20260623` 补列，无需新迁移）；验收含「GET 从 DB 查到落库结果」
  - 若**不做**（仅内存）：Phase 4 验收的「落库」改述为「内存存取」，DB 持久化另拆 spec；**§4 验收标准 §2「从 EvalTable 查」必须同步改写**，否则验收与实现矛盾
- **此决策点必须在 Phase 4 启动时明确，不得默认**——它直接决定验收标准的措辞

**数据流映射表（字段名跨层转换）**：

Retriever.evaluate() 返回的 dict key 与 EvalTable 列名、EvalResponse 字段不完全一致，需显式映射。仅列出**有明确落点**的 RAGAS 核心指标：

| evaluate() 返回 key | EvalTable 列名 | EvalResponse 字段 | 映射逻辑位置 |
|---|---|---|---|
| `faithfulness` | `ragas_faithfulness` | `ragas_faithfulness` | `rerun_eval` 内（落库与否见 4-B） |
| `answer_relevancy` | `ragas_relevancy` | `ragas_relevancy` | 同上 |
| `context_precision` | `ragas_context_precision` | `ragas_context_precision` | 同上（含启发式） |
| `context_recall` | `ragas_context_recall` | `ragas_context_recall` | 同上（Phase 2 后启用） |

**不在映射表内的辅助指标**：`recall_at_k`、`redundancy`、`latency_ms` 三个启发式指标由 Retriever.evaluate() 返回，但 **EvalTable 无对应列、EvalResponse 无对应字段**（经代码核查 `tables.py:46-57` / `schemas.py:39-47`）。去向：
- 若 4-B 选「做 DB」：**可选**存入 `eval_data` JSON 列（需在 4-B 实施时决定是否保留辅助指标）
- 若 4-B 选「不做 DB」：这些指标仅用于实时报告展示，不落库

**实施要点**：
- 执行顺序：`_resolve_test_cases` → `kernel.run_component_bench("retriever", cases)` 得 `list[EvalResult]` → `_aggregate_results` 求非 degraded 子集均值 → 映射字典 `{"answer_relevancy": "ragas_relevancy", ...}` 转 key → `EvalStore.save()`。表列名已确认（`tables.py:52-55`）。
- `EvalStore.save()` **当前只写内存**（见 4-B 前提事实），落 DB 是待决策的 4-B 范围。若 4-B 选「不做 DB」，映射后数据仅留内存；若「做 DB」，则 `save()` 内需补 `async with get_db() as db: db.add(EvalTable(**mapped_data))`。

**验收标准（随 4-B 决策分支）**：
- **共同**：`POST /eval/{session_id}/rerun` 返回 ragas_faithfulness/ragas_relevancy 为**非 degraded 用例的平均分**（非全 0）；全 degraded 时对应字段为 None（非 0）
- **聚合**：多条黄金用例（Phase 2 后 50+）的结果按 §4-A 聚合规则求均值，response 为单条 EvalResponse
- **若 4-B 选「做 DB」**：`GET /eval/{session_id}` 能从 `EvalTable` 查到落库记录（ORM 查询，非内存）
- **若 4-B 选「不做 DB」**：`GET` 从 `EvalStore` 内存返回（与当前一致），进程重启后丢失——此分支需另拆 spec 补 DB 持久化

---

## 5. 降级策略

判据：字符级占位与语义无关，伪装成真分数会误导选型。所以降级时**保留无 LLM 成本的启发式分数（recall_at_k/redundancy/context_precision 启发式）**，但 RAGAS 三件套字段归 0 并显式标 `degraded: true` + `degraded_reason`，让调用方与报告能识别。

| 降级场景 | 检测点 | 行为 |
|---|---|---|
| judge 不可用（同族 / 无 key / 构造失败）| `build_judge()` 返回 None | 返回 degraded，保留启发式 context_precision |
| 缺 golden_answer | evaluate 内判空 | 返回 degraded（faithfulness/answer_relevancy 无意义）|
| RAGAS / datasets 未安装 | ImportError | 返回 degraded |
| RAGAS 评估抛异常 | except Exception | 返回 degraded + 异常信息 |

**ComponentBench 对 degraded 的处理**：标 `passed=False`（保守），不静默跳过——通过率下降能暴露 judge 配置问题，促使修复。降级占比 > 50% 时报告顶部应警告「评估不可信，检查 judge 配置」（Phase 3 随分阶段诊断一并加）。

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| RAGAS 版本不兼容（langchain 路径变更）| — | — | Phase 1 已遇到并解决：装 `langchain-google-vertexai` + venv shim；后续锁定 ragas 版本，升级前跑回归 |
| 合成测试集质量差 | 中 | 高 | Phase 2 强制人工筛选 + 双标注 + κ≥0.6 校验，不达标重生成 |
| G-Eval 分数不稳定（主观）| 高 | 中 | §5.1.1 要求 judge 自身 κ≥0.6；Phase 3 验收抽查 20 个 Tutor 输出，不达标则细化 criteria |
| judge 成本超预算 | 低 | 中 | 当前用例少；测试集生成用 gpt-3.5（生成）+ gpt-4o（审查）分级 |
| 降级用例过多导致报告失真 | 中 | 中 | ComponentBench 统计 degraded 占比，>50% 报告顶部警告 |
| 两框架依赖冲突 | 低 | 中 | RAGAS/DeepEval 都基于 langchain，锁定 langchain 系版本 |

---

## 7. 与其他文档的关系

| 文档 | 角色 | 处理 |
|---|---|---|
| 本文档 | 混合方案**统一设计**（执行依据）| 随 Phase 推进更新「状态」标注 |
| `2026-06-22-deepeval-vs-ragas-adoption-report.md` | 决策**论证**（为什么混合）| 保持，作为本设计的依据来源 |
| `2026-06-22-deepeval-component-metrics.md` | 纯 DeepEval **备选**（回退方案）| 保留，RAGAS 受阻时回退 Retriever 部分 |
| 母 spec §5.1.1 / §5.2 | 指标与约束**源头** | 不改 |

---

**文档状态**：Phase 1 已落地（main `fc210d4`）；Phase 2/3/4 待实施，按 §4 顺序推进。
