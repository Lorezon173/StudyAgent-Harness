# RAG 基础能力建设 · 下一阶段核心主清单

> 创建日期：2026-07-24  
> 最近核验：2026-07-25  
> 唯一写者：RAG 基础能力主控窗口  
> 状态：🚧 **四路真实性核验完成，进入 P0 边界冻结与分批实施阶段**  
> 定位：本文件是下一阶段 RAG 基础能力建设的**唯一核心计划、全局 blocker 账本与执行 TodoList**。RAG-A/B/C/D 窗口只更新各自状态片段，不直接修改本文件。

---

## 0. 主控协议确认

- **主清单路径**：`docs/designs/2026-07-24-rag-foundation-parallel-todolist.md`
- **主清单唯一写者**：RAG 基础能力主控窗口
- **固定任务**：RAG-A EPUB 正式提取；RAG-B 通用 Chunking/摄入；RAG-C 在线 RAG P0；RAG-D 黄金集/评测
- **状态片段**：
  - `docs/rag-foundation-status/RAG-A.md`，唯一写者：RAG-A 窗口
  - `docs/rag-foundation-status/RAG-B.md`，唯一写者：RAG-B 窗口
  - `docs/rag-foundation-status/RAG-C.md`，唯一写者：RAG-C 窗口
  - `docs/rag-foundation-status/RAG-D.md`，唯一写者：RAG-D 窗口
- **主控允许直接写入**：本主清单；按项目规则同步 master 资产清单
- **主控禁止直接写入**：RAG-A/B/C/D 状态片段
- **本轮核验范围**：四个状态片段及其明确引用的源码、测试、配置、迁移、benchmark 和设计文档

### 本次涉及资产与三色血缘

| 名字 | 归属子系统 | 功能（干嘛） | 触发 / 入口 | 位置 | 本次影响 |
|---|---|---|---|---|---|
| RAG Foundation 主清单 | 研发治理 / RAG 基础能力 | 汇总真实状态、blocker、冻结边界与 TodoList | 主控合流与下一阶段派工 | `docs/designs/2026-07-24-rag-foundation-parallel-todolist.md:1` | 🟡 改动 |
| RAG 状态同步协议 | 研发治理 | 约束主清单单写者及 A/B/C/D 各写各的状态片段 | 每轮状态回写 | `docs/rag-foundation-status/README.md:6-53` | 🟢 保持 |
| RAG-A/B/C/D 状态片段 | 各任务状态面 | 记录各任务事实、阻断、方案与回报 | 各任务窗口独立更新 | `docs/rag-foundation-status/RAG-*.md` | 🟢 主控只读 |
| 资产清单 | 项目事实索引 | 记录主清单及下一阶段规划资产 | 方案/资产变更时同步 | `docs/asset-inventory.md:1` | 🟡 改动 |
| 根 README | 项目用户入口 | 描述已落地功能、架构、API 与运行方式 | 用户阅读/运行项目 | `README.md:1` | 🟢 暂不改；当前仅治理文档变化 |

---

## 1. 唯一产品主链与完成口径

下一阶段只能补齐项目现有 RAG，不得为 EPUB、黄金集、演示或评测另造平行链：

```text
知识源文件
  → 项目 Extractor
  → 项目 ChunkingService
  → KnowledgeIngestionService
  → RAGCoordinator.index_documents(source="vector")
  → EmbeddingService
  → PgVectorProvider / vector_chunks
  → RAGCoordinator.search
  → RetrieverAgent
  → RetrievedEvidence / RetrievalFailed
  → Orchestrator 受控证据投影
  → Tutor 实际消费当前回合证据
  → RetrieverAgent.evaluate / 项目 Eval 验证
```

### 当前实际存在与缺失

| 链段 | 当前事实 | 证据 | 状态 |
|---|---|---|---|
| Extractor | 仅 TXT/MD/CSV、PDF、DOCX；统一返回 `str` | `app/infrastructure/rag/extractors/base.py:7-28` | 部分存在 |
| EPUB extractor | spec 与 benchmark 参考存在，产品实现/注册/测试不存在 | `docs/designs/2026-07-24-epub-extractor-spec.md`; `tests/unit/infrastructure/test_extractors.py:8-56` | 缺失 |
| Chunking / ingestion | `ChunkingService`、`KnowledgeIngestionService` 尚未实现 | `docs/asset-inventory.md:101-108` | 缺失 |
| Coordinator / provider 写入 | 接受已成形 docs 并写入 provider | `app/infrastructure/rag/coordinator.py:135-139`; `app/infrastructure/rag/pgvector_provider.py:60-109` | 存在但契约开放 |
| 正式 schema | `vector_chunks` Alembic migration 已存在 | `alembic/versions/20260622_add_vector_chunks_table.py:21-69` | 已证实 |
| 在线 Retriever 启动 | 默认 seeds 不含 Retriever action | `app/orchestration/assembly.py:144-154` | 缺失 |
| Evidence → Tutor | Orchestrator 不路由；Tutor 不消费证据 | `app/harness/orchestrator.py:80-98`; `app/agents/tutor.py:32-97` | 缺失 |
| 离线评测 | `RetrieverAgent.evaluate` / `ComponentBench` 存在，但属离线旁路 | `app/agents/retriever.py:105-265`; `app/eval/component_bench.py:10-46` | 存在但口径受限 |
| 书籍 baseline | 20 题资产存在；未发现正式产品 baseline 运行产物 | `benchmarks/rag/books/the-myth-of-sisyphus/questions.v1.yaml:1-567`; `benchmarks/rag/books/the-myth-of-sisyphus/README.md:167-172` | 未运行 |

### 禁止宣称完成的情况

以下任一情况只能写 `blocked`、`degraded` 或 `infrastructure_inconclusive`，不得写 `verified`：

- 只有 spec、状态片段或外部 review 自述；
- 只有 benchmark 抽取/paragraph corpus；
- 只有 FakeRAGStore 或 SQLite 字符匹配；
- 只有检索事件出现，未证明 Tutor prompt 收到证据；
- 只有 RAGAS 分数，实际 `response` 使用人工 `golden_answer`；
- 只有手工测试建表，未验证正式 migration/deployment；
- 只有局部函数存在，未接入完整产品调用链。

---

## 2. A/B/C/D 独立真实性核验摘要

| ID | 当前真实状态 | 已证实进展 | 当前不能宣称 | 下一步定位 |
|---|---|---|---|---|
| RAG-A | `ready_for_implementation`（仅 extractor-only） | Extractor 边界、EPUB spine/UTF-8/失败语义 spec 已收敛；benchmark 机制可参考 | EPUB 正式摄入、chunk、索引、检索已接通 | 可实施 `EpubExtractor + factory + tests + README`，完成后仍只是提取能力 |
| RAG-B | `blocked` | Gate 0、ChunkDocument、stable-ID、provenance 方案已形成 | Chunking/ingestion 闭环、stable ID、幂等、隔离已落地 | 先补可复算 ID 协议并由主控复核，再编码正式 ID 与服务 |
| RAG-C | `blocked` | 默认不检索、证据不进 Tutor、权限/失败语义断点均已证实 | 在线 grounded answer、默认真实 PgVector、用户隔离已验证 | 先修订 spec 并冻结最小共享边界，再进入 P0 编码 |
| RAG-D | `blocked`（adapter 准备可推进） | 20 题 `verified_v1` 资产、corpus/manifest、离线 evaluator 边界已核实 | 《西西弗神话》产品 baseline 已完成；Tutor 质量已验证 | 可实现只读 validator/adapter/gate；真实 baseline 等待产品索引证明 |

### 关键事实纠偏

1. **RAG-A**：外部 review “通过”只能证明 spec review 声称，不能替代仓内实现和测试。
2. **RAG-B**：Gate 0 唯一入口是待冻结治理边界，不是现有全局事实；OCR/code 现有路径不应被误伤。
3. **RAG-C**：正式 `vector_chunks` Alembic migration 已存在；问题是测试 fixture 仍手工建表，而不是 migration 不存在。
4. **RAG-D**：RAGAS 使用人工 `golden_answer` 作为 `response/reference`，只能称 **gold-answer/context enrichment**，不能称 Tutor 或在线回答质量。

---

## 3. 全局 Blocker 账本

> Blocker ID 为稳定编号；优先级调整时不得换号。

| ID | 名称 | 优先级 | 类型 | 影响任务 | 事实状态 | 不处理后果 | 当前处理 | 责任方 | 可验证解除条件 | 当前允许输出 | 前置/下游 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BLK-001 | PgVector 读侧缺 user/scope 隔离 | P0 | 检索正确性与隔离 | C、D | 已证实 | 跨用户/范围召回，污染 Tutor 与评测 | **冻结最小边界，允许 C 实现** | C | PG/SQLite 在排序和 LIMIT 前执行同一授权矩阵；跨用户测试通过 | `blocked` | 下游 C 在线、D baseline |
| BLK-002 | 产品正式摄入主链缺失 | P0 | 产品主链缺失 | A、B、D | 已证实 | benchmark/fallback 被误报为产品摄入 | **A/B 分责并实施；D 等待证明** | A、B | 真实 EPUB 经 Extractor→Chunking→Ingestion→PgVector，产出可审计 run 证明 | `blocked` | A+B → D |
| BLK-003 | 在线 Evidence 未进入 Tutor | P0 | 在线证据消费 | C、D | 已证实 | 检索存在却回答不 grounded | **冻结职责边界；C 先修 spec 后实现** | C | 默认请求触发 Retriever；sentinel chunk 实际进入 Tutor prompt；连续请求不串证据 | `blocked` | 依赖 BLK-005；下游在线验收 |
| BLK-004 | Chunk/stable-ID/provenance 契约未冻结 | P0 | chunk / metadata / identity | A、B、C、D | 已证实 | 四路产生不兼容 ID；无法严格对齐证据 | **存储边界与 range 基线已冻结（DEC-005/006）；canonical bytes/normalization/测试向量待 B 补证** | B，主控复核 | 无歧义 canonical bytes 规范 + 测试向量；provider round-trip 返回可信 doc/chunk identity | `blocked` | B → C/D |
| BLK-005 | 请求/payload 保真与关联机制缺失 | P0 | 共享数据/接口契约 | C | 已证实 | seed/rule/conductor 丢 query、visibility、evidence | **冻结语义；字段落点由 C 提案** | C | 三条路径保留完整 request/projection；parent_id 与逻辑关联职责可测试 | `blocked` | BLK-003 前置 |
| BLK-006 | backend 与 provider outcome 真实性不足 | P0 | 观测、错误传播与可审计性 | C、D | 已证实 | fake/all-failed/empty 混同，异常可能外露 | **冻结状态语义；C 实现** | C | production 不静默 fake；empty/degraded/failed/invalid-request 可区分；安全摘要测试通过 | `blocked` | C/D |
| BLK-007 | 书籍 baseline 缺正式索引准入证明 | P0 | 离线评测口径 | D | 已证实 | 非本书/混源结果被称产品 baseline | **冻结 admission gate；真实运行后置** | D，A/B 提供输入 | PG+PgVector+vector-only；正式 ingestion attestation；隔离 DB 或可验证 corpus filter | `blocked:*` | A+B → D |
| BLK-008 | 正式 migration 与测试 fixture 分叉 | P1 | 运行环境与基础设施 | B、C、D | 已证实 | 手工 schema 测试无法证明正式部署 | **排期修复** | B/C 协作 | 干净 DB 执行 Alembic 后 provider 测试通过；fixture 不再漂移 | `investigating` | BLK-001/004 验收 |
| BLK-009 | EPUB extractor 尚未实现 | P1 | 产品主链缺失 | A、B | 已证实 | EPUB 仍只是 spec/benchmark 能力 | **允许 A 实现** | A | 工厂注册、动态 EPUB happy/degraded tests、README 同步 | `ready_for_implementation` | BLK-002 上游 |
| BLK-010 | RAG-D adapter/runner/report 不存在 | P1 | 测试缺口 | D | 已证实 | 黄金集不能自动、诚实地验证主链 | **允许只读实现** | D | validator、单次 evaluate、admission gate、状态化 report 测试通过 | `ready_for_implementation`（不含真实 baseline） | BLK-007 前置准备 |
| BLK-011 | shared/course 完整授权模型 | P2 | 共享数据/接口契约 | C | 未冻结 | 过早猜测产品业务语义 | **明确后置** | 主控/产品 | 产品规则明确且 global/private 基线已验证 | `deferred` | BLK-001 后续 |
| BLK-012 | 幂等/replace/delete 生命周期 | P2 | 摄入与 provenance | B | 当前 provider 不支持 | 过早扩展 Gate 0 范围 | **明确后置；Gate 0 append-only** | B 后续 | 一次性摄入闭环和稳定 ID 已验证后另立 spec | `deferred` | BLK-002/004 后续 |
| BLK-013 | strict identity recall 与在线质量阈值 | P2 | 离线评测口径 | C、D | 当前条件不足 | 猜测最终指标/阈值，误导完成状态 | **明确后置** | D | identity 回传、真实 baseline、在线 evidence 消费均完成 | `paragraph-containment proxy` | BLK-003/004/007 后续 |

---

## 4. P0 主控裁决

### BLK-001：最小 visibility 边界

**已证实**：写侧保存 `user_id/scope`，PG/SQLite 读侧均不筛选（`app/infrastructure/rag/pgvector_provider.py:77-180`）。

| | 方案 A：先冻结 global/private 最小矩阵 | 方案 B：等待完整 scope 模型 | 方案 C：只在 API 后过滤 |
|---|---|---|---|
| 做法 | global 公共行可见；private 仅同用户；缺身份拒绝受限检索 | global/private/shared/course 一次设计完 | 检索后再丢弃未授权 chunk |
| 收益 | 立即消除最高风险；范围可验 | 业务语义完整 | 表面改动小 |
| 代价 | shared/course 后置 | 阻断过久且易猜测 | 未授权数据已进入排序/LIMIT，错误 |
| 可验证性 | PG/SQLite 授权矩阵 | 依赖未明确产品规则 | 无法保证 top-k 正确 |
| 主链影响 | Provider 执行过滤，Coordinator 显式传上下文 | 大范围协议改造 | 污染主链 |

**裁决：选择 A。用户已确认历史歧义行采用 fail closed。**

#### P0 规范授权矩阵

| 存储行 | 已认证请求用户 | P0 行为 | 说明 |
|---|---|---|---|
| `scope=global, user_id=NULL` | 任意已认证用户 | 可见 | 唯一规范公共形态 |
| `scope=private, user_id=当前用户` | 同一用户 | 可见 | 唯一规范私有形态 |
| `scope=private, user_id≠当前用户` | 其他用户 | 不可见 | 防止跨用户泄漏 |
| `scope=private, user_id=NULL` | 任意 | 不可见 + 审计 | 所有者缺失，fail closed |
| `scope=global, user_id≠NULL` | 任意 | 不可见 + 审计 | 历史组合语义歧义，用户已确认先 fail closed |
| 未知/缺失 scope | 任意 | 不可见 + 审计 | 禁止猜测未知授权语义 |
| 任意受限行 | 缺失认证身份 | 不检索/invalid-request | 可信身份不得从请求体、用户文本或 LLM 补猜 |

- 现在冻结：P0 RAG scope 只支持 `global` 与 `private`；不复用语义不同的 `MemoryScope`。
- 现在冻结：可信用户身份只来自 `get_current_user` 验签和用户存在性校验；`ChatRequest.user_id` 不参与授权。
- 现在冻结：使用类型化 visibility 上下文沿 API/编排 → Retriever → Coordinator → Provider 单向传递；Provider 不反向依赖 API、WorkspaceState 或 Orchestration。
- 现在冻结：过滤必须在排序、去重、LIMIT、citation、Tutor 输入前；私有文档只对同一受信任用户可见；缺失身份不得读取私有范围。
- 现在冻结：歧义历史行在审计迁移前保持不可见；不得为兼容召回率而临时公开。
- 不冻结：shared/course 的完整业务语义，明确后置为 BLK-011。
- 数据治理后续：先统计 `global+owner`、`private+NULL`、未知 scope，再显式迁移为规范公共或私有形态；迁移结果核验后再评估数据库 CHECK/组合约束。
- 解除条件：PG/SQLite 对同一授权矩阵结果一致；未授权高相似数据不能占据 top-k；证据/citation/Tutor prompt 不含未授权 sentinel；歧义行审计可观测。

### BLK-002：正式摄入责任边界

| | 方案 A：A extractor-only + B 统一摄入 | 方案 B：A 直接做到索引 | 方案 C：D 用 benchmark 补主链 |
|---|---|---|---|
| 做法 | A 文件→str；B adapt/chunk/index | A 同时切块写库 | benchmark 脚本抽取、切块、索引 |
| 收益 | 职责正交、唯一产品入口 | 单窗口看似更快 | 很快得到分数 |
| 代价 | 需要 A/B 对接 | A 越权、形成双套契约 | 测到 benchmark 私有 RAG |
| 是否越权 | 否 | 是 | 是 |
| 可逆性 | 高 | 低 | 低 |

**裁决：选择 A。用户已确认单次 ingestion run 采用全有或全无事务语义，并确认 Gate 0 先使用受控 runner 输出版本化 JSON attestation。**

- A 允许实现 extractor-only，但完成口径仅为“EPUB 提取能力”。
- B 负责新增通用文档 Gate 0 的 adapter/chunk/ingestion/index；`KnowledgeIngestionService` 是 TXT/MD/CSV/PDF/DOCX/EPUB 正式文档摄入的唯一产品服务边界。
- “唯一入口”不追溯覆盖 OCR/Code 专用索引能力、Provider/Coordinator 单元测试或数据库迁移测试。
- `/api/knowledge` 本阶段保持 name/description CRUD；Gate 0 使用受控项目 runner 和集成测试调用 Service，上传 API 明确后置。
- Extractor 保持 `extract(file_path) -> str`；空串归约为 `extraction_empty` 非成功状态，不进入 chunk/index，也不得猜测具体失败原因。
- 摄入侧复用 BLK-001：仅允许 `global+NULL` 或 `private+可信 owner`；歧义组合和未知 scope fail closed。
- 单次 ingestion run 必须全有或全无：所有计划 chunk 在一个事务边界中完整写入；任一写入失败则整体 rollback，不生成成功 attestation。
- 全有或全无不等于幂等：成功 run 再次执行仍可能追加重复数据；replace/upsert/delete 继续后置为 BLK-012。
- Coordinator/Provider 的写入契约必须从仅返回 `None` 增强为可确认 planned/written count 与失败状态，支撑 `IngestResult`。
- `IngestResult` 最少记录：status、ingestion_run_id、source_sha256、source_format、doc_id、normalizer/chunking 版本、planned/written chunk count、backend、dialect、scope/owner、安全错误码/摘要。
- Gate 0 暂不新增 `ingestion_runs` 表；首本书由受控产品 runner 将成功 `IngestResult` 保存为版本化 JSON attestation，禁止包含密钥、连接串或原始敏感异常。
- benchmark 不得生成或伪造产品 attestation；RAG-D 只能消费正式产品 runner 的证明。
- BLK-004 canonical bytes 协议通过前，可以实现提取、适配、纯切分和校验壳，但不得写入临时 hash 并称为 production stable ID。
- 解除条件：真实 EPUB 完整经过产品链；provider 失败回滚后无部分行残留；成功结果 planned=written 且与数据库核验一致；版本化 JSON 可关联输入 SHA、版本、后端、目标索引和 chunk 数；RAG-D admission 能独立消费并核验该证明。

### BLK-003 + BLK-005：Evidence 消费与请求保真

| | 方案 A：Orchestrator 受控投影 | 方案 B：Tutor 直订 evidence | 方案 C：Tutor 读共享 evidence_pool |
|---|---|---|---|
| 做法 | Retriever 发结果；Orchestrator 关联并投影给 Tutor | Tutor 直接消费 Retriever 事件 | Tutor 从共享状态取最近证据 |
| 收益 | 保持“Agent 不互调、编排器路由”边界 | 接线短 | 改动看似小 |
| 代价 | 要补 payload 保真、关联和投影 | Agent 耦合、绕过 action 边界 | 跨轮污染、生命周期不清 |
| 可验证性 | 可用 sentinel、request 关联测试 | 需重写边界 | 很难证明不串轮 |
| 主链影响 | 补齐既有主链 | 改变架构范式 | 引入隐式旁路 |

**裁决：选择 A。用户已确认检索关联使用受控 payload `retrieval_id`，不修改全局 Event schema；并确认第一轮 P0 `max_attempts=1`，不自动 query expansion。**

- 现在冻结：Retriever 是唯一检索发起者；Orchestrator 是 evidence→Tutor 的唯一投影边界；Tutor 不直连基础设施，也不从未关联的 `evidence_pool` 读取“最近证据”。
- 现在冻结：seed/rule/conductor 三条路径都必须保留完整请求或证据投影。
- 现在冻结：`parent_id` 只表达直接物理因果；检索相关 payload 的 `retrieval_id` 表达一次逻辑检索单元。
- 现在冻结：初始 Retriever `ActionRequested.id` 作为 `retrieval_id`；evidence/failure、未来 retry 与 Tutor projection 继承该值；`attempt` 只由 Orchestrator 管理。
- 现在冻结：第一轮 P0 `attempt=1`、`max_attempts=1`；不自动执行 `retriever_expand_query`。低质量 evidence 进入受控降级，不在本轮新增 query rewrite 契约。
- 现在冻结：默认 seeds 改为 UserMessage、TopicEntered、完整 Retriever ActionRequested；删除无证据抢跑的首轮最终 Tutor action。
- 现在冻结：采用检索微回合屏障。Evidence/failure 到达后，Critic quality observation 优先于 retrieval barrier tick；tick 只生成一次最终 Tutor action。Critic 无输出时按机械状态继续并标记 quality unavailable，不得卡死。
- 现在冻结：Orchestrator 为每个 `retrieval_id` 维护会话内路由状态，至少包含请求、结果、attempt、quality、直接因果 ID 和 `final_tutor_action_emitted`；同一 retrieval 最多产生一次最终 Tutor action。
- 现在冻结：EvidenceProjection 至少包含 retrieval_id、retrieval_status、attempt、已授权 chunks、citations、sources_used、safe_summary；Tutor 不接触 Provider、Embedding、SQL 或原始异常。
- 解除条件：初始 action→evidence/failure→Tutor action→Tutor output 的 parent chain 正确；全链 retrieval_id 一致；sentinel 实际进入 Tutor LLM user prompt；连续请求证据不串轮；重复 evidence/迟到 quality/重复 tick 不重复回复；empty/failed/Critic 无输出仍产生一次受控回复而不落入空回复 fallback。

### BLK-004：Chunk identity 与 provenance

| | 方案 A：先冻结边界，bytes 机制补证后再冻结 | 方案 B：立即采纳当前字符串拼接公式 | 方案 C：使用 benchmark paragraph_id |
|---|---|---|---|
| 做法 | 先定字段/责任/权威源；B 补 canonical bytes 与向量 | 直接实现现 spec hash 拼接 | paragraph_id 作为生产 ID |
| 收益 | 防止错误协议固化 | 开工快 | 最省实现 |
| 代价 | 正式 ID 编码稍后开始 | 字段边界/Unicode/range 有歧义 | 单 benchmark 污染产品契约 |
| 可验证性 | 明确测试向量后可跨实现复算 | 当前不可跨实现证明 | 仅单书有效 |
| 对 D 影响 | 先用 containment proxy | 可能产生错误 strict recall | 越权冻结 |

**裁决：选择 A。**

现在冻结：

- 生产 `doc_id/chunk_id` 与 benchmark `paragraph_id` 分离；
- ChunkDocument 必须携带 content、doc identity、chunk identity、source、scope/user、版本与 source locator；
- 写前顶层 `doc_id` 与 metadata 身份必须一致；
- 读侧 SQL 顶层 `doc_id` 是权威来源，provider 必须补齐/覆盖返回 metadata；
- Gate 0 是 append-only，不承诺幂等、替换、删除。
- `vector_chunks` 新增可空顶层 `chunk_id` 列；协议生效后新摄入必填，不加唯一约束（DEC-005）。
- `canonical_element_range` 坐标基线为 0-based + Unicode code point + 半开 `[start,end)`；格式特有 `source_locator` 仅 metadata 审计，不参与 chunk 身份（DEC-006）。

退回 B 补证：

- Unicode 形式；
- 换行/空白归一化顺序；
- 无歧义 canonical serialization/framing；
- element 序号、offset 单位与区间语义已由 DEC-006 冻结；仍待补 Unicode normalization form 与换行/空白归一化顺序细节；
- 至少两组可公开复算测试向量。

在补证前，B 可做纯切分逻辑和测试壳，不得生成“正式 production stable ID”。

### BLK-006：真实 backend 与 outcome

| | 方案 A：production 显式 PgVector + 结构化 outcome | 方案 B：保留静默 fake fallback | 方案 C：继续异常即 empty |
|---|---|---|---|
| 做法 | 在线生产明确使用 PgVector；区分 empty/degraded/failed/invalid-request | pgvector 不可用时回 fake | provider 异常继续吞掉 |
| 收益 | 结果可审计、不虚假完成 | 本地始终有结果 | 改动最少 |
| 代价 | 环境不满足时诚实失败 | fake 冒充产品能力 | 无法解释结果 |
| 安全性 | 对外稳定码/安全摘要 | 易误报 | 可能泄露或误判 |

**裁决：选择 A。**

- 默认配置当前仍是 fake（`app/core/config.py:20-23`），因此 production composition 必须显式要求 pgvector 或等价依赖注入。
- 禁止生产静默回退 fake。
- 冻结 aggregate 状态：`empty`、`degraded`、`failed`、`invalid-request`。
- 原始异常、SQL、连接串、堆栈不得进入 Tutor/API payload；内部日志保留可分类诊断。

### BLK-007：RAG-D baseline admission

| | 方案 A：严格准入后再跑 | 方案 B：先跑 fake/SQLite 代理分数 | 方案 C：benchmark 自建索引 |
|---|---|---|---|
| 做法 | PG+PgVector+vector-only+正式 ingestion+语料隔离/filter | 先得到临时分数 | D 自行摄入/检索 |
| 收益 | 结论可解释、对象真实 | 快速观察 | 端到端看似完整 |
| 代价 | 等待 A/B 产品链 | 极易被误报为真实 baseline | 违反职责、平行 RAG |
| 当前允许结论 | 产品 Retriever baseline | 仅开发代理，不纳入正式结果 | 禁止 |

**裁决：选择 A。**

运行前必须同时证明：

1. `rag_backend=pgvector`；
2. 实际 provider class 为 `PgVectorProvider`；
3. DB dialect 为 PostgreSQL；
4. 被测 coordinator provider 集合严格为 `{"vector"}`，因为 `evaluate()` 当前固定 `sources=None`；
5. 正式 ingestion attestation 可关联输入 EPUB SHA、版本、目标索引和块计数；
6. 使用仅含本书当前产物的隔离 DB，或存在已验证的 corpus/doc provenance 查询过滤。

RAGAS 只称 **gold-answer/context enrichment**；第一轮正式主指标是 Retriever 的机械召回代理，不外推 Tutor。

---

## 5. 已冻结边界与明确后置

### 已冻结

1. **职责**：A=extractor；B=chunk/ingestion；C=online routing/visibility/outcome；D=只读验证。
2. **产品链**：不得绕过 `EmbeddingService → PgVectorProvider → RAGCoordinator → RetrieverAgent → RetrieverAgent.evaluate`，在线生成额外要求 evidence 经 Orchestrator 进入 Tutor。
3. **visibility 最小基线**：global/public 可见；private 仅同一受信任用户；缺身份不得读 private；过滤在排序/LIMIT 前。
4. **在线默认 source**：P0 默认请求限定 `sources=["vector"]`；保持 `sources=None` 的既有多源语义和回归测试（`tests/integration/test_retriever_integration.py:202-230`）。
5. **identity 边界**：benchmark paragraph ID 不得成为生产 ID；SQL 顶层 doc ID 为读侧权威；stable ID 不等于幂等。
6. **Gate 0 生命周期**：append-only；不承诺 upsert/replace/delete。
7. **评测口径**：D 第一轮使用 paragraph-containment proxy；RAGAS 是 gold-answer/context enrichment；不证明在线 Tutor。
8. **部署事实**：正式 Alembic migration 已存在；手工 fixture 不能替代正式迁移验收。

### 尚未冻结，禁止自行假定

- stable ID 的 canonical bytes 算法、Unicode normalization、换行/空白顺序与测试向量（range 坐标与区间已由 DEC-006 冻结）；
- EvidenceProjection 的最终字符/token 上限、citation schema；
-用户可见降级文案与具体错误码集合。

### 明确后置

- shared/course 完整权限模型；
- 重导幂等、replace/delete、文档生命周期；
- 图检索 / LightRAG；
- OCR/code 全 provider visibility 统一化；
- strict identity recall；
- 在线 grounded answer 正式阈值；
- 上传 API；
- EPUB 全标准兼容与 ZIP bomb 治理。

---

## 6. 下一阶段核心 TodoList

> Todo 的完成以证据为准；勾选时必须附源码、测试、运行结果或外部可审计证明。

### Phase 0：主控回应与 spec 收敛（必须先完成）

- [ ] **M-01** 向 RAG-A 分发主控回应：允许 extractor-only 实现，禁止宣称摄入完成。
- [ ] **M-02** 向 RAG-B 分发主控回应：range 基线已冻结（DEC-006），补 canonical bytes/normalization/测试向量，正式 ID 编码继续 blocked。
- [ ] **M-03** 向 RAG-C 分发主控回应：修正 migration 事实；补 evidence routing、visibility、outcome、production composition。
- [ ] **M-04** 向 RAG-D 分发主控回应：批准只读 adapter/gate；真实 baseline 继续 blocked。
- [ ] **M-05** 四个窗口分别只回写自己的 `RAG-X.md`，确认接受/请求修订。
- [ ] **M-06** 主控复核四份回执；任何共享契约冲突只在本主清单裁决。

### Phase 1A：RAG-A EPUB extractor-only（可并行）

- [ ] **A-01** 实现 `app/infrastructure/rag/extractors/epub_extractor.py`。
- [ ] **A-02** 在 `get_extractor()` 注册 `.epub` / `.EPUB`。
- [ ] **A-03** 动态 EPUB fixture 验证 OPF spine 顺序、strict UTF-8、`<br>`、HTML entity、块分隔。
- [ ] **A-04** 验证损坏 ZIP、缺 container/OPF/spine、无效 UTF-8均返回空串。
- [ ] **A-05** 去重 `docs/asset-inventory.md` 中 EpubExtractor 事实源，禁止产生第三条重复记录。
- [ ] **A-06** 同步 README：只声明 extractor 支持 EPUB，不宣称上传、chunk、索引或检索完成。
- [ ] **A-07** 完成单测、代码 review，并将证据回写 `RAG-A.md`。

**A 完成口径**：仅“EPUB extractor 已实现并验证”；BLK-002 仍需 B 接通摄入。

### Phase 1B：RAG-B 协议补证与纯逻辑准备（可与 A/C/D 并行）

- [ ] **B-01** 提交 canonical document bytes 规范：Unicode、换行、空白、字段 framing、版本字段。
- [ ] **B-02** range 坐标与区间已由 DEC-006 冻结；提交剩余 canonical chunk 规范：Unicode normalization form、换行/空白归一化顺序、canonical chunk text 序列化。
- [ ] **B-03** 提供至少两组含 Unicode、CRLF、空白、元素偏移的 doc/chunk ID 测试向量。
- [ ] **B-04** 主控独立复核 B-01~03；通过前不得实现正式 production ID。
- [ ] **B-05** 准备纯 Chunking 算法测试：空白、长段二切、短段合并、overlap、顺序保持。
- [ ] **B-06** 准备 provider provenance round-trip 测试壳与冲突负例。
- [ ] **B-07** 修订 RAG-B spec：唯一入口仅约束“新文档 Gate 0”，不误伤 OCR/code 既有路径。

### Phase 1C：RAG-C spec 修订（与 A/B/D 并行，编码前必须完成）

- [ ] **C-01** 修正“migration 未核实”：正式 Alembic revision 已存在，问题是 fixture 未消费它。
- [ ] **C-02** 写清 `RetrievedEvidence/RetrievalFailed → Orchestrator → Tutor` 各分支。
- [ ] **C-03** 写清 seed/rule/conductor 的 RetrievalRequest/EvidenceProjection 保真表。
- [ ] **C-04** 关联字段落点已由 DEC-003 裁决（受控 payload `retrieval_id`，不扩 Event schema）；C spec 据此记录 blast-radius 说明与三条路径保真测试设计，不再就落点本身二次裁决。
- [ ] **C-05** 写清 global/private visibility 真值表及 PG/SQLite 强制点。
- [ ] **C-06** 写清 empty/degraded/failed/invalid-request 的 provider/aggregate 归约。
- [ ] **C-07** 写清 production online composition：显式 PgVector、不可用时诚实失败、禁止 fake fallback。
- [ ] **C-08** 主控复核修订后的 C spec，达到可编码状态。

### Phase 1D：RAG-D 只读准备（可并行；禁止跑正式 baseline）

- [ ] **D-01** 实现题集/corpus/manifest/SHA/locator/excerpt validator。
- [ ] **D-02** 实现题集到瞬态 `evaluate` 输入的 adapter；完整 paragraph text → `golden_chunks`。
- [ ] **D-03** 实现 admission gate：backend/provider/dialect/provider-set/attestation/corpus isolation。
- [ ] **D-04** 实现 report envelope，区分 blocked、infrastructure_inconclusive、judge_degraded、completed。
- [ ] **D-05** 保证每题只调用一次 `evaluate()` 或 `ComponentBench.run()`，不得双跑。
- [ ] **D-06** 报告中固定名称 `paragraph-containment proxy` 与 `gold-answer/context enrichment`。
- [ ] **D-07** 单元测试只验证资产、映射、准入和状态；上游未就绪时不得生成产品分数。

### Phase 2：共享基础能力编码

> 前置：B-01~04 通过；C-08 通过。

- [ ] **B-08** 实现 `ChunkingService` 无状态纯服务。
- [ ] **B-09** 实现 `KnowledgeIngestionService` 薄编排。
- [ ] **B-10** 实现正式 doc/chunk ID 与 metadata 校验。
- [ ] **B-11** 修复 provider provenance round-trip：SQL doc ID 权威，chunk ID/locator 不丢。
- [ ] **C-09** 扩展 visibility 上下文端到端传递并在 PG/SQLite 查询执行过滤。
- [ ] **C-10** 实现 provider outcome 与安全摘要；移除对外原始 `str(exc)`。
- [ ] **C-11** online production 显式装配 PgVectorProvider，禁止静默 fake。
- [ ] **I-01** 让 PG/SQLite 测试从正式 migration/schema 契约消费，不再各自漂移。

### Phase 3：在线 evidence 接线

> 前置：C-09~11 完成，C 共享协议通过测试。

- [ ] **C-12** 默认在线请求先触发 Retriever，不并发无证据最终 Tutor action。
- [ ] **C-13** Orchestrator 消费 evidence/failure 并构造受控 Tutor projection。
- [ ] **C-14** Tutor 将受限 evidence 注入当前回合 prompt，不直连 RAG infrastructure。
- [ ] **C-15** 覆盖 empty/degraded/failed/invalid-request 的受控回复。
- [ ] **C-16** sentinel chunk + 双连续请求证明证据实际消费且不串轮。
- [ ] **C-17** `/api/chat` 与 `/api/chat/stream` 共享同一核心因果链。

### Phase 4：首本书正式摄入与证明

> 前置：A-01~07、B-08~11、C-09~11 完成。

- [ ] **F-01** 从干净 PostgreSQL 数据库执行正式 Alembic migration。
- [ ] **F-02** 真实 EPUB 通过产品 Extractor→Chunking→Ingestion→Embedding→PgVector。
- [ ] **F-03** 产出 ingestion attestation：EPUB SHA、normalizer/chunking 版本、目标 DB/index、doc/chunk 数、失败数。
- [ ] **F-04** 验证 doc/chunk identity 与 source locator round-trip。
- [ ] **F-05** 验证跨用户/范围隔离；无权限内容不进入排序、citation 或 Tutor。
- [ ] **F-06** 记录 append-only 边界；不把 stable ID 误写成幂等。

### Phase 5：黄金集 Retriever baseline

> 前置：F-01~05，D-01~07。

- [ ] **D-08** admission gate 全绿后运行 20 题，每题一次。
- [ ] **D-09** 保存 raw metrics、provider/dialect、sources_used、latency、degraded、attestation 引用。
- [ ] **D-10** 输出 Recall@1/3/5、context-precision proxy、redundancy 与失败分类。
- [ ] **D-11** RAGAS 可用时只作为 enrichment；不可用标 `completed_judge_degraded`。
- [ ] **D-12** 人工复核零召回、高冗余、疑似跨 corpus case。
- [ ] **D-13** 不宣称 strict identity recall，除非 BLK-013 后续解除。

### Phase 6：在线 grounded answer 端到端验证

> 前置：Phase 3、Phase 4、Phase 5 完成。

- [ ] **H-01** 用黄金题驱动真实 `/api/chat` 与 `/api/chat/stream`。
- [ ] **H-02** 证明 Tutor prompt 收到当前问题对应的产品 chunk/citation。
- [ ] **H-03** 区分召回失败、projection 失败、生成失败与基础设施失败。
- [ ] **H-04** 验证无权限/跨用户证据永不进入生成输入。
- [ ] **H-05** 在真实结果基础上另行制定在线质量指标和阈值；不得提前猜测。

---

## 7. 验证状态表

| 声称 | 状态 | 依据 |
|---|---|---|
| 默认 `rag_backend` 为 fake | ✅ 已验证 | `app/core/config.py:20-23` |
| `sources=None` 保留多 provider 语义且有集成测试 | ✅ 已验证 | `app/infrastructure/rag/coordinator.py:100-131`; `tests/integration/test_retriever_integration.py:202-230` |
| 正式 `vector_chunks` migration 已存在 | ✅ 已验证 | `alembic/versions/20260622_add_vector_chunks_table.py:21-69` |
| SQLite provider fixture 手工建表 | ✅ 已验证 | `tests/unit/infrastructure/test_pgvector_provider.py:40-72` |
| PG integration fixture 手工建表 | ✅ 已验证 | `tests/integration/test_pgvector_real.py:48-82` |
| 题集有 20 个 `verified_v1` case | ✅ 独立核验报告机械计数；题集全文 20 case | `benchmarks/rag/books/the-myth-of-sisyphus/questions.v1.yaml:1-567` |
| baseline 已运行 | ❌ 未发现 | `benchmarks/rag/books/the-myth-of-sisyphus/README.md:167-172` 仍未勾选 |
| range 坐标与区间语义已冻结（DEC-006） | ✅ 已确认 | `docs/designs/2026-07-27-rag-p0-confirmed-decisions.md` DEC-006 |
| stable ID canonical bytes/normalization 已冻结 | ❌ | B spec 仍缺无歧义序列化、Unicode form、换行/空白顺序与测试向量 |
| Tutor 已消费 evidence | ❌ 源码反证 | `app/harness/orchestrator.py:80-98`; `app/agents/tutor.py:32-97` |
| PgVector 已按 user/scope 隔离 | ❌ 源码反证 | `app/infrastructure/rag/pgvector_provider.py:131-180` |
| 正式 EPUB ingestion 已打通 | ❌ 未发现 | extractor 无 EPUB；chunk/ingestion service 待建 |

---

## 8. 下一轮主控复核触发条件

满足任一条件即触发主控重读状态片段与更新本账本：

1. RAG-A 回报 extractor 实现、测试、README/资产清单证据；
2. RAG-B 提交 canonical bytes/normalization 规范与测试向量（range 基线已由 DEC-006 冻结）；
3. RAG-C 提交修订后 spec 及关联字段落点对照；
4. RAG-D 完成 adapter/admission/report 的只读测试；
5. 任一任务请求新增、撤销或修订共享裁决；
6. 正式 ingestion run、真实 PG baseline 或在线 E2E 产生可审计证据；
7. blocker 解除条件与实际代码/运行结果发生矛盾。

主控复核时必须：更新 blocker 的事实状态和优先级；保留稳定 ID；不得仅依据状态片段自述把任务升级为 verified。

---

## 9. 向各任务窗口分发的主控回应摘要

### RAG-A

- **已冻结**：Extractor 保持 `file_path → str`；A 不负责 chunk/index。
- **允许**：实现 extractor、factory、tests、README、资产去重。
- **禁止**：宣称正式摄入完成或直接写向量库。
- **回写要求**：只更新 `docs/rag-foundation-status/RAG-A.md`，附实现与测试证据。

### RAG-B

- **已冻结**：新文档 Gate 0 的职责、identity/provenance 边界、append-only 非承诺。
- **已冻结**：新文档 Gate 0 的职责、identity/provenance 边界、append-only 非承诺、`chunk_id` 顶层可空列（DEC-005）、range 坐标基线（DEC-006）。
- **未冻结**：canonical bytes/Unicode form/换行空白顺序/测试向量（range 坐标与区间已由 DEC-006 冻结）；在补证前 production ID 编码 blocked。
- **允许**：协议补证、纯切分测试、provider round-trip 测试壳。
- **禁止**：另建 evaluator、宣称幂等/隔离、把 paragraph ID 当生产 ID。
- **回写要求**：只更新 `docs/rag-foundation-status/RAG-B.md`。

### RAG-C

- **已冻结**：Orchestrator 投影、vector-only online 默认、最小 visibility、结构化 outcome、production 禁止 fake fallback。
- **未冻结**：projection 字符/token 上限、最终 citation schema（关联字段落点已由 DEC-003 冻结为受控 payload）。
- **允许**：先修订 spec；主控复核后编码。
- **禁止**：只改 seed 就宣称接通、Tutor 直连 RAG、猜测 shared/course。
- **回写要求**：只更新 `docs/rag-foundation-status/RAG-C.md`，并修正 migration 事实。

### RAG-D

- **已冻结**：只读验证器、严格 admission gate、paragraph-containment proxy、gold-answer/context enrichment。
- **允许**：validator、adapter、gate、report、单元测试。
- **禁止**：上游未就绪时跑/发布产品 baseline，自建摄入/索引/检索。
- **回写要求**：只更新 `docs/rag-foundation-status/RAG-D.md`。

---

## 10. README 更新判据

本轮只更新研发治理主清单和资产索引，不改变功能、架构、API 或使用方式，因此根 README 暂不修改。以下事件发生后必须同步 README：

- EPUB extractor 真实实现并通过测试；
- Chunking/KnowledgeIngestionService 正式落地；
- 在线 RAG 主链与用户隔离接通；
- 新增用户可调用的摄入命令/API；
- 运行、迁移或测试方式发生变化。
