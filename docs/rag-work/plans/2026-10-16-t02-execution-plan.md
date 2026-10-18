# T02 写入确认与产品预计划接口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 执行时使用 superpowers:subagent-driven-development 或 superpowers:executing-plans，逐项执行 checkbox。先载入 karpathy-guidelines；本计划仅含文字设计与命令，不含实现或测试代码。

**当前状态：实施完成，主窗口定向复审通过，组合离线回归通过。** [执行证据](../evidence/t02/2026-10-16-execution.md)；[主窗口验收](../evidence/2026-10-16-first-wave-execution.md)。四文件158项通过；Ruff仅一项既有E402。下文保留批准时设计和步骤，实际执行与命令替代以证据为准；不表示真实PG或G1通过。

**Goal：** 产品摄入只准备一次，交付不可变准备结果和无正文清单，并仅对完成 commit 且数量一致的写入返回成功。

**Architecture：** 保持 Extractor → ChunkingService → KnowledgeIngestionService → Coordinator → PgVectorProvider 的依赖方向。准备与写入分离；写入侧先完整验证向量，再开始 insert。T02 不依赖 T04 新模块先实现，不生成运行意图、数据库快照或证明。

**Tech Stack：** Python、现有 dataclass/标准库 SHA-256/JSON、SQLAlchemy 同步连接、现有 pytest；不新增依赖，不执行迁移。

**Spec：** `docs/rag-work/specs/2026-10-16-rag-mvp-contracts-v1.md`，契约集 `rag-mvp-contracts-v1.0.1`，冻结 SHA-256 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。2026-10-16 已重读勘误 A1/A2/B1 并只读核验当前字节；原 v1 仅作历史追溯，归档 `docs/rag-work/specs/2026-10-16-rag-mvp-contracts-v1-original.md`，不作为执行基线。

## 全局约束与来源

- 唯一依据为上述 spec 的接口表、A1/A2/A3、C；冻结记录 `superpowers/rag-foundation/2026-10-16-t00-contract-freeze-record.md`；调度 `superpowers/rag-foundation/2026-10-16-rag-mvp-dag-and-scheduling.md`。设计追溯 raw `superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan.md`。执行者先阅读这些文件，发现 SHA 不符暂停而非适配未知版本。
- `prepared-ingestion-v1`、`prepared-manifest-v1`；旧 `doc-v1/doc-norm-1/chunk-v1/chunk-policy-1` 不重命名。默认策略 500/50/8192 是项目策略，不是模型实测上限。
- 保留现有公开 import 和完整 `ingest_file` 参数及默认值；不加上传 API、表、替换删除、幂等、upsert、重试写库或新的业务范围。
- T00 是硬前置；T04 与 T02 并行。T02 不能导入尚未交付的 `contracts.py`、`embedding_identity.py`、`ingestion_attestation.py`。标准库内部规范化辅助函数属于 T02 内部细节，不能擅自发布为新共享 API；向 T04/T08 交付同一规范 JSON 测试向量供一致性比对。
- 本次编写仅允许此 plan 文件；README 由主控单写。执行阶段的写入权见下表，必须经主控 review 后释放。

## 第一层：模块总览与事实基线

当前 `knowledge_ingestion.py` 在 `ingest_file` 中混合提取、切块和写入；`IngestResult` 为 frozen dataclass，字段为 status/doc_id/planned_chunk_count/written_chunk_count/warnings。当前判断 `written != len(docs)` 会把 True 与 1 混同；warnings 含 provider 原返回值，需改为安全固定摘要。`PgVectorProvider.index` 用 zip 且返回 docs 长度，短向量列表可能少写却报计划数；已有 insert/commit 异常 rollback，但没有数量、维度、有限数校验。`EmbeddingService.dim` 每次读取可变 settings；`embed_many` 每十条调用 SDK，响应超长可被回填逻辑截断，过短可能 IndexError。以上是代码事实，不把历史测试通过数当本包证据。

模块目标：准备只读源文件并调用一次现有工厂、提取器和切块器；交付嵌套不可变快照，写入前重新校验内容摘要与身份；provider 接收完整批次且只在 commit 成功后确认实际执行条数。内部异常保真向上传播，commit 异常不代表数据库一定没写入。

| 执行阶段文件 | 权限与职责 |
|---|---|
| `app/harness/knowledge_ingestion.py` | 修改；准备类型、异常、清单、两阶段摄入与兼容入口 |
| `app/infrastructure/rag/pgvector_provider.py` | 修改；整批校验、真实确认计数、事务失败保真 |
| `app/infrastructure/rag/embedding.py` | 修改；固定实例维度、批次响应完整性，维持请求参数 |
| `tests/unit/harness/test_knowledge_ingestion.py` | 修改；现有贯通回归和新的准备/兼容用例 |
| `tests/unit/infrastructure/test_pgvector_provider.py` | 修改；畸形批次、事务及确认用例 |
| `tests/unit/infrastructure/test_embedding.py` | 修改；维度快照、响应短长/多批/空输入回归 |
| `docs/rag-work/evidence/t02/2026-10-16-execution.md` | 执行时创建；无正文证据索引、命令与结论，不能现在填结果 |

不创建其他产品或测试模块；`chunking_service.py`、`tests/unit/harness/test_chunking_service.py` 只读回归。禁止改 T04 三个新模块和测试、T08 runner/snapshot、coordinator、schema/迁移、integration fixture、冻结 spec/raw/DAG、README/主清单及其他窗口状态。若修复需要这些文件，向主控申请明确串行变更，不在本包偷扩范围。无 commit/push，不执行真实服务测试。

## 第二层：子模块接口、数据流与状态

### 2.1 准备与快照

唯一类型路径为 `app.harness.knowledge_ingestion.PreparedIngestion` 和同模块 `IngestionPreparationError`。前者只持准备快照，不含 run/target/embedding；后者继承 ValueError，公开字段 status/safe_summary；对应精确值为 unsupported/“不支持的文档格式”、extraction_empty/“未提取到可用文本”、invalid_request/“摄入参数无效”，不带原始提取错误/路径/正文。

`prepare_file(file_path: str, *, import_namespace: str, scope: str = global, user_id: int 或 null = null, chunking_spec_version: str = chunk-policy-1, policy: ChunkPolicy 或 null = null)` 返回 PreparedIngestion。先校验请求，再检查支持格式和源字节 SHA，使用现有提取/切块流程一次，最后重读源字节 SHA；文件改变即 invalid_request。不调用 embedding/index/commit。预期不支持、空提取/空切块转对应准备异常；未知提取/IO编程错误不能不加区分地伪装成 extraction_empty。

状态流为请求 → 已校验 → 已提取切块 → 已核对源 SHA → prepared；任何准备失败无写库。没有“准备失败但仍允许写入”的状态。owner 对外由 user_id 一对一映射，global/null，private/正非bool整数；拒绝未知 scope、负数/零/bool/字符串 ID。

### 2.2 写入与兼容

`ingest_prepared(prepared: PreparedIngestion)` 返回原位置 IngestResult。消费快照并校验准备 schema、元数据、manifest 和 documents 一致性；验证失败在 index 前以 ValueError 拒绝。通过后转换为隔离的可写普通 docs dict，调用现有 coordinator.index_documents(docs, source=vector) 一次，不能重新提取或切块。写入故障抛原内部异常。只有非bool整数 written 与正 planned 相等才 status=ok；None、不符或非法计数均 index_unconfirmed，不能推断实际数据库为空。

`ingest_file` 完整签名与 `prepare_file` 相同，内部依次调用两阶段接口各一次。unsupported/extraction_empty 映射原非成功 IngestResult，无效参数仍 ValueError；其余内部异常原样抛出。保留 warnings 列表类型及原 oversized 安全提示语义，不把库/SDK异常写入 warnings。

### 2.3 向量批次与事务

`PgVectorProvider.index(docs: list[dict]) -> int 或 null` 保留协议，产品成功路径返回 int。空列表直接 0，无 embedding/连接。非空整批 embedding 后，在任何 insert 前确认数量相等、每向量等于当前绑定维度、每元素为非bool有限数值；之后逐条执行，记录实际成功执行数，commit 成功才返回。任何 insert/commit 异常尝试整体 rollback，并传播原始失败；rollback 再失败不能替代最初失败或生成成功。禁止遇错返回 0 或自动再 index。

EmbeddingService 保留构造参数、dim/client/embed_one/embed_many 签名，实例构造固定其维度，拒绝无效维度。请求仍只有 model/input，不加入 dimensions/encoding_format 请求参数。每个 SDK 批次先确认响应数量与本批输入一致；每项 index 必须为非 bool 整数、唯一且完整覆盖本批 0 至 batch_size-1，按 index 重排为输入顺序后，再回填原始空字符串位置。每批索引从 0 重新计算，不以全请求序号解释。缺失、重复、负值、越界、bool/字符串索引及长短响应均以不含响应原文的 ValueError 拒绝，不能截断、猜测顺序或回退按列表顺序处理。全部批次验证成功后才返回；任一批次非法不得给 provider 部分结果或触发 insert。provider 仍需防御任意注入 embedding service 的畸形返回，不能只依赖 SDK 层验证。

## 第三层：逐函数、字段与数据结构设计

### 3.1 PreparedIngestion 与内部辅助职责

字段精确为 schema_version、source_sha256、source_format、import_namespace、doc_id、scope、owner、normalizer_version、chunking_version、doc_protocol、chunk_protocol、chunk_policy、documents、manifest、warnings。schema_version 固定 prepared-ingestion-v1；除 owner 均不为 null；版本/身份字符串非空；warnings 为安全字符串 tuple；chunk_policy 为精确三键只读 mapping（chunk_size/chunk_overlap/hard_limit）。chunk_size/hard_limit 为正整数，chunk_overlap 为非负整数且小于 chunk_size，hard_limit≥chunk_size，全部拒绝 bool；不修改只读 chunking_service 的现有实现，在准备边界确保该契约。

documents 为有序只读序列，每项和所有 metadata/locator 嵌套结构递归冻结，不能仅 frozen 外层 dataclass。对进入构造器的可变对象作隔离快照，构造之后源字典变化不影响对象；向 index 传出时递归解冻到新的普通 dict/list，coordinator/provider 不得回写准备对象。保持现有 content/doc_id/scope/user_id 和 metadata 的 provenance，包括额外的 element_types/oversized 标记。

内部辅助函数按职责设计（私有命名可在 review 时确定，不成为跨包接口）：请求/策略验证输入上述参数输出安全有效上下文；字节 SHA 输入 Path 输出小写摘要；递归冻结/解冻输入 JSON 型嵌套值输出只读快照/隔离副本；规范 JSON 输入可序列化值输出 UTF-8 字节；准备行构建输入 docs 输出 rows；准备一致性验证输入快照输出无返回、失败 ValueError。不得通过反序列化正文到日志实现调试。

准备校验逐项检查：所有 doc_id 与顶层一致、metadata.doc_id 一致、scope/user_id 与准备身份一致；chunk_index 为从0连续的非bool整数，chunk_id 非空唯一；实际 normalizer_version/chunking_spec_version/source_format 与快照一致；source_locator 为严格 JSON 对象；planned>0。doc_protocol/chunk_protocol/normalizer 从现有 chunking_service 常量读取；chunking_version 使用实际 chunking_spec_version，不能写成 chunk-v1。不改 DEC-012 稳定 ID 算法，也不重做 content normalization。

### 3.2 to_intent_metadata 与 prepared-manifest-v1

`to_intent_metadata(self) -> dict` 返回独立 JSON 普通对象，精确键：schema_version、source_sha256、source_format、import_namespace、doc_id、scope、owner、normalizer_version、chunking_version、doc_protocol、chunk_protocol、chunk_policy、warnings。warnings 转 list；任何返回对象被修改不得反向修改准备快照。禁止 documents/content、run ID、目标、embedding、数据库信息。此对象供 T08 写入 intent.preparation，不在 T02 落盘。

manifest 精确键：schema_version=prepared-manifest-v1、doc_id、rows、row_count、manifest_sha256。rows 对外按 chunk_index 展示；每行精确为 doc_id、chunk_id、content_sha256、chunk_index、scope、owner、source_locator。row_count 为正非bool整数且等于 rows 长度；正文摘要对实际 content UTF-8 直接 SHA。manifest 是嵌套只读快照，不含正文。

规范 JSON：键按 Unicode 码点排序、UTF-8、不转义非ASCII、紧凑分隔、标准 null/true/false、禁止 NaN/Infinity，不进行额外 Unicode/URL 归一。manifest_sha256 只取 rows：先把每行完整规范 JSON 字节排序，保留重复项，再对所得数组规范 JSON 取 SHA。展示序与摘要序分离，不按 chunk_id 集合去重。ingest_prepared 重新构建 rows/摘要并比对 manifest，也检查身份与计数，不仅相信自报 digest。

固定非自生成向量直接复制 T04 plan §3.2，作为本包测试常量，不调用被测函数生成 expected，也不要求运行时导入 T04。content 精确为 ASCII `fixture content`，其 UTF-8 SHA 为 `77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a`。rows 是仅含下列单行的数组；单行完整规范 JSON 为 `{"chunk_id":"chunk-0","chunk_index":0,"content_sha256":"77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a","doc_id":"doc-fixture","owner":null,"scope":"global","source_locator":{"paragraph":0}}`。该单行数组的 expected manifest SHA 固定为 `7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176`。测试对内容摘要与最终 manifest 摘要分别断言该字面值，失败时不能重算后覆盖常量；独立 oracle 继续补充乱序/重复行等场景，不能替代此固定向量。

### 3.3 计数、维度与失败边界

IngestResult 字段和默认值保留。index_unconfirmed 的 written_chunk_count 仅在 provider 返回非bool且 0≤值≤planned 的整数时保留；null、bool、负数、浮点、字符串、超过planned等非法值统一为0。warnings 明确“写入未确认，计数0不代表已确认零写入”；安全 warning 不回显 provider 对象。status 仍为 index_unconfirmed，不能用0构造成功证明。数据库 insert 成功并非最终确认，只有 commit 返回成功才返回实际条数。

provider 在 embedding 前捕获本次正非bool维度，并在 embedding 后检查同一绑定未漂移；发现漂移在 insert 前拒绝。实际 EmbeddingService 固定实例维度后，settings 改变只影响新实例。向量短/长、错维度、bool、NaN、正负 Infinity、非数值在 insert 前拒绝。零向量本身允许，不能无依据新增质量阈值。

commit 已发出但响应失败时数据库可能已提交；rollback 尝试不证明未提交。T02 只抛出并保留故障，不新增 IngestResult 的“未决”状态、不伪造 RunRecord、不自行判定未写入。T08 按冻结 RunRecord/phase 与写前证据标 inconclusive，并只读恢复；T02 交接测试中的“commit生效后抛错”情景，严禁自动重导。T07 才提供真实 PostgreSQL 事务证据。

## 编号执行步骤与红绿验证

以下均为未来执行动作；本计划编写没有运行这些命令。所有测试使用临时文件、内存 SQLite 或受控替身，不能连默认业务库。先保存相关失败断言与原因，再最小实现，最后限定回归；导入失败不是所有行为用例的充分红灯证据。

### 执行前离线 fixture 隔离

- [ ] **0.1** 在允许修改的 `tests/unit/harness/test_knowledge_ingestion.py` 内加入模块级 autouse fixture，用 monkeypatch 将 settings.rag_backend 精确固定为 fake，生命周期覆盖该模块全部现有和新增测试；退出时自动恢复。当前若直接 `RAGCoordinator()`，会读取环境配置并可能装配 PgVectorProvider，故不得只假设开发机默认fake。已有显式 `_UnconfirmedVectorProvider` 和新增计数替身继续通过 vector_provider 参数注入。
- [ ] **0.2** 同一 ingestion 测试文件内将 `PgVectorProvider.__init__`/`_get_conn`、`EmbeddingService.embed_one`/`embed_many`、`openai.OpenAI` 工厂设为调用即失败的计数陷阱；SDK在构造入口被拦截，不能到达远端 `embeddings.create`，不先初始化真实 client 再打补丁。所有正常与失败准备/摄入用例断言陷阱调用为0。增加隔离用例：先将环境设置为 pgvector，再在本测试 fixture 内固定fake，确认默认 coordinator 仍用 fake，失败时停止后续红绿循环。不得修改共享 conftest、生产配置或全局环境文件。
- [ ] **0.3** `test_pgvector_provider.py` 只用本文件的显式 FakeEmbeddingService 和 sqlite:///:memory:，事务异常用本文件连接替身；本文件 monkeypatch `openai.OpenAI` 为失败陷阱，并为 `sqlalchemy.create_engine` 设置本地守卫：仅 sqlite:///:memory: 转交原工厂，其余 URL 立即失败且不输出URL；不能阻断合法内存SQLite连接。`test_embedding.py` 需要SDK行为时用本文件FakeOpenAI，其 embeddings.create 仅返回合成对象；默认 SDK 工厂设为失败陷阱，需要SDK替身的测试显式覆盖该陷阱；维度和settings修改均由monkeypatch自动恢复。只读 chunking 测试不新增 fixture。
- [ ] **0.4** 完成上述fixture后运行下述各命令；不得以“无外联意图”替代陷阱零调用证据。测试禁用 cacheprovider；若 uv 同步/工具解析需要网络或审批，按环境阻断记录，不自动安装依赖、不把该阻断当有效红灯。

### 任务1：维度绑定与 SDK 批次完整性

- [ ] **1.1** 在 `test_embedding.py` 新增 `test_dimension_is_bound_per_instance`：创建实例后更改 settings，旧实例维度不变、新实例读取新值；新增无效维度参数化和 `test_embed_many_rejects_batch_cardinality_mismatch`（每批少1/多1）。补 `test_embed_many_response_index_*`：两条等维有限向量按 index=1、0 返回时，精确输出按输入顺序对应的向量；缺失 index、重复0、负值、超本批上限、bool/字符串均 ValueError。更新既有 FakeEmbeddingItem 及所有多条响应 fixture，逐项明确合法 index，不沿用默认0掩盖重复；批次各自从0开始。覆盖11条非空输入跨批并穿插空字符串，核对每个非空位置和空串零向量，保持 SDK 懒加载。
- [ ] **1.2** 运行 `uv run pytest tests/unit/infrastructure/test_embedding.py -q -p no:cacheprovider`；预期新增维度漂移与长响应断言失败，短响应错误类型/安全拒绝不满足预期；记录真实原因。若已有实现通过，检查差异并记录已有覆盖，不人为制造失败。
- [ ] **1.3** 最小修改 embedding.py，固定实例维度，在每批回填前检查数量和 index 完整性，按 index 重排后恢复原始输入位置；任一批次非法整体抛安全 ValueError，不返回部分向量。无外部调用、无新请求参数。
- [ ] **1.4** 重跑1.2，预期全部通过，原默认/自定义配置与空输入不变。

### 任务2：整批验证与事务确认

- [ ] **2.1** 在 `test_pgvector_provider.py` 新增 `test_index_rejects_invalid_embedding_batch_before_insert`，参数覆盖短/长批、零/错维、bool/非数值/NaN/±Infinity；使用有维度的受控 embedding 替身与记录 execute/commit 的连接，断言 insert=0、commit=0。新增维度漂移拒绝及空输入无连接。
- [ ] **2.1a** 在同一允许测试文件补真实 EmbeddingService → PgVectorProvider.index 的受控贯通：局部覆盖 SDK 工厂陷阱为纯内存 SDK 替身，返回数量和维度均合法但 index 重复/缺失/越界的响应，断言安全 ValueError、连接/insert/commit均为0；11条非空输入的第2批非法时仍无部分写入。除该局部受控工厂外保留所有外联陷阱，不发真实请求。此用例随2.2及2.5命令执行；若因任务1修订已绿，如实记录首次即绿，不制造失败。
- [ ] **2.2** 运行 `uv run pytest tests/unit/infrastructure/test_pgvector_provider.py -q -p no:cacheprovider`；预期当前 zip/无校验导致新增断言失败，记录漏写成功的反例。
- [ ] **2.3** 最小修改 index：完整验证后执行、维护真实计数、只在 commit 成功后返回。保留 PG/SQLite、SQL identity 回退与旧 search 语义。
- [ ] **2.4** 新增 `test_index_rolls_back_insert_failure`（第二条失败、无 commit、回滚后无本批残留），`test_index_propagates_commit_failure`、`test_index_preserves_primary_error_when_rollback_fails`、`test_index_does_not_retry_after_commit_ack_loss`（替身已生效后抛错，后续写入次数不增加）；先运行对应 `-k 'failure or ack_loss or rollback' -p no:cacheprovider` 记录必要红灯，再修最小错误传播。
- [ ] **2.5** 重跑2.2，预期全部通过；SQLite 与替身证据标明不能证明真实 PG 原子性。

### 任务3：准备结果、清单与兼容入口

- [ ] **3.1** 在 `test_knowledge_ingestion.py` 新增 `test_prepare_file_has_no_index_side_effect`、`test_prepare_file_extracts_and_chunks_once`、`test_prepare_file_rejects_source_change`、`test_prepare_snapshot_is_deeply_immutable`。覆盖临时源变化、源嵌套对象后改、documents/manifest/locator 深层修改失败、返回 intent 副本修改不污染。
- [ ] **3.2** 新增 `test_prepared_manifest_matches_canonical_rows`，先断言§3.2复制的 content/单行rows/expected manifest SHA 固定向量，再用独立测试侧标准库规范化 oracle 检查中文、乱序 JSON 键、展示序与摘要序不同、重复行保留对摘要的影响；内容哨兵只出现在内存 docs，不能出现在 manifest/intent/warnings。新增 `test_intent_metadata_has_exact_keys` 检查所有冻结键及无运行绑定。
- [ ] **3.3** 运行 `uv run pytest tests/unit/harness/test_knowledge_ingestion.py -q -p no:cacheprovider`，预期新类型/方法缺失或契约断言失败；记录后实现 PreparedIngestion/准备异常及 prepare_file/to_intent_metadata 的最小逻辑。
- [ ] **3.4** 新增 `test_ingest_prepared_rejects_inconsistent_snapshot`，逐项篡改摘要、身份、index 连续性、重复 ID、scope/owner、版本和 locator；拒绝在 index 前发生。构造器能直接拒绝的畸形输入同样可接受，不能为测试绕开合法验证。新增 `test_ingest_file_delegates_once` 与 `test_ingest_prepared_requires_confirmed_integer_count`（None/True/False/浮点/负数/短数/超数/相等正整数）。
- [ ] **3.5** 新增准备异常公开 status/safe_summary 三组精确值及兼容映射、private owner非法参数化、策略bool/浮点拒绝及overlap=0接受、未知内部异常保真以及 `test_ingest_prepared_does_not_reextract`；对3.4所有非法确认值断言written=0且有精确未确认warning，合法短数保留、合法相等正整数成功。运行3.3先证明未实现行为失败，再实现 ingest_prepared 并重构兼容入口。现有 `_OversizedStubChunker` 缺 normalizer_version：更新这个测试替身使其满足真实 ChunkDocument 契约，不能降低生产校验以迁就旧替身。
- [ ] **3.6** 重跑3.3，预期全部通过；原 unsupported/extraction_empty/index_unconfirmed 仍非成功，现有 TXT 贯通和 oversized warning 保留。

### 任务4：限定回归、review 与交接

- [ ] **4.1** 运行 `uv run pytest tests/unit/harness/test_knowledge_ingestion.py tests/unit/harness/test_chunking_service.py tests/unit/infrastructure/test_pgvector_provider.py tests/unit/infrastructure/test_embedding.py -q -p no:cacheprovider`；预期通过，DEC-012 固定向量不变，所有新增行为有效执行而非 skip。
- [ ] **4.2** 运行 `uvx ruff check app/harness/knowledge_ingestion.py app/infrastructure/rag/pgvector_provider.py app/infrastructure/rag/embedding.py tests/unit/harness/test_knowledge_ingestion.py tests/unit/infrastructure/test_pgvector_provider.py tests/unit/infrastructure/test_embedding.py`；与 `.github/workflows/ci.yml` 对齐：项目未声明ruff，CI使用uvx。预期无本包新增 lint，既有问题须逐项记载，不能顺手扩改无关文件。工具缺失或下载需要审批均记环境阻断，不假称lint通过，不自动安装依赖或改依赖声明。
- [ ] **4.3** 运行 `git diff --check`、`git diff --stat`，逐项核对允许文件、接口、隐私和下表覆盖。给主控提交无正文证据索引和差异摘要；主控 review 通过之前不释放写入权或宣称 T02 完成。
- [ ] **4.4** 主控统一检查更新根 README，说明两阶段摄入/兼容/限制，并在交接记录中确认；执行者不抢写。仅 T02 本包完成不能放行 G1/G2/G3。

## 冻结接口覆盖矩阵

| 冻结要求 | 实现归属 | 必要验收 |
|---|---|---|
| A1 prepare_file 签名、无 IO 写库、一次提取切块、源 SHA 前后相等 | knowledge_ingestion | 3.1/3.3/3.5 |
| A1 唯一类型、字段/嵌套只读、版本及身份一致 | knowledge_ingestion | 3.1/3.4 |
| A1 to_intent_metadata 精确键、无 documents、安全 warnings | knowledge_ingestion | 3.2 |
| A1 准备异常状态与 ingest_file 兼容 | knowledge_ingestion | 3.5/3.6 |
| A2 非bool计数、ok planned=written>0、None不成功 | service/provider | 2.3/3.4 |
| A2 数量/维度/非bool有限值、任何 insert 前校验；SDK index 对应 | provider/embedding | 1.1/2.1/2.2；补受控 SDK 畸形 index 经真实 EmbeddingService → PgVectorProvider.index 的用例：响应数量/维度合法仍被拒绝，连接与 insert 调用均为0；失败在后续批次时也不部分写入 |
| A2 insert/commit rollback、原故障、commit未知不能零写入推断 | provider → T08 | 2.4、未决交接 |
| A3 prepared-manifest 精确键、无 run/target/embedding/正文 | knowledge_ingestion | 3.2 |
| C rows完整规范字节排序、重复保留、content直接SHA | knowledge_ingestion | 3.2/3.4 |
| C 固定实例实际维度，配置漂移拒绝 | embedding/provider | 1.1/2.1 |
| A4 运行意图/恢复、IndexSnapshot、成功证明 | T08/T04 所有 | T02仅交接口与未决边界，不冒领实现 |

## 隐私、失败处理与未决事项

正文仅留内存 documents 与产品写入参数；证据、warnings、异常安全摘要、manifest/intent 不含正文、密钥、端点、数据库 URL、SQL 参数或堆栈。source_locator 按现有产品结构保留可序列化对象（当前含 file_path）；不擅自删除 provenance 字段，公开证据只用合成文件名/无秘密定位信息，不复制真实用户绝对路径。无正文清单不等于可无审查公开发布全部 locator。

spec 明确要求准备摘要与身份验证，但未冻结私有 helper 名称/不可变容器实现，执行者可选标准库递归只读结构，不借此改变公开字段。v1.0.1 已闭合三个错误摘要、非法计数与overlap=0边界；不得继续沿用旧v1未定文案或自行放宽计数。provider 对畸形返回的具体异常类未冻结，使用 ValueError 一类内部错误即可，禁止新错误码/成功状态。

当前未发现要求 T04 先实现的硬依赖。跨包规范 JSON 算法须共享冻结语义与测试向量；若主控要求抽成新公共函数，须另行明确所有者和接口，不在 T02 单方抢建 contracts。commit未知状态归 T08，不能以新增 provider 返回对象改变既有 int/null 协议。

命令失败先判断环境与断言失败；缺依赖记录为未执行，不能计通过。长测试主动每30秒轮询进程/输出，不 sleep；平台故障同动作本轮只重试一次，第二次被挡停止变更并报主控，附相同命令的手工执行选项。真实PG、远端API、正式摄入均不属于本包失败后的自行替代方案。

## 证据与下游交接

执行证据统一进入 `docs/rag-work/evidence/t02/2026-10-16-execution.md`：执行日期、冻结 SHA、允许文件差异、各命令退出码/通过失败跳过数、红灯原行为与绿灯结果、安全场景名称、未执行项、review结论；不嵌真实正文和未经清理异常输出。缺证据保持未验收，不把本计划中的预期结果写作实测结果。

- **T08：** 交唯一类型路径、完整签名、intent 元数据/准备清单样例（合成数据）、规范 SHA 测试向量、一次准备/一次写入计数、None 与commit未知场景。T08 添加运行 envelope 不重生成 rows，并在获得 provider 写入权后实现 snapshot_index；不要求 T02 落盘或重试。
- **T10：** 交异常传播与无正文 warnings 边界、provider 差异、测试证据和明确释放时间；T10 补日志审计前取得文件写入权，不并写 provider 或其测试。T08/T10 如同需 provider，主控排串行顺序。
- **T07：** 交受控 insert/commit/rollback/ack-loss 场景与 SQLite 局限；真实PG正式schema fixture、向量维度和事务回滚由 T07 在 G1及其他前置就绪后验证。现有 `tests/integration/test_pgvector_real.py` 会手建表并 DELETE 全表，T02 不运行、不复制其清理策略，也不将其作为安全正式fixture。
- **主控：** review批准、README集中维护、写入权释放；T02通过仅贡献G1的一部分，不能声称真实摄入或MVP完成。

本次计划验收只检查文档、引用、冻结 SHA 和授权文件范围；无实现代码、无业务测试、无commit/push。
