# DeepEval vs RAGAS 对比与本项目借鉴报告

> **用途**：对比 DeepEval 与 RAGAS 两个 LLM/RAG 评估框架，结合 StudyAgent 已落地的实践，给出针对性的采纳与改造建议。
> **日期**：2026-06-22
> **调研来源**：`Learned/DeepEval_测评方案.md`、`Learned/RAGAS_评估方案.md`
> **关联设计**：`docs/designs/2026-06-22-deepeval-component-metrics.md`（DeepEval 落地 spec）
> **关联母 spec**：`docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` §5 评估体系

---

## 0. 一句话结论

本项目**早已为 RAGAS 铺好路**（依赖已装、数据表字段已建、Retriever 注释明写"后续替换 ragas"），但至今是字符级占位未落地；**DeepEval 则尚未引入**。建议走**混合方案**：Retriever 检索质量用 RAGAS（复用既有铺垫 + 分阶段诊断 + 合成测试集），Tutor 教学效果用 DeepEval G-Eval（自然语言定义"引导性/清晰度"更灵活）。

---

## 1. 本项目已落地的评估相关实践（事实核查）

下表全部经代码核实，未读实现的标 `⏳`。

| 产物 | 现状 | 位置 |
|---|---|---|
| `ragas>=0.2.0` 依赖 | ✅ 已声明，但代码未真正调用 | `pyproject.toml:33` |
| `EvalTable` 的 ragas 字段 | ✅ 建了 `ragas_faithfulness`/`ragas_relevancy`/`ragas_context_precision` 三列；**缺 `context_recall` 列** | `app/models/tables.py:52-54` |
| `EvalMetric` 枚举 | ✅ 定义了 4 个指标（含 CONTEXT_RECALL），但表里没对应列 | `app/harness/enums.py:86-91` |
| `EmbeddingService` | ✅ 已实现，复用 OpenAI 配置，RAGAS 需要的 embeddings **现成可用** | `app/infrastructure/rag/embedding.py:17` |
| `RAGCoordinator.search` | ✅ 多源检索，返回带 score、按 score 降序去重 | `app/infrastructure/rag/coordinator.py:100-128` |
| 多格式 extractors | ✅ pdf/docx/text + OCR，合成测试集的文档源就绪 | `app/infrastructure/rag/extractors/` |
| `KnowledgeStore` | ✅ 知识库 CRUD（create/get/list/delete） | `app/infrastructure/storage/knowledge_store.py:1` |
| `Retriever.evaluate()` | ⚠️ 三件套是**字符级 Jaccard/token 重叠占位**，注释自承"后续可替换 ragas" | `app/agents/retriever.py:105,114,151` |
| `Tutor.evaluate()` | ⚠️ 解释完整性是**字符 Counter 交并比占位** | `app/agents/tutor.py:99,126` |
| `api/eval.py` `rerun_eval` | ⚠️ **stub**：直接返回全 0 的 EvalResponse，未真跑评估 | `app/api/eval.py:28-35` |
| ComponentBench | ✅ Plan E 已实现调度，按 expected 阈值判 passed（不改） | `app/eval/component_bench.py:23` |
| 全 repo LLM-judge | ❌ 零实现 | grep 无结果 |

**核查结论**：评估的**调度框架**（ComponentBench/EvalKernel）和 **RAG 基础设施**（检索/embedding/文档抽取）都已就位；缺的只是**指标的真实实现**——当前全是字符级占位，且 `rerun_eval` API 是空壳。

---

## 2. DeepEval vs RAGAS 框架对比

### 2.1 定位差异

| | DeepEval | RAGAS |
|---|---|---|
| 定位 | 通用 LLM 应用评估（类 pytest） | RAG 专用评估 |
| 核心理念 | 把评估当软件测试，CI/CD 友好 | 分阶段诊断 + reference-free + 合成数据 |
| 最强卖点 | G-Eval（自然语言定义任意指标） | 合成测试集生成 + 检索/生成分阶段定位瓶颈 |
| 测试数据 | 需手动构建 TestCase | 可从文档自动演化生成 |

### 2.2 指标能力对比

| 能力 | DeepEval | RAGAS | 谁更适合本项目 |
|---|---|---|---|
| Faithfulness（幻觉检测） | ✅ | ✅ | 平手（都 reference-free） |
| Answer Relevancy | ✅ | ✅ | 平手 |
| Context Precision（排序质量） | ✅ ContextualRelevancy | ✅ | 平手 |
| Context Recall（漏检，需 ground_truth） | ✅ ContextualRecall | ✅ | 平手 |
| 检索/生成**分阶段诊断** | ❌ 偏端到端 | ✅ 核心卖点 | **RAGAS**（定位 RAG 瓶颈） |
| **合成测试集生成** | ❌ | ✅ 演化式，省 90% 出题 | **RAGAS**（填黄金集数量缺口） |
| **教学效果自定义指标** | ✅ G-Eval 灵活 | ⚠️ Rubrics 较死板 | **DeepEval**（引导性/清晰度） |
| pytest/CI 集成 | ✅ 核心卖点 | ⚠️ 可集成但文档弱 | DeepEval 略优 |

### 2.3 成本对比（两份调研笔记数据）

| 框架 | 单样本成本（GPT-4o） | 100 样本 |
|---|---|---|
| DeepEval | $0.003-0.004/指标 | ~$0.15/run |
| RAGAS | $0.002-0.005/行（4 指标合算） | ~$0.40-0.50 |

成本同量级，judge 模型选择（GPT-4o vs mini）影响远大于框架差异。

---

## 3. 与本项目的契合度分析

### 3.1 RAGAS 的契合点（高）

| 契合维度 | 本项目现状 | RAGAS 收益 |
|---|---|---|
| 依赖就绪 | `pyproject.toml:33` 已装 | 零新增依赖，直接 import |
| 数据表预埋 | `tables.py:52-54` 三个 ragas 字段 | 评估结果**有处可落**（补 context_recall 列即可） |
| embeddings 就绪 | `EmbeddingService` 复用 OpenAI 配置 | RAGAS 必需的 embeddings 现成（answer_relevancy 算余弦相似度要用） |
| 文档源就绪 | extractors + KnowledgeStore | 合成测试集的输入文档现成 |
| Retriever 注释 | `retriever.py:114` 写"后续替换 ragas" | 设计意图本就指向 RAGAS |

### 3.2 DeepEval 的契合点（中）

| 契合维度 | 本项目现状 | DeepEval 收益 |
|---|---|---|
| Tutor 教学指标 | 母 spec §5.2 要"解释完整性 rubric-LLM-judge"、"引导问题开放性" | G-Eval 用自然语言定义这些抽象维度，比 RAGAS Rubrics 灵活 |
| 依赖 | ❌ 未装 | 需新增 deepeval（可选 eval extra） |
| 数据表 | ❌ 无 deepeval 字段 | Tutor 指标可走 `eval_data` JSON 列（`tables.py:55`），不必新建列 |

### 3.3 §5.1.1 judge 独立性约束的影响

母 spec §5.1.1 强制 **judge 与被评 Agent 不同族**。项目 Tutor 用 Claude（Anthropic 族），而 `EmbeddingService`/LLM 配置目前只有 OpenAI（`config.py:9-11`）——**OpenAI 恰好满足"不同族"**，两个框架都可直接用现有 OpenAI 配置当 judge，无需额外接 provider。这点对 RAGAS 和 DeepEval 同等成立。

---

## 4. 混合方案建议（针对性采纳）

### 4.1 推荐分工

| 评估场景 | 推荐框架 | 理由（权衡表） |
|---|---|---|
| **Retriever 检索质量** | **RAGAS** | ① 项目已埋依赖+字段；② reference-free（Faithfulness/AnswerRelevancy 不需 ground_truth，当前 golden 用例直接可用）；③ 分阶段诊断定位瓶颈；④ 合成测试集填黄金集数量缺口 |
| **Tutor 教学效果** | **DeepEval G-Eval** | ① 自然语言定义「引导性」「清晰度」等抽象维度更灵活；② RAGAS Rubrics 需预定义 score1-5 描述，不如 G-Eval 的 criteria + evaluation_steps 可读性强 |
| **Critic/Curator/Conductor** | 暂不动（后续） | 本轮聚焦 Retriever+Tutor；母 spec §5.2 已设计掌握度一致率 κ 等指标，待验证前两者后再逐个落地 |

### 4.2 方案对照（vs 纯 DeepEval / 纯 RAGAS）

| | 混合方案 | 纯 DeepEval | 纯 RAGAS |
|---|---|---|---|
| **做法** | Retriever 用 RAGAS，Tutor 用 DeepEval G-Eval | Retriever+Tutor 都用 DeepEval | Retriever+Tutor 都用 RAGAS |
| **新增依赖** | deepeval 一个（eval extra） | deepeval 一个 | **零**（RAGAS 已装） |
| **数据表字段复用** | ✅ 复用 `ragas_*` 三列，Tutor 走 `eval_data` JSON | 需新建 `deepeval_*` 列或全走 JSON | ✅ 全部复用 ragas 列 |
| **合成测试集** | ✅ RAGAS 演化式生成 | ❌ 手动构建 | ✅ RAGAS 演化式 |
| **分阶段诊断** | ✅ RAGAS 检索/生成独立报告 | ❌ 需自己写分析逻辑 | ✅ RAGAS 原生支持 |
| **教学指标灵活性** | ✅ G-Eval 自然语言 criteria | ✅ G-Eval | ⚠️ Rubrics 较死板 |
| **golden 用例改动** | Retriever 零改（reference-free），Tutor 补 topic 字段 | 都需补字段（golden_answer / topic） | Retriever 需补 ground_truth（Context Recall 用） |
| **判据** | **选它**：扬两者所长，依赖/字段最省，测试集+分阶段开箱即用 | 依赖统一但浪费 RAGAS 既有铺垫 | 教学指标 Rubrics 不够灵活 |

---

## 5. 针对性改造建议（分优先级）

### 🔥 优先级 1：RAGAS 替换 Retriever 字符级占位（立即可做，1-2 天）

**改动范围**：`app/agents/retriever.py:151-165` 指标计算段。

**改前（当前占位）**：
```python
# :151-164 字符级 Jaccard 相似度
if golden_answer and combined:
    answer_tokens = set(golden_answer)
    retrieved_tokens = set(combined)
    intersection = answer_tokens & retrieved_tokens
    union = answer_tokens | retrieved_tokens
    faithfulness = len(intersection) / len(union) if union else 0.0
# 其余 answer_relevancy / context_precision 同样是 token 重叠启发式
```

**改后（RAGAS 真实指标）**：
```python
# :151 起替换段
try:
    from ragas import evaluate as ragas_eval
    from ragas.metrics import faithfulness, answer_relevancy, context_precision
    from datasets import Dataset
    
    # 构造 judge（复用 §5.1.1 不同族校验）
    from app.eval.judge import build_judge
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
    
    # 获取 embeddings（复用既有 EmbeddingService）
    from app.infrastructure.rag.embedding import EmbeddingService
    embedding_svc = EmbeddingService()
    
    # 包装为 RAGAS Dataset 格式
    eval_dataset = Dataset.from_dict({
        "question": [query],
        "answer": [golden_answer],  # 用黄金答案代表"理想生成"
        "contexts": [retrieved_contents],
        # ground_truth 可选：Context Recall 才需要，首版可不加
    })
    
    # 运行 RAGAS 评估（三指标）
    result = ragas_eval(
        dataset=eval_dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=judge_handle.model,  # 从 JudgeProvider 获取（OpenAI，满足不同族）
        embeddings=embedding_svc.client,  # 复用项目 EmbeddingService
        raise_exceptions=False,  # 单个失败不崩全局
    )
    
    return {
        "recall_at_k": recall_at_k,  # 保留启发式（不依赖 LLM，成本低）
        "faithfulness": result['faithfulness'],
        "answer_relevancy": result['answer_relevancy'],
        "context_precision": result['context_precision'],
        "latency_ms": latency_ms,
        "degraded": False,
    }

except ImportError:
    # RAGAS 虽在依赖但 import 失败（版本问题？），降级
    return {..., "degraded": True, "degraded_reason": "RAGAS import 失败"}
```

**配套改动**：
- `app/eval/judge.py`（新建）：judge 适配层 + §5.1.1 不同族校验（已在 DeepEval spec §4.1 设计）
- `app/models/tables.py:56`：补 `ragas_context_recall = Column(Float, nullable=True)`（枚举有定义但表缺列）
- `app/eval/fixtures/golden_cases.py:17`：golden_answer 已有，无需改

**价值**：
- 复用项目既有 `ragas_*` 字段，评估结果可落库展示（`api/eval.py` 已写好查询逻辑）
- reference-free：Faithfulness/AnswerRelevancy 无需 ground_truth，当前 6 个黄金用例**直接可用**
- 分阶段诊断定位瓶颈（见优先级 3）

---

### 🔥 优先级 2：RAGAS 合成测试集生成（填黄金集数量缺口，2-3 天）

**现状问题**：母 spec §5.1.1 要求黄金集「双人标注 + Cohen's κ ≥ 0.6」，但 `golden_cases.py` **只有 6 个用例**（Retriever 1 个，Tutor 1 个，其余 4 个占位），数量远不够支撑可信评估。

**RAGAS 杀手锏**：从文档/教材**自动演化生成**测试问题，节省 90% 人工出题时间（调研笔记 §5 承诺）。

**实施步骤**：

**Step 1: 从知识库生成候选测试集**（自动化）

```python
# 新建 scripts/generate_ragas_testset.py
from ragas.testset.generator import TestsetGenerator
from ragas.testset.evolutions import simple, reasoning, multi_context
from langchain_community.document_loaders import DirectoryLoader
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# 1. 从项目知识库加载文档
# 项目有 extractors（pdf/docx/text）+ KnowledgeStore，可直接读库或本地目录
loader = DirectoryLoader("./knowledge_base/", glob="**/*.{pdf,docx,txt}")
documents = loader.load()

# 2. 配置生成器
generator_llm = ChatOpenAI(model="gpt-3.5-turbo-16k")  # 生成用便宜模型
critic_llm = ChatOpenAI(model="gpt-4o")  # 质量审查用强模型
embeddings = OpenAIEmbeddings()

generator = TestsetGenerator.from_langchain(
    generator_llm, critic_llm, embeddings
)

# 3. 针对学习场景的问题类型分布
edu_distributions = {
    simple: 0.5,         # 50% 基础概念题（如"什么是 RAG"）
    reasoning: 0.3,      # 30% 推理应用题（如"RAG 如何解决幻觉问题"）
    multi_context: 0.2,  # 20% 综合题（需多个知识点）
}

# 4. 生成 100 个候选（后续人工筛选到 50 个）
testset = generator.generate_with_langchain_docs(
    documents, 
    test_size=100,
    distributions=edu_distributions
)

# 5. 导出供人工筛选
df = testset.to_pandas()
df.to_csv("ragas_generated_candidates.csv", index=False)
print(f"生成 {len(df)} 个候选测试用例，已导出到 ragas_generated_candidates.csv")
```

**Step 2: 人工筛选 + 标注**（半自动）

```python
# scripts/refine_testset.py
import pandas as pd

# 1. 人工筛选（删除质量差的，保留 50 个）
df = pd.read_csv("ragas_generated_candidates.csv")
# 手动审查 question/answer/contexts 列，删除不合理的行
df_refined = df.head(50)  # 示例：保留前 50 个

# 2. 双人标注 ground_truth（§5.1.1 要求）
# 分配给标注员 A 和 B，各自标注 ground_truth 列
# 标注完后计算 Cohen's κ
from tests.golden.cohens_kappa import cohens_kappa

annotator_a = df_refined['ground_truth_A'].tolist()
annotator_b = df_refined['ground_truth_B'].tolist()
kappa = cohens_kappa(annotator_a, annotator_b)

if kappa < 0.6:
    print(f"⚠️ κ = {kappa:.3f} < 0.6，标注不一致，需重新定义 rubric")
else:
    print(f"✅ κ = {kappa:.3f} ≥ 0.6，标注可采信")
    # 3. 冲突项仲裁后，生成最终 golden_cases
    # （仲裁逻辑：第三方裁定 A/B 哪个对，或取两者共识）

# 4. 转为 golden_cases.py 格式
# （手动或脚本生成 TestCase 列表）
```

**Step 3: 更新 golden_cases.py**

```python
# app/eval/fixtures/golden_cases.py 追加
GOLDEN_CASES["retriever"].extend([
    TestCase(
        name=f"retriever_ragas_{i}",
        component="retriever",
        input={
            "query": row['question'],
            "golden_chunks": extract_chunks_from_contexts(row['contexts']),
            "golden_answer": row['ground_truth'],  # 仲裁后的最终标注
            "top_k": 5,
        },
        expected={"recall_at_k": 0.8, "faithfulness": 0.85, ...},
        meta={"source": "ragas_generated_v1", "difficulty": infer_difficulty(row)},
    )
    for i, row in df_refined.iterrows()
])
```

**价值**：
- 黄金集从 6 个扩充到 50+ 个，满足 §5.1.1 数量要求
- 覆盖简单/推理/综合等多种难度，比手工出题更全面
- 节省 90% 人工出题时间（RAGAS 调研承诺），人工只需审核+标注

---

### 🔥 优先级 3：RAGAS 分阶段诊断集成（定位瓶颈，0.5-1 天）

**母 spec 缺口**：ComponentBench 的 `format_report` 只输出「通过率 + 指标分数」，**无法告诉你是检索漏检、还是 LLM 幻觉、还是排序差**——只给分数不给优化方向。

**RAGAS 核心卖点**：将 RAG 拆分为**检索阶段**（Context Precision/Recall）和**生成阶段**（Faithfulness/Relevancy），独立诊断，精确定位瓶颈（调研 §7.1）。

**改动点**：`app/eval/component_bench.py:82` 的 `format_report` 方法追加分阶段分析。

```python
# component_bench.py:82 追加
@staticmethod
def format_report(results: list[EvalResult]) -> str:
    lines = ["## ComponentBench 报告\n"]
    passed = sum(1 for r in results if r.passed)
    lines.append(f"**通过率**: {passed}/{len(results)}\n")
    
    # 🔴 新增：Retriever 分阶段诊断（RAGAS 特性）
    retriever_results = [r for r in results if r.component == "retriever"]
    if retriever_results:
        lines.append("### 🔍 Retriever 分阶段诊断（RAGAS）\n")
        
        # 计算平均分
        def avg(metric_key):
            vals = [r.metrics.get(metric_key, 0) for r in retriever_results if not r.metrics.get("degraded")]
            return sum(vals) / len(vals) if vals else 0.0
        
        avg_recall = avg("context_recall")
        avg_precision = avg("context_precision")
        avg_faithfulness = avg("faithfulness")
        avg_relevancy = avg("answer_relevancy")
        
        lines.append(f"- **检索阶段**：Context Recall {avg_recall:.3f}，Context Precision {avg_precision:.3f}")
        lines.append(f"- **生成阶段**：Faithfulness {avg_faithfulness:.3f}，Answer Relevancy {avg_relevancy:.3f}\n")
        
        # 诊断建议（照搬 RAGAS 调研 §7.1 策略）
        if avg_recall < 0.8:
            lines.append("⚠️ **检索召回不足** → 相关内容没被检索到，建议：")
            lines.append("  - 增加 `top_k` 参数")
            lines.append("  - 优化文档分块策略（chunk_size/overlap）")
            lines.append("  - 检查 embedding 模型质量\n")
        
        if avg_precision < 0.8:
            lines.append("⚠️ **检索噪声过多** → 检索到的内容相关性低，建议：")
            lines.append("  - 添加 reranking 步骤")
            lines.append("  - 改进检索 query（用 HyDE 等技术）\n")
        
        if avg_faithfulness < 0.9:
            lines.append("⚠️ **LLM 产生幻觉** → 答案未忠实于检索内容，建议：")
            lines.append("  - 改进 Tutor prompt，强调「仅基于 context 回答」")
            lines.append("  - 使用更强的模型（如 gpt-4o）\n")
        
        if avg_relevancy < 0.8:
            lines.append("⚠️ **答案跑题** → 生成内容未切中问题，建议：")
            lines.append("  - 检查 Tutor 是否正确理解 user_input")
            lines.append("  - 改进引导性问题的生成策略\n")
    
    # 原有逐用例展示逻辑
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        lines.append(f"\n### {r.test_name} ({status})")
        lines.append(f"- 组件: {r.component}")
        lines.append(f"- 指标: {r.metrics}")
        if r.errors:
            lines.append(f"- 错误: {r.errors}")
    
    return "\n".join(lines)
```

**价值**：
- 报告从"只看分数"变成**可执行的优化建议**（呼应母 spec §5.6 SelectionReporter 的选型推荐定位）
- 精确定位 RAG pipeline 瓶颈：检索召回？排序？幻觉？跑题？
- 复用 RAGAS 调研的分阶段诊断策略（调研 §7.1），不必自己探索

---

### 优先级 4：DeepEval G-Eval 替换 Tutor 字符级占位（1-2 天）

**为什么 Tutor 用 DeepEval 而非 RAGAS**：

| | DeepEval G-Eval | RAGAS Rubrics |
|---|---|---|
| 定义方式 | 自然语言 criteria + evaluation_steps | 预定义 score1-5 的分档描述 |
| 灵活性 | 可定义任意抽象维度（引导性/清晰度） | 需事先枚举所有分档，改动成本高 |
| 可读性 | criteria 一句话概括目标 | 5 段描述较冗长 |

**改动点**：`app/agents/tutor.py:126-135` 指标计算段。

```python
# tutor.py:126 起替换段
try:
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    from deepeval.metrics import GEval
    from app.eval.judge import build_judge
    
    judge_handle = build_judge(target_agent_family="anthropic")
    
    if judge_handle is None or not content:
        return {
            "explanation_completeness": 0.0,
            "guidance_quality": 0.0,
            "clarity": 0.0,
            "response_length": response_length,
            "degraded": True,
        }
    
    test_case_obj = LLMTestCase(
        input=f"请解释主题：{topic}",
        actual_output=content,
    )
    
    # G-Eval 引导性指标（对应母 spec §5.2 "引导问题开放性"）
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
    
    # G-Eval 清晰度指标（对应母 spec §5.2 "解释完整性 rubric-LLM-judge"）
    clarity_metric = GEval(
        name="Explanation Clarity",
        criteria="评估解释是否清晰、结构化、易于理解",
        evaluation_steps=[
            "检查是否使用了分步骤的解释",
            "确认是否包含了必要的例子",
            "评估术语使用是否适合学生水平",
        ],
        model=judge_handle.model,
    )
    clarity_metric.measure(test_case_obj)
    
    # 解释完整性用 G-Eval 替代原字符 Counter
    completeness_metric = GEval(
        name="Explanation Completeness",
        criteria="评估解释是否覆盖了主题的核心概念",
        evaluation_steps=[
            "确认主题的关键要素是否被提及",
            "检查解释的完整性",
        ],
        model=judge_handle.model,
    )
    completeness_metric.measure(test_case_obj)
    
    return {
        "explanation_completeness": completeness_metric.score,
        "guidance_quality": guidance_metric.score,
        "clarity": clarity_metric.score,
        "response_length": response_length,
        "degraded": False,
        # reasoning 传出到 EvalResult.meta，SelectionReporter 可展示
        "_reasoning": {
            "guidance": guidance_metric.reason,
            "clarity": clarity_metric.reason,
            "completeness": completeness_metric.reason,
        }
    }

except ImportError:
    return {..., "degraded": True, "degraded_reason": "DeepEval 未安装"}
```

**配套改动**：
- 新增 `deepeval` 到 `pyproject.toml` eval extra：`deepeval>=1.0.0`
- Tutor 指标走 `eval_data` JSON 列（`tables.py:55`），不新建列（因为 RAGAS 列名不匹配）
- `golden_cases.py` Tutor 用例补 `topic` 字段

**价值**：
- 自然语言定义教学效果，比 Rubrics 灵活且可读性强
- reasoning 输出可追溯为什么判某个分数（可解释性，呼应 DeepEval 调研 §7.3）

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| RAGAS 版本不兼容 | 中 | 中 | 锁定 `ragas==0.2.0`（项目已声明版本），升级前跑回归 |
| 合成测试集质量差 | 中 | 高 | Step 2 强制人工筛选 + 双人标注 + κ 校验（§5.1.1），质量不达标重生成 |
| judge 成本超预算 | 低 | 中 | 优先级 1-3 只用 RAGAS（已在依赖），DeepEval 可后置；测试集生成用 gpt-3.5-turbo-16k（生成）+ gpt-4o（审查）分级节省成本 |
| `EvalTable` 缺 context_recall 列 | 低 | 低 | 补列是简单 ALTER TABLE，迁移脚本一行搞定 |
| 两框架依赖冲突 | 低 | 中 | RAGAS 和 DeepEval 都基于 langchain，版本锁定 `langchain-openai==0.1.8`（RAGAS 调研推荐） |
| 降级用例过多导致报告失真 | 中 | 中 | ComponentBench 统计 degraded 占比，>50% 时报告顶部警告"评估不可信，检查 judge 配置" |

---

## 7. 实施时间线（分 Phase，逐步验证）

### Phase 1: RAGAS Retriever 替换 + judge 适配层（2-3 天）

**产出**：
- `app/eval/judge.py`（judge 适配层 + §5.1.1 不同族校验）
- `app/agents/retriever.py:151` 替换为 RAGAS 三指标
- `app/models/tables.py` 补 `ragas_context_recall` 列
- `tests/eval/test_judge.py` + `tests/unit/agents/test_retriever.py` 单测

**验收**：
```bash
pip install -e "."  # RAGAS 已在依赖，直接装
pytest tests/unit/agents/test_retriever.py::test_evaluate_ragas -v
# 期望：faithfulness/answer_relevancy/context_precision 非 0 分，且与字符 Jaccard 显著不同
```

### Phase 2: RAGAS 合成测试集生成（2-3 天）

**产出**：
- `scripts/generate_ragas_testset.py`（自动生成 100 候选）
- `scripts/refine_testset.py`（人工筛选 + 双人标注 + κ 计算）
- `golden_cases_v2.py`（50+ 个 Retriever 用例）

**验收**：
```bash
python scripts/generate_ragas_testset.py
# 输出：ragas_generated_candidates.csv（100 行）

# 人工筛选 + 标注后
python scripts/refine_testset.py
# 输出：κ ≥ 0.6，golden_cases_v2.py
```

### Phase 3: RAGAS 分阶段诊断 + DeepEval Tutor（2-3 天）

**产出**：
- `app/eval/component_bench.py:82` 追加分阶段诊断逻辑
- `app/agents/tutor.py:126` 替换为 DeepEval G-Eval
- `pyproject.toml` 新增 `deepeval>=1.0.0` 到 eval extra

**验收**：
```bash
pip install -e ".[eval]"  # 安装 deepeval
pytest tests/eval/test_component_bench.py -v
# 期望：Retriever 报告含分阶段诊断建议，Tutor 有 guidance_quality/clarity 分数

# 端到端运行 ComponentBench
python -m app.eval.kernel --run-component-bench
# 输出：Markdown 报告，含"检索召回不足 → 建议增加 top_k"等可执行建议
```

### Phase 4: API 集成 + 落库验证（1 天）

**产出**：
- 修改 `api/eval.py:28` 的 `rerun_eval` stub，真正调用 ComponentBench
- 验证评估结果落 `EvalTable` 的 `ragas_*` 字段

**验收**：
```bash
# 启动 API
uvicorn app.main:app

# 触发评估
curl -X POST http://localhost:8000/eval/test_session_123/rerun

# 查询结果
curl http://localhost:8000/eval/test_session_123
# 期望：返回 ragas_faithfulness/ragas_relevancy 等字段非空
```

**总工期**：7-10 天（含人工标注时间），可并行：Phase 1+2 可同时进行（两组人分工）。

---

## 8. 与既有 DeepEval spec 的关系（决策记录）

**问题**：刚写了 `docs/designs/2026-06-22-deepeval-component-metrics.md`（全 DeepEval 方案），现在调研发现项目更适合混合方案，如何处理？

**决策**：

| 产物 | 状态 | 处理方式 |
|---|---|---|
| `2026-06-22-deepeval-component-metrics.md` | 设计文档，已完成 | **保留作为备选方案**，顶部加注："本 spec 为纯 DeepEval 方案，经 `2026-06-22-deepeval-vs-ragas-adoption-report.md` 调研后，推荐改用混合方案（Retriever 用 RAGAS）。本文档作为纯 DeepEval 的技术储备，若后续 RAGAS 遇到阻塞可回退此方案。" |
| `2026-06-22-deepeval-vs-ragas-adoption-report.md` | 本报告 | **作为最新推荐方案**，后续实施以此为准 |

**理由**：DeepEval spec 的 §4.1 JudgeProvider 设计、§5 降级策略、§6 Phase 拆分等工程设计仍然有效（RAGAS 也需要 judge 适配），只是 Retriever 部分改调 RAGAS API。保留原 spec 作为技术文档，新报告作为执行方案。

---

## 9. 核心收益总结（给决策者的一句话）

采纳**混合方案（RAGAS for Retriever + DeepEval for Tutor）**，可获得：

1. **零新增依赖成本**（RAGAS 已装）+ 复用既有数据表字段（`ragas_*` 三列）
2. **合成测试集节省 90% 出题时间**，黄金集从 6 个扩充到 50+，满足 §5.1.1 要求
3. **分阶段诊断精确定位瓶颈**（检索召回/排序/幻觉/跑题），报告从"只看分数"变成"可执行优化建议"
4. **教学效果指标灵活定义**（DeepEval G-Eval 的自然语言 criteria）
5. **评估结果可落库展示**（`api/eval.py` 查询逻辑已就位，只需真跑评估）

**代价**：需同时维护两个框架（RAGAS + DeepEval），但通过 JudgeProvider 统一适配层，接口成本可控（两者都需 LLM + embeddings，适配层可复用）。

---

## 10. 附录：快速决策表

| 如果你关心… | 推荐方案 | 理由 |
|---|---|---|
| 最小改动成本 | **RAGAS only**（Retriever+Tutor 都用 RAGAS Rubrics） | 依赖已装，零新增；但 Tutor 教学指标 Rubrics 不如 G-Eval 灵活 |
| 最优技术方案 | **混合方案**（本报告推荐） | 扬两者所长：RAGAS 的测试集+分阶段 + DeepEval 的教学指标灵活性 |
| 最快见效 | **优先级 1 单独做**（RAGAS Retriever） | 1-2 天可见字符占位→语义评估的质变，其余可后置 |
| 依赖统一 | DeepEval only（原 spec） | 只装一个框架，但浪费 RAGAS 既有铺垫，且无合成测试集 |

---

## 11. 下一步行动建议

1. **立即可做**（无需等审批）：
   - 补 `EvalTable` 的 `ragas_context_recall` 列（一行 SQL）
   - 新建 `app/eval/judge.py` 骨架（§5.1.1 不同族校验逻辑，RAGAS 和 DeepEval 都要用）

2. **待决策**（需拍板）：
   - 是否采纳混合方案？还是保持原 DeepEval spec？
   - 测试集生成（优先级 2）是否纳入首轮实施？（会增加 2-3 天，但填黄金集缺口）

3. **待评审通过后**：
   - 按 §7 时间线进入 Phase 1 实施（RAGAS Retriever 替换）
   - 同步修订原 DeepEval spec 的 §4.2（改为调用 RAGAS API，保留其余设计）

---

**文档状态**：✅ 调研完成，待决策后进入实施。

**关联产物**：
- 调研来源：`Learned/DeepEval_测评方案.md`、`Learned/RAGAS_评估方案.md`
- 既有设计：`docs/designs/2026-06-22-deepeval-component-metrics.md`（备选方案）
- 母 spec：`docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` §5
- 既有框架：`app/eval/component_bench.py`（Plan E）、`app/models/tables.py:52-54`（ragas 字段）




