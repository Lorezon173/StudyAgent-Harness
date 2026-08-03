# StudyAgent-Harness 工作交接

> 交接时间：2026-07-14 15:10:36
> 工作目录：`/Users/ywwl/Downloads/my/code/StudyAgent-Harness`
> 说明：本文仅总结当前窗口的工作状态。涉及已有文档时只保留路径索引，不复制文档正文。

## 1. 本窗口目标与范围

本窗口主要围绕 StudyAgent 旁路评估体系开展以下工作：

1. 核实当前评估体系的 LLM-as-judge 使用现状、适用范围、层次及禁止边界。
2. 评估 DeepEval G-Eval 借鉴方案的可行性，并对 API 兼容性进行 spike。
3. 设计单人条件下的 κ 校准流程，并实现相关辅助脚本。
4. 实施 Phase 2：RAGAS 合成测试集生成脚本。
5. 对 Phase 2 代码执行多轮独立审查，发现并修复部分问题；当前仍有一个阻断问题待决策和修复。
6. 修改全局 `pre-commit-review` skill 的 subagent 等待纪律，禁止长时间固定 sleep，改为每 10 秒轮询。

## 2. 关键结论

### 2.1 LLM-as-judge 边界

- 项目不需要另建一套全新的 LLM-as-judge 体系；当前已经是混合评估体系。
- LLM judge 仅适用于 L2 离线旁路中的开放语义维度，例如 Retriever 的语义质量和 Tutor 的教学质量。
- SystemBench 的事件断言、CollaborationBench 的结构指标、ABController 的数值差分等确定性维度不应引入 LLM。
- judge 不得进入在线 `handle()` 路径；不得由被评对象自评；judge 与被评模型应不同族；降级结果不得伪装成真实语义分；未经校准的 judge 分数不得直接采信。

相关文档索引：

- `Learned/LLM-as-judge适用边界与红线.md`
- `docs/designs/2026-06-22-hybrid-evaluation-ragas-deepeval.md`
- `docs/research/2026-06-22-deepeval-vs-ragas-adoption-report.md`
- `docs/designs/2026-06-22-deepeval-component-metrics.md`
- `Learned/DeepEval_测评方案.md`
- `Learned/RAGAS_评估方案.md`

### 2.2 `.evolve/` 归属纠正

- `.evolve/` 属于用户的工作流自进化系统，不属于 StudyAgent 的项目评估子系统。
- 项目评估反馈不能默认写入 `.evolve/_inbox/`。
- 本次暴露出两条可复用经验：引用产物前要核实归属；评估是否引入能力前要先穷举现状。

相关索引：

- `.claude/rules/solution-presentation.md`
- `.evolve/_inbox/2026-06-28-引用前先核实归属-与-能力引入先穷举现状.md`

### 2.3 DeepEval 可行性

- DeepEval G-Eval 用于 Tutor 的引导性、清晰度、概念覆盖评估，在能力上可行。
- `GEval.model` 不接受 `langchain_openai.ChatOpenAI` 实例，只接受模型名字符串或 `DeepEvalBaseLLM`；因此现有 `build_judge()` 需要返回模型名，或增加适配器。
- 当前优先考虑传模型名字符串的最小方案；若必须支持自定义 base URL，则需要进一步确认 DeepEval 内部模型客户端是否兼容，或实现 `DeepEvalBaseLLM` wrapper。
- Phase 3 尚未实施。

相关索引：

- `spike_geval_compat.py`
- `app/eval/judge.py`
- `app/agents/tutor.py`
- `docs/designs/2026-06-22-hybrid-evaluation-ragas-deepeval.md`

## 3. κ 校准工作

### 3.1 约束与选择

用户只有一名人工标注者，因此原双人双盲方案调整为：

- 黄金测试集：Human + LLM second annotator，计算 Cohen's κ。
- G-Eval 校准：单人人工评分与 G-Eval 分数比较，计算 Pearson / Spearman；另保留可选 Test-Retest，由同一人工间隔一周重标 10 个样本。

### 3.2 已新增产物

- `scripts/refine_testset.py`
- `scripts/kappa_calibration.py`
- `scripts/templates/ragas_generated_candidates.csv`
- `scripts/templates/calibration_samples_guidance.csv`
- `scripts/KAPPA_CALIBRATION_README.md`
- `app/eval/fixtures/golden_cases_v2.py`

当前这些产物已做 dry-run 验证，但未完成真实人工标注与 κ 校准。

## 4. Phase 2 实施状态

### 4.1 已新增/修改

- 新增：`scripts/generate_ragas_testset.py`
- 修改：`pyproject.toml`
- 修改：`README.md`

脚本目标：从项目 markdown 文档生成 RAGAS 候选测试集，并输出下游 `refine_testset.py` 可读取的 CSV。

CSV 契约已统一为：

- `user_input`
- `retrieved_contexts`
- `reference`
- `ground_truth_human`

### 4.2 已验证通过

1. `--dry-run` 能生成 3 条 mock CSV。
2. 输出列可被 `scripts/refine_testset.py:load_candidates()` 接收。
3. 无 API key 时输出空模板并退出，不崩溃。
4. `--size <= 0` 会拒绝执行。
5. 脚本可将项目根加入 `sys.path`，直接执行时可导入 `app.core.config.settings`。
6. embedding 模型会读取 `settings.embedding_model`。
7. `_join_contexts()` 已处理 pandas NaN，避免写入字面值 `nan`。
8. 已删除把 `reference_contexts` 错映射成 `retrieved_contexts` 的逻辑。
9. `pyproject.toml` 的 eval extra 已加入 `rapidfuzz>=3.0.0`。
10. `langchain-google-vertexai==3.2.4` 是 RAGAS 0.4.3 导入链所需的兼容依赖，不是项目业务直接 import 的依赖。

### 4.3 当前阻断项

**RAGAS 0.4.3 的 HeadlineSplitter 仍会报错：**

`ValueError: 'headlines' property not found in this node`

第二轮独立审查核实：

- `default_transforms()` 内 `HeadlinesExtractor` 只处理满足 `filter_doc_with_num_tokens` 的节点。
- `HeadlineSplitter` 没有使用相同 filter，会尝试处理所有节点。
- 对于未被 HeadlinesExtractor 写入 `headlines` 的短节点，HeadlineSplitter 抛异常。
- 仅显式传 `transforms=default_transforms(...)` 并不能稳定修复当前文档集合下的问题。

当前项目代码中加入的相关注释有两处需要后续纠正：

1. “经 spike 验证 default_transforms 可跑通”的断言不可靠。
2. “raise_exceptions=False 让单条失败不中断整批”的描述不适用于 transforms 阶段；transforms 异常仍会冒泡。

### 4.4 待决策的修复方向

候选方案：

1. 自建 transforms 链，让 `HeadlineSplitter` 使用与 `HeadlinesExtractor` 相同的 `filter_doc_with_num_tokens`。
2. spike 新版 RAGAS，确认该 bug 是否已修复，并评估 breaking changes。
3. 跳过 HeadlineSplitter，验证剩余 transforms 是否可生成可用样本。
4. 暂时接受空模板降级，但此时 Phase 2 不能算真实完成。

推荐下一窗口优先做方案 1 的最小 spike：只在 `/tmp` 构建与默认链一致、但为 HeadlineSplitter 补 filter 的 transforms 链；生成 1-2 条样本并完整检查最终退出码、stderr 和 `to_pandas()`，不能只看 tqdm 的中间进度。

## 5. 代码审查状态

使用 `pre-commit-review` skill 执行了两轮独立审查：

### 第一轮

发现：

- sys.path 导入问题。
- embedding_model 硬编码。
- NaN 污染。
- CSV 列语义错配。
- RAGAS HeadlineSplitter 报错。

前四项已经修复。

### 第二轮

确认前四项修复有效；推翻了第一次 transforms spike 的“成功”结论，确认 HeadlineSplitter 问题仍阻断真实生成。

当前审查结论：**未通过**。需解决 HeadlineSplitter 后再启动第三轮审查。

## 6. 全局 skill 修改

修改文件：

- `~/.claude/skills/pre-commit-review/SKILL.md`

新增纪律：

- 审查/修复/验证 subagent 禁止使用长时间固定 sleep。
- 必须每 10 秒轮询进程、日志、产物或健康检查；条件满足后立即继续。
- 派发 subagent 时必须显式复述该纪律。

注意：用户指出此前 subagent 会先长时间 sleep，这种模式不允许再次出现。

## 7. README 状态

README 已同步：

- 评估技术栈/依赖说明曾更新。
- 项目结构中的 `scripts/` 已包含测试集生成与 κ 校准说明。

本交接文档本身不涉及新功能，因此不需要再次修改 README。

## 8. 当前工作区注意事项

工作区原本已有其他未提交改动和未跟踪文件，后续不要误删或覆盖。特别注意：

- `README.md`
- `docs/asset-inventory.md`
- `docs/research/2026-06-22-deepeval-vs-ragas-adoption-report.md`
- `docs/designs/2026-07-03-phase-b1-lightrag-dual-retrieval-spec.md`
- `docs/designs/2026-07-03-phase-b2-mastery-temporal-review-spec.md`
- `docs/designs/2026-07-03-phase-b3-pdf-layout-parsing-spec.md`
- `docs/designs/2026-07-03-rag-upgrade-todolist.md`
- `ragas_generated_candidates.csv`
- `spike_geval_compat.py`

不要把 `ragas_generated_candidates.csv` 的 mock/空模板误当成真实黄金测试集。

## 9. 下一窗口建议执行顺序

1. 读取本交接文档。
2. 读取 `scripts/generate_ragas_testset.py` 当前实现。
3. 对照 RAGAS 0.4.3 源码确认默认 transforms 链与 filter 行为。
4. 在 `/tmp` 做“HeadlineSplitter 同 filter”最小 spike，生成 1-2 条真实样本。
5. 验证完整进程退出码、最终 stderr、最终 CSV 非空；不要只看 tqdm 进度。
6. spike 成功后，以外科手术式修改接回 `generate_testset()`。
7. 修正上述两处不准确注释。
8. 重新调用 `pre-commit-review` skill，派发全新 subagent 做第三轮审查。
9. 第三轮通过后再宣布 Phase 2 完成；否则继续记录剩余阻断项，不得以空模板降级冒充成功。

## 10. 常用验证命令

```bash
cd /Users/ywwl/Downloads/my/code/StudyAgent-Harness

# dry-run
.venv/bin/python scripts/generate_ragas_testset.py --dry-run

# 检查配置解析
.venv/bin/python -c "import sys; sys.path.insert(0, 'scripts'); import generate_ragas_testset as g; print(g.resolve_api_config())"

# NaN 防护
.venv/bin/python -c "import sys, numpy as np; sys.path.insert(0, 'scripts'); import generate_ragas_testset as g; print(repr(g._join_contexts(np.nan)))"

# transforms / rapidfuzz 依赖
.venv/bin/python -c "from ragas.testset.transforms import default_transforms; import rapidfuzz; print('OK', rapidfuzz.__version__)"

# 真实生成（当前预计仍会被 HeadlineSplitter 阻断）
.venv/bin/python scripts/generate_ragas_testset.py --size 1 -o /tmp/ragas_test.csv
```

等待长任务时必须用每 10 秒轮询查看日志与产物，不得使用长时间固定 sleep。
