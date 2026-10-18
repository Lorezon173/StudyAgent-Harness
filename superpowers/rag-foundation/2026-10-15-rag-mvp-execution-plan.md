# RAG MVP 修订执行方案（已确认，待实施）

日期：2026-10-15。修订源：2026-10-13 总规划、子代理 review、主会话针对性核验，以及既有交接/spec/DEC。本文优先于旧总规划中的执行排序；原 Phase 和全局 BLK 编号不变。S0～S6 是本轮执行顺序，R01～R27 是本文件的问题索引，不替换全局 blocker 编号。

本次补修依据 [2026-10-15 执行方案 review](2026-10-15-rag-mvp-execution-plan-review.md)，RV-01～RV-05 均已纳入任务、详细契约及验收设计，见文末追溯表。这里的“纳入”仅表示规划修补，不表示代码缺陷已修复或 review 中受控复现由本轮重新执行。

用户于 2026-10-16 确认本执行方案。批准范围为本文的 MVP、修订边界和实施方向，尚未实施，不表示代码问题已修复。S0 将已确认设计细化为一致的接口/spec 与责任记录，不重复索取同一方案批准；超出已确认范围的变更另行处理。本文仍为文字规划，不提供实现代码。依赖与最大并发见 [DAG 与调度规划](2026-10-16-rag-mvp-dag-and-scheduling.md)。用户本轮要求先产出 DAG，未在本轮启动编码。

后续T00增量：[共享契约v1](../../docs/rag-work/specs/2026-10-16-rag-mvp-contracts-v1.md)已在用户明确启动后完成归档、独立审阅与冻结，[记录](2026-10-16-t00-contract-freeze-record.md)。下面S0清单保留阶段范围，不据此把环境盘点或各任务plan标成完成；跨任务新增接口以正式共享spec为准。

## 事实基线与依据

- [原三层规划与 Phase 进展](2026-10-13-progress-and-todolist.md)。
- [子代理审阅](2026-10-13-plan-review.md)、[针对性核验](2026-10-13-review-verification.md)。
- 总交接：`remain-work/2026-09-02-RAG进展提交与工作区现状-主控handoff.md`；A 交接：`remain-work/2026-08-27-RAG-A-EPUB提取器验收与Phase4接续-主控handoff.md`。
- 主清单与 DEC：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`、`2026-07-27-rag-p0-confirmed-decisions.md`。
- 设计来源：`docs/rag-work/specs/2026-07-24-{epub-extractor,project-chunking-service,online-rag-p0-repair}-spec.md`；实施证据为四条线状态顶部与实际实施回报，不使用旧快照推断当前能力。
- A 提取器、B 切块/摄入、C 权限/故障/在线环境校验、D 只读工具已实现；B3 修复有主控复核。新发现的写入计数边界、评测状态、gate 和审计缺口不能被旧验收覆盖。
- 2026-10-13 定向测试 99 passed / 1 skipped / 1 deselected；同日受控复现确认本文列明的缺口。2026-10-15 仅文档复核，未重跑测试。真实 PG/embedding/正式 baseline 尚无完成证据。

## 第一层：MVP 模块总览

### MVP 的可交付结果

一部真实 EPUB 通过产品提取、切块、真实 embedding 和 pgvector 建立可审计索引；同一产品检索链运行 20 道黄金题并准确报告故障与机械指标；普通聊天和 SSE 的 Tutor 真正消费当前回合、当前用户有权限的证据。失败时说明检索不可用，不伪装为有证据教学或可用基线。

MVP 采用现有 Python/FastAPI、五 Agent 事件协作环、SQLAlchemy/Alembic、PostgreSQL/pgvector 与现有 embedding。保留 Retriever→Coordinator→PgVector→Orchestrator→Tutor 主链。不新增回答器、数据库表或上传 API，不改变四层依赖，不重构所有 provider。

范围：单书、单 vector 来源、global/private、一次检索尝试、append-only。首本书正式索引优先用 global；private 与歧义数据在独立权限测试资源中验证，不能牺牲既有隔离要求。产品稳定 ID 不等于幂等；文件级 locator 不伪称章节/页码定位；指标维持 containment proxy，不承诺严格 identity recall 或教学效果。

### 为什么调整排序

旧方案把不少问题放入真实验收或后续复核。现在已经证明“失败被标完成”“少写却报成功”“无效证明被接纳”等边界，应先让写入与评测可信，再运行正式数据。推荐串行顺序：**S0 最小契约 → S1 可信性修复 → S2 真实环境 → S3 正式摄入 → S4 检索基线 → S5 在线证据消费 → S6 MVP 联合验收**。

S4 在 S5 前是减少定位变量的执行选择，不新增技术依赖；多人工作时 S5 可在相关契约确认后独立实现，但最终联合验收必须具备 S3/S4 的真实证据。环境/资产可用性在 S0 即只读检查，避免等到 S2 才发现资源缺失。

## 问题账本与优先级

以下优先级为本轮建议：P0 阻止成功/安全/质量结论可信；P1 为跑通和验收 MVP 的必要工作；P2 为后续增强。P1 不是可以跳过的可选项。顺序由依赖决定，不等于逐行优先级排序。范围限已读 RAG 材料和核验结果，不宣称穷尽全仓潜在缺陷。

| ID | 问题与当前证据 | 优先级 | 安排与关闭条件 |
|---|---|---|---|
| R01 | Coordinator 故障 outcome 被 evaluate 丢弃；20 次数据库失败可报告 judge 降级完成（已复现） | P0 | S1：检索失败保真，基础设施失败不进入有效质量均值，不标完成 |
| R02 | provider 接受短 embedding 列表后 zip 截断，2 文档写 1 行却确认 2（条件性复现） | P0 | S1：数量/维度契约与实际写入确认；默认服务不足时写库前报错的边界保持准确 |
| R03 | attestation 无生产 runner；gate 接受空 run ID/版本、None 计数、非法 scope-owner（已核验） | P0 | S0 定契约，S1 强消费校验，S3 产品生成并实际核对 |
| R04 | 隔离只接受 mode/verified 声明；无 corpus/doc 查询过滤；权限样本可能污染书籍基线 | P0 | S0 选隔离方案；S2/S3 双资源与真实产物清单；无证据不准入 |
| R05 | 检索已有，但默认请求、路由与 Tutor 尚无完整证据消费链（BLK-003/005） | P0 | S5：三路径保真、屏障、当前轮 prompt 证据、最多一次最终动作 |
| R06 | C §F/§G 采用值待追认，§H 上限/citation 仍候选 | P1 | S0 最小决策表；S5 只能按批准值实现 |
| R07 | I-01：provider fixture 手工建表，与正式迁移分叉（BLK-008） | P1 | S2：PG/SQLite fixture 消费正式 schema；不再依赖漂移建表 |
| R08 | 真实 PG、扩展、连接、embedding 及 2048 维一致性未实测 | P1 | S0 盘点资源，S2 实际探测并保存无密钥证据；不可用则阻断相关验收 |
| R09 | 真实 run 中途写入失败整体 rollback 未验证；SQLite 已通过 | P1 | S2 独立 PG 对抗：无本轮残留；不重写已存在的事务逻辑 |
| R10 | 首本书正式摄入、数量/ID/locator 往返与证明尚未完成（BLK-002/004/007） | P1 | S3：真实产品主链、输入 SHA 和输出产物对应 |
| R11 | 真实 EPUB 兼容/内容完整性未验证；li/blockquote/pre 有已知边界 | P1 | S3：检查本书关键内容；确实影响 MVP 时再规划最小兼容修复 |
| R12 | 仅单个 recall_at_k，无法输出同次 Recall@1/3/5 | P1 | S1：单次 top-5 前缀派生，兼容旧指标，各返回分支一致 |
| R13 | 基线缺 outcome/来源/分类失败及 backend/目标证明关联，judge 降级与检索故障混淆 | P1 | S1 定报告字段；S4 实际报告，20 题各至多一次，无隐式重试 |
| R14 | 内部异常无 retrieval_id；歧义行过滤但无无正文审计 | P1 | S1 日志契约/错误边界，S5 关联贯通；S6 核验日志与事件 |
| R15 | embedding_failed 有码位但 provider 异常未准确分类 | P1 | S1 只细分已批准错误类别，未知异常安全归类，保留内部根因 |
| R16 | corpus/EPUB 本地版权资产是否齐全及 hash 权威尚需核对 | P1 | S0 可用性检查，S3/S4 现有 validator 校验；新增 corpus digest 契约需确认 |
| R17 | 全局/私有及歧义行真实 PG 隔离、在线两用户/多轮隔离待验证 | P1 | S2 Provider 对抗，S5/S6 在线对抗；无权限正文不进入生成 |
| R18 | 20 题真实产品 baseline 与异常题人工复核未运行 | P1 | S4：raw metrics、报告、零召回/高冗余/混源检查 |
| R19 | 普通 chat/SSE 共享因果链及在线端到端未验收 | P1 | S5/S6：同核心链路、受控降级、证据消费和不串轮 |
| R20 | 主清单旧勾选、README/入口滞后、状态历史残留、B/C/D 交接欠缺、链接问题 | P1 | S0 最小事实表；各阶段同步文档，不等全量文档美容才动工 |
| R21 | 旧交接 lint 344 项不是当前基线，CI 当前状态未知 | P1 | S0/S1 记录现状，阶段结束跑必要检查；实际阻断再最小修复，不全仓无关清理 |
| R22 | shared/course、幂等/替换/删除、strict identity recall、教学阈值/DeepEval、图检索、泛化 EPUB/上传防护 | P2 | 后续单独规划；本 MVP 不做上传，ZIP bomb 未实现不是既有 extractor 验收失败 |
| R23 | validator/runner 跳过未验证题，无完成数量约束，可出现零调用 completed（RV-01 受控复现） | P1 | S1/S4：20 个唯一非空 ID、全部 verified_v1/gold 合法；有效=20/失败=0/未跑=0 才能放行 |
| R24 | 摄入与查询未绑定 embedding 身份，同维度模型切换无法发现（RV-02 条件风险） | P1 | S0 定指纹，S3 证明记录，S4/S6 比较实际查询配置，不匹配阻断 |
| R25 | Alembic env.py 覆盖 URL，fixture 的 TEST_PG_URL 未必被迁移消费（RV-03 代码事实） | P1 | S0 定注入路径，S2 在任何 DDL/清理前校验实际目标；A/B 对抗只允许测试 B 变化 |
| R26 | 提交后证明未落盘缺计划清单和前态，无法唯一恢复（RV-04 条件风险） | P1 | S3：写库前持久化产品计划/空库前态；只读核验完整产物后补证，不唯一则阻断 |
| R27 | judge 分数可缺失或非有限却不降级（RV-05 NaN 受控复现） | P1 | S1/S4：逐指标校验、不可用用 null 和原因、机械指标保留；JSON 禁止 NaN/Infinity |

这些问题对应既有 BLK-001～013：已验证的 A/B/C 部分继续复用；BLK-011/012/013 的后置边界不因本计划缩小 MVP 而自动解锁。

## 第二层：阶段 Todo、进展与放行门

### S0：最小契约与问题归档（原 Phase 0）

**基线/已完成**：共享 DEC 已冻结；review 已逐项核验；有原三层总规划，A 提取器等无需重做。

**职责与接口**：输入冻结决策、代码、核验报告；输出本轮可执行决策表、资源清单、执行包和问题映射，不写运行状态为 verified。

- [ ] S0-01 将 R01～R27 映射到原 BLK、任务、执行责任及验收材料位置，逐项区分缺陷/待实现/环境未知/后置。
- [ ] S0-02 确认 C §F/§G 与 §H 投影/citation 候选；候选 5 块、单块 2000、总计 6000 字符、5 引用不自动冻结。
- [ ] S0-03 确认 E1～E4 的报告、证明、隔离及错误契约；批准后再更新对应 spec，注明本 raw 文件与原 DEC 来源。
- [ ] S0-04 只读盘点 PG/embedding/本地书籍与 corpus 可用性，不打印密钥；记录当前测试/CI 条件。
- [ ] S0-05 修正立即影响派工的状态/链接，补交接安排；非阻断历史格式清理随阶段完成。
- [ ] S0-06 确认无密钥 embedding 配置指纹、模型/部署及参数绑定规则；确认 Alembic 使用 fixture 已预检连接的唯一注入路径，禁止测试迁移静默回退 settings。
- [ ] S0-07 确认完整 20 题放行不变量、逐指标 judge 有效性规则、产品预计划接口及提交后只读恢复契约，不把失败尝试报告视为取得基线。

**门 G0**：执行包范围和候选字段经用户确认；环境缺口有明确记录。不以文档数量代替确认，也不在这一步启动业务编码。

### S1：修复可信性底座（原 Phase 2 + D 工具补修）

**基线/已完成**：正常写入、权限过滤、五态 SearchResult、部分安全日志、单 k 评测与 runner 已存在；99 项定向测试为既有证据，不覆盖新增复现。

**职责与接口**：输入 docs/embeddings/SearchResult/证明；输出可信写入确认、带 outcome 的评测结果、严格 gate、单次多 k 与安全诊断。

- [ ] S1-01 对 provider embedding 数量、维度作边界验证，修复虚假成功计数，补服务贯通回归；不先重构整个 embedding 模块。
- [ ] S1-02 evaluate 保留检索 outcome、分类码、来源与检索耗时；runner 区分成功空结果、基础设施失败、部分来源失败及 judge 降级。
- [ ] S1-03 补齐版本化证明消费校验，拒绝空 ID/版本、bool/None/负计数及错误 owner；隔离声明需绑定实际目标和可核验产物证据。
- [ ] S1-04 从单次 top-5 派生 Recall@1/3/5，旧 recall_at_k 保留；mechanical context-precision proxy 不被 RAGAS 同名值覆盖。
- [ ] S1-05 日志关联与歧义行审计设计落地；在线尚无 seed 时先用带 ID 请求测试，S5 再接真实生成路径。补已有错误类别的准确映射，不新建全套错误系统。
- [ ] S1-06 将复现变成必要回归，跑相关测试和检查；记录结果及已知 CI 阻断。
- [ ] S1-07 强化正式题集 validator 与完成计数断言：恰有 20 个唯一非空题 ID，全部 verified_v1 且 gold 合法；全 draft、部分未验证、重复/空 ID 均不得进入正式评测。
- [ ] S1-08 对 judge 每项分数校验存在性、数值类型、有限性与已确认范围；部分缺失、NaN、Infinity 均标记相应 enrichment 不可用并降级；报告输出严格 JSON，不以 0 代替缺失分数。

**门 G1**：两文档一 embedding 不可能成功；数据库失败或零题执行不标 completed/completed_judge_degraded；无效证明/未完整验证题集不能准入；两种排名输出不同 Recall@1；无效 judge 分数不伪装有效值且 JSON 无非有限值；日志可关联且无正文/密钥泄露。全量测试通过不替代这些行为断言。

### S2：正式 schema 与真实环境（原 I-01/F-01）

**基线/已完成**：SQLite 正式 7 步迁移及回程已有验证，PG 待实测，provider fixture 仍分叉。

- [ ] S2-01 fixture 复用正式迁移/schema；由显式测试配置打开并预检实际连接，经 Alembic connection 属性传入 env.py 的独立分支。测试路径缺失注入即失败，不允许 settings URL 回退；DDL/清理前核对数据库/schema/资源标识，确保测试目标不同于业务/基线目标。
- [ ] S2-02 从干净测试 PG 跑正式迁移，核对扩展、字段、实际 provider/dialect、embedding 维度与当前表一致，并记录实际 embedding 配置/指纹而非只读维度。
- [ ] S2-03 测试 PG 中途写入失败 rollback、正常写入实数、doc/chunk/locator 往返。
- [ ] S2-04 在权限测试库执行两用户、公共、私有、歧义及排序前过滤对抗；产出可追溯证据。
- [ ] S2-05 新增 settings 指向 A、fixture 指向 B 的对抗用例；迁移与清理只允许 B 发生变化，A 不执行 DDL/DML。错误库/schema、缺少资源标识或连接注入均在变更前拒绝。

**门 G2**：迁移目标传递与变更前预检成立，真实 PG 迁移/embedding/事务/过滤通过；不可用标基础设施未确认，禁止 fake 代验。环境受阻时可继续不依赖真实库的 S5 实现与测试，但不得勾选真实里程碑。

### S3：正式摄入与产品证明（原 F-02～F-06）

**基线/已完成**：Extractor、ChunkingService、KnowledgeIngestionService 已有；完整证明生成与首本书真实兼容尚未验收。

- [ ] S3-01 真实 EPUB hash/内容检查；固定 namespace、normalizer、chunk policy 版本，不擅自调参。
- [ ] S3-02 通过产品 service 准备计划，写库前持久化无正文运行意图、计划清单、目标为空的前态及 embedding 指纹；本目标独占且未决 run 不允许另一摄入。随后同一准备结果写入一次，从实际库核对数量和完整产物，不靠 docs 长度推断。
- [ ] S3-03 输出成功证明或非成功运行记录；校验库目标、版本、scope/owner、输入 SHA 和实际 embedding 指纹，一致后才放行。
- [ ] S3-04 检索回读身份、正文和实际 locator；记录纯文本路径的定位限制。
- [ ] S3-05 保存隔离证据并验证 gate 消费；提交后证明未落盘时，以预先落盘的意图/计划/空库前态执行只读恢复；完整数量、多重身份、内容摘要、scope/owner 及目标/配置全部吻合才补写证明，不再次 index。无意图、非空前态、并发写入或不一致时保持未准入并交人工处置。
- [ ] S3-06 覆盖提交成功后、证明落盘前退出的恢复验收；覆盖无清单、重复行、部分行、错目标和模型指纹不符时不能补证或自动重导。

**门 G3**：真实索引与成功 JSON 证明及 embedding 指纹一致；预意图/计划和提交后恢复路径可验证；基线资源没有权限对抗样本或其他书产物；append-only 边界明确。目标文件缺失/解析空串/写入未确认或恢复不唯一均不能产生成功证明。

### S4：20 题真实检索基线（原 Phase 5）

**基线/已完成**：20 题资产和只读工具存在，正式分数未产出；需消费 S1 修复与 S3 证明。

- [ ] S4-01 正式题集恰有 20 个非空唯一题 ID、全部 verified_v1 且 gold 校验通过；validator 与六项 gate 全绿，provider 集合严格 vector-only；运行前比较实际目标、清单和查询 embedding 指纹，无漂移才开始。
- [ ] S4-02 每题 evaluate/检索至多一次，单次 top-5 派生多 k，保存题 ID、指标、耗时、来源与安全状态。
- [ ] S4-03 真正检索基础设施失败时保留已运行结果，报告 inconclusive/未跑数，不重试或当零召回平均；成功 empty 可记有效零召回。
- [ ] S4-04 judge 不可用、部分缺失/无效分数仅影响对应 enrichment；无效项写 null 与安全原因，不能填有效 0，健康检索机械指标保留，完整 20 题健康执行时才可标 completed_judge_degraded。
- [ ] S4-05 人工复核零召回、高冗余和混源迹象，区分 proxy 局限、内容缺失与检索问题；写首次基线报告。

**门 G4**：正式题集 20 题全部有效执行，且有效题数=20、失败数=0、未跑数=0，题 ID 与已准入集合一一对应，检索配置与成功证明一致，才能以 completed 或 completed_judge_degraded 放行；低召回仍是有效执行，不新增质量阈值。inconclusive、blocked、零调用或部分完成只保留尝试记录，不能放行 G4/G6。报告可审计且为严格 JSON。不能以“分数不高”直接修改策略重跑并挑选最好结果；修复后另编号重跑，不覆盖首次结果。

### S5：在线检索证据进入 Tutor（原 C-12～C-17）

**基线/已完成**：两个入口已有真实后端 fail-fast；证据仍未完成在线消费。

- [ ] S5-01 认证上下文创建完整 vector-only 检索种子；取消无证据最终 Tutor 抢跑；保真 seed/rule/conductor。
- [ ] S5-02 Orchestrator 管理 retrieval_id 状态与屏障；关联 Critic 观察，缺质量观察可继续，重复事件不重复发最终动作。
- [ ] S5-03 按确认的 §H 投影，将当前轮正文/来源/状态注入 Tutor；证据是数据，不允许替代控制身份或动作契约。
- [ ] S5-04 覆盖五态、低质量与未授权情形的受控回复；不静默回退 fake 或空回复。
- [ ] S5-05 sentinel、两连续请求、迟到质量/重复 Tick、跨用户和引用截断验证；普通/SSE 共用核心路径。

**门 G5**：当前问题→检索→受控证据→Tutor 输入的实际关联成立；每个 retrieval 最多一个最终 Tutor 动作；无权限/上轮正文不进入当前生成，全部相关日志能追踪。

### S6：MVP 联合验收与交接（原 Phase 6）

**基线/已完成**：验收设计已有，真实联合证据尚无。

- [ ] S6-01 使用同一受证明本书索引验证真实普通/SSE 入口，核对本轮实际查询 embedding 配置指纹与摄入证明一致，检查正文与来源实际消费；同维度但模型/部署/参数不同也拒绝旧索引。
- [ ] S6-02 真实两用户、多轮与失败路径；区分召回、投影、生成和基础设施失败。
- [ ] S6-03 运行相关回归及必要 CI，核对本轮引入问题；更新 README、主清单、交接，状态文件由对应唯一写者回写。
- [ ] S6-04 保存本轮证明、基线和验收证据索引，列明 proxy、文件级 locator、append-only 及未定教学质量阈值。

**门 G6（MVP 完成）**：G1～G5 均有实证，其中 G4 必须是同一受证明索引/配置上的完整 20 题有效基线，不接受失败尝试代替；真实双入口及安全/故障验证通过，文档一致。可声称“单书真实 RAG 教学链路可用并有基线”，不能声称已证明教学效果或达到未定义质量阈值。

## 第三层：子模块详细实施设计

以下新增名称、字段和路径为已确认方案的设计约定，具体接口在 S0 按职责固定，不假称当前已经存在。保持单一职责，不在执行中临时创造另一套回答器/评测器。

### E1：写入确认与原子性（S1/S2，B 责任边界）

落点：`app/infrastructure/rag/embedding.py`、`pgvector_provider.py`、`app/harness/knowledge_ingestion.py`；针对对应 unit/integration 测试。

复用 embed_many、provider.index、ingest_file。新增私有批次校验职责：输入 docs、向量列表及配置维度；输出有效批次或明确失败；要求向量数量严格等于文档数量、维度一致，非法值不进入写入。写入确认只在全部计划 insert 成功且 commit 成功后生成，不允许 zip 静默截短。

状态：planned_count 来自合法切块，written_count 来自已确认事务写入，失败不返回成功；provider 缺失/未确认仍维持 IngestResult 非成功。已有 rollback 保留，新增真实 PG 故障注入证明；不把 API 回包不足的 IndexError 本身当成已发生部分提交。

数据结构：现有 ChunkDocument/metadata 与 IngestResult 尽量不变；计数非负整数且拒绝 bool。验证零文档、短/长向量列表、错误维度、第二条写入失败、commit 失败及服务贯通；PG 验证使用明确隔离测试资源。

### E2：评测指标与故障报告（S1/S4，D 与 Retriever 接口）

落点：`app/agents/retriever.py`、`benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py`；对应 agent/eval 测试。

evaluate 保留四键输入兼容，内部仍只搜索一次；增加结果归一职责，消费 SearchResult 的 chunks/outcome/error_code/sources_used/attempted/failed providers。新增机械指标职责从同一有序 top-5 计算三个前缀召回、precision proxy、redundancy；保留旧 recall_at_k，新增 recall_at_1/3/5 与 context_precision_proxy，既有 RAGAS context_precision 继续作为 enrichment，不覆盖新 proxy 字段。

候选结果字段：retrieval_status、error_code、安全摘要、sources_used、attempted_providers、failed_providers、latency_ms、机械指标、judge_degraded/安全原因。保留旧 degraded 字段作兼容，但 runner 不再仅凭它分类。日志完整根因只进内部，报告不复制异常连接信息。

正式题集验证职责扩展：恰有 20 条记录，每条题 ID 是非空且唯一的字符串，状态全部 verified_v1；question、gold_answer、gold_evidence、locator、excerpt 等继续通过既有校验。未验证题不能静默跳过而将剩余子集当正式基线。runner 对准入题 ID 集合保存快照，结束时核对有效结果 ID 集合完全相同、有效=20、失败=0、未跑=0；不满足时不得输出任何完成状态。全 draft、部分 draft、重复/空 ID 和首题故障均有回归，首题故障有效数=0、失败数=1、未跑数=19，保持 inconclusive。

judge 结果校验职责：逐项验证返回存在性、非 bool 数值、有限性与对应指标合法范围；本 MVP 三个归一化分数候选范围为 [0,1]，S0 需对照采用的指标契约确认后固定。NaN、正负 Infinity、缺字段/空列表、非数值、越界或单项异常均不能当有效 0 分或 healthy judge。每项输出 value（有效数值或 null）、available、safe_reason；有效项可保留，任一无效项使 judge_degraded=True。机械指标独立保留，不能被 enrichment 的缺失覆盖。序列化拒绝 NaN/Infinity，覆盖部分缺失和非有限值的回归，不新增整体报告状态。

runner 状态规则：准入失败不调用 evaluate；健康 ok/empty 计算指标；failed 或带来源故障的 degraded 报 infrastructure_inconclusive，不计作有效质量样本；invalid-request 作为输入/执行契约失败，不伪装成健康零召回，具体沿用现有状态的失败明细记录。MVP 默认 vector-only，不新增聚合完成状态；首个此类失败停止后续评测并保留已执行结果/未执行题数，不重试。仅健康检索且 judge 不可用才 completed_judge_degraded。

报告补 backend/provider/dialect、无密钥 target_index_id、实际查询 embedding 配置与指纹、证明引用、隔离证据引用、题级来源/状态及有效/失败/未跑数量。健康低召回不是基础设施错误；没有 golden 的输入不能得到误导性的正式 baseline 满分。运行前与运行期间固定查询配置，实际模型/部署/参数或维度与证明不同则阻断旧索引评测；仅服务端无法锁定的版本别名保留明确限制，不能以相同维度替代配置匹配。

### E3：产品 runner、证明与准入（S0/S1/S3）

候选新文件：`scripts/rag_ingest.py`（受控产品运行入口）；`app/harness/ingestion_attestation.py`（证明 schema/验证，禁止导入 benchmark）；输出 `artifacts/rag-runs/<run_id>/` 下的运行记录、成功证明与产物清单。输出不得默认加入 Git，不能保存密钥或版权正文。runner 只调用产品 service、读取校验实际产物并生成证明；benchmark 只消费，不造索引。

函数候选：run_ingestion 输入文件路径、namespace、scope/owner、策略与目标配置，输出 IngestResult 加运行核验信息；verify_written_manifest 输入本轮期望 identities 和实际目标，输出数量、ID/locator 一致性与产物摘要；build_attestation 仅消费成功核验结果输出版本化 JSON；validate_attestation 输入 JSON、预期源/目标与隔离证据，输出允许或完整安全拒绝原因。具体签名在批准后的 spec 按该职责固定，不在执行中互相漂移。

为使提交后恢复有依据，产品 service 候选增加 prepare_file 与 ingest_prepared 两个职责，现有 ingest_file 保留为调用两者的兼容入口。prepare_file 在 service 内复用唯一 Extractor/ChunkingService 流程，输出不可变 PreparedIngestion：本轮 docs、身份/版本/来源信息、planned count、warnings 和无正文计划清单；不调用 index。runner 持久化清单成功后，ingest_prepared 消费同一个准备结果，经 E1 校验后执行一次写入，不能重新提取切块。runner 不另写提取/切块逻辑，准备接口需在 spec 中确认后方可实施。

| 候选字段 | 类型/来源与限制 |
|---|---|
| schema_version、status | 非空版本常量、成功必须 status=ok；失败是独立运行记录 |
| ingestion_run_id | runner 本次生成 UUID 字符串，不复用 doc_id |
| source_sha256、source_format | 实际输入字节 SHA-256、epub；与 manifest 校验一致 |
| import_namespace、doc_id | 显式 namespace、产品服务实际 doc_id，均非空 |
| normalizer_version、chunking_version | 实际 NORMALIZER_VERSION 和实际 chunking_spec_version；不把 chunk-v1 身份协议误作切块策略版本 |
| doc_protocol、chunk_protocol、chunk_policy | 实际身份协议与 chunk_size/overlap/hard_limit；当前默认不等于模型实测上限 |
| planned_chunk_count、written_chunk_count、failure_count | 非负整数、拒绝 bool；成功必须 planned=written>0 且 failure=0，写入数经过实际核验 |
| backend、provider、dialect、target_index_id | 实际 pgvector/PgVectorProvider/postgresql、无密钥目标标识；消费方核对实际目标，不只比较自报字符串 |
| embedding_config、embedding_fingerprint | 来自实际 EmbeddingService 实例的模型/部署身份、无密钥服务标识、实际维度及影响向量生成的参数；规范化序列化后取 SHA-256，禁止包含 API key、鉴权查询参数或连接凭据 |
| embedding_version、version_binding | 可取得的不可变模型/部署版本；不可取得则显式标 unavailable/alias_unpinned 并记录限制，不能编造服务版本 |
| scope、owner | global+null 或 private+有效用户整数；不能使用 private+null、global+owner |
| error_code、safe_summary、warnings | 成功无错误码；失败用已有安全分类，摘要不含 SQL/密钥/堆栈 |
| artifact_manifest_sha256、isolation_evidence_ref | 本轮实际产物 ID/数量清单摘要、隔离核验引用，与消费目标一致 |

embedding 配置应记录实际实例使用值而不是事后 settings 快照；未显式设置但影响生成的参数记录明确默认/服务端默认状态。相同模型名而服务部署不同也必须可辨别，输出只能用无密钥的服务/部署标识。采集与比较职责输入实际 embedding 实例和证明，输出配置摘要/指纹及匹配结果；摄入、baseline 和在线验收共用此逻辑。新增“维度相同、模型不同”“部署或参数不同”拒绝回归。指纹只能证明可观测配置匹配；若远端别名原地升级而无可取得版本，保留无法证明向量空间不变的限制，不宣称已完全消除此风险。

proof schema 版本和新增字段是候选扩展；在 S0 确认生产者与 gate 同步升级，不让旧证明默认适配成可信成功。JSON 写出须避免半文件作为成功证据；DB 已提交但文件未生成时不回滚假称未写入、不自动重摄入。不为恢复引入 upsert/delete 生命周期。

MVP 首次摄入/恢复契约限定：独占且 vector_chunks 为空的专用目标，同一目标有未决意图时禁止新 run。写库前先持久化 intent.json 与 plan-manifest.json，包含 run ID、schema/target 标识、预检空库计数、源 SHA、版本/embedding 指纹、计划行数，以及每行 doc_id/chunk_id、content SHA、scope/owner、实际 locator 等无正文元数据和清单摘要；持久化失败不得写库。先记录真实前态，再做唯一一次写入，期间禁止其他 writer。此空库条件是 MVP 恢复范围约束，不将所有 append-only 导入永久改成只允许空库。

恢复入口候选为 runner 的只读核验模式：只消费已持久化意图/计划，不调用 prepare_file 或 index，不依赖故障前尚未返回的 IngestResult。比较实际目标/源配置、行总数及逐行多重集合（身份、正文摘要、scope/owner、locator），不能仅比较去重 ID 集合；验证本轮目标独占且从空前态开始。全部吻合且本轮无失败/并发证据，才补写完整成功证明。行重复、缺失、元数据不符、意图不完整、非空前态或无法证明独占时，一律保留 blocked/未决，不自动删库、重导或补成功。

无法唯一恢复时，保存诊断和未决记录，由用户明确处置原资源；如需重新尝试，使用另一个明确空的隔离目标和新 run ID，保留原库且不宣称旧 run 成功。回归覆盖提交前退出、提交后证明前退出、证明半文件，以及计划/目标/配置不匹配。该设计不新增 run 数据表，也不以稳定 ID 代替 run 归属证据。

### E4：迁移、隔离与资产（S0/S2/S3）

落点：`alembic/env.py`、既有 PG/SQLite provider fixture、真实集成测试、runner 目标校验；不得由 benchmark 自建产品表或向量。fixture 初始化职责是从配置的独立测试目标执行正式 Alembic revision，输出连接/版本/schema 证据；环境探测返回实际 dialect/provider、维度及配置指纹与可用性，无需打印连接串。

迁移目标的唯一测试注入路径：fixture 从显式 TEST_PG_URL 或明确 SQLite 测试资源创建同步连接，先以只读信息核对实际数据库、schema、测试资源标识及与业务/基线目标的区别，然后通过 Alembic Config.attributes 的 connection 注入。env.py 需新增消费该连接的显式测试分支，直接用此连接配置迁移，不能在该分支无条件用 settings 覆盖 URL，也不能连接失败后回退 settings；测试标识存在但连接未提供时立即拒绝。常规部署入口保留原有 settings 路径，两者不能混用。此为待实施设计，当前 env.py 尚不支持该注入消费。

迁移和测试清理共用已核验连接与目标守卫，守卫在每次 DDL/DML/清理前生效；只读预检可以访问目标身份，不允许先迁移再证明目标正确。PostgreSQL 校验实际 database/schema 和显式独立测试标识；SQLite 校验解析后的绝对测试文件/内存资源，禁止误用业务文件。A/B 对抗用例：settings 指 A、fixture 指 B，只有 B 可执行 revision 或清理，A 的 schema/数据不变；错目标、缺标识和漏注入均在变更前失败。真实 PG 验收仍需独立资源，不因模拟连接回归通过就声称真实数据库已验证。

MVP 推荐两类资源：权限/事务对抗测试库可含人工样本；纯本书基线库只含当前成功产物，供评测和受控在线冒烟。隔离核验读取实际 target_index_id、doc/chunk 清单与 scope-owner，和成功证明比较；不接受未经验证的 provenance_filter 模式。若选择过滤模式则新增查询过滤设计与独立证明，不把 visibility WHERE 替代 corpus filter。

源资产检查复用既有 SHA/validator，若版权 corpus 缺失按既有合法来源恢复，不上传正文。不对 EPUB 实施泛化重写；真实书籍确实提取缺失时先明确涉及标签/片段及 ID/策略版本影响，再审批最小修复。

### E5：在线状态、投影和日志（S1/S5/S6，C 责任边界）

落点：assembly.py、orchestrator.py、tutor.py、critic.py、规则动作转译及现有日志接口。种子构建职责输入认证会话和当前消息，输出完整 RetrievalRequest；微回合路由职责保存结果/质量，Tick 生成唯一 Tutor action；投影构建职责截取已授权正文与引用，Tutor 仅消费该数据。

请求保真字段：retrieval_id、query、top_k、purpose、sources、user_id、visibility、attempt。每次关联状态：request/result/attempt/quality/direct_parent/final_tutor_action_emitted，只属于当前会话；检索 ID 在 payload，Event schema 不变。最终动作发出后，重复/迟到观察不生成第二份最终动作。

EvidenceProjection 沿用 spec 的状态、chunks/citations、来源、安全摘要及截断标记，字段和上限先确认。认证身份不得被 Conductor 或用户文本改写；五态与 quality unavailable 都有明确动作，不自动重试。日志关联上下文沿既有依赖方向传递，不能让基础设施反向依赖 Orchestrator；可选轻量上下文携带 retrieval_id/attempt，准确接口在 S0 对齐。

歧义行审计只记录目标、关联 ID、行标识/类别等必要元数据，不返回被拒绝正文。验证 PG/SQLite 的过滤前提与线上上下文，避免为审计而把无权限正文读进 prompt；全库逐行扫描的开销不应成为在线新默认，按已确认 spec 的审计语义设计。

### E6：联合验收与可追溯交接（S4/S6）

输入：成功证明、实际隔离索引、题集、认证测试用户及当前配置；输出：题级报告、普通/SSE 因果证据、安全对抗结果和剩余问题清单。验收记录保存当前问题与 retrieval_id/产品 chunk/citation/Tutor 输入的必要关联，不公开正文或凭据。

每次验收新进程从实际在线 embedding 实例提取配置/指纹，在查询前与摄入证明及 S4 基线绑定值比较；不匹配先拒绝使用旧索引，不能以向量维度相同放行。运行期间固定实例配置，发生可观测配置变化必须重新核验。若服务端模型别名无法固定版本，验收记录保留该限制。G4 只接受 20 题有效完成的报告；真实服务失败的尝试记录可用于诊断，不满足 MVP 的“已有基线”条件。

新增测试应覆盖本轮真实缺陷和链路风险，而不是镜像实现；各执行包先复现、最小实现、相关测试、审阅后进入下一包。用户确认后优先由子代理实施，主会话负责规划与核验；不得在共享 HEAD amend，不用 git add -A，不自动提交或推送。

## MVP 外工作与触发条件

- 图检索、跨源排序、查询扩展、多次重试：有真实基线证明现有检索不足后再规划。
- shared/course、上传 API、防解压炸弹与完整导入生命周期：有对应产品入口需求后另立 spec；当前无上传 MVP 不提前扩张。
- strict identity recall 与 GoldEvidence 映射：稳定身份和产品来源验证后单独裁决，不替代本轮 proxy。
- DeepEval 教学打分与质量阈值：先获得真实在线回答，另行设计/确认，不阻断证据链路工程验收，也不因此宣称教学效果已验证。
- EPUB 其他标签全面支持：以首本书实测缺失决定必要范围；不默认扩展所有格式。
- 全仓 lint 清理、历史文档排版归一：仅处理实际阻断，避免挤占主链。

## 当前下一步

方案已确认；启动实施时先执行 S0 契约归档及环境盘点，按 DAG 在写入、评测和共享证明模块间分配最多三个子代理，主会话审阅并集成。每关闭一项 R 问题须附具体测试/运行证据与文档链接；仅有设计或测试替身不得升级真实产品结论。

## 本轮 review 补修追溯

| Review | 问题索引 | 任务/执行包 | 放行与必需回归 |
|---|---|---|---|
| RV-01 | R23 | S0-07、S1-07、S4-01；E2/E6 | G1/G4/G6；全 draft、部分未验证、重复/空 ID、首题失败、完整 20 题低召回仍可完成 |
| RV-02 | R24 | S0-06、S2-02、S3-02/03、S4-01、S6-01；E2/E3/E6 | G3/G4/G6；同维度不同模型/部署/参数拒绝，无法固定别名版本明确披露 |
| RV-03 | R25 | S0-06、S2-01/05；E4 | G2；settings=A/fixture=B 仅 B 变更，错目标/漏注入在 DDL/清理前拒绝 |
| RV-04 | R26 | S0-07、S3-02/05/06；E3 | G3；提交后证明前退出可只读补证，重复/缺行/无清单/非空前态不自动恢复成功 |
| RV-05 | R27 | S0-07、S1-08、S4-04；E2 | G1/G4；部分分数缺失、NaN/Infinity/越界降级，机械指标保留，严格 JSON |

R23～R27 在本方案按 P1 跟踪，是相关执行包的必要边界；review 中 RV-04/RV-05 的 P2 分级并不表示可延后到 MVP 之外。本轮只完成代码事实对照与规划修订，未运行 review 的受控复现、业务测试或真实基础设施验证，原 review 文件保持不变。
