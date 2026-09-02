# 评估体系 DeepEval 与 RAGAS Phase 2：工作交接

## 1. 一句话接手说明

当前窗口已完成评估体系的 LLM-as-judge 边界讨论、DeepEval 可行性与 API spike、单人 κ 校准工具和 RAGAS Phase 2 生成脚本的初步实现；当前唯一未关闭的核心阻断是 RAGAS 0.4.3 的 `HeadlineSplitter` 真实生成失败，下一窗口应先完成最小修复 spike，再接回脚本并进行第三轮代码审查。

## 2. 当前状态

- **已完成：**
  - 已核实评估体系各层的 LLM 使用边界，并形成项目内知识记录。
  - 已完成 DeepEval G-Eval 借鉴可行性分析与构造接口 spike。
  - 已按单人条件调整 κ 校准方案。
  - 已创建黄金测试集精炼、G-Eval 校准和 RAGAS 测试集生成辅助脚本及模板。
  - 已实现 Phase 2 生成脚本的文件知识源、RAGAS 构造、CSV 导出、dry-run 和降级路径。
  - 已修复 settings 导入路径、embedding 模型读取、NaN 序列化和 context 字段错配问题。
  - 已补充 `rapidfuzz` 到 eval extra。
  - 已完成两轮独立代码审查；第一轮可直接修复项已处理，第二轮确认 HeadlineSplitter 阻断仍存在。
  - 已修改全局 `pre-commit-review` skill，明确禁止 subagent 长时间固定 sleep，长任务需每 10 秒轮询。

- **进行中：**
  - Phase 2 真实生成路径的 RAGAS transforms 修复。

- **未开始但已确认要做：**
  - 解决 HeadlineSplitter 问题后接入最终 transforms 方案。
  - 修正生成脚本中两处不准确的注释。
  - 启动第三轮独立代码审查。
  - 在真实候选集上执行人工筛选、LLM second annotator 与 κ 校准。

- **当前卡点 / 待确认项：**
  - `ragas==0.4.3` 真实生成仍会出现 `ValueError: 'headlines' property not found in this node`。
  - 初次 spike 将“进度条跑完”误判为成功；第二轮审查通过最终 stderr 与 RAGAS 源码确认该判断错误。
  - 尚未决定采用“自建 transforms 补 filter”“升级 RAGAS”还是“跳过 HeadlineSplitter”的最终修复路径；应先做最小真实 spike，不要直接凭纸面结论改主脚本。

## 3. 接手后第一动作

1. 打开 `scripts/generate_ragas_testset.py` 的 `generate_testset` 实现，并对照当前已安装的 RAGAS 0.4.3 transforms 源码，确认 `HeadlinesExtractor` 与 `HeadlineSplitter` 的 filter 行为。
2. 只在 `/tmp` 构造一个最小 spike：复用默认 transforms 链，但让 `HeadlineSplitter` 使用与 extractor 相同的文档过滤条件；输入少量 markdown，目标生成 1–2 条样本。
3. 使用后台进程时，每 10 秒轮询日志、进程和输出文件；禁止使用长时间固定 `sleep`，也不要只看 tqdm 进度。
4. 以最终进程退出码、完整 stderr 和 `testset.to_pandas()` 的非空结果共同判定 spike；只有三者都满足，才把修复接回项目脚本。
5. 接回后修正不准确注释，再重新调用 `pre-commit-review` 做第三轮审查。

## 4. 关键决策与边界

### 已确认决策

- `.evolve/` 是用户的工作流自进化系统，不是 StudyAgent 评估体系；评估体系不得把它作为反馈存储或架构依赖。
- LLM-as-judge 只属于 L2 离线旁路中的开放语义评估；确定性事件、结构和数值指标继续使用算法。
- DeepEval G-Eval 的借鉴方向是 Tutor 语义质量评估，不扩展到 SystemBench、CollaborationBench 或 ABController 的确定性指标。
- RAGAS 测试集生成脚本只从 markdown 文件加载知识源；当前不接入空的 `VectorChunkTable` DB 分支。
- 生成 CSV 必须满足下游精炼脚本的四列契约：`user_input`、`retrieved_contexts`、`reference`、`ground_truth_human`。
- 生成阶段的 `ground_truth_human` 留空，由后续人工标注填充。
- LLM judge 不得进入在线 `handle()` 路径，不得以降级结果冒充真实语义分。
- 当前真实生成若失败，只能输出明确的空模板降级，不能把 dry-run mock 或空模板当作 Phase 2 候选集。

### 明确不要做的事

- 不要把 `.evolve/_inbox/` 当作项目评估反馈目录。
- 不要在 HeadlineSplitter 修复未经真实 spike 验证前宣布 Phase 2 完成。
- 不要只根据 tqdm 进度条判断 RAGAS 成功；必须检查最终异常、退出码和非空结果。
- 不要在未修复阻断项前进入真实 100 条生成或 κ 校准。
- 不要把 `raise_exceptions=False` 描述为能够吞掉 transforms 阶段的异常；它不能替代 transforms 链的错误处理。
- 不要用 `git add -A`、`git add .` 或重置命令处理当前工作区；仓库有大量其他会话的未提交修改。
- 不要让修复 subagent 用 `sleep 60`、`sleep 300` 等估时等待；长任务必须轮询。

### 仍未定论、不能当作事实的点

- 自建 transforms 链的完整参数、过滤器导入路径和跨版本稳定性尚未由项目内最终 spike 固定。
- 升级 RAGAS 是否解决该 bug，以及会否带来新的 API/依赖破坏，尚未验证。
- 火山方舟 endpoint 在所有 RAGAS 生成步骤中的长期兼容性只做过一次 spike 观察，不能替代回归验证。
- DeepEval 与自定义 judge adapter 的最终实现尚未进入 Phase 3；当前只完成 API 兼容性分析。
- κ 校准的真实样本、人工标签和最终统计结果尚未产生。

## 5. 必看材料索引

### 评估体系与 DeepEval 设计

- 用途：查看评估体系当前的整体评估架构、Phase 状态、RAGAS/DeepEval 分工及既有决策。
  - 索引：`docs/designs/2026-06-22-hybrid-evaluation-ragas-deepeval.md`
- 用途：查看 DeepEval 与 RAGAS 的选型论证。
  - 索引：`docs/research/2026-06-22-deepeval-vs-ragas-adoption-report.md`
- 用途：查看原始 DeepEval 组件指标设计。
  - 索引：`docs/designs/2026-06-22-deepeval-component-metrics.md`
- 用途：查看项目内 DeepEval 学习记录。
  - 索引：`Learned/DeepEval_测评方案.md`
- 用途：查看项目内 RAGAS 学习记录。
  - 索引：`Learned/RAGAS_评估方案.md`
- 用途：查看 LLM-as-judge 适用层次与禁止边界。
  - 索引：`Learned/LLM-as-judge适用边界与红线.md`

### κ 校准工具与契约

- 用途：查看阶段 1/2 校准脚本的当前实现和 CLI 入口。
  - 索引：`scripts/refine_testset.py`
  - 索引：`scripts/kappa_calibration.py`
- 用途：查看校准脚本、CSV 字段和 dry-run 的使用约定。
  - 索引：`scripts/KAPPA_CALIBRATION_README.md`
- 用途：查看输入模板格式。
  - 索引：`scripts/templates/ragas_generated_candidates.csv`
  - 索引：`scripts/templates/calibration_samples_guidance.csv`
- 用途：查看当前已生成的候选 fixture 草稿，不将其视为真实完成结果。
  - 索引：`app/eval/fixtures/golden_cases_v2.py`

### Phase 2 实现与 RAGAS API

- 用途：定位当前生成脚本的所有实现入口、配置解析和导出逻辑。
  - 索引：`scripts/generate_ragas_testset.py`
- 用途：核对下游 CSV 的硬契约。
  - 索引：`scripts/refine_testset.py` 中的 `load_candidates`
- 用途：核对项目 API 配置字段和 embedding 默认模型。
  - 索引：`app/core/config.py` 中的 `Settings`
- 用途：核对项目 embedding 服务实际使用的 SDK 与字段。
  - 索引：`app/infrastructure/rag/embedding.py` 中的 `EmbeddingService`
- 用途：核对 RAGAS 0.4.3 运行时 API、transforms 和默认过滤行为。
  - 索引：当前 `.venv/lib/python3.12/site-packages/ragas/` 下对应模块
- 用途：回看首次错误成功判断的完整日志（若文件仍保留）。
  - 索引：`/tmp/spike.log` 或本窗口 workflow task 输出目录

### 审查与工作流约束

- 用途：查看第一、二轮代码审查发现及验证命令。
  - 索引：本窗口的 `pre-commit-review` workflow task 输出
- 用途：查看当前三轮审查规则、subagent 隔离要求和禁止长时间 sleep 纪律。
  - 索引：`~/.claude/skills/pre-commit-review/SKILL.md`
- 用途：查看项目级语言、README、规划和命令执行约束。
  - 索引：`CLAUDE.md`
  - 索引：`.claude/rules/dev-standards.md`
- 用途：查看交接文档的固定骨架和“引用只给索引”规则。
  - 索引：`~/.claude/skills/handoff-document/SKILL.md`

## 6. 代码 / 产物落点

- `scripts/generate_ragas_testset.py`：Phase 2 主脚本；已完成文件加载、RAGAS 构造、CSV 导出和多种降级分支，但真实生成仍被 HeadlineSplitter 阻断。
- `pyproject.toml`：eval extra 依赖声明；本窗口加入了 `langchain-google-vertexai==3.2.4` 与 `rapidfuzz>=3.0.0`，后者用于默认 transforms 的字符串距离构造。
- `scripts/refine_testset.py`：Phase 2 下游精炼与 Human-LLM κ 入口；当前要求四列输入。
- `scripts/kappa_calibration.py`：Phase 3 前的 G-Eval 与单人人工分相关性校准入口；尚未用真实样本执行。
- `scripts/templates/`：阶段输入模板。
- `scripts/KAPPA_CALIBRATION_README.md`：脚本使用说明。
- `app/eval/fixtures/golden_cases_v2.py`：已有 fixture 草稿；不能视为已完成的 50+ 可信黄金集。
- `spike_geval_compat.py`：DeepEval GEval API 兼容性 spike 产物。
- `~/.claude/skills/pre-commit-review/SKILL.md`：全局审查 skill，已增加 10 秒轮询纪律。
- `README.md`：已同步 `scripts/` 测试集生成与 κ 校准工具描述；后续若真实 Phase 2 状态或命令改变，需再检查。

## 7. 待办清单

### 必须先做

1. 在 `/tmp` 完成 HeadlineSplitter filter 修复 spike，并记录完整最终日志、退出码和非空样本结果。
2. 根据 spike 结果选择并实现最小修复；不要同时引入 RAGAS 升级和自建 transforms 两条路径。
3. 删除或改正 `generate_testset` 中关于 `default_transforms` 已验证成功的注释。
4. 改正 `raise_exceptions=False` 注释，使其不暗示 transforms 阶段异常会被吞掉。
5. 运行 dry-run、配置解析、NaN、CSV 下游契约和至少一次真实小规模生成验证。
6. 重新调用 `pre-commit-review`，启动第三轮独立审查；第三轮结果需按 skill 规定告知用户并等待后续处理决定。
7. 第三轮通过后，再运行真实 Phase 2 候选生成和人工筛选/LLM second annotator κ 流程。

### 可后做

8. 生成 100 条真实候选并完成人工质量筛选。
9. 执行 `scripts/refine_testset.py` 的 Human-LLM κ 校准，确认 κ 达到项目门槛后再输出最终黄金集。
10. 评估并记录候选集质量、空值比例、失败比例与来源覆盖，不把自动生成数量等同于质量。
11. 在 Phase 2 数据可信后，重新评估 Phase 3 DeepEval G-Eval 的依赖、adapter、degraded 协议和单人校准结果。
12. 如 Phase 2 的真实 CLI、依赖或状态说明发生变化，更新 `README.md` 并同步资产清单。

## 8. 风险与坑点

- **tqdm 假成功风险：** 进度条完成不代表任务成功；必须看最终 stderr 和退出码。第一次 spike 正是在这里误判。
- **RAGAS 0.4.3 transforms 缺陷：** 默认 extractor 与 splitter 的过滤边界不一致，短文档可能没有 `headlines` 属性。
- **异常参数语义风险：** `raise_exceptions=False` 不能覆盖 transforms 阶段的异常传播，不能用它替代真正的过滤或异常策略。
- **配置 cwd 风险：** 项目 `Settings` 的 `.env` 路径与运行目录有关；脚本已修复 `app` 导入路径，但非项目根运行时的 env 加载仍需留意。
- **模型/网关风险：** 项目 embedding 默认是 `doubao-embedding-vision`；不能再硬编码 OpenAI 的 `text-embedding-3-small`。
- **CSV 语义风险：** `retrieved_contexts` 是实际检索上下文；`reference_contexts` 是参考上下文，不能互相映射。
- **mock/空模板风险：** dry-run 仅验证流程，空模板仅代表降级；二者都不能进入最终黄金集。
- **统计解释风险：** 单人 + LLM second annotator 的 κ 只能作为辅助一致性证据，不能无条件等同于双人独立人工标注；后续报告需明确标注者身份和局限。
- **依赖管理风险：** RAGAS 0.4.3 的导入链、`langchain-google-vertexai` 和 `rapidfuzz` 必须通过 `uv sync --extra eval` 在干净环境复现，不能只依赖当前 `.venv` 的偶然安装状态。
- **工作树隔离风险：** 当前工作区存在大量其他会话的修改和未跟踪文件；后续只做明确路径的修改，不重置、不宽泛 add。
- **交接索引风险：** 交接文档只提供来源索引；接手者必须回源读取最新代码/日志，不能把本文件的二手状态当作永久事实。

## 9. 交接完成判据

- 新窗口打开本文即可知道 Phase 2 当前不是“真实生成已完成”，而是被 HeadlineSplitter 阻断。
- 新窗口能按第 3 节顺序立即开展最小 spike，不需要回放本窗口对话。
- 所有关键源文档、代码、日志和规则均有路径索引，本文没有复制其正文。
- 已完成、进行中、未开始、阻断项和未验证假设被明确分开。
- 新窗口知道第一次 spike 的“tqdm 假成功”陷阱，并会以最终退出码、stderr 和非空输出共同验收。
- 新窗口知道 `.evolve/` 不属于项目评估体系，也知道不得用它承载评估反馈。
- 新窗口知道第三轮 `pre-commit-review` 是当前审查 gate，不能在阻断项未关闭前宣布交付。
