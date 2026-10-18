# 首批 T02 / T03 / T04 实施调度与主窗口验收

日期：2026-10-16。用户批准实施，明确三个子代理均使用 gpt-6-luna、xhigh。执行分支：codex/rag-mvp-first-wave。初始产品代码无未提交差异；已有规划、spec、README文档差异保留。

冻结契约：rag-mvp-contracts-v1.0.1，SHA-256 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。

## 认领和进展

| 包 | 子代理 | 模型 / 思考强度 | 状态 | 唯一实施证据 |
|---|---|---|---|---|
| T02 | implement_t02 | gpt-6-luna / xhigh | 实施完成、定向复审及最终组合离线回归通过 | [T02记录](t02/2026-10-16-execution.md) |
| T03 | implement_t03 | gpt-6-luna / xhigh | 实施完成、两轮定向复审及最终组合离线回归通过 | [T03记录](t03/2026-10-16-t03-verification.md) |
| T04 | implement_t04 | gpt-6-luna / xhigh | 实施完成、定向复审及最终组合离线回归通过 | [T04记录](t04/2026-10-16-t04-verification.md) |

三包证据已由对应实施代理写入，最终验收以本文末尾主窗口结果为准。

## 派发前接口和文件核对

| 检查对象 | 生产 / 消费与写权 | 判定 |
|---|---|---|
| T02内部 | embedding/provider/ingestion及三测试，设计与验收含index重排和写前拒绝 | 按已批准plan执行，T02独占 |
| T03内部 | evaluate/rag_d及两测试，含judge跨字段不变量与完整20题计数 | 按已批准plan执行，T03独占 |
| T04内部 | 三个新纯模块/三测试，独立离线验收与主控组合回归分离 | 按已批准plan执行，T04独占 |
| T02 ↔ T03 | T03只消费既有Coordinator/SearchResult，不修改provider/embedding/ingestion | 无文件并写，不新增硬依赖 |
| T02 ↔ T04 | IngestResult既有路径/字段保持；T04不依赖T02新PreparedIngestion；摘要用同固定向量 | 无文件并写；T04读取embedding时须考虑T02同时固定dim |
| T03 ↔ T04 | T03不导入T04新模块；正式gate/report留T09 | 无文件并写；跨包旧回归等离线fixture稳定后主控运行 |

Ruling: 保留当前共享工作区及已批准未提交文档，在新功能分支上按明确文件所有权并行实施，不复制尚未提交的spec/plan到其他checkout；不在main上编码。代价是必须审查组合版本、禁止代理切换分支/commit/amend，并由主控集中处理状态文档。

Ruling: 用户明确要求三个Luna实施代理，优先于技能默认模型分级；不擅自提高模型。三个代理不再派生其他代理，主窗口先做逐包规范与代码质量复核；代理完成腾出并发槽后，如需独立审阅再由主控安排。

## 验收边界

- 所有测试先确定离线隔离，禁止真实PG、embedding、LLM和正式摄入。
- 各代理按plan记录红绿循环、退出码、覆盖、lint及限制；平台故障同动作最多重试一次，不sleep。
- 不修改其他模块plan、冻结spec、正式资产或共享conftest；越界需求报主控裁定。
- README、plan状态和全局集成记录由主控单写；无commit/push。
- 本文件的“实施中”不表示测试通过；完成后由主窗口填写实际审阅、组合验证结果及剩余限制，不提前释放G1等后续门。

## 中途检查记录（未做最终验收）

- BASE为 `6324b9442b6f1671ccb4a19cdacb42bb91597187`；无commit/push，最终审阅应包含工作区已跟踪差异与T04新增未跟踪文件，不能只看HEAD提交。
- T02报告已完成embedding批次/索引、provider校验与事务缺陷的受控红灯；摄入两阶段实施仍在进行。初始旧测试embedding 11、provider 27、chunking 17项通过；系统Temp权限错误不能计产品红灯。
- T03报告状态信封10项、多k/proxy9项、judge矩阵14项、资产契约10项分组通过；runner与消费方贯通仍在进行。主控发现旧默认agent的隔离边界不完整，已要求并确认代理补全fake装配和PG零调用断言。
- T04报告contracts21项、identity10项通过，attestation拒绝矩阵在修订。主控增量审阅发现浅拷贝污染固定ROW、模型/版本标签明显秘密形式漏检、草稿无行为占位函数与外层dict边界，均已发回T04定向核验修正；最终关闭以稳定交付代码复查为准。
- 各代理使用既有.venv直接运行pytest，避免uv缓存目录权限问题；pytest改用工作区独占临时目录。主控找到已缓存ruff 0.15.7并通知三代理直接调用，禁止为静态检查自动安装依赖。
- 上述分组数量来自实施代理中途报告，仅用于恢复执行进度；最终结论必须结合本包证据、代码及主窗口组合验证，不以中途消息代替验收。
- 主控在T03 runner草稿中发现并退回：不可hash的状态/错误码/reason可能使验证器在evaluate异常保护之外抛错；非健康检索携带三项available judge值可能漏过null约束；asset异常出口仍复制str(exc)。要求补最小拒绝用例、安全合成失败项和无原文的asset阻断出口，最终关闭待稳定代码/证据复核。
- Ruling: 正式question/gold_answer的非空校验按strip后非空解释，保留原文本不改写；空白项应asset_invalid且evaluate零次，不能先准入再产生非法query尝试。该修复只涉及T03已认领validator和测试，不扩展schema。

## T04 首次稳定交付与独立审阅

- implement_t04首次交付：193 passed、限定六文件ruff通过；主控将六个新增实现/测试文件制作完整工作区diff包（BASE无提交，须含untracked文件），交只读review_t04_impl（gpt-6-luna / xhigh）检查规范与质量。
- 独立审阅两个不通过结论：P1，build/validate接受pdf或未知处理版本，违反B1表中epub及冻结处理协议；P1，encoding_format只校验非空，可让明显凭证文本进入Identity/repr/JSON/证明。主控已读取spec表和对应代码/测试，确认成立，退回原实施代理修复；193项通过不能覆盖这两项正确性缺口。
- Ruling: source_format及协议/normalizer/version必须同时服从冻结支持值与原preparation，不能以“无独立Expectation字段”豁免固定值检查。import_namespace无固定值，仍从可信preparation透传，不新增expected字段、不修改spec。
- 审阅另报P2潜在asdict(binding)导出endpoint风险，但明确未发现调用点。主控判断当前无实际泄露路径：Identity导出只接收Identity，Binding不应被通用序列化。记录消费方约束，不为假设路径重构纯类型；可公开序列化Identity，禁止通用序列化含内存端点的Binding。
- 修复轮次：T04 round 1，实施中；待两个成立问题定向复审后才可关闭。
- Round 1结果：T04先新增用例观察197 passed / 15 failed，修复后212 passed、限定ruff通过；review_t04_impl定向复审确认原两个P1均关闭，无新实现阻断。复审提出非阻断测试独立性补充：显式float/base64与service_default指纹应互异；主控采纳，只补现有identity测试及定向验证，不改产品逻辑，最终组合回归覆盖。

## T02 执行分段调整

20:04（本地时间），任务3测试文件自19:49后约14分钟无变化，未见pytest/uv进程、ingestion产品文件仍未改动，两次主控进度消息未收到答复。主控中断该过长工作段并由同一implement_t02、相同Luna/xhigh续做，要求先报告/落盘已完成组，再按准备类型与helper、prepare_file、ingest_prepared/兼容入口分小步执行。没有认定发生产品故障，也未撤销任何代码、重派或变更模型。

## T03 首次稳定交付与独立审阅

- 实施证据首次稳定联合结果152 passed / 1 deselected、四文件ruff通过；主控提供完整四文件diff给review_t03_impl（Luna/xhigh），不重复测试，以规范和质量两个维度审阅。
- 复核成立并交round 1：empty信封可带非零机械分；failed可错误搭配invalid_request；被引用的空白gold和空excerpt可让containment虚假命中；原样带出corpus_isolation可引入NaN/秘密；D2固定合成失败原因不被自身D1验证器接受。
- Ruling: gold修复只约束被引用全文与excerpt，未引用空corpus行不因本次修复增加新拒绝规则；正常文本不改写。报告隔离对象只投影既有公开mode/verified，未知字段不外传，已知字段非法类型在执行前安全阻断；不修改正式gate，真实证明和资源绑定仍留T09。
- 所有修复限T03原文件，要求定向红绿、限定联合/ruff及复审，不修改其他模块plan或共享spec。

## T02 首次独立审阅

- review_t02_impl（Luna/xhigh）读取六文件完整diff后，认为核心实现基本符合、代码质量整体清晰，未发现P1；唯一P2是直接构造的非法PreparedIngestion可先to_intent_metadata导出，不受ingest_prepared写前验证保护。
- 主控确认该数据流缺口成立：T08先持久化intent再调用ingest，导出边界不能只校验warnings。退回round 1，要求导出前复用已有完整快照校验，补owner/schema/policy/摘要拒绝与合法导出对照，不新增公共接口、不读取源文件。
- 先前增量发现的bool/int清单相等绕过与不安全warnings，实施代理已报告7项红灯、18项定向绿灯及ingestion全文件62项通过；主控已读取修订后的严格owner、双向实际摘要/规范字节比较和warnings共用验证逻辑。
- Round 1结果：导出前复用完整_validate_prepared后，定向6 passed / 61 deselected；review_t02_impl确认原P2关闭、无本次修复新增风险。T02最终四文件组合158 passed。原六文件ruff命令退出1，唯一为已用git show HEAD确认存在的test_pgvector_provider.py E402（现行667行），未掩盖为原命令全过、未顺手修无关基线。真实PG/远端SDK未执行；保留独占临时目录不阻塞交付。

## 用户要求继续后的恢复

用户再次明确“继续子代理的工作”。21:11（Asia/Shanghai）主控检查发现T03上轮因usage limit失败，错误提示21:10可重试；使用时钟核实已过提示时间后，恢复同一implement_t03、同一Luna/xhigh，不新建代理或换模型绕过额度。额度查询工具未能读取当前账户限制，不能据此声称剩余额度已恢复。

T03已确认此前可选临时目录清理命令中断/超时。主控要求所有清理立即让位于产品修订，残留专属临时目录可保留。T02同样因长工作段无响应被中断并恢复原代理，要求优先唯一导出P2；两包均不撤销已有差异、不重做已通过组。恢复后验收仍须按实际红绿与定向复审，不能把恢复派发视作实现完成。

## 主窗口组合验证（Round 1 快照）

T03 round 1稳定交付后，主窗口在三包共同工作区运行以下全新组合（独占临时目录此前不存在，不复用待清理目录）：

```text
.venv/Scripts/python.exe -m pytest tests/unit/harness/test_knowledge_ingestion.py tests/unit/harness/test_chunking_service.py tests/unit/infrastructure/test_pgvector_provider.py tests/unit/infrastructure/test_embedding.py tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py tests/eval/test_component_bench.py tests/unit/infrastructure/test_rag_contracts.py tests/unit/infrastructure/test_embedding_identity.py tests/unit/harness/test_ingestion_attestation.py -q -p no:cacheprovider --basetemp .pytest-tmp-root-firstwave-20261016-r1
```

实际退出码0，**542 passed, 1 deselected in 14.70s**。覆盖T02四文件158项、T03三文件171项和T04三文件213项；T04原计划的兼容回归由该组合补齐。受控provider/SDK/judge与内存SQLite边界保持，不连接真实PG或远端服务。

缓存Ruff 0.15.7对三包16个变更实现/测试文件执行`check --no-cache`，退出码1，唯一诊断为`tests/unit/infrastructure/test_pgvector_provider.py:667`的既有E402；该导入已核对HEAD原有内容，无新增诊断，不宣称lint全通过。`git diff --check`退出码0。

当前契约及原始归档SHA分别仍为`31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`和`64e1f13d58adc2c30685284f2e221584951b974416609637d6ee46192e133cc0`。HEAD仍为`6324b9442b6f1671ccb4a19cdacb42bb91597187`，分支仍为`codex/rag-mvp-first-wave`，无commit/push。只发生三包声明范围内的产品变更和主控文档更新。

各包及主窗口的专属测试临时目录保留，避免可选清理阻塞交付；它们不是正式资产或摄入证明，不应整体暂存。组合测试不代表G1～G6、真实PG事务、正式摄入、20题真实质量基线或在线双入口验收通过。后续工作仍须独立plan和既定放行门。

## T03 Round 1关闭与Round 2

review_t03_impl确认原五项问题及run ID/隔离类型前置边界均已关闭。主控核对后接受两个相邻残余P2：普通evaluate仍接受空白gold列表项，导致空字符串containment假命中；D2验证器仍接受empty且sources_used非空，与Coordinator仅在有返回块时记来源的行为矛盾。已交同一实施者作第二轮最小修复：空列表仍允许普通无gold评测，非空列表项必须有非空白正文；正式empty来源必须为空。后续重跑限定及组合回归，不能把542项的Round 1结果当最终Round 2结果。

Ruling: run_baseline在旧gate前做非法类型阻断是明确设计裁定，可能先返回blocked:unattested_product_index；不为同时存在的无效backend恢复旧优先次序，不修改validate_admission。完整正式准入仍归T09。

## Round 2 最终组合验证

T03补充拒绝空白gold列表项及empty非空来源后，主窗口再次执行上方相同十文件命令，仅将独占临时目录改为`.pytest-tmp-root-firstwave-20261016-r2`。实际退出码0，**547 passed, 1 deselected in 15.16s**，替代Round 1的542项作为最终组合结果。T02贡献158项、T03贡献176项、T04贡献213项。16文件Ruff再次退出1，仍只有既有E402，无新增诊断。


## 最终交接

review_t03_impl对Round 2两项定向核验均判定关闭，未发现本次修改直接导致的回归。T02/T03/T04均已完成各自批准范围的实现、定向复审与主窗口组合离线验收；本批无未关闭的已接受审阅问题。README、工作区说明、三包计划状态、索引与主清单已同步；原计划步骤保留作设计追溯，实际红绿、命令替代和限制以执行证据为准。

释放本批实现文件供后续计划认领：T08可消费T02/T04接口，T09可消费T03/T04接口，T10可准备日志审计；共享provider/retriever等文件须重新由主控分配写权，不自动并写。T01真实环境/资产盘点、T05迁移守卫、T06在线离线核心以及其余后续包尚未由本批完成，G1～G6保持未通过。下一批先按已确认DAG编制独立三层plan，再进入实施。

## 用户验收与提交授权

2026-10-16，用户明确确认本批验收，授权更新TodoList并提交当前更新。提交范围包括T02/T03/T04实现与测试、T00冻结契约、已审阅规划/raw材料及执行证据；测试临时目录和临时review差异包不纳入提交。提交说明列明具体功能、验证结果、既有E402及未执行真实环境范围。此前“无commit/push”描述为实施时历史状态；本次新增授权仅执行本地commit，不push。

提交前主窗口再次运行同一十文件组合，独占临时目录`.pytest-tmp-root-precommit-20261016`：547 passed、1 deselected，15.77s，退出0。
