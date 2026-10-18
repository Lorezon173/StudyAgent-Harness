# RAG Foundation 分阶段进展与推进 TodoList（待确认）

日期：2026-10-13。本文是基于现有交接与 spec 的原始规划材料，不是新的冻结决策，不授权直接编码。

2026-10-15 修订：已纳入子代理 review 和主会话针对性复现。最新执行顺序、问题优先级、MVP 范围与执行包以 [MVP 修订执行方案](2026-10-15-rag-mvp-execution-plan.md) 为准；本文继续保留原 Phase 编号和进展基线。核验依据见 [核验报告](2026-10-13-review-verification.md)。本轮仅修订规划，所有新增任务均未实施。

执行约束：用户确认规划后，按模块使用 subagent-driven-development 或 executing-plans 逐项实施；代码变更前加载 karpathy-guidelines。后续新增或修订 spec 必须追溯本文及既有冻结决策，不覆盖历史设计来源。

## 事实来源与状态口径

- 总交接：`remain-work/2026-09-02-RAG进展提交与工作区现状-主控handoff.md`。
- A 交接：`remain-work/2026-08-27-RAG-A-EPUB提取器验收与Phase4接续-主控handoff.md`。
- 权威主清单：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`。
- 冻结决策：`docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md`（DEC-001～012）。
- spec：`docs/rag-work/specs/2026-07-24-epub-extractor-spec.md`、`2026-07-24-project-chunking-service-spec.md`、`2026-07-24-online-rag-p0-repair-spec.md`。
- 实施证据：`docs/rag-work/status/RAG-{A,B,C,D}.md` 顶部当前状态、实施回报和主控复核记录。

主清单及 spec 保留实施前快照，不能直接按未勾选数量判断进展。本文将“已实现”“已验收”“真实环境已验证”分别描述。597 passed / 1 skipped / 8 deselected、RAG 定向 166 passed 是交接记录，本次未复跑。此前同步已确认 main 与 origin/main 一致；不再安排历史交接中的推送任务。

## 第一层：模块总览

目标：完成首本书真实产品摄入、受控在线证据消费、真实 Retriever 基线及教学链路验收。

沿用 Python/FastAPI、现有事件协作环、SQLAlchemy/Alembic、PostgreSQL/pgvector 和现有 embedding 服务。当前向量表与配置默认维度为 2048，必须与实际 embedding 输出一致。保持四层单向依赖及唯一主链：文件→Extractor→ChunkingService→KnowledgeIngestionService→Embedding/PgVector；用户消息→Retriever→Coordinator→PgVector→证据/失败事件→Orchestrator→Tutor。

边界：不新增回答器，不让 Tutor 直连数据库或检索，不扩展 Event schema；retrieval_id 留在受控 payload；max_attempts=1，不自动扩展查询；权限仅 global/private；Gate 0 为 append-only；不新增 ingestion_runs 表，不改 knowledge API。图检索、shared/course 权限、替换删除、严格 identity recall 扩展另行规划。

修订顺序：最小契约确认 → 可信性修复（写入计数、评测状态、准入、指标与日志）→ 正式迁移和真实环境 → Phase 4 摄入与证明 → Phase 5 真实检索基线 → Phase 3 在线接线 → Phase 6 联合验收。这里先做 Phase 5 是为先建立可诊断的检索基线，不表示 Phase 3 在技术上依赖 Phase 5；多人实施时在线离线代码工作可独立开展，最终验收仍遵循前置门禁。

## 第二层：阶段与子模块概述

### Phase 0：主控复核与 spec 收敛——已有裁决，剩余追认

**实现基线**：共享契约以 DEC-001～012 为准；主控维护主清单，各窗口唯一维护各自状态。候选值不能直接标为冻结。

**已完成**：共享决策记录；A 验收、B canonical bytes 复核、C-08 provisional 放行、D 只读工具放行；已有 A 专项交接和总交接。

**剩下工作**：
- [ ] P0-01 按当前实现和证据核对 M-01～M-06 回执，更新主清单的历史勾选与 blocker 状态。
- [ ] P0-02 复核 C spec §F/§G 采用值：在线入口、三条件校验、503/SSE 语义、六码错误、top_k 默认 5/上限 10、受限 payload 身份契约。
- [ ] P0-03 复核 §H 投影与引用契约。候选为最多 5 块、单块 2000 字符、总计 6000 字符、最多 5 个引用；核对完整 citation schema、截断标记与非法投影处理后确认，未经确认不当作正式默认。
- [ ] P0-04 补 B/C/D 主控交接；统一 README、工作区入口的阶段描述和迁移后链接，保留历史记录。
- [ ] P0-05 核对本地 EPUB、corpus、manifest 与题集可用性；记录缺失项及责任人。corpus digest 的权威来源如需扩展，必须另行裁决。

**完成判据**：待追认项有明确接受或修改结论；主清单与状态证据一致；下一模块三层规划经用户确认。

### Phase 1A：EPUB 提取——已验收

**实现基线**：extract(file_path) 返回字符串；标准库解析 container/OPF/spine，按 spine 顺序读取；严格 UTF-8；任一规定失败返回空字符串，不进行磁盘解包。

**已完成**：A-01～A-07；EPUB 工厂注册、动态多页顺序对抗 fixture、换行/entity/失败路径、README 与资产记录；主控验收通过。

**剩下工作**：
- [ ] A-R1 在 F-02 中验证真实书籍内容完整性和章节顺序，区分既有支持边界与缺陷。
- [ ] A-R2 若真实书籍依赖 li/blockquote/pre 等当前未提取内容，先提交兼容性调整规划，再决定是否扩展。

**完成判据**：维持 extractor-only 验收结论；真实兼容性证据归入 Phase 4。ZIP bomb 防护并非此 spec 第一版强制项，不因其未实现撤销既有验收。

### Phase 1B：切块与身份协议——协议补证已完成

**实现基线**：DEC-006 元素半开区间与 DEC-012 canonical bytes；Unicode NFC、换行/空白归一化顺序、版本字段及 framing 决定稳定 ID；benchmark paragraph_id 不充当产品身份。

**已完成**：canonical document/chunk 规范、测试向量、B-04 独立复算及 DEC-012 冻结；算法与来源信息测试已随 Phase 2 落地。

**剩下工作**：
- [ ] B-R1 核对 B-01～B-07 的历史勾选与证据链接，避免把已实施项重复派工。
- [ ] B-R2 将当前策略、协议版本写入正式摄入证明；验证真实存储往返，归入 Phase 4。

**完成判据**：协议与实现版本可追溯，真实验证不重新定义 ID 算法。

### Phase 1C：在线 RAG spec——已修订并 provisional 放行

**实现基线**：完整 RetrievalRequest、seed/rule/conductor 三路径保真、retrieval_id 关联、微回合屏障、五态结果和受控 EvidenceProjection。

**已完成**：C-01～C-08 的规范工作；C-09～C-11 已据此实施。spec 中部分实施前事实已过时。

**剩下工作**：
- [ ] C-R1 完成 Phase 0 的 §F/§G/§H 复核，明确被冻结的部分与候选部分。
- [ ] C-R2 为 C-12～C-17 整理三层文字实施规划，记录代码落点、接口、路由状态和测试矩阵。

**完成判据**：在线接线执行者可按确认后的契约实施，不自行决定共享字段或投影上限。

### Phase 1D：只读评测准备——工具已完成

**实现基线**：validate_assets→to_evaluate_input→validate_admission→run_baseline；六项准入检查；每题一次 evaluate；固定 proxy/enrichment 口径。

**已完成**：D-01～D-07；资产/SHA/locator 校验、题集适配、六项 gate、六状态报告封装、单次 runner、异常路径测试；黄金题 locator 错配修复。

**剩下工作**：
- [ ] D-R1 验证工具可以消费 F-03 的真实 attestation 和实际隔离证明。
- [ ] D-R2 若本地版权 corpus 缺失，先恢复可用输入并校验，不以 fake 结果替代正式评测。
- [ ] D-R3 修复 evaluate 丢弃检索 outcome/来源/失败信息的路径，runner 不得将数据库失败归为 completed_judge_degraded；强化证明有效性与隔离证据校验，新增同次检索多 k 指标。历史 D-01～D-07 完成不代表这些新增缺口已关闭。

**完成判据**：只读工具完成状态维持；真实分数只在 Phase 5 产出。

### Phase 2：共享基础能力——实现完成，验证缺口未闭合

**实现基线**：无状态 ChunkingService；KnowledgeIngestionService 薄编排；可信 provenance 与实际写入确认；过滤先于排序/LIMIT；在线 pgvector/PostgreSQL fail-fast。

**已完成**：B-08～B-11、B3-01～B3-07、C-09～C-11；chunk_id 迁移；init 补 mastery 表；SQLite 7 步正式迁移链与回程验证。B 主控复核通过仅限代码/SQLite 维度。

当前代码策略：chunk_size=500、overlap=50、hard_limit=8192，按 Unicode 字符计数；8192 是保守策略值，不是 embedding 模型实测上限。IngestResult 返回状态、doc_id、planned/written count 和 warnings，不是完整 attestation。

**剩下工作**：
- [ ] I-01 让 PG/SQLite provider 测试消费正式迁移/schema 契约，消除手工建表分叉。
- [ ] P2-02 补真实 PG 的迁移、写入、来源往返及权限过滤验证，结果与 Phase 4 复用。
- [ ] P2-03 补齐已确认的内部异常关联及歧义行无正文审计要求；将 embedding 等已有错误码的准确归类与可选统一重构分开，不延后既有验收项。
- [ ] P2-04 执行相关回归与 CI 检查，重新记录 lint 现状；交接中的 344 项告警是历史记录，不能视为当前实测值。
- [ ] P2-05 修复 provider 对短 embedding 列表 zip 截断后返回 planned count 的条件性误报；约束数量/维度并验证端到端 IngestResult。默认 embedding 数量不足会写库前报错，不将该触发边界夸大为正常线上必现。

**完成判据**：正式部署 schema 与测试一致；真实基础设施失败明确标 inconclusive；没有将单测结果升级成产品链完成。

### Phase 3：在线 evidence 接线——未开始

**实现基线**：默认 sources=['vector']，认证身份生成可见性；同 retrieval 最多一次最终 Tutor action；Critic 缺 quality 时可继续；Tutor 只消费受控投影。

**已完成**：规范与 Phase 2 的安全基础；未完成 seed、路由、投影和 Tutor 接线。

**剩下工作**：
- [ ] C-12 改造在线种子，先检索，取消无证据最终 Tutor 抢跑；保护 seed/rule/conductor 请求保真。
- [ ] C-13 Orchestrator 处理 evidence/failure 和质量观察，在屏障处生成唯一 Tutor 投影动作。
- [ ] C-14 Tutor 将正文、来源、状态加入当前回合 prompt；遵守确认后的长度和引用限制。
- [ ] C-15 对 empty/degraded/failed/invalid-request 产生受控回复，避免空回复兜底和异常泄露。
- [ ] C-16 用 sentinel chunk、连续两次请求、重复事件/迟到 quality 验证消费、关联和不重复回复。
- [ ] C-17 验证 chat/SSE 共用核心链路；补真实 pgvector 冒烟，结合 Phase 4 索引完成。

**完成判据**：证明当前回合 prompt 实际包含正确证据；请求、权限、来源与状态不在路由中丢失；每个检索单元最终回复最多一次。

### Phase 4：首本书正式摄入与证明——未完成

**实现基线**：真实 EPUB 走产品主链，真实 embedding 与 PostgreSQL/pgvector；测试/运行消费正式迁移；完整可审计 JSON attestation；append-only。

**已完成**：提取、切块、摄入、provider 和迁移代码；真实环境与正式摄入证据未完成。

**剩下工作**：
- [ ] F-01 从隔离的干净 PG 执行正式迁移；验证 vector 扩展、表结构、2048 维一致性及连接/embedding 可用性，不清理既有业务数据库。
- [ ] F-02 真实 EPUB 经产品服务摄入；检查正文顺序与完整性；读取实际写入数量，不用 planned 推断 written。
- [ ] F-02a 在独立测试资源中制造中途写入失败，真实 PG 验证整体 rollback、无本轮残留；已有 SQLite 回滚通过不替代此项。
- [ ] F-03 由受控产品 runner 生成版本化摄入证明，明确 ingestion_run_id、source_sha256/source_format、namespace、normalizer/chunking/identity 版本、doc_id、planned/written/失败统计、backend/provider/dialect、目标 DB/index、scope/owner、安全错误码和摘要；校验类型、非空、数量及真实目标绑定，失败记录不作为成功证明。
- [ ] F-04 检索回读并核对 doc/chunk ID 与可用 source locator。当前纯文本适配的文件来源不能宣称为完整 EPUB 章节/页码定位。
- [ ] F-05 用两用户、公共/私有及歧义行对抗样本验证权限过滤；Provider 层先验，Tutor 层验收与 Phase 3/6 联合完成。
- [ ] F-06 记录追加式生命周期、隔离方式和重跑处理，避免把稳定 ID 宣称为幂等；不通过直接造 benchmark 向量替代产品摄入。
- [ ] F-07 MVP 推荐权限对抗使用独立测试库、正式本书使用纯本书基线库；保存目标和产物清单证明。provenance_filter 目前未实现，不能仅凭 verified=true 放行；此项是隔离方式的执行建议，待方案确认。

**完成判据**：真实索引、摄入证明、来源往返和隔离证据成立，D admission gate 能实际接受。真实环境不可用时记录 infrastructure_inconclusive，不勾选摄入完成。

### Phase 5：黄金集 Retriever baseline——未运行

**实现基线**：Phase 4 F-01～F-05 与 D-01～D-07；被测 coordinator 只含 vector；已证明 corpus 隔离；20 道 verified_v1 题每题一次。

**已完成**：题集与只读工具准备；无正式产品 baseline。

**剩下工作**：
- [ ] D-08 六项准入全绿后运行 20 题，记录 proxy/enrichment 与隔离方式。
- [ ] D-09 保存 raw metrics、provider/dialect、sources_used、latency、degraded、attestation 引用。
- [ ] D-10 在 D-08 之前明确扩展 evaluator：从同一次 top-5 检索按排名前缀派生 proxy Recall@1/3/5，保留既有 recall_at_k、context-precision proxy、冗余度；补检索失败与 judge 降级分开报告的测试。当前接口已核实只有单个 recall_at_k，不能仅靠报告层恢复多 k，也不能重复查询。
- [ ] D-11 RAGAS 只作 enrichment；不可用标 completed_judge_degraded，保留有效机械结果。
- [ ] D-12 人工复核零召回、高冗余与疑似跨 corpus 题。
- [ ] D-13 维持 paragraph-containment proxy 口径；BLK-013 未解除前不称 strict identity recall，不外推 Tutor 教学质量。

**完成判据**：可审计报告和原始结果齐全，blocked、基础设施异常、judge 降级与完成清楚区分；不预设无实测依据的质量阈值。

### Phase 6：在线教学完整链路——未开始

**实现基线**：Phase 3/4/5 完成；真实 chat/SSE、当前回合产品 chunk/citation、认证权限隔离。

**已完成**：API 与协作环基础；尚无该阶段验收证据。

**剩下工作**：
- [ ] H-01 用黄金题驱动真实普通/流式聊天。
- [ ] H-02 保存当前问题→retrieval_id→产品证据→Tutor prompt 的关联证据，验证来源准确。
- [ ] H-03 分类定位召回、投影、生成和基础设施失败，不统一归为回答质量差。
- [ ] H-04 对跨用户证据、连续请求和降级分支进行端到端验证。
- [ ] H-05 根据实测结果另行规划并确认教学质量指标、判定方法和阈值；不把 Retriever proxy 当教学质量。

**完成判据**：在线证据消费与权限安全得到真实验证；质量结论具有具体测量依据。

## 第三层：剩余子模块详细实施设计（文字，待确认）

### 1. 迁移与真实环境验证子模块

职责：I-01/F-01；修改测试 fixture 的建库流程与现有集成验证，不重写生产迁移体系。输入为隔离测试数据库配置、正式 revision 和 embedding 配置；输出迁移版本、schema 检查、真实 embedding 维度与可用性证据。

函数职责：fixture 初始化执行正式迁移并提供连接；环境检查读取实际 dialect/provider 和向量输出维度；验证结束只清理明确属于本轮的测试资源。数据库配置不进入公开报告。错误区分连接、权限、扩展、迁移和 embedding；失败阻断真实验收，不回退 fake。

### 2. 正式摄入及 attestation 子模块

职责：F-02～F-07；复用 get_extractor、ChunkingService.chunk_text、KnowledgeIngestionService.ingest_file、Coordinator.index_documents。受控 runner、版本化证明 schema 和隔离执行包的候选文件及接口详见 2026-10-15 修订方案，不改 knowledge API。

函数职责：摄入执行函数输入文件、namespace、scope/owner、版本和策略，输出现有 IngestResult；证明构建函数结合文件 SHA、运行配置、实际写入核验与失败统计，输出 JSON；回读核验函数输入 doc_id/目标库，输出 identity/locator/数量一致性结果；隔离核验函数执行两用户对抗检索，输出允许/禁止样本证据。

数据结构：现有 IngestResult 保持服务结果职责；attestation 是独立运行证明，不把缺失字段编造成服务已有输出。稳定 ID 和版本字段消费 DEC-012；源文件 SHA、目标索引标识与写入数来自实测。失败时保留非成功状态和证据，不伪造成功证明。不得新增未获批准的持久化表。

### 3. 在线检索路由子模块

职责：C-12/C-13；主要落点 assembly.py、orchestrator.py 及规则配置相关路径。输入为认证会话、消息、完整 RetrievalRequest 和事件；输出为检索种子及携带 EvidenceProjection 的 Tutor ActionRequested。

函数职责：在线种子构建创建初始动作并将动作 ID 用作 retrieval_id；请求复制逻辑保护 query/top_k/purpose/sources/user_id/visibility/attempt；Orchestrator 事件处理保存结果与质量观察，Tick 处理在屏障处发出唯一动作；Conductor 转译保留受控请求/投影，不接受其改写身份。

状态结构按 retrieval_id 保存 request、result、attempt、quality、direct_parent、final_tutor_action_emitted，仅属于当前会话。重复、迟到和缺字段事件不得造成二次最终动作或串轮；缺 quality 标 unavailable 并继续；max_attempts 固定 1。Event dataclass 不变。

### 4. 证据投影与 Tutor 消费子模块

职责：C-14/C-15/C-16；Orchestrator 为唯一投影边界，Tutor 仅生成教学内容。输入为可信检索状态、已授权 chunks/citations 和质量观察；输出为经过长度/引用约束的投影及教学 prompt。

函数职责：投影构建筛选字段、关联 retrieval_id、限制正文和引用并标记截断；Tutor.handle 校验目标动作负载，现有教学生成函数加入当前回合正文/来源/状态；Critic 质量事件携带同一 retrieval_id。具体 helper 名称在模块实施规划中结合代码确定，此处不假称现有接口。

关键结构为 EvidenceProjection：关联 ID、状态、quality、chunks、citations、sources_used、安全摘要及需要的安全错误信息。引用字段与上限先在 P0-03 确认。无证据/失败产生受控说明，不泄露 SQL、异常或连接串；无权限内容不进入 prompt。

### 5. 基线报告子模块

职责：D-08～D-13；复用 rag_d.py 的 validate_assets、to_evaluate_input、validate_admission、run_baseline 和 RetrieverAgent.evaluate。输入为已核验题集、真实 agent、attestation、隔离证据；输出六状态 envelope、原始指标和人工异常复核记录。

运行状态沿用 blocked:asset_invalid、blocked:not_real_pgvector、blocked:unattested_product_index、infrastructure_inconclusive、completed_judge_degraded、completed。任一准入失败不调用 evaluator；每题一次；检索基础设施失败保真到报告，不能记为有效零召回或单纯 judge 降级。多 k 已确认为能力缺口，增加单次 top-5 前缀派生的正式任务，且全量返回分支保持一致。

### 6. 在线验收子模块

职责：C-17/H-01～H-05；输入真实产品索引、黄金问题和两用户身份；输出 API/SSE 结果、请求因果记录、当前回合 prompt 消费证据及故障分类。

验证函数分别负责普通入口、流式入口、连续请求、跨用户和失败分支；观测仅保存验证必需证据，不把密钥或无权限正文写进公共报告。教学质量评分函数与字段目前未冻结，H-05 根据真实结果单独规划，不提前制造评分标准。

## 执行与更新纪律

每个执行包先确认对应三层规划；复用已有测试与真实验证证据，新增测试必须验证行为风险。每阶段完成后更新根 README、主清单及相应交接，状态文件遵守唯一写者协议。明确文件暂存，不 amend 已推送历史，不提交/清理本地 self-evolution 或版权资产。

当前仅修订原始规划与 README 索引，不修改生产代码、既有 spec、权威主清单或各窗口状态。下一步按 2026-10-15 方案确认 S0/S1 的详细执行包，再启动实施；不将本次规划修订视为问题已修复。
