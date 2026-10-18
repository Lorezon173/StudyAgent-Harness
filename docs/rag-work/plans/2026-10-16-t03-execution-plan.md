# T03 评测状态、多 k 与完整 20 题执行 Implementation Plan

> **For agentic workers:** 实施时使用 superpowers:subagent-driven-development 或 superpowers:executing-plans 逐项执行；批准时计划经文档复核；当前已完成实现和主窗口验收，证据见下文。用户要求优先中文、三层文字设计，不提供实现或测试代码。本包不再派子代理，不 commit/push。

**Goal:** 让现有唯一 Retriever evaluator 保真输出检索状态、单次多 k 机械指标和逐项 judge 有效性，让 baseline 核心只在 20 个唯一 verified 题全部有效执行后完成。

**Architecture:** 保留 RetrieverAgent.evaluate(test_case:dict) 的四键输入与公开 import 路径；只消费现有 Coordinator.search 的 SearchResult，不修改 Coordinator。rag_d.py 负责资产验证、单次顺序执行及停止/计数，T09 随后接入 T04 证明 schema 和正式报告目标绑定；T03 不依赖 T04 新模块，能与 T02/T04 首批并行。

**Tech Stack:** 项目 Python >=3.11；pytest；现有 Counter / JSON / YAML；judge 复用现有 RAGAS 0.4.3、datasets、app.eval.judge。无新增第三方依赖。

**Spec:** [共享契约](../specs/2026-10-16-rag-mvp-contracts-v1.md)，固定版本 `rag-mvp-contracts-v1.0.1`，冻结字节 SHA-256 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。本次只读核对实际 SHA 与冻结记录一致。

## 全局约束与材料入口

- 当前状态：**实施完成，两轮定向复审与主窗口组合离线回归通过**。[T03执行证据](../evidence/t03/2026-10-16-t03-verification.md)；[主窗口验收](../evidence/2026-10-16-first-wave-execution.md)。本包最终三文件176项通过，四文件Ruff通过；未获得G1/G4/G6。下文保留批准时设计、基线与步骤用于追溯，实际执行以证据为准。
- 设计来源依次为 [MVP raw](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan.md) E2、[review](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan-review.md) RV-01/RV-05、[针对性核验](../../../superpowers/rag-foundation/2026-10-13-review-verification.md) §1/§6、[冻结记录](../../../superpowers/rag-foundation/2026-10-16-t00-contract-freeze-record.md)、[DAG](../../../superpowers/rag-foundation/2026-10-16-rag-mvp-dag-and-scheduling.md)、[就绪审计](../../../superpowers/rag-foundation/2026-10-16-execution-readiness-audit.md)。旧 99 项测试结果属于历史证据，不能写成本包通过。
- 正式 baseline 的 top_k=5、expected_count=20；普通 evaluate 默认5，允许1～10的非bool整数；每题最多一次 evaluate/search，无重试、无为多 k 补搜。
- 机械指标名称固定 `paragraph-containment proxy`；judge 固定 `gold-answer/context enrichment`，不得宣称在线 Tutor 质量或 strict identity recall。
- 六码只用 backend_unavailable/db_error/embedding_failed/provider_degraded/invalid_request/timeout，摘要复用 retriever.py 的 SAFE_SUMMARIES；不得泄露异常原文、SQL、堆栈、连接串或正文到诊断。
- failed/degraded/invalid-request 不参与质量均值；健康 empty 是可有效执行的零召回；judge 降级与检索故障分开。兼容字段 degraded 不能作为 runner 的唯一判据。
- 仅离线受控测试；不连接真实 PG、embedding、LLM，不读取或修改本书实际正文资产，不产生摄入或成功证明。真实 20 题由 T12 执行。
- 冻结 spec 不得改；跨包共享字段不一致报告主控。耗时命令不使用 sleep，每30秒主动轮询；平台阻挡同动作仅重试一次，再失败报告手动命令。

## 第一层：模块总览

T03 包含三个边界：evaluate 的稳定质量结果契约、资产的完整可执行性约束、baseline 的停止与完成计数。现有 evaluate 只使用 chunks，失败可变成 recall=0；没有 gold 时给满分，RAGAS 缺项回填0且 NaN 不降级；现有 validate_assets/runner 跳过 draft，runner 无数量不变量。这些是本次只读代码核对所得现状，并非真实基础设施运行结论。

模块依赖为 rag_d → evaluate → Coordinator.search → provider。生产者继续返回现有 SearchResult（chunks、total_found、sources_used、outcome、attempted_providers、failed_providers、error_code）；T03 消费现有数据结构，不反向导入 benchmark，不新增 schema 层。不将等待 T04 的类型导入放进 T03；不复制 T04 的证明、身份、ContractCheck 或 RunRecord。

T03 完成意味着受控回归证明 D1/D2 与 D3 的执行计数/JSON 子集有效；完整 `rag-baseline-report-v1`、目标/指纹/隔离证据绑定与准入修复仍由 T09 完成。本包不能单独放行 G1，更不能放行 G4。

### 精确文件与所有权

| 路径 | T03 权限和职责 | 交接 |
|---|---|---|
| app/agents/retriever.py | 只改 evaluate 及其新增私有评测辅助函数、必要 imports；handle/_do_retrieve_and_emit/_emit_failure 与在线行为不改 | review通过后交T10添加context/日志，不同时写 |
| benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py | 修改validate_assets、run_baseline、_envelope；新增本计划列出的私有metrics/计数函数；to_evaluate_input只补契约校验且四键不变 | review通过后整体交T09；validate_admission及正式schema接入留T09 |
| tests/unit/agents/test_retriever.py | 更新纠偏后的evaluate断言，增加状态/多k/judge矩阵；保留在线handle回归 | 随retriever交T10 |
| tests/eval/test_rag_d.py | 扩充20题fixture、真实Coordinator/evaluate受控贯通、停止和计数测试 | 随rag_d交T09 |
| docs/rag-work/evidence/t03/2026-10-16-t03-verification.md | 实施时新建受控验证记录，含失败/通过命令、实际结果、SHA、限制与交接 | 主控review，非正式baseline报告 |

当前规划任务只写本计划文件。上表是未来实施允许清单；不新增其他业务模块。只读：coordinator.py、app/eval/judge.py、app/eval/component_bench.py、tests/eval/test_component_bench.py、.github/workflows/ci.yml、pyproject.toml、冻结spec/raw/review及相关入口测试。禁止改 provider、embedding、knowledge_ingestion、scripts/rag_ingest.py、T04新文件、在线装配、日志、迁移、正式资产、冻结契约。README由主控集中维护；执行完成将准确变更摘要交主控同步根README，不抢写。

## 第二层：子模块概述

| 子模块 | 接口与输入/输出 | 数据流、状态与错误策略 |
|---|---|---|
| A 结果信封/状态保真 | evaluate(test_case:dict)→dict；统一retriever-evaluation-v1 | 入口校验后一次search；保留来源列表和安全码，先状态后质量；异常只转安全失败结果 |
| B 机械质量 | 私有机械函数接有序正文、去重gold和top_k→机械指标mapping | 前缀派生1/3/5，全文containment，Counter字符multiset Jaccard冗余；不调judge、不重搜 |
| C judge校验 | 私有score函数接原始值/存在标记/范围→value、available、safe_reason | 独立逐项处理；可用0与缺失分开；NaN/Infinity不出现在输出；无效judge保留机械值 |
| D 资产验证 | validate_assets(asset_dir:Path, source_path:Path或null)→既有AssetBundle | 在执行前验证恰20、全verified、唯一ID与原SHA/locator/excerpt关系；任一不合格抛既有AssetValidationError |
| E 执行与完成 | run_baseline保持现有参数→既有dict增加执行子集；_envelope保留现有参数 | 准入后按题集顺序，每题一次evaluate；先记录attempt再校验；首次失败停止；验证ID一一对应和20/0/0 |

不引入持久化状态、共享连接并发或重试。judge不可用是enrichment降级；来源故障是执行失败。T03对现有gate使用受控替身开展核心测试，不将旧gate的弱校验视为正式准入证据。

## 第三层：逐函数详细实施设计

### A. evaluate 与统一结果

保留 `RetrieverAgent.evaluate(self, test_case:dict) -> dict`，消费 query、golden_chunks、golden_answer、top_k；缺省分别沿现有调用兼容，query必须非空字符串，top_k默认5。缺gold允许普通部件调用，正式baseline由资产验证阻止。gold类型破坏或query/top_k不合法在search前拒绝。使用单调计时源测本次search；未检索或无法取得可信search耗时时latency_ms=null，合法查询真实耗时为非负有限数；不得把judge耗时当检索耗时。此为v1.0.1已落盘的勘误约束。

新增私有 `_new_evaluation_result`：输入top_k及安全状态信息，输出拥有下列所有键的初始dict；所有返回出口从该信封填充，禁止各分支手写不同字段。字段固定：schema_version、retrieval_status、error_code、safe_summary、sources_used、attempted_providers、failed_providers、latency_ms、top_k、valid_for_quality、recall_at_k、recall_at_1、recall_at_3、recall_at_5、context_precision_proxy、redundancy、faithfulness、answer_relevancy、context_precision、judge_scores、judge_degraded、degraded、degraded_reason。

schema_version固定retriever-evaluation-v1；来源为字符串list，保持SearchResult的顺序与值，不从chunks反推尝试源；latency为非负有限数或仅未检索/未知耗时情况下的null。judge_scores精确三键，每项精确value/available/safe_reason；不可用值null，不额外塞原异常。三个judge顶层数值与对应value完全一致。

状态映射：ok→ok；健康无chunks→empty；degraded即使有成功chunks仍保留degraded，valid_for_quality=false；failed+invalid_request映射invalid-request，其余failed仍failed。error_code保留合法安全码，未知值不得外传；调用search抛TimeoutError用timeout、其他未知异常安全归类backend_unavailable，不新增异常层或日志。T10才负责更细的provider错误类别与关联日志。本包不得将embedding_failed无依据地猜成db_error覆盖上游合法码。

失败、来源降级、非法请求：所有机械和judge质量值为null，valid_for_quality=false，保留诊断；不调用judge。健康ok/empty：valid_for_quality=true；无gold的相关机械指标null，不用满分或query词重叠冒充gold质量；冗余仍按实际检索正文计算。健康empty有gold：recall系列可评估部分、precision proxy、redundancy为0。top_k<固定k对应字段null，优先于empty零值规则。degraded始终等于judge_degraded或retrieval_status不属于ok/empty；degraded_reason仅安全静态摘要或null。

**v1.0.1已冻结边界**：非法top_k输出null，禁止回显原始bool/字符串；仅query非法而top_k合法则保留合法整数。非法输入不调用search，latency_ms=null，所有来源空、质量null、judge_scores全unavailable、judge_degraded/degraded=true。无gold时recall系列/context_precision_proxy为null，健康redundancy仍从正文计算。已核对原v1与v1.0.1完整差异；当前以新SHA为准，旧冻结SHA仅作历史追溯。

### B. 机械函数

新增私有 `_compute_mechanical_metrics(retrieved_contents:list[str], golden_chunks:list[str], top_k:int) -> dict`，输入均由evaluate校验；函数不IO、不修改输入、不调用search。gold按全文字符串保序去重；正文消费Coordinator已按分数去重的结果，不重新排序、不按集合改变顺序。containment命中为gold包含在某正文或正文包含在gold；分母为去重gold数。

recall_at_k用本次返回前top_k项；recall_at_1/3/5仅在请求top_k达到该k时用对应前缀，返回条数不足仍按已有全部计算，无额外搜索。context_precision_proxy分子为与任一gold有containment的返回正文数，分母为返回数；无返回且有gold为0，无gold为null。redundancy保留现有字符Counter的multiset Jaccard：相似度严格大于0.8为相似对；相似对/全部无序对，少于2条为0。不要为测试人为让Coordinator返回重复正文；重复正文消重仍验证真实Coordinator路径，另用不同但高度相似正文验证冗余。

### C. judge函数与严格JSON

新增私有 `_validate_judge_score(value, *, present:bool, minimum:float, maximum:float) -> dict`；先检查缺失，随后数值类型（拒bool和数值字符串），再有限性，再闭区间；返回缺失missing、类型non_numeric、非有限non_finite、越界out_of_range，合法则available=true/safe_reason=null。此验证顺序保证每项只有一个稳定原因。

新增私有 `_collect_judge_scores(raw_scores或null, *, unavailable:bool) -> dict`，精确产出faithfulness/context_precision的[0,1]，answer_relevancy的[-1,1]；键不存在或结果列表为空记missing，judge未装、无key/同族、无golden_answer、调用异常均unavailable。RAGAS现有_scores_dict兼容接口只在此提取；不要float强制转换字符串或bool。三项独立校验，部分坏分数不能抹掉其他有效分数。judge_degraded为任一available=false；合法0和合法负answer_relevancy不降级。无golden_answer不调用外部judge。

普通evaluate结果与所有runner出口都必须可被json.dumps(..., ensure_ascii=False, allow_nan=False)序列化。验证和转换在产生输出时完成，不以全局“NaN替换成0”掩盖坏数据；原始NaN/Infinity、未知异常文本不得进入结果或failures。RAGAS异常不抛为检索失败，不覆盖context_precision_proxy。

### D. validate_assets 与 adapter

保留既有validate_assets签名与AssetBundle字段。题集先验证list长度恰20；逐题必须mapping、id为去空白后非空字符串且不重复、status=verified_v1，再校验现有question/gold_answer非空字符串、gold_evidence非空、source_locator.page=null及paragraph顺序等于evidence ID、excerpt属于corpus全文、source与corpus_version SHA关系、文件SHA、corpus计数。任何draft/缺ID/空白ID/重复ID不能continue。采用不改变case ID的验证，不静默strip改写业务标识；有首尾空白但非空的ID是否接受沿非空契约，不另加新命名规范。

to_evaluate_input继续返回且仅返回query/golden_chunks/golden_answer/top_k；gold使用corpus全文而非excerpt，保序去重。正式runner固定传5，不通过题目字段覆盖。不会生成产品索引或从benchmark提取新的产品chunk。

### E. runner、metrics边界与计数

新增私有 `_validate_evaluation_metrics(metrics:object) -> bool`，校验schema_version、所有D1必需键、状态/六码/来源list、bool字段类型、非负有限或符合未检索/未知规则的null latency、top_k=5、机械有限[0,1]或null、judge三项范围与value/available/reason一致，以及degraded等价关系。健康ok/empty必须valid_for_quality=true且有正式gold时机械字段可计算；failed/degraded/invalid-request必须false且质量全null。仅取metrics.valid_for_quality的真值不够，bool类型或结构不符同样停止。函数不修补缺键来接受旧格式。

该边界还必须逐项比较顶层 faithfulness/answer_relevancy/context_precision 与各自 judge_scores.value：两边同时 null 或相同的合法数值才一致，不能仅靠 Python 的 bool 与数值相等放行。judge_degraded 必须严格等价于三项中任一 available=false，随后再验证 degraded 等价关系；三项不可用/部分不可用却声明未降级、三项均有效却声明降级、顶层与子项数值不一致均返回 false。不自动纠正矛盾字段，不将生产端正确计算汇总标志当作 runner 可以省略验证的依据。runner 依既定 D2 合成 evaluator_invalid_metrics 失败项，failed 加1并停止，不能输出 completed 或 completed_judge_degraded。

新增私有 `_failed_attempt_metrics`：仅用于evaluate抛异常或返回结构不合法；按同一D1信封合成按原因分类的失败结果、valid_for_quality=false、top_k=5、全质量null，来源未知为空list；不得把非法metrics原对象塞进报告。未检索或无法取得可信search耗时时latency_ms=null，不用0冒充真实耗时；报告安全诊断注明未取得耗时。TimeoutError分类timeout，其他未知执行异常backend_unavailable；非dict/坏schema映射retrieval_status=invalid-request、error_code=invalid_request；异常映射failed，三项judge unavailable、judge_degraded/degraded=true，degraded_reason固定“评测结果不可用”，safe_summary用E1文案。failures记录安全规则ID、题ID和分类码，异常文本不外传；具体失败规则ID采用evaluator_exception/evaluator_invalid_metrics，不扩展六错误码。这些是D2已冻结的内部诊断规则，不是新增公共错误码。

run_baseline保留现有参数顺序、默认值与gate调用；本包不添加T04类型依赖，不改validate_admission。assets/gate阻断直接返回results=[]、expected=20、attempted=valid=failed=0、not_run=20，继续保留原状态。正式报告的schema_version/contract_version/run_id/created_at/backend/target/embedding/attestation/isolation完整绑定留T09，T03局部envelope不能冠名为完整rag-baseline-report-v1，也不能伪造这些字段。

runner先固定准入case_id有序列表；每题在调用evaluate前attempted加1，拿到合法结果或安全合成结果后立即append且只append一次；valid true加valid，否则加failed并停止；not_run=20-attempted。失败尝试保留results项，禁止异常时只保留之前成功题。每次返回满足attempted=valid+failed，results长度=attempted，results ID为准入列表的已执行前缀且无重复；不跳题、不补跑、不根据degraded统计检索失败。

首题DB故障为attempted1/valid0/failed1/not_run19，状态infrastructure_inconclusive；第2题失败为2/1/1/18。未满20、ID错位、计数不符不能completed。只有20/20/0/0且所有judge有效为completed；同计数但任一judge降级为completed_judge_degraded；健康empty/低召回不新增质量阈值。当前模块不计算均值；本包保持如此，交T09的聚合只能选valid结果，故障项不得计为质量0。

## 编号执行步骤：每项独立产物与回归循环

以下命令均从项目根目录执行，使用现有 `.venv/Scripts/python.exe`；执行代理必须先加载karpathy-guidelines。每组按新增测试→先失败→最小实现→通过执行；只有相应新增行为断言失败才是预期红灯，import/setup/权限故障属于阻断，不伪称先失败。命令不安装依赖或调用真实服务。

### 1. 基线与锁定

- [ ] 1.1 只读核对冻结SHA：`Get-FileHash docs/rag-work/specs/2026-10-16-rag-mvp-contracts-v1.md -Algorithm SHA256`。产物：证据记录SHA；期望等于本计划固定值，否则停止并报主控。
- [ ] 1.2 核对写入权：`git status --short`；`git diff -- app/agents/retriever.py benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py`。产物：已有差异摘要；存在他人重叠改动须主控交接后再编辑，不reset。
- [ ] 1.3 仅收集当前用例：`.venv/Scripts/python.exe -m pytest tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py --collect-only -q -p no:cacheprovider`。产物：实际收集数与可用性；期望无收集错误，不调用judge。正式红绿运行前，在允许测试文件中加离线fixture：默认替换app.eval.judge.build_judge为不可用，RAGAS happy-path测试局部覆盖为受控judge；所有Coordinator显式注入fake/受控provider，不受环境rag_backend影响。真实judge/integration标记仍保持不执行。不得只凭测试名字声称不会远端调用。

### 2. 评测信封与故障保真

- [ ] 2.1 在test_retriever增加命名组 `test_evaluate_contract_*`：ok/empty/degraded/failed/failed+invalid_request、直接TimeoutError和普通异常、来源三列表保真、所有分支键一致、bad query、top_k的bool/0/11/字符串、故障不调judge。产物：受控SearchResult/计数spy测试，非法top_k输出null、未检索latency_ms=null。
- [ ] 2.2 红灯：`.venv/Scripts/python.exe -m pytest tests/unit/agents/test_retriever.py -k evaluate_contract -q -p no:cacheprovider`。期望因现有缺schema/status/source/valid字段失败，search spy在非法输入为0，其余至多1。
- [ ] 2.3 最小实现A信封与状态映射，不更改在线方法。产物：evaluate全出口结构一致，错误无原文。
- [ ] 2.4 绿灯：重复2.2命令；期望新增组全通过，失败/降级机械指标全null，empty与故障不同。

### 3. 单次多k与机械proxy

- [ ] 3.1 增加 `test_evaluate_proxy_*`：gold在第1/3/5位，多gold去重、双向containment、top_k=1/2/3/5/10、返回不足请求数、健康empty、无gold null、不同高相似正文冗余、真实Coordinator重复正文去重。产物：每场景明确预期数字与search_calls=1，无gold召回不等于1。
- [ ] 3.2 红灯：`.venv/Scripts/python.exe -m pytest tests/unit/agents/test_retriever.py -k evaluate_proxy -q -p no:cacheprovider`。期望缺recall_at_1/3/5或无gold错误分数导致失败。
- [ ] 3.3 最小实现B，原test_evaluate_context_precision调整到context_precision_proxy；judge context_precision不可再断言为启发式。产物：单次有序前缀派生，不补搜。
- [ ] 3.4 绿灯：重复3.2；期望精确proxy/冗余结果、top_k<k为null、search至多一次。

### 4. judge逐项有效性

- [ ] 4.1 增加 `test_evaluate_judge_contract_*`：三项合法0、边界1、answer_relevancy负数与-1、缺键/空列表、null/bool/字符串、NaN/正负Infinity、越界、部分有效、judge缺包/不可用/抛错/无golden_answer。用受控模块替身，不真实judge；所有结果断言allow_nan=False可序列化。
- [ ] 4.2 红灯：`.venv/Scripts/python.exe -m pytest tests/unit/agents/test_retriever.py -k evaluate_judge_contract -q -p no:cacheprovider`。期望现有缺失填0、NaN不降级或分支字段不齐导致失败。
- [ ] 4.3 最小实现C，并更新既有happy path、bounds、无golden_answer测试预期。产物：每项value/available/reason与顶层一致，机械proxy在judge全部不可用时仍保留。
- [ ] 4.4 绿灯：重复4.2；期望全部通过，合法0/负相关无误降级，NaN不能漏出。

### 5. 恰20唯一verified资产

- [ ] 5.1 在test_rag_d增加 `test_assets_contract_*`：19/21条、20draft、1draft、缺/空/空白ID、重复ID、非mapping题目、缺gold、源SHA/locator/excerpt漂移，并保留完整合法20题全文adapter测试。产物：每项AssetValidationError，runner evaluate_calls=0。
- [ ] 5.2 红灯：`.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py -k assets_contract -q -p no:cacheprovider`。期望draft/重复ID现状被接受而断言失败。
- [ ] 5.3 最小实现D；不编辑真实questions/corpus。产物：全部资产前置验证，不再continue跳draft。
- [ ] 5.4 绿灯：重复5.2；期望所有非法集合阻断，合法集合严格20且四键adapter仍有效。

### 6. runner首次失败与完成计数

- [ ] 6.1 将FakeAgent默认metrics改为完整D1受控结果，增加 `test_runner_contract_*`：20健康含低召回/empty、20健康部分judge不可用、首题/第2题/第20题failed、degraded、invalid-request、evaluate抛错、非dict/缺schema/缺必需字段/计数型bool/NaN、无效输出中带秘密文本、阻断前0执行；每例检查所有计数、结果前缀ID、失败项保留和不重试。
- [ ] 6.1a 在同一 `test_runner_contract_*` 组加入完整 D1 外形的矛盾结果：三项 unavailable 但 judge_degraded/degraded 均 false；仅一项 unavailable 但声称未降级；三项均合法却 judge_degraded=true；顶层值与子项不同或一边 null。其余检索状态/机械分数/类型均合法，防止因缺键提前拒绝而漏测汇总关系。分别在首题与第20题注入，断言合成 evaluator_invalid_metrics、质量全null、首次失败停止、计数分别1/0/1/19与20/19/1/0，均不能 completed。对照组覆盖三项合法0、合法负 answer_relevancy 的 completed，以及20题健康但judge unavailable的 completed_judge_degraded；不调用真实judge。
- [ ] 6.2 红灯：`.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py -k runner_contract -q -p no:cacheprovider`。期望现有无count/忽略valid、漏失败attempt或接受完整但汇总矛盾的metrics导致失败；每个新用例核对真实拒绝原因。
- [ ] 6.3 最小实现E。产物：局部envelope具expected_count/attempted_count/valid_count/failed_count/not_run_count/results/failures，旧报告状态与函数签名保持；不接T04正式准入。
- [ ] 6.4 绿灯：重复6.2；期望首题1/0/1/19、第2题2/1/1/18、第20题20/19/1/0；正常20/20/0/0；judge降级不加failed；results包含失败尝试且严格JSON通过。

### 7. 跨真实组件的受控回归与交接

- [ ] 7.1 在test_rag_d增加 `test_runner_real_evaluator_*`：真实RAGCoordinator+RetrieverAgent，provider受控抛db错误、返回健康空、返回有序结果；gate用显式受控AdmissionResult替身，judge固定可用/不可用。产物：覆盖核验文件§6的异常被Coordinator捕获后不抛至runner路径；不得只用FakeAgent抛错替代。
- [ ] 7.2 红灯在原实现仍在或修补步骤前记录：`.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py -k runner_real_evaluator -q -p no:cacheprovider`。期望原行为会把首题数据库故障误判质量0或judge降级完成；如果已因前面最小实现通过，如实记录“集成回归首次即绿”，禁止人为破坏代码伪造红灯。
- [ ] 7.3 联合绿灯与消费方兼容回归：`.venv/Scripts/python.exe -m pytest tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py tests/eval/test_component_bench.py -q -p no:cacheprovider`。期望离线全通过，既有handle五态/身份/安全错误回归无变化，integration真实judge不执行。test_component_bench.py只读运行，保留其FakeEvaluatable替身；本包不能修改该测试或app/eval/component_bench.py。现有消费方用例主要使用FakeEvaluatable，不能单独证明新接口兼容；代码对None会记录“未返回”并生成失败结果，并不直接比较None。必须在允许写入的tests/unit/agents/test_retriever.py中补充test_evaluate_component_bench_contract_*受控贯通用例：真实ComponentBench.run经agent_map调用真实RetrieverAgent.evaluate，Coordinator/provider/judge用离线替身。无gold场景对recall_at_k设置非空数值期望，断言输出null被保留、返回EvalResult且passed=false、errors包含该指标未返回、不崩溃；检索failed/degraded场景同样要求质量字段null、EvalResult失败且来源/状态仍可检查，不允许expected为空导致假通过。健康完整gold与合法judge分数场景沿旧recall_at_k/faithfulness等数值阈值断言passed=true、metrics保持旧键并携带新状态字段。每例检查evaluate/search最多一次，不能用FakeAgent替代真实evaluate；只跑既有consumer测试不得当作该贯通证据。若暴露消费方错误，不越权修改或弱化断言，报告主控并暂停相关完成声明，由主控决定修复归属。
- [ ] 7.4 静态范围复核：`git diff --check`；`git diff --stat`；`git diff -- app/agents/retriever.py benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py`。期望无空白问题，无在线/Coordinator/T04/gate越界。
- [ ] 7.5 限定lint：`uvx ruff check app/agents/retriever.py benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py`。此命令与当前CI的uvx ruff工具保持一致，仅检查本包四个可写文件；产物为实际退出码及按既有/新增分类的告警清单。实施前以同命令记录原始告警基线，实施后对照；新增告警须在本包允许文件修复，既有告警如超范围或需改变行为则报主控，不把“无新增”说成lint全通过。uvx缺失或ruff需下载时按权限/网络审批规则处理，不自动安装依赖、不将未运行写成通过；不可用则记录阻断及原样手动命令。
- [ ] 7.6 写验证记录与handoff，交主控review并提交根README更新摘要；主控通过后释放T09的rag_d/test_rag_d和T10的retriever/test_retriever。产物：实际命令结果、未执行真实服务说明、变更文件列表、接口/诊断规则/未决事项。无commit/push。

## 验收覆盖矩阵

| 要求/风险 | 覆盖步骤 | 必须观察到的证据 |
|---|---|---|
| R01/R13/核验§6 outcome与来源保真 | 2、6、7 | 真实Coordinator捕获DB异常后首题停止，0有效/1失败/19未跑，来源/六码保留 |
| R15错误分类边界 | 2、7 | 合法上游embedding_failed等原样传递；T10细化分类不越界到T03 |
| 核验§1/DEC-011单次多k | 3 | 第1/3/5排名与固定k一致，一题一个search，top_k<k不补搜 |
| 无gold/重复gold/重复正文 | 3 | 相关无gold值null，gold去重分母，正文沿Coordinator去重，冗余按Counter |
| RV-05/R27 judge有效性 | 4 | 缺失/类型/有限性/范围逐项安全原因；合法0/负相关有效；proxy不被覆盖 |
| runner judge跨字段一致性 | 6.1a～6.4 | 完整外形下汇总误标、反向误标及顶层/子项不一致均安全失败停止；合法0/负相关及健康judge降级对照组正确完成 |
| RV-01/R23完整资产 | 5 | 20draft/部分draft/缺空重复ID阻断，evaluate零次，gold/locator/SHA原校验保留 |
| D2/D3停止与计数 | 6、7 | attempted=valid+failed，not_run=20-attempted，results=attempted且ID唯一前缀；不重试 |
| 零题不可completed/低分不阻断 | 5、6 | blocked为0/0/0/20；20健康低分或empty仍20/20/0/0 |
| 检索/empty/judge降级分离 | 2、4、6 | 来源degraded停止；empty有效；judge缺失可completed_judge_degraded |
| 严格JSON/无敏感异常 | 2、4、6 | 每分支allow_nan=False成功，秘密文本无输出 |
| 兼容与写权 | 1、7 | 四键和函数签名保留，在线handle与只读ComponentBench消费回归通过，null/状态组合受控贯通，无T04模块仍可离线测试 |
| 当前CI限定lint | 7.5 | 四文件uvx ruff实际结果、既有/新增告警分开；下载/工具阻断如实记录 |

## 完成证据、阻断与交接

实施证据唯一入口 `docs/rag-work/evidence/t03/2026-10-16-t03-verification.md`，按步骤记录命令、环境Python/依赖版本、实际退出码/汇总、红灯对应缺口、绿灯摘要、spec SHA和可审阅差异；不复制版权正文、SQL、密钥或伪造正式baseline JSON。若需要保留安全测试输出，写同目录 `pytest-summary.txt`，仅命令与汇总，不保存fixture正文或异常秘密。新增证据文件应在派发时由主控纳入允许清单。

主控复核：所有必需键稳定；SearchResult降级先于空结果判定；机械与judge字段不混用；每题search/evaluate调用计数有断言；失败尝试未丢弃；20个ID与结果前缀对应；来源、空结果、非法请求、judge不可用分别覆盖；T03没有导入T04新模块、伪造证明或修改在线/Coordinator；README摘要已由主控处理。完成后只解锁T09/T10相应写权，G1还需T02/T04/T09/T10共同证据。

T09接收：D1完整metrics、D2资产/执行不变量、D3计数/results/failures子集；负责新增expected/snapshot参数、调用T04共享验证、真实目标与查询指纹绑定、完整rag-baseline-report-v1的必需键/null字段/安全失败及版本标签、alias_unpinned局限。旧gate保留至T09并不代表已准入；本包所有受控结果不用于产品验收。

T10接收：retriever评测分支/私有函数清单与回归结果；只在主控释放后补context、日志关联、错误归类，不改变D1数值/状态语义。T09和T10各拿不同文件，可并行；如需跨改对方测试先串行交接。T12接收完整T09报告后才执行真实书籍20题，T03不占正式baseline目标。

阻断处理：spec SHA漂移、冻结字段冲突、共享文件被其他包持有均报主控，暂停对应写入；继续只读核对或不受影响的测试设计，不擅自修spec。虚拟环境/依赖缺失如实标阻断，不安装未授权依赖、不fallback真实服务；pytest临时目录权限失败与产品行为失败分开。平台同动作第二次阻挡即停，附本计划精确手动命令。实际实现不通过仍归T03修复，不把失败移给T09，不将本计划checkbox提前勾选。
