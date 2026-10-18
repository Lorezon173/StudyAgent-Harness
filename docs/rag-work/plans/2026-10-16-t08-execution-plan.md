# T08 摄入 runner 与只读恢复执行计划

> **执行约束：** 本计划仅在主控审阅并获得用户确认后执行。执行者按本文逐任务完成隔离红绿验收；不在本计划阶段运行实现、测试或真实服务。

**目标：** 实现一次性摄入 runner、运行意图与清单的原子持久化、实际索引快照，以及仅凭已保存意图和实际快照完成的只读恢复。

**架构：** runner 只通过 T02 的 `KnowledgeIngestionService.prepare_file` 准备一次产品快照，并将 T04 的 embedding 身份、T02 的无正文准备清单封装为运行意图和计划清单；两份文件都持久化后才允许调用一次 `ingest_prepared`。提交后由同一受控 `PgVectorProvider` 读取目标索引的完整实际行多重集合，复核隔离证据后调用 T04 的证明构造器与校验器。恢复只读已有 intent/manifest 和数据库，不重新打开 source、不重新准备、不再次调用 `index`。

**技术栈：** 现有 Python、SQLAlchemy 同步连接、`PgVectorProvider`、`KnowledgeIngestionService`、T04 RAG contracts/embedding identity/attestation；文件持久化使用标准库同目录临时文件与原子替换。计划不新增依赖、不修改共享 `conftest.py`。

**冻结规格：** [RAG MVP 共享契约 v1.0.1](../specs/2026-10-16-rag-mvp-contracts-v1.md)，SHA-256 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。

**设计血缘：** [2026-10-15 raw 执行方案](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan.md)、[RV-01～05 review](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan-review.md)、[2026-10-16 DAG 与调度](../../../superpowers/rag-foundation/2026-10-16-rag-mvp-dag-and-scheduling.md)。

**状态：草案，待主控审阅和用户确认；没有实现或测试通过声明。**

## 全局约束

- T08 依赖已验收的 T02 与 T04；真实 G1～G6 尚未通过。T08 只交付 runner 与离线受控验证，不执行 T11 正式摄入。
- T08 唯一新增公共接口为冻结规格中的 `PgVectorProvider.snapshot_index(*, target_index_id: str) -> IndexSnapshot`、`run_ingestion(...) -> RunRecord` 和 `recover_ingestion(...) -> RunRecord`。保留现有公开构造器与 import 路径；锁、资源配置与文件帮助函数均为 `scripts/rag_ingest.py` 或 provider 的私有实现。
- `prepare_file` 必须恰好准备一次；只有 `intent.json` 和 `plan-manifest.json` 都完整原子落盘后，才可调用一次 `ingest_prepared`。任何分支都不得自动重试 `index`、重切块、upsert、删除或覆盖旧 run。
- `IndexSnapshot.rows` 必须包含目标表完整行多重集合并保留重复；正文仅在 provider 计算 SHA-256，不写进 snapshot、日志、intent、manifest、隔离证据或证明。
- `RunRecord` 的 phase、summary、六种允许的 `error_code` 和 failures 规则 ID 均遵守冻结契约；不把异常原文、凭证、连接 URL、source 正文或私有 endpoint 写入任何输出。
- 实现必须支持受控生产装配所需的真实 PostgreSQL 与 embedding SDK；本轮 T08 实施验收只运行离线单测，测试为外联、SDK、数据库引擎/真实 provider 连接和 LLM 设置陷阱，使用显式受控替身。测试临时目录须位于仓库内独占且此前不存在的 `.pytest-tmp-t08-*` 路径，不清理或复用旧目录。
- 使用已缓存 Ruff，不安装依赖；原 `tests/unit/infrastructure/test_pgvector_provider.py:667` 存在基线 E402。记录完整原始 Ruff 输出并与已知基线逐项对照，只允许既有诊断、不允许新增诊断；不以忽略 E402 的结果作为通过条件。
- T08 代码写权只覆盖本文列出的四个实现/测试路径；执行证据单独写入表中指定的唯一文件。README、计划索引、TodoList、证据索引和主控总状态由主控单写。T08 实现期间独占 `pgvector_provider.py`；与 T10 对该文件串行交接，不并写。不得修改 `benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py`（T09）或 `app/core/config.py` / `env.py`（T05）。

## 第一层：模块总览

### 目标边界

T08 为后续受控摄入提供可审查、可恢复的运行闭环：

1. 解析受控 target 和 embedding binding，确认实际 provider 指向唯一的 PostgreSQL database/schema，并确认目标专用隔离与排他条件。
2. 在任何产品写入前，用 T02 准备结果原样建立并持久化 intent 和 ingestion manifest；不从 source 复制一套提取或切块逻辑。
3. 检查本轮实际前态为空后，仅写一次；对写入结果不确定时返回未决，不把计数 0 当作未写入，也不自动重写。
4. 从真实 provider 只读读取完整目标行集合；仅在行多重集合、计数、source 摘要、目标、原始 embedding identity、排他与资源证据全部相符时写成功证明。
5. 恢复入口只消费已落盘原意图/清单和当前实际快照。它不读 source、不调用 `prepare_file`、`ingest_prepared` 或 `index`。

明确非目标：T11 的正式书籍摄入、T07 真实 PG fixture/资源建置、T09 gate/report 接入、schema/table 创建或 migration、共享上传 API、run 数据库表、删除/替换/幂等/upsert、权限模型扩展、对在线服务或 benchmark 的接入。目标 schema/table 未准备好时按数据库错误拒绝，不在 T08 中自行创建。

### 依赖关系与已验收事实

| 依赖 | 当前真实接口/事实 | T08 消费方式 |
|---|---|---|
| T02 摄入 | `app.harness.knowledge_ingestion.KnowledgeIngestionService(coordinator, chunker=None)`；`prepare_file(file_path, *, import_namespace, scope="global", user_id=None, chunking_spec_version="chunk-policy-1", policy=None) -> PreparedIngestion`；`PreparedIngestion.to_intent_metadata()`；`ingest_prepared(prepared) -> IngestResult`。 | 一次准备并保留同一 `PreparedIngestion`；intent.preparation 来自受校验的 `to_intent_metadata()`；成功路径只传同一对象给 `ingest_prepared` 一次。恢复不调用 service。现有 `ingest_file` 是兼容入口，T08 不使用它。 |
| T02 provider | `PgVectorProvider(embedding_service=None, db_url=None)`；`index(docs) -> int | None` 先校验批 embedding，再 insert/commit，失败 rollback 后抛异常。`RAGCoordinator(store=None, vector_provider=None)` 可显式装入 provider。 | 通过显式注入而非 `settings.rag_backend` 默认分支装配产品 provider；对所有外层未确认/异常按冻结状态保守分类，不再次调用。 |
| T04 embedding | `describe_embedding(service, binding) -> EmbeddingIdentity`、`fingerprint_embedding(identity) -> str`、`to_json_dict(identity) -> dict`。描述身份检查服务实际配置/binding，不做 embedding 请求。 | 使用同一个实际 service 和 binding 生成身份；manifest、intent、恢复比较和证明都用这一原身份；不序列化 `EmbeddingBinding`，不输出 `expected_endpoint`。 |
| T04 合同/证明 | `IndexSnapshot(target_index_id, database_id, schema_name, row_count, rows, manifest_sha256)`、`RunRecord(...)`；`canonical_json_bytes`、`manifest_sha256`；`build_attestation(*, intent, manifest, result, snapshot, identity, verified_at)`；`validate_attestation(attestation, *, expected, snapshot) -> ContractCheck`。 | 复用这些类型和函数，不复制 schema。恢复在完整实际快照核验后按规格从实际计数构造仅供 `build_attestation` 消费的确认结果；若有已知 `index_unconfirmed` 记录，绝不构造成功结果。 |
| T02/T04 安全边界 | `PreparedIngestion` 深冻结 documents/manifest；`to_intent_metadata()` 先执行完整快照校验并返回隔离副本。`IngestionPreparationError` 只暴露固定 status/safe_summary。`RunRecord` 限定五种 phase、固定摘要、六码和安全规则 ID。 | 不从准备对象外部重建字段，不用当前默认值补历史 preparation；所有失败输出只使用安全 summary、error_code 和规则 ID。 |

### 文件结构与精确写权

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `scripts/rag_ingest.py` | T08 公共 runner/recovery、私有资源装配、目标排他控制、原子 JSON 文件操作和状态归约。 |
| 修改 | `app/infrastructure/rag/pgvector_provider.py` | 新增冻结 `snapshot_index`；实现仅供 T08 内部控制目标排他的私有帮助方法（如采用本计划推荐的 PostgreSQL advisory lock）。保持既有 `index/search/doc_count/__init__` 公开签名。 |
| 新建 | `tests/unit/scripts/test_rag_ingest.py` | runner/recovery 的离线状态矩阵、文件原子性、调用次数、秘密边界和外联陷阱。 |
| 修改 | `tests/unit/infrastructure/test_pgvector_provider.py` | `snapshot_index` 的 SQL 映射、多重集合和数据库错误用例；不改共享 fixture/conftest。 |
| 执行时新建 | `docs/rag-work/evidence/t08/2026-10-16-execution.md` | T08 实施者记录本包红绿、局部 lint、差异审计和未覆盖限制；主控只向同一文件追加跨 T02/T04/T08 组合结果。当前草案阶段不创建该证据文件。 |

## 第二层：子模块概述

### 1. 受控运行装配与 target 准入

私有 adapter 在 source preparation 前读取受控配置，将调用方的 `target_index_id` 与 `resource_record_ref` 精确匹配到已授权 database/schema、DSN 环境变量名、resource-only writer 策略及唯一的 `binding_ref`；再把 API 收到的 `EmbeddingBinding` 与该受控 binding record 逐字段核对，expected endpoint 只从指定环境变量读入内存，不写文件或日志。它从实际 `EmbeddingService` 描述模型/版本/维度身份，并从同一个 embedding service 装配 provider、`RAGCoordinator` 和 `KnowledgeIngestionService`。在真实 provider 确认 dialect=`postgresql`、database/schema 与注册目标相等、resource/binding record 有效、排他 lease 成功、pending marker 不存在且目标为空前，不读取 source、不执行任何写入。

资源与 binding adapter、锁/未决标记的当前状态：仓库没有 target registry、`resource_record_ref` 解析器、受控 `EmbeddingBinding` 注册或排他锁实现，`app.core.config.settings.database_url` 默认是 SQLite URL。冻结 spec 只定义了引用字段和必须达到的隔离效果，没有指定注册文件格式、secret 来源、目标映射、binding 授权映射、lease 存储或过期规则。因此以下注册 adapter 与持久化方式均是**本计划建议，不是现有事实，也不是共享冻结 schema**：

- 建议 T08 私有环境变量 `RAG_INGEST_CONTROL_DIR` 指向受控、权限受限的本机目录；其中 `resources.json` 使用本地版本标记 `rag-ingest-resource-registry-v1`，每条记录精确包含 `resource_record_ref`、`target_index_id`、`database_id`、`schema_name`、`database_url_env`、`mode`、`exclusive_writer_evidence_ref`、`binding_ref` 八个字段。`database_url_env` 是只含环境变量名的字符串；DSN/密码不写进 JSON。`mode` 只有 `isolated_db` 可准入。resource ref、target ID 与 binding ref 都必须唯一匹配；重复、缺失、未知版本、环境变量未配置、database/schema/dialect 不一致或不能读取并匹配 runner-only writer evidence 时失败关闭。另建议 `bindings.json` 使用本地版本标记 `rag-ingest-binding-registry-v1`，每条记录精确含 `binding_ref`、`service_id`、`deployment_id`、`model_version`、`expected_endpoint_env`；endpoint 环境变量名可持久化，其值仅在内存中读取，并与 API 收到的 `EmbeddingBinding.expected_endpoint` 比较，值不匹配、未配置或字段不等一律拒绝，不写入 intent、日志或证明。建议 writer evidence 本身使用同目录受控记录，字段为本地版本 `exclusive-target-writer-v1`、target/database/schema、专用 writer role、UTC 核验时间及可定位的 T07 资源审计引用；T08 消费其可信性，但不能自行伪造 T07 的权限审计事实。
- 建议注册目录另有 `pending/<sha256(target_index_id)>.json` 作为跨 run 目录的唯一未决标记，精确记录本地 schema 版本、target ID、run UUID、run_dir、`exclusivity_record_ref` 和阶段。另在 `exclusivity/<run_uuid>.json` 原子创建每 run 只增不改的 runner lease 记录，精确含本地 schema version、run UUID、target/database/schema、resource ref、T07 writer evidence ref、`lock_scheme=pg_session_advisory` 和 `acquired_at`；intent 的 `exclusivity_record_ref` 指向该记录。lease 记录只是 runner 在取得锁时的可定位事实，不单独证明无外部 writer。先在同一 provider 数据库连接上取得 PostgreSQL session advisory lock，再创建 lease 记录及 pending 标记；锁仅在已确认为 completed、或已确认本轮未写入时释放并移除对应 marker。PG 会话/进程崩溃时 session lock 由数据库释放；pending marker 不按时间自动过期，lease 记录保留不改；新 run 被未决 marker 阻断。recover 必须再次取得 advisory lock，并校验 lease 记录、intent 与 marker 的 target/run ID 全部相同后才核验。marker 缺失时只允许“已完成历史 run”分支：intent、manifest、isolation evidence 和 attestation 均有效且当前快照/identity/resource 复核通过时只读返回 completed；缺 proof 或 proof 无效仍为 inconclusive。marker 损坏、冲突或无法证明外部 writer 被排除时保持 inconclusive，不自动删除 marker、不偷取锁、不开始新写入。
- `exclusivity_record_ref` 是上述 runner lease 记录的安全引用。数据库 advisory lock 只能协调遵循 T08 锁协议的 writer；它本身不能证明无外部 writer。真实环境必须由 T07/受控资源提供 runner-only PG 写权限或等价、可审计证据。无法提供时不得产生 `exclusive_target=true` 的成功证明。
- 该格式只属于 T08 adapter，不改 `contracts.py`、冻结 spec、T09 或 T05 配置。主控在实施前需决定接受此私有适配器，或提供等效现有受控 registry。无论选择哪种，T08 离线测试都以显式替身构造 adapter；真实装配缺失时生产函数失败关闭。T09 只读消费冻结的 isolation evidence/attestation JSON，不导入或依赖 T08 registry 模块。

建议的私有结构字段（只供本计划实现/测试 adapter 使用，不导出为共享契约）：`ResourceRecord` 保存 registry 八字段；`BindingRecord` 保存 binding registry 五字段；`BoundTarget` 保存 `target_index_id`、`database_id`、`schema_name`、`resource_record_ref`、`database_url_env`、`exclusive_writer_evidence_ref`、`binding_ref`，另有 `db_url` 内存字段并设 repr 隐藏；`Runtime` 保存同一 `EmbeddingService`、经验证的 `EmbeddingIdentity`、`PgVectorProvider`、`RAGCoordinator` 和 `KnowledgeIngestionService`；`TargetLease` 保存 target 的安全摘要、同一 provider connection 的锁持有状态及 lease release 状态，不含 DSN；`ExclusivityRecord` 保存 runner lease record 的冻结本地字段；`PendingRecord` 保存本地 schema version、target ID、run UUID、run_dir、`exclusivity_record_ref`、phase 和 UTC 更新时间。以上私有结构不复用 T04 `RunRecord`，也不修改 frozen intent/isolation/attestation 键。

### 2. snapshot_index 实际快照

`PgVectorProvider` 使用本实例已绑定的同步连接，只读取得实际 `current_database()`、`current_schema()` 与目标表全部行。行映射以数据库顶层 `doc_id`、`chunk_id`、`scope`、`user_id` 为权威，`metadata_json.source_locator` 提供 locator；对数据库原始 `content` 在 provider 内计算 UTF-8 SHA-256 后丢弃正文。查询不得过滤掉不匹配行、不得将 rows 转 set、不得把异常转成空库。metadata 缺失/非法、scope-owner 不合法、读取不完整或 DB 异常均抛内部异常。输出由 T04 `IndexSnapshot` 再执行字段、数量和摘要校验；row_count 必须等于实际完整行数，0 行是合法前态快照，成功证明另要求正数。

### 3. intent/manifest 持久化及一次写入

run 先确保 run_dir 是本次唯一新目录，取得有效 resource/排他 lease，验证空前态和 identity；调用 `prepare_file` 一次后从同一 prepared 对象读取 preparation 与准备级 manifest。T08 只把准备清单包装成 `ingestion-manifest-v1` envelope，原样复制 rows、row_count、manifest_sha256，仅增加 run UUID、target、source SHA 和 embedding fingerprint。

写入 `intent.json` 和 `plan-manifest.json` 都通过 `_create_run_evidence_atomically`：严格规范 JSON → 同目录唯一临时文件 → flush/fsync → close → 使用同一文件系统内的原子“仅当目标不存在才发布”操作。禁止“先 exists 检查、再 replace”的有竞态序列；若运行平台/文件系统不支持原子 no-replace 发布则失败关闭。两个目标任何一个已存在都拒绝，不得替换。任何一个最终文件不可读/缺失/不完整时不得进入 `ingest_prepared`。intent 字段只按冻结 A4 精确键写入，`phase` 保持 `prepared`；准备数据来自 `to_intent_metadata()`，embedding_config 来自 T04 `to_json_dict(identity)`。两份证据原子创建后原子创建本 run 的 prepared marker，再以 `_update_pending_atomically` 将其更新为 write_started，再且仅再调用一次 `ingest_prepared(prepared)`。

对 `IngestResult.status != "ok"`、provider 返回未确认、错误计数或 provider 抛出的异常不得重试。只有确认 `status=ok` 且计划/写入计数一致时，才尝试一次 post-write `snapshot_index`；即使 commit acknowledgement 丢失，恢复入口也只读判断实际状态。provider 调用过程异常而无法证明事务确实回滚时归为 `inconclusive`。写入确认后快照/文件/隔离核验失败则记录 `committed_unattested` 或 `inconclusive`，绝不声称成功。

### 4. 隔离证据、成功证明与 RunRecord

只有在实际 snapshot 与 manifest 的完整多重集合相等、目标/dialect/database/schema 与受控注册项相符、binding 与 identity 指纹相等、pending/lease 仍属于本 run、资源记录仍有效时，才生成 `isolation-evidence.json`。它精确含 `mode`、`target_index_id`、`manifest_sha256`、`row_count`、`verified_at`、`resource_record_ref`，不增加冻结字段；文件由本 run 的固定 `isolation_evidence_ref` 与 run_dir 关联。全新 run 使用 `_create_run_evidence_atomically` 创建。若进程在隔离证据落盘后、attestation 落盘前崩溃，恢复必须重新完成当前快照、资源和 lease 核验；若该引用路径下已有 isolation evidence，六个字段精确匹配冻结 schema，绑定字段与 intent、target、mode、manifest SHA、row_count、resource ref 完全一致，且原 `verified_at` 是合法 UTC 时间，则仅原子刷新 `verified_at` 为本次核验时间，再用同一时间构造证明，以满足 T04 时间一致性。绑定不符或文件损坏时不覆盖并保持 inconclusive。然后以同一 intent、manifest、snapshot、identity、明确传入的 UTC `verified_at` 调用 `build_attestation`；构造后以对应 `AttestationExpectation` 调用 `validate_attestation`，只在允许时原子创建 `attestation.json`。恢复沿用原 run UUID、preparation 和 embedding config；证明创建时间是本次核验时间，written count 从实际 snapshot 行数重建。

`intent.json` 和 `plan-manifest.json` 永不覆盖；有效 `attestation.json` 永不重写，坏/字段不符 attestation 保持 inconclusive 且不替换。恢复若缺 isolation evidence，可在 marker/intent 完整且当前快照、资源、lease 全部通过时原子新建；若已存在，则只在同 run 引用路径、同 target、同 manifest、同 row_count、同 mode、同 resource ref 经新鲜复核完全匹配且原 `verified_at` 合法时允许原子刷新时间戳，其它情况不覆盖。无 marker 的 completed-history 核验要求有效 attestation 和有效 isolation evidence 均已存在且相互一致，只读验证，不改文件。pending marker 的状态严格为 `prepared→write_started→index_ok→completed`，未知 commit 路径为 `write_started→index_unknown→completed`（后续完整快照与 attestation 验证通过），显式未确认路径为 `write_started→index_unconfirmed` 终止未决；更新前持有同目标 session lease、重读 marker 原始字节并与预期摘要/身份比较，只允许本 run 合法迁移。受控 writer 由同一 PostgreSQL session advisory lock 串行化；control_dir ACL/所有权限制为 runner 服务身份，防止非协议写者并发改动。marker 更新使用同目录临时文件、flush/fsync、close 后原子 replace；若重读不匹配、lease 丢失或目录不再受控则拒绝更新，保留未决证据。此 CAS 语义依赖 lease 串行化遵守 T08 协议的进程和受控目录的独占访问；若目录权限/lease 无法验证，不更新并失败关闭。创建 intent/manifest/首次 marker/isolation/attestation 均使用原子 no-replace 发布，不能用检查后替换模拟。半写临时文件不是证据。`RunRecord` 只从 T04 类型创建：phase=`prepared/committed_unattested/completed/failed/inconclusive`，使用类型内固定中文 summary；failures 为安全规则 ID 的去重排序 tuple；只有契约允许的六个 error_code 可输出。异常原文只用于内部控制流，不进入返回值或文件。

### 5. 只读恢复

恢复从 run_dir 精确读取既有 intent/manifest，并判断本地 pending marker 状态；校验固定 schema、完整字段、原 run UUID、空前态、target/database/schema、prepared identity/source SHA/rows 摘要、资源引用和 binding identity。它绝不以当前默认策略或模型补全 intent 缺字段，也不读取 source_path。取得同目标 lease 后调用 `snapshot_index` 一次，比较完整行多重集合（包含重复）、数量、locator、scope/owner、source/config 和摘要。

marker 存在时，marker 必须同 target/run_dir/run UUID，phase 必须属于本 run 状态机；不匹配或被其它进程持锁时保持 inconclusive。marker phase 为 `prepared` 且当前目标仍空时，可确认尚未开始写入并清除；marker phase 为 `write_started` 或 `index_unknown` 时，只有完整实际快照与意图完全相符、隔离条件成立且 T04 校验成功，才允许补写证明并进入 completed，空表或任何不等都保持 inconclusive，不重新写入；`index_ok` 仍须实际快照与证明校验。显式收到并持久化的 `index_unconfirmed` 是终止未决分支，绝不升级为 completed，即使当前行集合完全匹配。marker 缺失时只走“已完成历史 run 核验”分支：intent、manifest、isolation evidence、attestation 必须全部存在且字段/identity 完整有效；再次取得 target lease、比较当前完整实际快照并通过 T04 `validate_attestation` 后返回 completed，不创建新 marker、不重建或覆盖文件。若 marker 缺失且成功 attestation 不存在/无效，即使 snapshot 与 manifest 相符也返回 inconclusive，不补成功证明、不重开运行。部分行、额外行、重复行导致不等、目标不符、marker 冲突、意图/清单不全、非空前态、资源或外部 writer 排他无法证明时保持 `inconclusive`，不删库、不补证明、不自动重导。

### 6. 离线验收边界

provider snapshot 测试使用 recording connection 检查 SELECT、完整行映射和错误传播，不创建真实 engine。runner/recovery 使用构造好的 T02 `PreparedIngestion`、受控假 service/provider/registry/lease 和 T04 contracts；fixture 在测试开始即阻断 socket、OpenAI SDK、SQLAlchemy engine/真实 provider connection 与 LLM client，结束时断言调用计数为零。假 provider 只提供确定性 snapshot 和可计数 `ingest_prepared/index`，不模拟“真实 PG 已验收”。T08 不修改共享 pytest fixture。

## 第三层：子模块详细实施计划

### 任务 1：在 PgVectorProvider 增加真实行快照

**文件所有权：** 修改 `app/infrastructure/rag/pgvector_provider.py`；修改 `tests/unit/infrastructure/test_pgvector_provider.py`。

**接口：** `PgVectorProvider.snapshot_index(self, *, target_index_id: str) -> IndexSnapshot`。这是冻结公共签名。内部私有函数按职责可拆为 `_read_target_identity(connection) -> tuple[str, str]` 和 `_snapshot_row(row) -> dict[str, Any]`；前者取真实 database/schema，后者映射一条数据库记录，任何非法字段抛异常。

**字段与数据结构：** 每行严格包含 T04 `ManifestRow` 的 `doc_id:str`、`chunk_id:str`、`content_sha256:str`、`chunk_index:int`、`scope:str`、`owner:int | None`、`source_locator:Mapping[str, JSON]`。SQL 的 `user_id` 映射为 snapshot 的 `owner`；content 只用于 UTF-8 SHA，不外传；source locator 从 `metadata_json` 读取。rows 保留 SQL 返回的每一行及重复项，最终 SHA 调用 `contracts.manifest_sha256(rows)`。IndexSnapshot 的 `target_index_id` 来自显式安全参数，database/schema 必须来自实际连接查询，不从调用方自报数据库名。

**实施步骤与验收：**

1. 在现有 provider 单测旁增加缺失/拒绝矩阵，覆盖空表、完整正常行、同一行重复两次、非法 metadata/source_locator、非法 owner/scope、database/schema 读取值及连接异常；所有测试使用 recording connection，并断言无 engine、SDK 或网络调用。
2. 运行 snapshot 定向红灯，确认原因是 `snapshot_index` 尚不存在或预期字段映射不成立，而不是 pytest 临时目录/平台权限问题。
3. 实现只读完整行查询、行映射、正文哈希、实际数据库身份与 IndexSnapshot 构造；任何 DB/JSON/类型错误原样以内部异常向 runner 传播，不用空快照掩盖。
4. 运行新的 snapshot 用例与 provider 文件回归绿灯；确认重复行仍使 row_count 增加且影响 SHA，正文不在 snapshot 输出内。

定向命令（每次执行前确认 basetemp 不存在；若路径已占用则使用新的唯一 T08 后缀，不删除旧目录）：

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_pgvector_provider.py -q -p no:cacheprovider -k snapshot_index --basetemp .pytest-tmp-t08-provider-red-20261016
.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_pgvector_provider.py -q -p no:cacheprovider -k snapshot_index --basetemp .pytest-tmp-t08-provider-green-20261016
```

首次命令应因新增接口/行为缺失而红；实现后定向命令应全绿。不得用真实 PG 代替。

### 任务 2：增加 T08 私有运行装配、原子文件和状态归约

**文件所有权：** 新建 `scripts/rag_ingest.py`；新建 `tests/unit/scripts/test_rag_ingest.py`。任务 1 释放 `pgvector_provider.py` 后，本任务可使用其快照及私有 lease 方法。`scripts/` 无现有 RAG runner；不得借此修改 `app/core/config.py`、`env.py` 或其它配置模块。

**公共函数：**

- `run_ingestion(source_path: str, *, import_namespace: str, scope: str, owner: int | None, run_dir: Path, target_index_id: str, resource_record_ref: str, binding: EmbeddingBinding, policy: ChunkPolicy | None = None) -> RunRecord`。签名与冻结规格一致；`owner` 在内部一对一映射到 T02 的 `user_id`。
- `recover_ingestion(run_dir: Path, *, target_index_id: str, binding: EmbeddingBinding) -> RunRecord`。签名与冻结规格一致；原 resource ref 从 intent 读取并在受控注册项中复核。

**私有函数及契约：**

| 函数 | 输入 → 输出 | 具体职责/拒绝条件 |
|---|---|---|
| `_load_resource_registry() -> ResourceRegistry` | `RAG_INGEST_CONTROL_DIR` 环境变量 → 已验证 resource/binding registry | 读取本文第二层建议的 `resources.json` 与 `bindings.json`；目录/文件不存在、路径不安全、未知版本、extra/missing key、重复 ref/target/binding 或格式错误均拒绝，不回退到 `settings.database_url` 或调用方默认 binding。 |
| `_resolve_target(registry, target_index_id: str, resource_record_ref: str) -> BoundTarget` | registry 与两个显式安全 ID → 内存 target 绑定 | 唯一精确匹配 resource 记录并保留其 `binding_ref`；从 `database_url_env` 取出 DSN，检查 mode=`isolated_db` 和 runner-only 资源策略。DSN 仅保存在 `BoundTarget` 内存对象的 repr 禁止字段；绝不返回到文件/日志。任一条件无法证明均失败关闭。 |
| `_resolve_binding(registry, target: BoundTarget, binding: EmbeddingBinding) -> RegisteredBinding` | 已绑定 target 与公开 API binding → 受控 binding 配置 | 仅取 target 指向的唯一 binding record；逐字段比较 `service_id`、`deployment_id`、`model_version` 和环境变量解析出的 `expected_endpoint`。重复、缺记录、env 未配置或任一不符均失败关闭；endpoint 值只在内存比较，不持久化/打日志。 |
| `_build_runtime(target: BoundTarget, binding: RegisteredBinding) -> Runtime` | target、受控 binding → identity/service/provider/coordinator/ingestion service | 从实际配置创建一个 EmbeddingService，调用 `describe_embedding`；用显式 DSN 和同一 service 创建 `PgVectorProvider`，显式装入 `RAGCoordinator(vector_provider=provider)`，再装配 `KnowledgeIngestionService`。受控 binding 不匹配真实模型/版本/维度/endpoint identity 时拒绝；不走默认 fake provider，不发送 embedding/LLM 请求。 |
| `_create_exclusivity_record_atomically(control_dir: Path, target: BoundTarget, *, run_id: str, acquired_at: str) -> str` | 已持有 target lease 与 run identity → 持久 runner lease 引用 | 生成唯一 `exclusivity/<run_uuid>.json`，字段精确按本计划私有 schema；原子 no-replace 创建，已有文件、目录权限异常或 lease 丢失即失败关闭。返回安全引用供 intent 写入，不记录 DSN、session id、credential 或原异常；文件保留不更新，T09 不依赖此私有格式。 |
| `_create_run_evidence_atomically(path: Path, value: Mapping[str, Any]) -> None` | 本次新建 run_dir 内不存在的证据路径和值 → 完整原子文件 | 仅用于 intent、plan manifest、首次 isolation evidence、attestation。规范 JSON；同目录唯一临时文件写入、flush/fsync、close 后使用原子 no-replace 发布，不能“先检查再 replace”；run_dir 必须由本 run 独占创建且由受控权限保护，任何目标已存在、权限/lease 不可确认或文件系统不支持原子 no-replace 时拒绝，绝不替换。半文件不是证据。 |
| `_read_json_exact(path: Path, expected_keys: frozenset[str]) -> dict[str, Any]` | 最终证据路径与字段集合 → 精确普通 dict | 仅接受 UTF-8 严格 JSON object、无重复/额外/缺失字段、无非有限数字；缺文件/损坏/字段不符返回安全 rule ID，不返回原文或路径内容。 |
| `_read_exclusivity_record(ref: str, intent: Mapping[str, Any]) -> ExclusivityRecord` | intent 中已冻结引用 → 已验证 runner lease record | 安全解析仅指向受控 `exclusivity/` 的相对引用；按精确本地 schema 校验 run/target/database/schema/resource/writer evidence/lock scheme/acquired time 与 intent 和当前 registry 一致。路径逃逸、缺失、字段不符或损坏时拒绝，不修补、不重建、不读任何 secret。 |
| `_refresh_same_run_isolation_atomically(path: Path, previous: Mapping[str, Any], *, expected_binding: Mapping[str, Any], verified_at: str) -> dict[str, Any]` | 本 run 固定 isolation 引用下已有证据、刚完成的实际复核及新 UTC 时间 → 刷新后的同一绑定证据 | 只允许冻结六字段 schema 精确有效、target/mode/manifest SHA/row_count/resource ref 与 intent/实际快照完全相同且旧 `verified_at` 是合法 UTC 时，将其更新为本次核验时间并原子替换；run 归属由 intent 的固定文件引用及 run_dir 提供，不新增 shared 字段。字段、绑定或 JSON 任一不符则保持 inconclusive，不替换。不得修改 intent/manifest；attestation 已有效存在时不刷新。 |
| `_build_ingestion_manifest(prepared: PreparedIngestion, *, run_id: str, target_index_id: str, fingerprint: str) -> dict[str, Any]` | T02 prepared 和运行绑定 → `ingestion-manifest-v1` | 从 prepared 的受校验准备 manifest 原样复制 rows、row_count、manifest_sha256；只添契约规定的运行字段；任何重提取、重切块、重新生成 chunk ID、正文输出或摘要/计数变化都拒绝。 |
| `_build_intent(prepared: PreparedIngestion, identity: EmbeddingIdentity, manifest: Mapping, target: BoundTarget, *, run_id: str, created_at: str, resource_record_ref: str, exclusivity_record_ref: str) -> dict[str, Any]` | 已校验运行值 → 精确 A4 intent | 精确输出冻结键；`before_row_count=0`、`phase="prepared"`、`exclusive_target=true`；preparation 来自 `to_intent_metadata()`；`embedding_config` 来自 `to_json_dict(identity)`；`isolation_evidence_ref` 指向本 run 的 `isolation-evidence.json`。缺失原值不得默认补齐。 |
| `_acquire_target_lease(provider, target_index_id: str) -> TargetLease` | 同一个受控 provider/target → 已持有数据库 session advisory lease | 使用 provider 的私有锁方法和同一同步连接。锁已占用、数据库不是 PostgreSQL、DB 无法确认、hash/target 绑定冲突时拒绝；没有成功 lease 不允许准备后写入。 |
| `_read_pending(control_dir: Path, target_index_id: str) -> PendingRecord | None` | control dir 和 target → 未决记录或空 | 只按 target ID 的 SHA-256 文件名查 marker；marker 字段必须精确、target hash/UUID/run_dir 一致。任意已有未决 marker 都阻止新 run；坏 marker 不能被覆盖或自动过期。 |
| `_create_pending_atomically(control_dir: Path, record: PendingRecord) -> None` | 已取得 target lease 且该 target marker 不存在 → 初始 marker | 先在私有 control_dir 内写唯一临时文件并刷新/关闭，再用原子 no-replace 发布；不以 exists 检查后 replace 实现。已有 marker、lease 丢失或目录权限异常均拒绝，不覆盖旧 run。 |
| `_update_pending_atomically(control_dir: Path, previous: PendingRecord, updated: PendingRecord) -> None` | 当前 target lease、磁盘已读 marker 与同 run 的下一状态 → 原子 sidecar 更新 | 只允许同 target/run UUID/run_dir 的 `prepared→write_started`、`write_started→index_ok/index_unconfirmed/index_unknown`、`index_ok→completed`，以及 `index_unknown→completed`（仅完整只读快照/attestation 核验通过）迁移；`index_unconfirmed` 是终止未决状态，禁止进入 completed。`prepared` 仅在确认写入从未调用且目标仍空时可清除。更新前要求仍持有同一 provider session lease、重读原始 JSON 并核对摘要、target/run/path/phase；不匹配则拒绝。更新仅以临时文件+flush/fsync+close+replace 原子替换；其 TOCTOU 防护前提是单目标 advisory lease 串行化所有 T08 writer 且 control_dir ACL 禁止非协议写者，任一前提不可确认便失败关闭并保留 marker。 |
| `_clear_pending(control_dir: Path, target_index_id: str, run_id: str) -> None` | target 和当前 run UUID → marker 删除或明确文件错误 | 仅 marker 精确属于本 run、lease 仍持有且成功路径已有从磁盘重读并验证的有效 attestation，或能确定尚未调用写入且 target 仍为空时移除；其它情况保留。删除前重读并比对 marker 身份/摘要。删除/文件故障返回 `record_io_failed`，不把它转换为 DB 成功/失败事实。 |
| `_close_runtime(runtime: Runtime) -> None` | 已创建 runtime → advisory lease 尝试释放且 provider connection 关闭 | 在 run/recover 的 `finally` 中调用；若持有 lease，先尝试对同一 key 调用 `_release_target_lock`，即使释放抛错也必须继续 `_close_connection`；即使 lease 未成功获取也关闭已打开的连接。锁连接必须是可确定终止的专用 session；release 失败时 close 必须使该 PG session 断开/失效而非把仍持锁的物理连接归还连接池。若无法确认 session 已结束，保留 marker 并记安全失败。此函数不清 pending；未决状态靠持久 marker 保留，不在返回后长时间占用连接。 |
| `_make_run_record(run_id: str, phase: str, error_code: str | None, failures: Sequence[str], attestation_path: str | None = None) -> RunRecord` | 已归约的安全状态 → T04 RunRecord | 调用 T04 类型验证固定 summary、规则 ID 与阶段/path 约束；禁止异常文本进 fields。 |

provider 同文件中的私有生命周期函数精确为 `PgVectorProvider._try_target_lock(self, *, target_index_id: str) -> bool`、`PgVectorProvider._release_target_lock(self, *, target_index_id: str) -> None` 和 `PgVectorProvider._close_connection(self) -> None`。前两者只锁当前 provider 的同一个同步 PG session，使用 `sha256(target_index_id)` 派生的 64-bit session advisory key；false 表示已有受控 writer，DB/方言异常传播为内部异常。release 只对本实例实际持有的同一 key 生效；close 必须结束/失效专用锁 session，不能把仍持有 session lock 的物理连接归还 pool，并清空内部连接引用。session lock 在 provider 连接/进程丢失时由 PostgreSQL 释放；没有时间 TTL，也不尝试自动夺取其它连接的锁。所有成功获得 runtime/provider 的 run/recover 控制流均在 `finally` 释放 lease 并关闭连接；release 抛错也必须继续 close；异常路径也执行 close。持久 pending marker 在锁释放后仍阻止新 run，只有匹配 run 的只读恢复/已完成核验能清理。

**字段/状态设计：** run_dir 每次必须是全新目录；已有文件或目录不得复用。run UUID 由 T08 生成并保留在 intent/manifest/所有记录中。intent/manifest 为不可变证据；有效 attestation 不重写、坏 attestation 不覆盖；isolation evidence 仅在本计划规定的同 run 绑定复核后刷新 `verified_at`。pending 是 control_dir 中按 target 唯一键管理的 T08 私有协调状态。状态图为 `prepared→write_started→index_ok→completed`，另有 `write_started→index_unknown→completed` 的只读恢复成功边（要求完整快照与 T04 证明验证均通过）；显式 `index_unconfirmed` 从 `write_started` 进入终止未决分支，永不升级。有效证明落盘并从磁盘验证后，先把 marker 更新至 completed 再尝试删除；marker 已清的历史 run 只可通过有效证明进入只读核验分支。确知 provider 未被调用且 target 仍为空时可归为 failed 并清 marker；commit/rollback 结果不能证实时归为 inconclusive 并保留 marker。收到 `index_unconfirmed` 后优先持 lease 将其持久化到 marker；持久更新失败则返回 inconclusive 并保留原 marker，但崩溃发生在该状态落盘前时无法保证重启后辨认该返回值，具体边界是待主控裁定的规格缺口，不能声称覆盖该窗口。

**步骤与验收：**

1. 先写 `test_rag_ingest.py` 的独立 fixture 和 RED 用例。fixture 创建 T02 真正 `PreparedIngestion` 数据结构但使用 recording service；显式替身给出 identity/provider/resource/lease/snapshot。陷阱覆盖 socket、OpenAI 构造、SQLAlchemy engine、PgVectorProvider 真实连接和 LLM client；teardown 断言全部外部调用为零。
2. RED 覆盖：模块/接口未实现、registry 缺失或目标/ref 不匹配、默认 SQLite/非 PG、未决 marker、run_dir 已存在、前态非空、source/identity/owner/policy 不合法、intent/manifest/pending 原子创建失败。每种前置拒绝都断言 `ingest_prepared/index` 为 0 次。
3. 实现私有 resource/binding registry adapter 与 runtime 装配；目标 identity、DB/schema、dialect、writer-only resource 和 lease 都验证通过后，先原子创建可定位的本 run exclusivity record，再调用 T02 `prepare_file` 一次。
4. 实现 manifest/intent exact schema、规范 JSON 原子持久化和 pending 状态机。使用 recording service 对调用顺序断言为：取得 lease/核对空前态 → 原子创建 exclusivity record → 一次 prepare → intent 与 manifest 均可重新读取 → 原子创建 prepared marker → 更新为 write_started → 一次 `ingest_prepared`。任何计划/marker/lease record 落盘失败都断言写入次数 0；无 marker 的 prepare 前崩溃不会发生 DB 写入。
5. RED/GREEN 校验计数：完整成功调用 1 次；显式 `index_unconfirmed`、非 ok、异常、计数错、已存在 pending、重复 run_dir 均不触发第二次写入。对显式 `index_unconfirmed` 断言 marker 进入终止分支且永不完成；对未知 commit 异常断言 marker 更新为 `index_unknown`，recover 只能凭完整实际行快照及 T04 证明核验完成。对原子 no-replace 创建和 marker 状态更新覆盖临时文件写失败、目标竞态、lease 丢失、磁盘 marker 已变化、非法阶段跃迁；均断言不覆盖别的 run 且保留可恢复的 pending。commit 结果不确定时 phase=`inconclusive` 并保留 pending；异常只保留安全 rule/error code。另验证 `run_ingestion`/`recover_ingestion` 所有早退、异常和正常路径 finally 均尝试释放已取得的 lease 并关闭连接；release 抛错仍执行 close，未决 marker 不随 finally 删除。

### 任务 3：加入成功证明和只读恢复状态机

**文件所有权：** 继续仅修改 `scripts/rag_ingest.py` 与 `tests/unit/scripts/test_rag_ingest.py`；不修改共享 contracts/attestation/schema。

**`run_ingestion` 返回流程：**

1. 先严格验证参数、resource 与受控 binding registry、实际 PostgreSQL target/database/schema、writer-only 条件、lease、无 pending marker 和空前态；为本次调用生成 UUID，在取得 lease 后创建唯一 runner exclusivity record，再调用 `describe_embedding`。任一条件失败时返回安全 RunRecord，不读取 source、不准备、不写 DB。
2. 调用 `prepare_file(source_path, import_namespace=..., scope=..., user_id=owner, policy=policy)` 恰好一次。`IngestionPreparationError` 的固定 status/safe summary只用于安全归类；失败没有 DB 写入时 phase=`failed`，不保留输入路径或原异常。
3. 构造 UUID、准备级 manifest envelope、intent；确认 `to_intent_metadata()` 成功。先用原子 no-replace 写 intent，再写 `plan-manifest.json`。任一失败时 `ingest_prepared` 必须仍为 0 次，并返回 `failed/record_io_failed`；损坏临时文件绝不被恢复入口当成证据。
4. 原子创建本 run 的 prepared marker，随后原子更新至 write_started，然后执行一次 `ingest_prepared(prepared)`。不得调用兼容 `ingest_file`，不得在异常后重试。确认 `result.status="ok"` 且 planned/written 为同一个正整数后先持久更新 marker 为 index_ok；status=`index_unconfirmed` 时优先持久更新为 index_unconfirmed 并归为 `inconclusive/provider_degraded`，不能补成功证明。遇到无法证明已回滚的未知 provider 异常时，持久更新 marker 为 `index_unknown`，返回 `inconclusive`；该状态只能由后续完整实际快照匹配并通过 T04 证明验证后完成。任何 sidecar 更新失败都返回 inconclusive、保留原 marker、不在当前调用中继续生成证明；`index_unconfirmed` 更新失败造成的崩溃窗口按文末规格缺口处理。未知异常若没有可证明的明确错误码则 `error_code=null`。
5. 对已确认的 ok 结果调用同一 provider 的 `snapshot_index`；重读受控 resource/writer 证据并确认 lease/target 仍一致。snapshot 非空且与运行 manifest 完整多重集合相等、摘要/计数一致后，原子写隔离证据，构造完整 AttestationExpectation，调用 `build_attestation` 再 `validate_attestation`。validation 拒绝、隔离或证据持久化失败时不得写 attestation，返回 `committed_unattested` 或 `inconclusive` 并保留 marker。
6. 只在已核验 attestation 原子 no-replace 落盘且从磁盘重新读取后仍与 validation 输入完全一致时，将 marker 更新为 completed，再返回 completed。attestation_path 指向本 run 的 `attestation.json`。然后尝试清除本 run pending marker；marker 清理失败仍返回 completed 加 `record_io_failed`，保留 marker 供只读恢复重新验证后清理。无论返回 phase 或清理结果如何，`finally` 都释放持有的 PG advisory lease 并关闭 provider 连接；释放失败不得阻止 close，也不得清除未决 marker。

**`recover_ingestion` 输入/输出和步骤：** 输入只有 `run_dir`、`target_index_id`、`binding`；输出由 `RunRecord` 表示已完成、确定未摄入、确定失败或仍不可判定。恢复步骤必须按以下顺序：

1. 先读取 run_dir 下 intent/manifest 并按精确字段校验 schema_version、UUID、target、空前态、manifest rows/row_count/digest、preparation、完整 embedding_config；用 intent 的 `exclusivity_record_ref` 读取并校验 runner lease record；然后读取 control marker。若 marker 存在，必须精确匹配 target/run_dir/run UUID 且 phase 为本状态机允许值；若 marker 缺失，只允许继续检查是否是已有完整有效证明的 completed-history 分支。缺失/损坏 intent、manifest 或 lease record，marker 冲突、未知版本都不修补、不读 source。
2. 将 intent 中的 `resource_record_ref` 与调用的 target ID 精确映射回同一受控 resource registry，并按该 resource 的 `binding_ref` 校验本次传入 binding 和 binding registry，取得当前真实 runtime；用当前 service/binding 的 `describe_embedding` 与 intent 身份逐字段相等并重新算 fingerprint。任何 identity drift 立即 inconclusive；不得使用当前配置覆盖 intent。
3. 取得同 target PG session advisory lease；如果另一个进程仍持有、存在的 pending marker 不属于该 run、数据库/模式/实际 target 不同或外部 writer 无法排除，保持 inconclusive，不查询后写证明。marker 缺失时不得创建新 marker，只能在后续完整只读证明核验通过后返回 completed。
4. 对真实 provider 调用 `snapshot_index(target_index_id=...)` 只读一次。绝不读取 intent preparation 中的 source 路径（其中没有路径），不调用 `prepare_file`、`ingest_prepared`、`index` 或 embedding 请求。snapshot 为空时返回失败/未摄入诊断，不自动重导；marker 只在确定没有 commit 不明问题时释放。
5. 实际行数与计划不符、行多重集合不等、额外/缺失/重复行、content SHA、source locator、scope/owner、target、database/schema 或 identity 不等，都返回 inconclusive，保留原文件和 pending marker。禁止用 set、仅 chunk ID 或 count 相等代替完整比较。
6. 只有 marker phase=`write_started`、`index_ok` 或 `index_unknown` 且 snapshot 完全一致时，才用 actual snapshot 的 row_count 构造 T02 `IngestResult(status="ok", doc_id=原doc_id, planned=实际行数, written=实际行数, warnings=原preparation warnings)` 作为 `build_attestation` 输入；此对象只表示经独立快照重建的恢复核验结果，不回写 intent。使用当前核验 UTC `verified_at`，原 UUID 与原 identity/preparation 不变。若 isolation evidence 缺失，则以冻结六字段和本次时间原子创建；若已存在，必须精确匹配冻结六字段和当前 target/manifest/count/resource，才允许原子刷新其 `verified_at` 并以同一时间创建成功证明。若有效 attestation 已存在，则不刷新 isolation、不改任何文件，只验证。坏/字段不符 attestation 或损坏/不匹配 isolation evidence 均保持 inconclusive 且不覆盖。marker 不存在时不调用证明构造或写文件；只允许在 intent、manifest、isolation、attestation 均存在且 `validate_attestation` 成功、当前 snapshot/identity/resource 全部匹配时只读返回 completed。marker 缺失且没有有效 attestation（无论 snapshot 是否相符）都保持 inconclusive，不创建 marker、不重建成功证明。marker phase=`index_unconfirmed` 永远禁止补成功证明。marker 为 prepared 且实际表空时可以确认未写入并清除；其它不一致保留 marker。
7. marker 存在的恢复路径中，成功证明通过 validate 并完成原子 no-replace 落盘后，从磁盘重读证明，再将 marker 更新为 completed 并尝试清除；已有有效证明直接核验并清 marker。锁/marker 清理故障使用安全 failures 保留人工可见阻断。任何路径离开前均在 `finally` 释放已取得的 lease 并关闭连接。

**恢复矩阵 RED/GREEN 用例：** 覆盖 marker 存在且证明缺失、隔离证据缺失、隔离文件合法但 attestation 缺失的崩溃窗口；该窗口恢复必须重新核对当前完整快照/identity/resource/lease，使用原 run/intent 并原子刷新同绑定 isolation `verified_at`，再创建证明；损坏、字段不符、绑定不符 isolation 不得刷新。覆盖有效证明已写但 marker 未清，以及 marker 已清且 intent/manifest/isolation/attestation 均完整的只读历史核验，两者均不重写文件。marker 缺失无有效 proof、proof 损坏、marker index_unconfirmed 均不得成功；source 原路径不存在仍可恢复；recover 对 service prepare/index 调用计数为零；原始 identity/namespace/warnings/strategy 不被默认值替换；旧 run ID 不变且 `created_at` 使用本次 UTC；空表不重导；partial、extra、duplicate、wrong locator/scope/owner、wrong target/db/schema、identity drift、坏/缺字段 intent、manifest mismatch、非空前态、pending 冲突、lease 被占用、resource ref 缺失、已存在坏证据均不生成 success proof、不覆盖 intent/manifest/attestation、不调用写入。所有恢复成功、inconclusive、拒绝和异常分支均检查释放 lease 并关闭连接。

恢复行为采用独立红绿段，不能只以任务 2 的 runner 成功用例代替：

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/scripts/test_rag_ingest.py -q -p no:cacheprovider -k recover_ingestion --basetemp .pytest-tmp-t08-recovery-red-20261016
.venv/Scripts/python.exe -m pytest tests/unit/scripts/test_rag_ingest.py -q -p no:cacheprovider -k recover_ingestion --basetemp .pytest-tmp-t08-recovery-green-20261016
```

RED 必须来自新增恢复契约失败；GREEN 必须覆盖恢复成功及不准入矩阵，调用陷阱明确断言 `prepare_file`/`ingest_prepared`/`index` 均为 0 次。

**待主控裁定的契约缺口：** 冻结 spec 要求“显式 `index_unconfirmed` 不得恢复成成功”，也要求进程在成功 commit 后、证明落盘前能通过完整实际快照恢复；但 intent 固定为 `phase=prepared`，`RunRecord` 仅为返回对象，spec 没有规定写入结果的持久化 sidecar，也未定义 index 返回 `index_unconfirmed` 后到 sidecar 原子更新前进程崩溃时的裁决。本文建议用 T08 私有 pending marker 持久保存阶段；明确收到 `index_unconfirmed` 后永久标记该 run 不可成功恢复。进程崩溃在调用结果尚未持久化的窄窗口，现有接口无法识别“明确返回 unconfirmed”与“commit ack 丢失”；需要主控确认接受以“已持久化的明确 unconfirmed 阻断、其余只按完整快照恢复”的边界，或要求调整T02写入确认接口。T08 不通过猜测消除此冲突，也不改共享冻结字段。

### 任务 4：T08 包内组合离线验收与交接

**文件所有权：** 仍仅允许前述四个实现/测试文件。唯一未来执行证据文件为 `docs/rag-work/evidence/t08/2026-10-16-execution.md`；T08 实施者写入本包红绿、局部 lint、差异审计和限制，主控只向同一文件追加跨包组合结果。本计划不创建 evidence、README 或索引文件。

**命令和接受标准：**

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/scripts/test_rag_ingest.py -q -p no:cacheprovider --basetemp .pytest-tmp-t08-runner-red-20261016
.venv/Scripts/python.exe -m pytest tests/unit/scripts/test_rag_ingest.py -q -p no:cacheprovider --basetemp .pytest-tmp-t08-runner-green-20261016
.venv/Scripts/python.exe -m pytest tests/unit/harness/test_knowledge_ingestion.py tests/unit/harness/test_chunking_service.py tests/unit/infrastructure/test_pgvector_provider.py tests/unit/infrastructure/test_embedding.py tests/unit/infrastructure/test_rag_contracts.py tests/unit/infrastructure/test_embedding_identity.py tests/unit/harness/test_ingestion_attestation.py tests/unit/scripts/test_rag_ingest.py -q -p no:cacheprovider --basetemp .pytest-tmp-t08-combined-20261016
C:/Users/A1985/AppData/Local/uv/cache/archive-v0/QcnXSOJpzJovd_JVU2u2H/ruff-0.15.7.data/scripts/ruff.exe check --no-cache app/infrastructure/rag/pgvector_provider.py scripts/rag_ingest.py tests/unit/infrastructure/test_pgvector_provider.py tests/unit/scripts/test_rag_ingest.py
git diff --check
```

**通过标准：** T08 两个单测文件定向红灯都由预期未实现契约引起；绿色组合中所有新用例通过，陷阱计数证明本轮验收没有真实 PG/SQLAlchemy 引擎、OpenAI SDK、socket 网络或 LLM 外联；runner happy path 的 prepare/index 均为一次，所有前置拒绝为零次写入，recover 永远为零次 source preparation/index；恢复和失败矩阵不覆盖不可变文件，允许的 isolation 时间戳刷新仅限前述同 run 绑定崩溃恢复；完整 Ruff 原始输出与基线逐项对照，只可保留已确认的既有 E402，不得增加新诊断，也不以忽略规则后的命令作为通过条件；`git diff --check` 全过。每条 pytest 命令使用独占、此前不存在且未复用的 basetemp。不得因清理临时目录而扩大写权限或删除旧目录。

包内离线全绿只证明受控替身下的逻辑与写入边界。不得据此宣称真实 PostgreSQL advisory lock/事务、真实 resource registry、实际 embedding、正式摄入或任何 G1～G6 门通过。T11 正式运行需要独立 plan 和新的用户授权/既定门禁。

## 规格覆盖与实施前待决事项

| 冻结要求 | 本计划落点 |
|---|---|
| A1 一次 prepare、不可变 preparation、source SHA/策略/warnings 不丢失 | 第一层依赖表；任务2、任务3的 `run_ingestion` 步骤2/6与恢复步骤6。 |
| A3 prepared manifest 无正文原样进入运行 envelope；snapshot 完整行多重集合、保留重复 | 第二层 snapshot/manifest；任务1全部映射和任务3恢复步骤5。 |
| A4 意图/清单写前原子落盘、空前态、lock/pending、异常不假成功 | 第二层资源 adapter/原子持久化；任务2函数契约；任务3写入流程。 |
| A4 只读恢复、无 source 重读、原 run/identity、使用当前 verified_at、空结果不重导 | 第二层恢复；任务3 `recover_ingestion` 步骤及红绿矩阵。 |
| A4 phase/error_code/safe_summary/failures/attestation_path | 第二层 RunRecord；任务2 `_make_run_record` 和任务3结果归约。 |
| B/C T04 attestation/embedding identity，不复制契约 | 第一层依赖表；任务3证明流程，所有路径复用 T04 纯函数。 |
| 写入确认/未知 commit/`index_unconfirmed` | 全局约束；任务2状态设计、任务3第4步、规格缺口说明。 |
| T02/T04 完成后写 runner/provider，provider 与 T10 串行 | 全局文件权表；任务1/2明确交接点。 |

实施前请主控裁定两项不扩展冻结契约的装配决定：

1. 是否接受本文建议的 T08 私有 `RAG_INGEST_CONTROL_DIR/resources.json` + `bindings.json` adapter，或由主控/T07提供等价的真实 target/resource/binding 注册方式；target、resource、binding 映射或 runner-only writer 证据任一未就绪时，所有生产入口必须 fail closed。此决定不使 T09 依赖 T08 adapter。
2. 是否接受本文的 session advisory lock + 无 TTL pending marker 方案，以及“明确持久化的 index_unconfirmed 永不升级；未持久化返回值只能由完整快照裁决”的恢复边界；若不接受，需先补充 T02/T08 可消费的持久写入确认契约。

上述缺口不改变计划所需的离线替身验收，也不授权真实运行。文档状态保持“草案待主控审阅/用户确认”，不可标记 T08 实现、真实 PG 或 G1～G6 通过。

## 主窗口文档复核状态

已完成一轮定向修订与主窗口复读，具体发现、关闭说明及实施前待确认设计见[第二批计划审阅记录](2026-10-16-second-wave-plan-review.md)。当前仍为待用户确认的计划，未开始实现或运行测试。

## 2026-10-17 最新正式审阅状态

**需修订，暂不派发实现。** [正式审阅问题与修订顺序](2026-10-17-second-wave-plan-review.md)更新本计划先前初读状态；当前未处理的问题须定向修订并复核关闭，再确认计划。此次仅追加审阅状态，未代为修改设计或实施。
