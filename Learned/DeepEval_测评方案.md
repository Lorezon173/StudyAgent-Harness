# DeepEval 测评方案详解

> **项目**: DeepEval - The LLM Evaluation Framework  
> **GitHub**: https://github.com/confident-ai/deepeval (16.4k+ stars)  
> **定位**: 生产级LLM应用评估框架，类pytest的测试体验  
> **适用场景**: RAG系统评估、LLM输出质量监控、CI/CD集成、模型对比

---

## 一、核心理念

DeepEval将LLM评估视为**软件测试**，而非学术研究。它的设计哲学是：
- **类pytest体验**：写测试用例就像写单元测试
- **可解释的分数**：每个指标输出0-1分数 + 详细reasoning
- **CI/CD友好**：失败即报错，可集成到持续集成流程
- **生产导向**：从开发到部署全周期支持

---

## 二、核心架构

### 2.1 测试用例结构

DeepEval的基本单元是`TestCase`，而不是传统的数据集行：

```python
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric

# 定义测试用例
test_case = LLMTestCase(
    input="法国的首都是哪里？",
    actual_output="法国的首都是巴黎。巴黎是一座历史悠久的城市...",
    expected_output="巴黎",  # 可选，用于某些指标
    retrieval_context=[  # RAG场景的检索上下文
        "巴黎是法国的首都和最大城市。",
        "法国位于欧洲西部。"
    ]
)

# 定义指标
faithfulness = FaithfulnessMetric(threshold=0.7)
answer_relevancy = AnswerRelevancyMetric(threshold=0.5)

# 运行评估
faithfulness.measure(test_case)
print(f"Faithfulness: {faithfulness.score}")
print(f"Reason: {faithfulness.reason}")
```

### 2.2 使用pytest集成

```python
# test_rag_pipeline.py
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    ContextualRelevancyMetric
)

@pytest.mark.parametrize(
    "test_case",
    [
        LLMTestCase(
            input="解释量子纠缠",
            actual_output="量子纠缠是...",
            retrieval_context=["量子物理的基本概念..."]
        ),
        # 更多测试用例...
    ]
)
def test_rag_pipeline(test_case):
    faithfulness = FaithfulnessMetric(threshold=0.7)
    answer_relevancy = AnswerRelevancyMetric(threshold=0.5)
    
    assert_test(test_case, [faithfulness, answer_relevancy])
```

运行：
```bash
deepeval test run test_rag_pipeline.py
# 或使用pytest
pytest test_rag_pipeline.py
```

---

## 三、评估指标体系

DeepEval提供**30+内置指标**，分为以下几类：

### 3.1 RAG三元组指标（RAG Triad）

这是RAG系统评估的核心，由三个指标组成：

#### **1. Answer Relevancy（答案相关性）**
- **衡量**: 答案是否真正回答了问题
- **适用场景**: 检测答案是否跑题、过于冗长
- **计算方式**: 
  - 使用LLM从答案反向生成N个问题
  - 计算这些问题与原问题的语义相似度
  - 公式: `score = mean(cosine_sim(original_q, generated_q_i))`

```python
from deepeval.metrics import AnswerRelevancyMetric

metric = AnswerRelevancyMetric(
    threshold=0.7,  # 及格线
    model="gpt-4o",  # 评估用的LLM
    include_reason=True  # 输出详细原因
)
```

**示例输出**:
```
Score: 0.85
Reason: The answer directly addresses the question about quantum entanglement, 
providing a clear explanation with relevant examples. No off-topic information detected.
```

#### **2. Faithfulness（忠实度/准确性）**
- **衡量**: 答案的每个声明是否都有检索上下文支撑
- **适用场景**: 检测幻觉、事实错误
- **计算方式**:
  - 将答案分解为独立的声明（claims）
  - 对每个声明判断是否被context支持
  - 公式: `score = supported_claims / total_claims`

```python
from deepeval.metrics import FaithfulnessMetric

metric = FaithfulnessMetric(
    threshold=0.8,
    model="gpt-4o"
)
```

**关键点**: Faithfulness **不关心context是否正确**，只关心答案是否忠实于context。这是检测幻觉的核心指标。

#### **3. Contextual Relevancy（上下文相关性）**
- **衡量**: 检索到的context是否真正相关
- **适用场景**: 评估检索器质量
- **计算方式**:
  - 提取context中与问题相关的句子
  - 公式: `score = relevant_sentences / total_sentences`

```python
from deepeval.metrics import ContextualRelevancyMetric

metric = ContextualRelevancyMetric(
    threshold=0.7,
    model="gpt-4o"
)
```

### 3.2 其他重要指标

#### **4. Contextual Precision（上下文精确度）**
- **衡量**: 最相关的context是否排在前面
- **需要**: `ground_truth`字段
- **适用**: 评估检索排序质量

#### **5. Contextual Recall（上下文召回）**
- **衡量**: 检索到的context是否包含回答问题所需的所有信息
- **需要**: `ground_truth`字段
- **公式**: `ground_truth中被context覆盖的句子比例`

#### **6. Hallucination Metric（幻觉检测）**
- **衡量**: 答案中是否包含context不支持的内容
- **与Faithfulness的区别**: 
  - Faithfulness: 正向检查（答案的每个声明是否被支持）
  - Hallucination: 反向检查（是否存在不被支持的内容）

#### **7. Toxicity（毒性检测）**
```python
from deepeval.metrics import ToxicityMetric

metric = ToxicityMetric(threshold=0.5)
```

#### **8. Bias（偏见检测）**
检测性别、种族、政治等多个维度的偏见。

### 3.3 G-Eval：万能自定义指标

**G-Eval是DeepEval最强大的功能**，可以用自然语言定义任何评估标准：

```python
from deepeval.metrics import GEval

# 为教学场景定义自定义指标
pedagogical_effectiveness = GEval(
    name="Pedagogical Effectiveness",
    criteria="评估答案是否：1) 引导学生思考而非直接给答案；2) 提供适当的例子；3) 使用清晰的解释",
    evaluation_steps=[
        "检查答案是否包含引导性问题",
        "确认是否提供了具体例子来说明概念",
        "评估解释的清晰度和适合学生水平",
        "判断是否直接给出了完整答案（应该避免）"
    ],
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT
    ],
    threshold=0.7
)

test_case = LLMTestCase(
    input="如何解二次方程？",
    actual_output="让我们一步步来。首先，你知道二次方程的一般形式是什么吗？\\n\\
    对，是ax²+bx+c=0。现在，有两种主要方法：配方法和求根公式。\\n\\
    我们先看一个简单例子：x²-5x+6=0，你能尝试分解因式吗？"
)

pedagogical_effectiveness.measure(test_case)
```

**G-Eval的优势**：
- 可以评估任何抽象概念（清晰度、专业性、教学效果等）
- 输出详细的reasoning
- 人类评分一致性高达80%+

---

## 四、针对学习辅助Agent的评估方案

### 4.1 核心评估维度

根据学习辅助的特点，建议建立**三层评估体系**：

#### **第一层：基础质量指标**（必须达标）

1. **Faithfulness** (threshold=0.85)
   - 确保不教错误知识
   - 对学习场景，容错率应该更低

2. **Answer Relevancy** (threshold=0.75)
   - 确保回答切题
   - 避免答非所问

3. **Contextual Relevancy** (threshold=0.70)
   - 检索到的学习材料相关性

#### **第二层：教学效果指标**（使用G-Eval自定义）

```python
# 1. 引导性指标
guidance_quality = GEval(
    name="Guidance Quality",
    criteria="评估答案是否通过提问、提示等方式引导学生自己思考，而非直接给出完整答案",
    evaluation_steps=[
        "检查是否包含启发性问题",
        "判断提示的程度是否适当（不能太明显也不能太隐晦）",
        "确认是否给学生留出了思考空间"
    ],
    threshold=0.7
)

# 2. 清晰度指标
clarity_metric = GEval(
    name="Explanation Clarity",
    criteria="评估解释是否清晰、结构化、易于理解",
    evaluation_steps=[
        "检查是否使用了分步骤的解释",
        "确认是否包含了必要的例子",
        "评估术语使用是否适合学生水平"
    ],
    threshold=0.75
)

# 3. 适应性指标
adaptability = GEval(
    name="Difficulty Adaptability",
    criteria="评估内容难度是否适合学生当前水平",
    evaluation_steps=[
        "分析学生的输入问题复杂度",
        "判断答案的难度是否匹配",
        "检查是否在必要时降低或提升难度"
    ],
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.RETRIEVAL_CONTEXT  # 可以包含学生历史记录
    ],
    threshold=0.70
)
```

#### **第三层：个性化指标**

```python
# 4. 知识连贯性
knowledge_coherence = GEval(
    name="Knowledge Coherence",
    criteria="评估答案是否与学生之前学过的内容建立了连接",
    evaluation_steps=[
        "检查是否引用了学生之前学习的概念",
        "判断知识点之间的衔接是否自然",
        "确认是否帮助学生建立知识体系"
    ],
    threshold=0.65
)

# 5. 例子质量
example_quality = GEval(
    name="Example Quality",
    criteria="评估提供的例子是否有助于理解",
    evaluation_steps=[
        "确认例子是否与概念直接相关",
        "判断例子的难度是否适当",
        "检查例子是否具体、可操作"
    ],
    threshold=0.70
)
```

### 4.2 完整测试套件

```python
# test_learning_agent.py
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    ContextualRelevancyMetric,
    GEval
)

# 基础指标
faithfulness = FaithfulnessMetric(threshold=0.85, model="gpt-4o")
answer_relevancy = AnswerRelevancyMetric(threshold=0.75, model="gpt-4o")
contextual_relevancy = ContextualRelevancyMetric(threshold=0.70, model="gpt-4o")

# 教学效果指标（前面已定义）
guidance_quality = GEval(...)
clarity_metric = GEval(...)
adaptability = GEval(...)

@pytest.mark.parametrize(
    "test_case,metrics",
    [
        # 场景1：基础概念解释
        (
            LLMTestCase(
                input="什么是二次函数？",
                actual_output="二次函数是形如y=ax²+bx+c的函数...",
                retrieval_context=["二次函数定义：..."]
            ),
            [faithfulness, answer_relevancy, clarity_metric]
        ),
        # 场景2：引导式答疑
        (
            LLMTestCase(
                input="我不会解这个方程：x²-5x+6=0",
                actual_output="让我们一起来分析。首先，你觉得能不能把它分解成两个括号的形式？\\n提示：想想哪两个数相乘等于6，相加等于-5？",
                retrieval_context=["因式分解方法：..."]
            ),
            [faithfulness, answer_relevancy, guidance_quality]
        ),
        # 场景3：难度适应
        (
            LLMTestCase(
                input="三角函数太难了，我看不懂",
                actual_output="没关系，我们从最基础的开始。你还记得直角三角形吗？...",
                retrieval_context=["三角函数基础...", "学生历史：刚学完几何基础"]
            ),
            [faithfulness, answer_relevancy, adaptability]
        ),
    ]
)
def test_learning_scenarios(test_case, metrics):
    assert_test(test_case, metrics)
```

### 4.3 运行和分析

```bash
# 运行全部测试
deepeval test run test_learning_agent.py

# 生成报告
deepeval test run test_learning_agent.py --output report.json

# 只运行特定场景
pytest test_learning_agent.py -k "guidance"
```

**分析结果**：
```python
import json
import pandas as pd

# 加载结果
with open('report.json') as f:
    results = json.load(f)

# 转为DataFrame分析
df = pd.DataFrame(results['test_results'])

# 找出失败的测试
failed = df[df['success'] == False]

# 按指标分组统计
metric_scores = df.groupby('metric_name')['score'].agg(['mean', 'min', 'max', 'std'])
print(metric_scores)

# 找出表现最差的场景
worst_cases = df.nsmallest(10, 'score')
```

---

## 五、集成到CI/CD

### 5.1 GitHub Actions示例

```yaml
# .github/workflows/rag_evaluation.yml
name: RAG Pipeline Evaluation

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install deepeval pytest
          pip install -r requirements.txt
      
      - name: Run DeepEval tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          deepeval test run tests/test_learning_agent.py --verbose
      
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: evaluation-results
          path: results/
```

### 5.2 设置阈值门槛

```python
# conftest.py - pytest配置
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "critical: mark test as critical (must pass)"
    )

@pytest.mark.critical
def test_core_faithfulness(test_case):
    """核心场景必须通过faithfulness检查"""
    metric = FaithfulnessMetric(threshold=0.90)  # 更高阈值
    assert_test(test_case, [metric])
```

---

## 六、成本优化

### 6.1 LLM选择策略

DeepEval的指标计算需要调用LLM，成本考虑：

| 指标类型 | 推荐模型 | 成本/样本 | 说明 |
|---------|---------|----------|------|
| Faithfulness | GPT-4o | $0.003 | 需要复杂推理 |
| Answer Relevancy | GPT-3.5-turbo | $0.001 | 相对简单 |
| G-Eval自定义 | GPT-4o | $0.004 | 依赖推理能力 |
| Contextual Relevancy | GPT-3.5-turbo | $0.001 | 可用较弱模型 |

```python
from deepeval.models import GPT4Model, GPT3_5Model

# 为不同指标配置不同模型
faithfulness = FaithfulnessMetric(
    threshold=0.85,
    model=GPT4Model()  # 高要求指标用GPT-4
)

answer_relevancy = AnswerRelevancyMetric(
    threshold=0.75,
    model=GPT3_5Model()  # 简单指标用GPT-3.5
)
```

### 6.2 批量评估优化

```python
from deepeval import evaluate

# 批量评估，自动并行处理
results = evaluate(
    test_cases=[tc1, tc2, tc3, ...],  # 多个测试用例
    metrics=[faithfulness, answer_relevancy],
    run_async=True,  # 异步执行
    throttle_value=10,  # 控制并发数，避免rate limit
    show_indicator=True  # 显示进度条
)
```

### 6.3 采样策略

对于大数据集：
```python
import random

# 只评估一部分数据
full_dataset = load_test_cases()  # 1000个
sample_size = 100

# 分层采样
easy_cases = [tc for tc in full_dataset if tc.difficulty == 'easy']
hard_cases = [tc for tc in full_dataset if tc.difficulty == 'hard']

sample = random.sample(easy_cases, 50) + random.sample(hard_cases, 50)

results = evaluate(sample, metrics=[...])
```

---

## 七、最佳实践

### 7.1 测试数据组织

```
tests/
├── test_basic_qa.py           # 基础问答测试
├── test_guided_learning.py     # 引导式学习测试
├── test_difficulty_adapt.py    # 难度适应测试
├── test_knowledge_coherence.py # 知识连贯性测试
├── fixtures/
│   ├── test_cases.json        # 测试用例数据
│   └── ground_truths.json     # 标准答案
└── conftest.py                # pytest配置
```

### 7.2 版本对比

跟踪不同版本的表现：

```python
# 保存baseline
baseline = evaluate(test_cases, metrics)
baseline.to_json('baselines/v1.0.0.json')

# 新版本对比
new_results = evaluate(test_cases, metrics)

# 对比分析
import json
with open('baselines/v1.0.0.json') as f:
    baseline_data = json.load(f)

for metric in ['faithfulness', 'answer_relevancy']:
    baseline_score = baseline_data['metrics'][metric]
    new_score = new_results[metric]
    delta = new_score - baseline_score
    print(f"{metric}: {baseline_score:.3f} → {new_score:.3f} ({delta:+.3f})")
```

### 7.3 失败案例分析

```python
# 自动标记低分样本
for result in results:
    if result.score < 0.7:
        # 保存到待review列表
        failed_cases.append({
            'test_case': result.test_case,
            'score': result.score,
            'reason': result.reason,
            'metric': result.metric_name
        })

# 导出供人工review
pd.DataFrame(failed_cases).to_csv('failed_cases_review.csv')
```

---

## 八、与学习辅助Agent的结合

### 8.1 实时评估（生产环境）

```python
from deepeval.metrics import FaithfulnessMetric

# 在RAG pipeline中集成
class LearningAgent:
    def __init__(self):
        self.faithfulness_check = FaithfulnessMetric(threshold=0.8)
    
    def generate_answer(self, question, contexts):
        answer = self.llm.generate(question, contexts)
        
        # 实时评估
        test_case = LLMTestCase(
            input=question,
            actual_output=answer,
            retrieval_context=contexts
        )
        
        score = self.faithfulness_check.measure(test_case)
        
        if score < 0.8:
            # 触发重新生成或人工review
            answer = self.regenerate_with_higher_quality(question, contexts)
        
        return answer
```

### 8.2 A/B测试框架

```python
# 对比不同提示词/模型的效果
variant_a_results = evaluate(test_cases, metrics, config='variant_a')
variant_b_results = evaluate(test_cases, metrics, config='variant_b')

# 统计显著性检验
from scipy import stats
t_stat, p_value = stats.ttest_ind(
    variant_a_results.scores,
    variant_b_results.scores
)

if p_value < 0.05:
    print(f"Variant B is significantly {'better' if variant_b_mean > variant_a_mean else 'worse'}")
```

---

## 九、总结与建议

### 9.1 DeepEval的优势

1. **开发友好**: pytest集成，写测试就像写单元测试
2. **可解释性强**: 每个分数都有详细reasoning
3. **灵活性高**: G-Eval可以定义任何评估维度
4. **生产就绪**: CI/CD集成、实时评估支持

### 9.2 对学习辅助Agent的价值

1. **建立质量门槛**: 通过阈值确保输出质量
2. **快速迭代**: 每次改动都能看到量化效果
3. **发现问题**: 自动找出表现差的场景
4. **持续监控**: 生产环境实时评估

### 9.3 快速上手路径

**第1周**:
- 安装DeepEval，跑通基础示例
- 用RAG Triad（3个指标）评估现有系统
- 建立baseline分数

**第2周**:
- 设计2-3个教学专用的G-Eval指标
- 收集20-30个典型测试用例
- 集成到pytest，跑通自动化测试

**第3-4周**:
- 覆盖更多场景（50+测试用例）
- 集成到CI/CD pipeline
- 建立评估报告dashboard

### 9.4 面试展示点

"我使用DeepEval建立了完整的评估体系：
- **基础质量层**: Faithfulness (0.87), Answer Relevancy (0.82), Contextual Relevancy (0.79)
- **教学效果层**: 用G-Eval定义了Guidance Quality、Clarity、Adaptability三个自定义指标
- **自动化测试**: 集成pytest，50+测试用例，覆盖基础问答、引导学习、难度适应等场景
- **CI/CD集成**: 每次PR都自动运行评估，阈值不达标自动阻断合并
- **成本优化**: 通过模型分级（GPT-4用于复杂指标，GPT-3.5用于简单指标）和采样策略，将评估成本控制在$0.15/run"

---

**参考资源**:
- [DeepEval官方文档](https://docs.confident-ai.com/)
- [RAG Triad指南](https://deepeval.com/guides/guides-rag-triad)
- [G-Eval详解](https://docs.confident-ai.com/docs/metrics-llm-evals)
- [CI/CD集成](https://deepeval.com/docs/evaluation-prompts)
