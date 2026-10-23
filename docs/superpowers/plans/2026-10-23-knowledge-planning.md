# 网络与文档知识规划、可编辑权重实施计划（第二阶段）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为本人主题画像提供默认网络来源的LLM知识规划、文档来源、人工编辑及可追溯权重计算。

**Architecture:** 第一阶段主题画像与知识库为基础，资料采集→规划候选→人工修改→显式激活版本→同源画像汇总。规划不依赖embedding，不绕过既有RAG索引/可见性门槛。

**Tech Stack:** 既有FastAPI、SQLAlchemy、Pydantic、LLMService与extractors、React/TypeScript；新外部检索Provider适配器和上传解析依赖在TaskK0确认实际配置后锁定，不预设平台工具可以成为生产API。

**Spec:** [终稿三层实施原稿](../../../superpowers/frontend-ui/2026-10-23-final-implementation-raw.md) F节、[用户知识规划需求原稿](../../../superpowers/frontend-ui/2026-10-23-knowledge-planning-future-raw.md)。前置：[第一阶段计划](2026-10-23-study-workspace-core.md)已通过真实验收。

## 全局约束

- 此阶段保留为后续独立交付，不把“页面终稿确认”当作网络Provider/凭据/额度已确定。
- 默认source_mode=web，手动可选择document或mixed；仅新建/重新规划时搜索，不强制每轮教学联网。
- 用户本人主题、资料和上传文件隔离；全网含义为公开网络查询，不是绕过付费墙、账号或抓取限制。
- 无真实检索或解析时明确失败；不把LLM常识包装成已检索事实。外部资料是内容，不能执行其内嵌指令。
- 人工修改需版本和锁定保护；规划候选需用户激活，重新生成不覆盖已激活内容。
- 篇幅首版单位为字数，内容占比与重要性权重分别维护；mastery、coverage与权重分别显示。
- 第一阶段真实API与会话恢复不因本阶段未配置而不可用。不自动把资料加入向量索引。
- 同样遵循任务前测试、父先flush/业务一次commit、README同步、明确文件提交；不自动发布。

## Review Focus

1. 检索无结果/供应商失效时不伪造来源——K1/K3。
2. 上传恶意文件名、损坏压缩文档、大文件/解压放大不越权或耗尽服务——K2。
3. 人工锁定字段遇到模型重规划不被覆盖——K3/K4。
4. 同一主题两个标签页编辑激活相同旧版本，必须409而不是最后写入覆盖——K4。
5. 增删节点、未评估项和零权重混合时，综合指标不可制造“学完”假象——K3/K5。

## 第一层：模块总览与执行门槛

第一阶段完成以前不执行本阶段产品代码。K0确认真实Provider、凭据注入、预算和运行环境；没有这些信息只能实现可测适配接口和明确不可用状态，不能标记默认全网规划已完成。既有HTTP教学不需等待它。

## 第二层：子模块与接口

| 模块 | 文件 | 输入/输出与状态 |
|---|---|---|
| 网络资料 | app/infrastructure/search/{contracts,provider}.py（新） | SearchQuery→有URL/摘录的SourceDocument；真实Provider配置失败分类返回 |
| 文档资料 | app/orchestration/document_service.py、app/infrastructure/storage/document_store.py、app/api/documents.py（新） | 本人上传→解析状态/内容/定位；不生成伪向量 |
| 规划模型 | app/models/knowledge_plan_tables.py、knowledge_plan_schemas.py（新） | 原始候选、人工变更、激活版本、来源与历史可追溯 |
| 规划业务 | app/orchestration/knowledge_plan_service.py、app/harness/knowledge_plan.py（新） | 资料→候选→校验→版本激活→画像节点稳定映射 |
| API与UI | app/api/knowledge_plans.py（新）、web/src/components/planning/（新） | 选来源/编辑权重/对比修订/确认生效，不新增左栏产品导航 |

新增表 planning_documents、knowledge_plans、knowledge_plan_nodes、knowledge_plan_sources。规划id属于profile/user；每个plan有base_profile_revision与schema_version、status=draft/active/archived，profile只引用一个active_plan_id。稳定node_id跨版本沿用；删除只归档，历史evidence不丢。

每个节点含标题、范围说明、estimated_characters、raw_content_weight、normalized_content_share、raw_importance_weight、normalized_importance_share、locked_fields、source_refs、origin与用户编辑记录。归一值由服务端计算，前端不能把浮点和为99.9当精确要求。

来源SourceDocument至少有source_id、kind、title、url或document_id、locator、excerpt、retrieved_at、content_hash；网络结果缺正文时只可显示摘要级依据，不能声称读过全文。未经获取的网页不标注页码。

## 第三层：实施任务

### TaskK0：真实Provider与运行配置决策

**文件**：docs/designs/2026-10-23-knowledge-source-runtime.md（新），.env.example和README待确定后更新。

**接口**：SearchProvider.search(query,limit=8)返回SourceDocument列表；配置SEARCH_PROVIDER、SEARCH_API_BASE、SEARCH_API_KEY、SEARCH_TIMEOUT_SECONDS=20。真实Provider请求/响应映射在此任务确定，不能用自造协议试生产服务。

- [ ] 核对用户运行环境是否已有合法可用搜索服务；仅列配置键和可用性，不读取/输出秘密。必要时由用户提供供应商选择和配置，预算约束未定不发付费请求。
- [ ] 用官方服务文档核实API、凭据、限额与允许的来源字段，记录选择依据；如需联网核实必须使用真实官方来源，不编版本或价格。
- [ ] 确认首版上传部署路径和可接受格式：TXT/MD、可提取文字PDF、DOCX、EPUB；扫描PDF需OCR则首版明确不支持而非返回空成功。将实际解析依赖及支持表锁定到配置文档。
- [ ] 无Provider则标K0阻塞、本阶段未完成；不影响第一阶段。此步骤无编码失败测试，证据为真实配置决策和最小只读连通性验证。

### TaskK1：默认网络资料采集

**文件**：search/contracts.py、provider.py、app/orchestration/planning_sources.py（新）；core/config.py；tests/unit/infrastructure/test_planning_search.py（新）。

**接口**：collect_planning_sources(user_id,profile_id,source_mode,document_ids,query)返回SourcesResult；web默认，mixed先文档后网络补足，不相互覆盖；实际供应商适配遵守K0决定。

- [ ] 写失败测试：没有配置、超时、无结果、格式错误、无URL均分类失败；mock是测试替身，不能出现在真实成功回包中。
- [ ] 验证查询不携带整份私有文档或聊天记录，只发送用户主题范围与必要搜索词；来源正文只作为模型资料，不产生工具指令权限。
- [ ] 若要抓URL正文，限定HTTP(S)并阻止私网/回环/重定向至内网，校验DNS和响应大小；否则使用Provider已有摘录，不为“全网”自行无限抓取。
- [ ] 运行 uv run pytest tests/unit/infrastructure/test_planning_search.py -q 先红后绿；实现单次最多8条、20秒超时、保留来源及内容hash。
- [ ] 真实Provider小样本验证有实际URL、摘要与时间记录；无凭据不宣称完成，更新README与提交。

### TaskK2：私有文档上传、解析与可定位来源

**文件**：document_service.py、document_store.py、documents.py、knowledge_plan_tables.py、alembic/versions/20261023_planning_documents.py（新）；现有extractors按需增加结构化定位适配，不改变Gate0规范；tests/unit/api/test_planning_documents.py（新）。

**接口**：POST /api/documents采用multipart；GET /documents/{id}及DELETE本人文件；DocumentService.upload/extract/get_owned返回uploaded/ready/failed和可追溯片段。

- [ ] 写失败测试：越权document_id、路径穿越文件名、MIME/扩展不符、空内容、损坏文档、解析依赖缺失、超过20MiB均不返回成功；解压总体文本/内容上限100MiB、最多10000个归档条目，超出失败并清临时文件。
- [ ] 文件写入配置数据目录，随机内部文件名，保留原文件名只作元数据；不接收任意服务器绝对路径，不把上传目录暴露静态伺服。
- [ ] 复用get_extractor的格式识别；TXT/MD按段落、PDF按页、DOCX按段落、EPUB按章节定位。既有纯extract返回字符串不足以证明页码时补结构化提取或只显示真实段落号。
- [ ] 运行 uv run pytest tests/unit/api/test_planning_documents.py -q先红后绿；上传/解析状态失败可重试，进程中断记录failed/interrupted，不无限running；删除清理引用按软删除保护已激活来源。
- [ ] 实文件验收各格式一个，重启后仍可读；未启用OCR明确说明。更新README、依赖锁与提交。

### TaskK3：LLM规划候选、权重和指标

**文件**：harness/knowledge_plan.py、orchestration/knowledge_plan_service.py、knowledge_plan_schemas.py（新）；app/specs/planning/knowledge_plan.md及knowledge_plan.prompt.md（新对）；tests/unit/harness/test_knowledge_plan.py（新）。

**接口**：propose_plan(user_id,profile_id,sources,base_plan)→KnowledgePlanDraft；validate_plan(draft)→ValidatedPlan；normalize_plan_weights(nodes)→归一占比；summarize_weighted_mastery(plan,assessments)→weighted_mastery(nullable)、assessed_weight_coverage。

- [ ] 写LLM边界断言：生成最多100个节点、id由服务端分配/映射，来源必须引用本批sources；模型编造source_id或无依据引用拒绝，不静默改成真实来源。
- [ ] 写权重断言：篇幅是>=0的整数字数；原始占比/重要性非负有限数且各至少一项>0；两组分别归一；锁定字段不得被新候选静默覆盖。
- [ ] 写指标断言：已评估权重和为0则mastery=null；权重3/1、分数80/null则已评估平均80且覆盖75%；全评估80/40则综合70且覆盖100%；不将覆盖75%显示成掌握度75%。
- [ ] 写版本断言：删除旧节点只归档，新增节点未评估；改变权重产生新指标版本，不改历史证据；Prompt使用资料但拒绝其操作指令。
- [ ] 运行 uv run pytest tests/unit/harness/test_knowledge_plan.py -q先红后绿；LLM只提建议，数据校验和计算为确定性代码，不让模型直接返回“已学会百分比”。
- [ ] 更新README计算示例、当前能力边界并提交。

### TaskK4：版本化规划API与人工编辑

**文件**：knowledge_plan_tables.py、alembic/versions/20261023_knowledge_plans.py、app/infrastructure/storage/knowledge_plan_store.py、api/knowledge_plans.py（新）；topic_profile_store.py、profile_service.py；tests/unit/api/test_knowledge_plan_api.py（新）。

**接口**：POST /topic-profiles/{id}/plans/propose；GET /.../plans/{plan_id}；PATCH草案携expected_version；POST /.../plans/{plan_id}/activate携expected_profile_revision。所有接口校验本人profile、document及source引用。

- [ ] 写失败断言：A不能使用B资料、修改B草案；同一旧revision激活只有一个成功，另一409；模型重规划只生成草案并列出差异，不覆盖人工版本。
- [ ] 激活在单事务内保存节点映射、人工锁定字段、权重和active_plan引用；历史计划归档但可读，旧证据仍关联原版本。
- [ ] 运行 uv run pytest tests/unit/api/test_knowledge_plan_api.py -q先红后绿；summary新增metric_kind=weighted_assessed及plan_version、coverage；没有active_plan仍使用第一阶段assessed_mean，不能悄悄改口径。
- [ ] PG并发激活与回滚验证，更新README接口/计算版本与提交。

### TaskK5：规划编辑UI与真实来源验收

**文件**：web/src/api/planning.ts、components/planning/{SourcePicker,KnowledgePlanEditor,PlanDiff}.tsx（新）；Knowledge.tsx、Profile.tsx、FloatingProfile.tsx；相应DOM与web/e2e/planning-real.spec.ts（新）；docs/delivery/2026-10-23-planning-acceptance.md（新）。

**接口**：沿用右上入口与主题画像页，不改变终稿主导航；编辑器区分范围、字数、内容占比、重要性，用户可添加/归档/改名/锁字段/确认激活。

- [ ] 写DOM断言：默认网络、可选本人文档或混合；无Provider说明可手动规划；候选→修改→预览差异→激活；非法权重不能保存；409保留编辑内容。
- [ ] 浮卡与详情同版本，显示掌握度和已评估覆盖率；用户手动修改后重新登录仍恢复；新节点待评估而非自动0分或100%。
- [ ] npm --prefix web test和build通过；正式HTTP浏览器用真实Provider、真实文档与真实LLM完成一条规划，核对来源实际支持对应内容，修改权重后两处显示一致。
- [ ] 执行后端默认回归、相关PGintegration、前端/浏览器检查；确认普通教学在搜索不可用时仍可使用，真实上传不冒充向量索引。
- [ ] 更新README、支持格式/限额/Provider配置、来源隐私说明和证据；独立审查后才声明第二阶段完成，不自动部署。

## 依赖与本轮自审

K0→K1/K2；K1+K2→K3→K4→K5。共享schema/store/README的任务不并发修改；无真实Provider时可以完成纯函数与本地文档部分，但网络验收仍未完成。

- [x] 覆盖用户默认LLM规划、网络/文档来源、人工添加修改、篇幅和重要性设置。
- [x] 来源、权重、掌握度及覆盖率分开；人工修改和旧证据不静默丢失。
- [x] 运行配置门槛明示，不假造可用搜索服务或承诺扫描件OCR。
- [x] 第一阶段与第二阶段都有独立完成标准；本轮未开始实现。
