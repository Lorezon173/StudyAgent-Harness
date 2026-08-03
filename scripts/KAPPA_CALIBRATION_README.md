# κ 校准脚本使用说明

## 概述

本项目提供两个阶段的校准脚本，用于确保评估体系的可靠性：

- **阶段 1：`refine_testset.py`** — 黄金测试集精炼。通过 LLM 自动标注与人工标注的对比，计算 Cohen's κ 一致性系数，筛选出高质量的黄金测试用例。
- **阶段 2：`kappa_calibration.py`** — G-Eval 校准。将 LLM Judge 的评分与人工评分进行相关性分析，验证 G-Eval 评估标准是否与人类判断对齐。

## 前置依赖

```bash
pip install pandas scikit-learn openai scipy deepeval
```

## 阶段 1：黄金测试集精炼（refine_testset.py）

### 流程

1. **准备 CSV** — 使用 `scripts/templates/ragas_generated_candidates.csv` 作为模板，包含以下列：
   - `user_input`：用户问题
   - `retrieved_contexts`：检索到的上下文（多条用分号分隔）
   - `reference`：参考答案
   - `ground_truth_human`：人工标注的相关性标签（`relevant` / `partial` / `irrelevant`）

2. **人工标注 `ground_truth_human` 列** — 对每条样本判断其与检索上下文的相关性：
   - `relevant`：问题与上下文高度相关
   - `partial`：部分相关
   - `irrelevant`：不相关

3. **运行脚本** — 脚本会调用 LLM 对相同样本进行自动标注，并与人工标注计算 κ 值。

4. **解读结果**：
   - κ ≥ 0.6：一致性可接受，自动输出 `golden_cases_v2.py`
   - κ < 0.6：不一致过高，输出冲突列表供人工分析

### 用法

```bash
# dry-run 模式（不调用 API）
python scripts/refine_testset.py --dry-run

# 正式运行
python scripts/refine_testset.py --input path/to/candidates.csv --output app/eval/fixtures/golden_cases_v2.py

# 自定义模型
python scripts/refine_testset.py --model gpt-4o --input path/to/candidates.csv
```

### 参数说明

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--input` | 输入 CSV 路径 | `scripts/templates/ragas_generated_candidates.csv` |
| `--output` | 输出 .py 文件路径 | `app/eval/fixtures/golden_cases_v2.py` |
| `--dry-run` | 不调用 API，使用 mock 数据 | 关闭 |
| `--model` | LLM 模型名称 | `gpt-4o` |

### κ 阈值说明

| κ 值范围 | 含义 | 处理 |
|---|---|---|
| κ ≥ 0.6 | 人机一致性可接受 | 输出 `golden_cases_v2.py` |
| κ < 0.6 | 不一致过高 | 输出冲突列表，需人工审查 |

## 阶段 2：G-Eval 校准（kappa_calibration.py）

### 流程

1. **准备校准样本 CSV** — 使用 `scripts/templates/calibration_samples_guidance.csv` 作为模板，包含以下列：
   - `topic`：教学主题
   - `student_question`：学生提问
   - `tutor_response`：教师/辅导系统的回答
   - `human_score`：人工评分（1-5 分）
   - `human_score_t1`：（可选）间隔 1 周后的重标分数，用于 test-retest 信度检验

2. **人工打分（1-5 分）** — 对每条 tutor_response 从以下维度评分：
   - 1 分：回答质量极差，未回应问题
   - 2 分：回答有重大缺陷
   - 3 分：回答基本合格但有明显改进空间
   - 4 分：回答质量良好
   - 5 分：回答质量优秀，引导性强

3. **（可选）间隔 1 周后重标部分样本** — 填写 `human_score_t1` 列，用于计算 test-retest 信度。

4. **运行脚本** — 脚本会调用 LLM Judge 对相同样本评分，并与人工评分计算 Pearson 相关系数。

5. **解读结果**：
   - r ≥ 0.7：Human-Judge 一致性可接受，G-Eval 标准可靠
   - r < 0.7：建议修订 G-Eval 的 criteria

### 用法

```bash
# dry-run 模式
python scripts/kappa_calibration.py --dry-run

# 正式运行（含 test-retest）
python scripts/kappa_calibration.py --input path/to/samples.csv

# 跳过 test-retest
python scripts/kappa_calibration.py --skip-test-retest --input path/to/samples.csv
```

### 参数说明

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--input` | 输入 CSV 路径 | `scripts/templates/calibration_samples_guidance.csv` |
| `--dry-run` | 不调用 API，使用 mock 数据 | 关闭 |
| `--skip-test-retest` | 跳过 test-retest 步骤 | 关闭 |

### 相关性阈值说明

| r 值范围 | 含义 | 处理 |
|---|---|---|
| r ≥ 0.7 | Human-Judge 一致性可接受 | G-Eval 标准可靠，可用于正式评估 |
| r < 0.7 | 一致性不足 | 建议修订 G-Eval 的 criteria 后重新校准 |

## 输出文件

- **阶段 1**：`app/eval/fixtures/golden_cases_v2.py` — 精炼后的黄金测试用例集
- **阶段 2**：终端输出分析报告 — 包含相关系数、散点图统计、逐条对比等

## 注意事项

- API key 从环境变量 `OPENAI_API_KEY` 或 `.env` 文件读取（通过 `app.core.config.settings`）
- dry-run 模式下不需要 API key
- 建议在正式运行前先用 dry-run 确认流程无误
