# T09 准入与基线报告对接实施计划

> 执行要求：本计划经主控审阅及用户确认后，按 `superpowers:executing-plans` 逐项实施；各步骤使用 checkbox 跟踪。当前仅为草案，任何 checkbox 均未开始。

**目标：** 将已验收的 T03 评测器与 T04 纯契约核验接入 RAG-D 正式准入门，并使每次离线或正式运行都产生符合 `rag-baseline-report-v1` 的严格、安全、可追溯报告。

**架构：** T09 只维护书籍 benchmark 的准入编排与报告适配，复用 T03 的资产校验和 `evaluate` 结果契约，复用 T04 的 `AttestationExpectation`、`IndexSnapshot`、embedding identity 与 `validate_attestation`。准入所需的 expectation、真实目标映射、实际快照、embedding binding 和隔离记录必须来自证明之外的受控来源；T09 不创建或写入产品索引，也不从证明回填 expectation。

**技术栈：** 现有 Python 3.12 项目环境、pytest、已缓存 Ruff 0.15.7；不安装依赖，不连接 PostgreSQL、embedding SDK、judge 或其他外部服务。

**冻结依据：** [共享契约 `rag-mvp-contracts-v1.0.1`](../specs/2026-10-16-rag-mvp-contracts-v1.md)，计划编写时 SHA-256 为 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。本计划同时追溯至 [`2026-10-15-rag-mvp-execution-plan.md`](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan.md)、[`2026-10-15-rag-mvp-execution-plan-review.md`](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan-review.md) 与 [`2026-10-16-rag-mvp-dag-and-scheduling.md`](../../../superpowers/rag-foundation/2026-10-16-rag-mvp-dag-and-scheduling.md)。

**状态：** 草案，待主控审阅及用户确认。spec SHA 或字段若发生变化，先由主控裁定新版本和任务影响，本计划不得自行改写冻结契约。

## 全局约束

- 正式 baseline 固定 `top_k=5`、题目恰为 20 条；每题最多调用一次 `evaluate`，不得为重试或多 k 再次检索。
- `validate_admission` 与 `run_baseline` 保持现有公开位置和既有参数；只按冻结 spec 增加 keyword-only `expected` 与 `snapshot`，默认 `None` 仅为签名兼容，缺失时必须拒绝准入。
- `AttestationExpectation` 必须逐字段来自独立受控来源；严禁从 `attestation` 复制 source、target、fingerprint、manifest、scope、owner 或 isolation 作为期望值。
- 证明必须由 T04 `validate_attestation(attestation, expected=..., snapshot=...)` 校验。T04 的校验器不读取资源记录或隔离文件；T09 还须确认这些引用与受控来源匹配。一个 `verified=True` 或同名引用字符串不能单独成为证据。
- `IndexSnapshot` 必须代表实际目标的完整行多重集合；保留重复行，并核对 target、database、schema、row count 和 manifest 摘要。T09 只消费传入快照，不复制 T08 的 provider 写入/恢复逻辑，也不直接改 provider。
- 实际 embedding identity 从当前 `agent._coordinator._providers["vector"]` 对应 `PgVectorProvider._embedding` 读取，使用 T04 `describe_embedding(service, binding)` 与 `fingerprint_embedding(identity)`。允许为读取配置而惰性创建 SDK client；禁止调用 `embed_one`、`embed_many`、`embeddings.create` 或任何远端 embedding 请求。
- 当前已知六种报告状态固定为 `blocked:asset_invalid`、`blocked:not_real_pgvector`、`blocked:unattested_product_index`、`infrastructure_inconclusive`、`completed_judge_degraded`、`completed`。探测已确认的非 PG 后端或 SQLite 为 `blocked:not_real_pgvector`；连接、embedding 或 I/O 探测无法判断时为 `infrastructure_inconclusive`；证明、资源或隔离证据缺失/不符为 `blocked:unattested_product_index`。
- 首个检索失败、非法请求或结构不合规结果立即停止，失败尝试仍写入 `results` 并计入 `failed_count`。judge 缺失、部分无效或全部不可用不增加检索失败数；20 题检索均健康时允许 `completed_judge_degraded`。低召回不设阻断阈值。
- 报告所有必需字段始终存在；尚不可得字段写 JSON `null`。报告错误仅使用安全规则 ID、题目 ID 和冻结错误码；不得输出异常原文、SQL、堆栈、连接串、API key 或完整 SDK endpoint。所有报告必须通过严格 JSON 编码，不允许 NaN/Infinity。
- 本地测试使用合成资产及受控对象，不读正式 EPUB/corpus，不调用真实 PostgreSQL、SDK、judge 或外网；不安装依赖、不改共享 `conftest.py`。pytest 使用证据目录下本次唯一且运行前确认不存在的临时目录，禁用 cache provider；不清理已有临时目录。
- T09 仅在离线用例中验逻辑，不宣称真实资源、真实证明、真实检索质量或 G1 通过。G1 仍需 T02/T03/T04/T09/T10 集成验收；G1～G6 当前均未通过。
- README、`docs/rag-work/README.md`、执行计划索引、状态和主执行清单由主控单写。本计划不改 T03/T04 证据，不改冻结 spec、原始 superpowers 计划或其 DAG 文档。

---

## 第一层：模块总览

### 边界与数据流

T09 的责任是把 RAG-D benchmark 从“收到几个看似成功的声明便开始评测”改为“验证资产、独立准入上下文、实际索引快照和当前查询实例全部一致后才开始评测”，并把结果写成完整基线报告。入口仍是 `benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py` 中的 `validate_admission` 与 `run_baseline`。

受控数据流如下：

1. `validate_assets(asset_dir, source_path)` 检验正式资产结构、20 个唯一且已核验的问题、源文件 SHA 和 corpus 证据；资产失败立即产生 `blocked:asset_invalid`，不调用 evaluator。
2. 对 coordinator 的 backend、provider 集合与实际 dialect 做检查；明确非 PG 时阻断，无法连接而不能判断时报告基础设施未决。
3. 从受控环境适配层取得独立 target/resource 映射和 `EmbeddingBinding`；从可信只读读取方取得 `IndexSnapshot`；隔离证据由受控引用解析器读取并验证。任何一项缺失、来源不可信、目标不唯一或字段不一致都在首题前拒绝。
4. 对运行中实际 `EmbeddingService` 读取 model、dim、SDK endpoint，并与受控 `EmbeddingBinding` 比较；重算实际 fingerprint，要求它与独立 expectation、快照 target 和证明完全一致。该步骤不发 embedding 请求。
5. 用 T04 校验器对完整 attestation、独立 expectation 和真实快照执行纯逻辑核验；另外比较隔离记录引用与受控引用，因为 T04 仅能验证引用格式，不能打开引用目标。
6. 只有全部 gate 通过，才以固定顺序每题一次调用 `agent.evaluate`。遇首个基础设施/结果结构故障便停止并保留失败 attempt；judge 降级单独计入报告。
7. 报告构造器统一补齐 D3 全字段、状态、资源与 identity 绑定、计数、结果、错误分类和 limitations，并以严格 JSON 可序列化性作为输出不变量。

benchmark 不负责解析或再验证 T08 摄入计划、不写库、不造成功证明、不改变线上检索链，也不把受控测试的成功报告解释成产品验收。T09 的离线开发可独立于 T08；实际目标快照由经过授权的调用方传入，T09 不导入尚未完成的 T08 runner。

### 当前实现事实与边界

- T03 Round 2 和 T04 的纯逻辑实现已完成各自批准范围；主控组合离线结果为 547 passed、1 deselected。T03 明确记录这不代表真实 PG/embedding/judge、真实 20 题 baseline 或正式 gate 通过；T04 明确记录资源记录、真实数据库快照、隔离引用来源仍由后续调用方核查。
- 当前 `validate_admission` 只要求 attestation 含最小字段集合，并检查 backend/provider/dialect/provider-set、写入计数相等、doc id 和源 SHA；corpus isolation 仍接受 `mode` 加真值 `verified`。它没有核对完整 T04 schema、真实 target、独立 fingerprint、完整快照、scope/owner 或真实隔离内容。
- 当前 `run_baseline` 没有 `expected`、`snapshot` 参数，也没有输出 D3 的完整字段；但已有资产阻断、单次逐题 evaluate、首错停止、judge degraded 分类、坏 metrics 安全合成和部分计数不变量。T09 应在这些行为上收紧 gate 并补足报告，不改写 T03 evaluator 的指标语义。
- 当前测试文件已经局部禁止 `PgVectorProvider` 构造/连接、`ChatOpenAI`/`OpenAI` SDK 构造并默认禁用 judge；它没有覆盖任意裸 socket 外联。T09 必须补充仅作用于 `tests/eval/test_rag_d.py` 的网络陷阱，且不改全局 fixture。
- `app/core/config.py` 现有配置含 `rag_backend`、`embedding_model`、`embedding_dim` 等字段，但未定义受控 service/deployment/version 注册、公开 target 映射或 resource record 解析配置。`EmbeddingService` 持有 model/base_url/dim 和 lazy client，但 API key/base URL 不能代替受信 service identity。不得将这些缺失格式写成已经存在的项目配置。
- `validate_attestation` 会校验 `AttestationExpectation`、`IndexSnapshot` 的字段与行、manifest、target、embedding identity、count、scope/owner，以及 isolation 的 mode/target/manifest/row_count/time/resource reference；它不会读取 resource record，也不会验证 `isolation_evidence_ref` 指向的文件内容或授权来源。T09 必须补足边界核验，不能宣称 T04 已证明这些外部事实。

### 推荐的最小运行时装配方式

冻结函数签名只允许新增 keyword-only `expected` 与 `snapshot`；不修改 `Settings`、不增加环境变量或共享 schema。推荐将当前 `settings_obj` 参数用作兼容载体：现有 `Settings` 仍照常提供 `.rag_backend`；需要准入时，调用方传一个轻量 wrapper（例如 `SimpleNamespace`），保留相同 `.rag_backend`，并附带 `.t09_admission_context`。缺少该属性时 resolver 明确拒绝。这是 T09 benchmark 私有输入约定，不是已经存在的项目配置，也不改变 `validate_admission`/`run_baseline` 的公开签名。

`.t09_admission_context` 是精确字段集合，字段类型如下：

| 字段 | 类型 | 来源及用途 |
|---|---|---|
| `binding` | T04 `EmbeddingBinding` | 受控 service/deployment 注册转换出的实际 SDK endpoint 匹配绑定；`expected_endpoint` 仅内存使用。 |
| `target_index_id`、`database_id`、`schema_name` | 非空 `str` | T07 核验后的公开资源映射。与 `snapshot` 三字段逐一相等。 |
| `resource_record_ref` | 非空安全 `str` | 受控资源注册给出的定位引用；与隔离文件中的引用逐字相等。T09 不把它当文件路径。 |
| `scope` | `Literal["global", "private"]` | 受控本次摄入意图；与 `expected.expected_scope` 相等。 |
| `owner` | `int | None` | global 必须为 `None`；private 必须为正整数且拒绝 bool。与 `expected.expected_owner` 相等。 |
| `ingestion_run_id` | UUID `str` | T11 运行记录中的 ingestion run ID；必须等于 attestation 的 `ingestion_run_id`。它只绑定历史摄入事实。 |
| `run_dir` | `pathlib.Path` | T11 受控调用实际传给 T08 `run_ingestion(..., run_dir=...)` 的目录，由同一授权调用者传入 T12；不是从 `RunRecord` 未声明字段、proof 或自由 CLI 字符串推导。 |
| `isolation_evidence_ref` | 非空安全 `str` | T11 run record 中对本次隔离证据的登记值；必须等于 attestation 的同名字段。它只作引用比较，不用于拼接任意路径。 |
| `ingestion_exclusivity` | 精确 mapping，键为 `target_index_id:str`、`ingestion_run_id:str`、`verified:bool`、`record_ref:str` | 经验证并保留的历史摄入排他事实；要求 target/run ID 与摄入上下文一致、`verified is True`。此处没有 `active` 字段，也不要求 T08 已释放的 writer lease 继续 active。 |
| `baseline_protection` | 精确 mapping，键为 `target_index_id:str`、`database_id:str`、`schema_name:str`、`holder_report_run_id:str`、`mode:str`、`active:bool`、`record_ref:str`、`verified_at:str` | T12 调用前取得的当前只读/冻结资源保护；要求 target/database/schema 一致、`mode == "read_only_frozen"`、`active is True`、`verified_at` 为 UTC。T12 先生成合法 UUID 并以它取得保护，T09 将同一 UUID 用作本次 baseline `run_id`；不与 proof 的 ingestion UUID 比较。 |

这组字段是推荐的 T09 私有 adapter 输出形状，便于主控审阅和单测；当前 repo 尚没有提供者或正式配置路径。可本地实现的行为边界是确定的：`_resolve_admission_context(settings_obj, expected, snapshot, attestation, expected_source_sha256)` 仅从现有 `settings_obj.t09_admission_context`、冻结 `expected`/`snapshot`、attestation 和 `expected_source_sha256` 参数读取并逐字段核对，不尝试发现环境变量、解析任意 URI、从 proof 回填或导入 T08 runner。T12 生产 adapter 必须按已批准的来源装配，具体顺序为：取得 T07 核准的公开 target/database/schema 映射及其 resource record ref；通过 T07 指定的只读 reader 校验该 resource record 与受控 `EmbeddingBinding` 注册，重复、缺失、冲突或无法读取时不构造 wrapper；从本轮 T11 调用实际使用的 T08 run directory 及其受验证 intent/运行证据读取 `ingestion_run_id`、历史排他记录和 `isolation_evidence_ref`，不依赖 `RunRecord` 未声明的目录字段，也不把已清理的 pending marker 或已释放 writer lease 当作 active 门槛；在授权目录内只读验证隔离证据并构造完整 `IndexSnapshot`（保留重复 rows）；从独立 source/assets、resource mapping、binding 与 snapshot 组装 `expected`；先生成 baseline report UUID，再由 T12 当前调用者取得匹配的只读/冻结保护，最后把以上已验证值按本表装入 `SimpleNamespace` wrapper。任一来源格式尚未批准、reader 未绑定、验证结果不唯一或保护不 active，adapter 不返回可准入 context，调用进入 `blocked:unattested_product_index` 且 evaluator 调用数为零。T01/T07/T11/T12 的生产来源和格式目前仍未就绪，不能用测试 fake 或本建议声称其已存在。

`run_dir` 是唯一授权 ref 根。隔离内容只从固定子项 `run_dir / "isolation-evidence.json"` 只读读取；先确认原始 candidate 不是 symlink，再解析根目录和文件真实路径，要求文件存在、为普通文件且真实路径仍位于根目录内。proof 的 `isolation_evidence_ref` 不可直接送入 `open`；它须先与 context 的登记引用完全相等。JSON 必须恰含 `mode`、`target_index_id`、`manifest_sha256`、`row_count`、`verified_at`、`resource_record_ref` 六键，值与 context、`expected` 和实际 snapshot 对齐。`ingestion_exclusivity` 是历史事实，校验 `verified=True` 即表示受控 adapter 已凭 `record_ref` 核验历史持有记录；不能把已释放的历史 writer lease 当当前门。`baseline_protection` 是当前事实，独立校验 `holder_report_run_id` 与 report run ID 相等。读取 resource record 与实际 lease 的过程由可信 adapter 提供；T09 不臆造它们的磁盘 schema，只校验已解析的 typed/mapping 输出。

`expected` 独立来源固定为：source SHA 从 `validate_assets` 后的 source digest；target/database/schema、scope/owner、resource ref、binding 和历史排他事实由上面的受控 context；fingerprint 由受控 binding 与当前真实 service instance 经 T04 identity 函数计算后与 `expected.expected_embedding_fingerprint` 对照；manifest/count/rows 来自真实只读 `snapshot`；isolation evidence 来自授权根内实际文件。T04 对 expectation/snapshot/attestation 的纯值核验仍须执行。

`baseline_protection.holder_report_run_id` 是调用方在 T12 先生成的报告 UUID；T12 用它取得本次只读/冻结保护，再放入 wrapper。`run_baseline` 在调用 gate 前从精确 context 取该 UUID，校验其 UUID 格式并原值用作 D3 `run_id`，不能另造一个与保护持有者不同的值；resolver 校验同一 context 中保护记录的 active 状态、资源字段、引用和时间。缺 context 时可自行产生 UUID 以形成完整 blocked 报告。历史 `ingestion_exclusivity.ingestion_run_id` 则必须等于 attestation ingestion UUID，两者是不同生命周期、不同含义的 ID。T09 既不要求已完成摄入的 pending marker 仍存在，也不要求旧 writer lease 仍 active；它要求的是独立核验的历史事实、独立快照/proof 绑定，以及当前 baseline 只读/冻结保护。

缺 adapter 时，传原始 `Settings` 可以正常构造 D3 blocked 报告，但不得调用 evaluator。为使本包并非“永远 blocked 的 stub”，离线测试还必须以独立构造的受控 fake wrapper/context、完整 fake snapshot 与 embedding service identity 跑通 20 题，产生结构完整的受控 `completed` 或 `completed_judge_degraded` 报告。该离线正例证明 T09 编排能力，不是产品成功证据。

## 第二层：子模块概述

| 子模块 | 职责与接口 | 数据流、状态与错误 |
|---|---|---|
| 资产准入 | 保留 `validate_assets(Path, Path\|None) -> AssetBundle`；验证资产、源和题集。 | 资产不合法为 `blocked:asset_invalid`，报告无结果且 20 题均未运行；安全错误仅写 `asset_validation`。 |
| 独立信任上下文 | `_resolve_admission_context(settings_obj, expected, snapshot, attestation, expected_source_sha256)` 从既有 `settings_obj` 参数的私有 wrapper、冻结 expectation/snapshot 参数及已校验的 source SHA 解析精确字段。 | 原始 Settings、缺注册、字段类型/引用不符在首题前阻断；真实只读探测失败归 `infrastructure_inconclusive`。不得以 attestation 自报值补齐。 |
| 六项 gate 与 T04 契约验证 | 保留 `AdmissionResult(allowed, status, failures)`；验证 backend/provider/dialect/provider-set/attestation/corpus-isolation，并调用 `validate_attestation`。 | 聚合所有已判定失败的安全规则 ID；backend/provider 明确非 PG优先 `blocked:not_real_pgvector`，证明/资源/隔离不符为 `blocked:unattested_product_index`。 |
| 当前 embedding identity | 从实际 vector provider 的同一 `EmbeddingService` 与受控 binding 构造 `EmbeddingIdentity`，计算 SHA-256 指纹；每题 evaluate 前后重读同一对象。 | 首题前不符则阻断；运行中对象替换/配置漂移时，未开始的题不调用，正在评测的题改为失败 attempt，不计有效；endpoint/API key 不进入报告。 |
| 单轮 baseline 与计数 | 保留 T03 `evaluate` 输入和 `_validate_evaluation_metrics` 语义；一次遍历题单，首错停止，并复核 identity。 | healthy/empty 且前后 identity 一致才计有效；judge 降级不计检索失败；首个 retrieval error/identity drift/invalid metrics/evaluator exception 保留完整 D1 attempt 并停止。 |
| D3 报告 envelope | 新增私有报告构造/序列化边界，输出所有 D3 字段并安全投影资源和 embedding 信息。 | blocked 前置报告填 null/空数组和 0/20；attempted = valid + failed；not_run = 20 - attempted；严格 JSON 失败则报告构造不成功，禁止静默 NaN。 |
| 离线测试与证据 | 仅改 `tests/eval/test_rag_d.py`，记录结果到唯一执行证据入口。 | 假 target、fake snapshot、fake binding 只证明适配/规则逻辑；零网络、零 SDK request、零 PG connection 断言必须通过；不把离线绿色升格为 G1。 |

## 文件职责与写入范围

### 执行时允许变更

- `benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py`：T09 唯一产品代码文件；只扩展 gate/context/report 编排。
- `tests/eval/test_rag_d.py`：T09 唯一测试文件；更新 helper 使准入用例显式提供受控 expectation/snapshot/context，增加信任边界、report schema、联网陷阱覆盖。
- `docs/rag-work/evidence/t09/2026-10-16-t09-verification.md`：经批准执行后，作为 T09 唯一实施证据入口；计划阶段不创建该文件。
- `docs/rag-work/evidence/t09/.pytest-tmp-t09-fixture-smoke-20261016/`、`docs/rag-work/evidence/t09/.pytest-tmp-t09-admission-red-20261016/`、`docs/rag-work/evidence/t09/.pytest-tmp-t09-admission-green-20261016/`、`docs/rag-work/evidence/t09/.pytest-tmp-t09-runner-red-20261016/`、`docs/rag-work/evidence/t09/.pytest-tmp-t09-runner-green-20261016/`、`docs/rag-work/evidence/t09/.pytest-tmp-t09-report-red-20261016/`、`docs/rag-work/evidence/t09/.pytest-tmp-t09-report-green-20261016/`、`docs/rag-work/evidence/t09/.pytest-tmp-t09-full-20261016/`、`docs/rag-work/evidence/t09/.pytest-tmp-t09-combined-handoff-20261016/`：执行命令使用的专属临时目录；每次运行前逐一确认目标不存在，保留，不清理，不纳入产品/证据数据。同名目录存在时使用新的完整唯一目录名并在证据中记录。组合交接 tmp 由主控确认和使用。

### 明确不写入

不改 `app/agents/retriever.py` 或 `tests/unit/agents/test_retriever.py`；不改 T04 的 `contracts.py`、`embedding_identity.py`、`ingestion_attestation.py` 及其测试；不改 T08 的 `scripts/rag_ingest.py` 或其后续新增代码；不改 T02 的 `pgvector_provider.py`、`embedding.py`、`knowledge_ingestion.py`；不改 `app/infrastructure/rag/coordinator.py`、`app/core/config.py`、`alembic/env.py`、共享 `conftest.py`、正式 EPUB/corpus/question assets、README、spec、索引、T03/T04/T08/T10 计划或证据。若实现发现跨包公共接口必须改变，停止该项并由主控串行裁定，不在本包扩大写权。

### Task 0：先建立本模块安全围栏与测试隔离

**文件：** `tests/eval/test_rag_d.py`。这是任何新增测试或红灯运行前的第一个实现步骤。

**步骤与边界：**

- [ ] 先只读确认 T03 已释放 `rag_d.py`/`test_rag_d.py` 写权，且主控没有同时运行本包或组合 pytest；核对 T09 专属 tmp 路径不存在。不得先跑现有或新增测试。
- [ ] 先在 `test_rag_d.py` 局部 fixture 安装 `socket.socket.connect`、`socket.socket.connect_ex`、`socket.create_connection` 和当前测试依赖中实际可触达的 HTTP client 连接入口陷阱；保留现有 PG provider 构造/连接、OpenAI/ChatOpenAI 构造、禁用外部 judge 的陷阱及零调用 teardown 断言。任何调用即抛出固定安全错误，输出中不带 endpoint 或秘密。
- [ ] 同一 fixture 增加 embedding `embed_one`/`embed_many`/`embeddings.create` 与 judge 调用计数，初始均为零。只给允许的受控 identity metadata 读取，不允许触发模型或数据库调用。
- [ ] 先人工审阅 fixture 是否涵盖模块里所有外联入口和初始化顺序，再运行一个不会进入 gate 的现有纯资产用例 `test_assets_validate_and_adapter_uses_full_paragraphs`，确认围栏建立后测试仍可本地运行且调用计数为零。
- [ ] 把隔离规则、陷阱覆盖范围和首次安全 smoke 结果记入 T09 唯一证据文件；Task 1～3 的新行为测试只能在本步骤通过后开始。

**首轮 smoke 命令：**

```text
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py::test_assets_validate_and_adapter_uses_full_paragraphs --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-fixture-smoke-20261016 -q -p no:cacheprovider
```

## 第三层：子模块详细实施计划

### Task 1：增加独立 context 消费边界与严格准入

**文件：** 修改 `benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py`；测试 `tests/eval/test_rag_d.py`。

**消费接口：** `AttestationExpectation` 精确字段为 `expected_source_sha256`、`expected_target_index_id`、`expected_embedding_fingerprint`、`expected_manifest_sha256`、`expected_scope`、`expected_owner`、`isolation_evidence`。`IndexSnapshot` 含 `target_index_id`、`database_id`、`schema_name`、`row_count`、完整 `rows` 与 `manifest_sha256`。`EmbeddingBinding` 含 `service_id`、`deployment_id`、`model_version`、仅内存的 `expected_endpoint`。validator 为 `validate_attestation(attestation, *, expected, snapshot) -> ContractCheck`。

**生产接口：** 当前函数签名是 `validate_admission(agent, settings_obj, attestation, corpus_isolation, dialect_getter=_default_dialect, expected_source_sha256=None) -> AdmissionResult`。新增的 `expected: AttestationExpectation | None = None` 与 `snapshot: IndexSnapshot | None = None` 为 keyword-only 参数；保留原有 positional 兼容。签名可被旧调用，但 `expected`、`snapshot` 或受控 context 缺失时 `allowed=False`，不会因旧调用形式而被放行。

**私有字段设计：** `_resolve_admission_context` 从 `settings_obj.t09_admission_context` 读取精确 mapping，字段与“推荐的最小运行时装配方式”表一致：包括 `binding`、target/database/schema、resource ref、scope/owner、`ingestion_run_id`、`run_dir`、`isolation_evidence_ref`、`ingestion_exclusivity`、`baseline_protection`。不得再使用含糊的 `run_id`、`exclusivity_record_ref` 或单一 `exclusivity` 字段。`ingestion_exclusivity` 必须恰含 `target_index_id:str`、`ingestion_run_id:str`、`verified:bool`、`record_ref:str`，其中 verified 必须是字面 `True`，target/run 与独立 context 匹配；不要求已释放的历史 writer lease 仍 active。`baseline_protection` 必须恰含 `target_index_id:str`、`database_id:str`、`schema_name:str`、`holder_report_run_id:str`、`mode:str`、`active:bool`、`record_ref:str`、`verified_at:str`；它表示本次 baseline report run 持有的当前 `read_only_frozen` 保护，active 必须是字面 `True`，target/database/schema 与 snapshot 一致，holder 必须等于报告 `run_id`，verified_at 是 UTC。所有标识非空且通过安全引用检查；scope/owner 组合有效；bool 不可冒充 int。多键、缺键、额外键和未知对象一律按 `types_invalid` 或 `isolation_unproven` 失败。测试中用独立构造的 `SimpleNamespace(rag_backend="pgvector", t09_admission_context=...)`，不在 Pydantic `Settings` 增加字段；未来 T12 在授权调用边界先创建 report UUID、获取当前保护，再构造同形 wrapper。该 wrapper/context 是本包私有适配协议，不是已经存在的配置事实。

**需要的私有函数及结果：**

- `_resolve_admission_context(settings_obj, expected, snapshot, attestation, expected_source_sha256)`：从现有 settings 参数的私有 wrapper 和冻结 `expected`、`snapshot` 参数解析 context；把 `expected_source_sha256` 与 expectation source 对照，把 context target/database/schema/scope/owner 与 expectation 和 snapshot 对照，把 `ingestion_run_id` 与 attestation ingestion ID 对照。context 的 `baseline_protection.holder_report_run_id` 是 T12 adapter 预先绑定的报告 UUID；`run_baseline` 必须采用该 UUID 作为报告 `run_id`，不可重生成。只允许从已解析的 context `run_dir` 下固定读取 `isolation-evidence.json`；返回经结构检查的 `_ResolvedAdmissionContext` 或安全 `ContractCheck`。不解析 attestation 内的路径，不把秘密放进失败文本。缺 context 时 `run_baseline` 自行产生 UUID 形成完整 blocked 报告。
- `_describe_runtime_embedding(vector_provider, binding)`：输入已确认的 `PgVectorProvider` 与受控 binding；读取该 provider 真实 `_embedding`，调用 `describe_embedding` / `fingerprint_embedding`；输出 actual identity 与 fingerprint。捕获异常时只返回 `identity_unobservable` 或 `identity_mismatch` 等安全规则，不发 embedding 请求。
- `_read_isolation_evidence(context)`：输入经授权的 context；计算 `root = context.run_dir.resolve(strict=True)`，只读 `root / "isolation-evidence.json"`，解析后要求 file realpath 在 root 内、不是 symlink、是普通文件，JSON 顶层恰含 spec 的六键。不得根据 attestation/ref 字符串选择文件。
- `_validate_admission_evidence(attestation, expected, snapshot, context, actual_identity)`：先核对证明 `isolation_evidence_ref` 与 context 登记值，再把实际读出的 isolation JSON 与 `expected.isolation_evidence` 逐字段比较；交 T04 validator 验 schema、fingerprint、snapshot full rows/count/scope/owner；另比较 context target/database/schema、resource record ref、ingestion run ID、历史摄入排他事实和当前 baseline protection。当前保护的 holder 必须等于 adapter 绑定并由 `run_baseline` 采用的报告 run ID，不要求 proof ingestion UUID 充当 holder。返回安全 `ContractCheck`，不尝试证明 Python 对象的历史来源。
- `validate_admission(...)`：先检查 `settings_obj.rag_backend == "pgvector"`、实际 provider 是 `PgVectorProvider`、provider 集合恰为 `{"vector"}`；再区分 dialect 实测为非 PostgreSQL 和无法探测；随后验证真实 identity、独立 context 和完整 attestation。若 `expected_source_sha256` 缺失，或不等于独立 expectation source SHA，按 proof/context 不完整 fail closed；`run_baseline` 必须将刚完成 `validate_assets` 得到的 `assets.manifest["source"]["sha256"]` 通过既有参数传入。返回原 `AdmissionResult`，不抛原始异常，不启动评测。

**失败规则和优先级：** 确定 backend/provider/provider-set/SQLite 不符时返回 `blocked:not_real_pgvector` 并保留其余可确定 failures；连接或实际配置读取抛错、无法判断真实 dialect 时返回 `infrastructure_inconclusive`。expectation/snapshot/binding/resource/isolation context 缺失、字段或引用不匹配时返回 `blocked:unattested_product_index`。资产校验仍由 `run_baseline` 优先执行。安全 failure IDs 维持六项 gate 的既有 `backend`、`provider`、`provider-set`、`dialect`、`attestation`、`corpus-isolation`；必要的私有新 ID 如 `context_missing`、`resource_mismatch`、`identity_changed` 只含小写字母/数字/下划线，不扩充冻结六码 `error_code`。

**局部测试要求：** 当前 `_run_report` helper 和 `attestation()` fixture 使用最小旧形态，须改为显式构造全量 `AttestationExpectation`、`IndexSnapshot`、`EmbeddingBinding` 和成功 attestation。期望值由合成 source hash、受控资源、假 identity 与假完整 rows 独立构造；不得先读取证明再复制字段。

- 新建用例断言 legacy 调用缺 `expected`/`snapshot`/`expected_source_sha256` 任一项时阻断且 evaluator 调用数为 0。
- 用例分别改变 source SHA、target ID、database/schema、embedding service/deployment/model/dim/fingerprint、scope/owner、完整 manifest、行数和隔离证据的 mode/target/manifest/row_count/time/resource reference，确认失败且无评测调用。
- 对 context 缺失/多键/错类型、`run_dir` 越界文件或 symlink、文件缺失/JSON键多缺、resource reference 不同、target mapping 冲突、排他记录 run/holder/target 错误以及只提供 `verified=True`，逐项断言 fail closed。
- 构造完整多重集合含重复行；确认重复项不能被 set 去重后放行。
- 让 provider dialect getter 返回 `sqlite`，确认 `blocked:not_real_pgvector`；让 getter 模拟无法连接，确认 `infrastructure_inconclusive` 且不泄漏异常内容。
- 让 endpoint 或 SDK 配置读取失败并嵌入假凭证，确认报告和失败 ID 不含 endpoint、凭证或异常文本；fixture 断言 embed 请求计数为零。

**红绿步骤：**

- [ ] 在 fixture safety smoke 已通过后，先增加独立构造的 expectation/context/snapshot 正例及 legacy 缺 context 拒绝例；正例必须能跑完整 20 题并生成受控 completed envelope。
- [ ] 定向红灯只选择 `test_admission_requires_independent_context_before_evaluate`、`test_admission_rejects_mismatched_context_and_isolation_file`；记录当前缺参或旧 `verified` gate 导致的具体断言失败。
- [ ] 实现精确 mapping resolver、授权根内只读 isolation reader、binding identity 核验与严格 gate，保持既有公开位置、六个公共 error code 和 evaluator 契约。
- [ ] 定向绿灯重复同两项用例，并补全 backend/provider/dialect/provider-set 与 proof 匹配矩阵；确认合法受控 wrapper 可准入、legacy/no-context 明确拒绝、网络/PG/SDK调用为零。

### Task 2：实现统一 `rag-baseline-report-v1` envelope

**文件：** 修改 `benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py`；测试 `tests/eval/test_rag_d.py`。

**字段与结构：** 报告必须包含冻结 D3 字段：`schema_version`、`status`、`contract_version`、`run_id`、`created_at`、`backend`、`provider`、`dialect`、`target_index_id`、`embedding_config`、`embedding_fingerprint`、`attestation_id`、`artifact_manifest_sha256`、`isolation_evidence_ref`、`asset_sha256`、`expected_count`、`attempted_count`、`valid_count`、`failed_count`、`not_run_count`、`results`、`failures`、`evaluation_alignment`、`judge_enrichment`、`limitations`。JSON 中 unavailable 的 backend/provider/dialect/target/identity/attestation/manifest/isolation/assets 使用 `null`；blocked 结果的 `results=[]`、`attempted=valid=failed=0`、`not_run=20`。`expected_count` 一直表示正式基线要求 20。

**需要的私有函数及结果：**

- `_new_report_context(known_report_run_id=None)`：有已解析受控 context 时采用其中已绑定到当前保护的 `holder_report_run_id`，另生成 UTC `created_at`；缺 context 的 blocked 路径才新建 UUID `run_id`。绝不复用 attestation 的 ingestion run ID 作为报告 run ID。
- `_empty_report(status, failures, known_context)`：输出 D3 全字段，并用调用前已独立验证的信息填充字段；未知项写 `None`，题目结果保持空。
- `_completed_report(admission_context, assets, counts, results, failures, status)`：用已验证的真实 runtime identity、target、manifest、资源引用和题目资产摘要形成完整报告；从事实来源读取，不使用 attestation 补缺。
- `_validate_report(report)`：检查六状态、UUID/UTC 时间、必要字段、count 公式、results 顺序/ID 与已尝试题目一致、安全 failure 结构和有限数；用 `json.dumps(..., allow_nan=False)` 作为可序列化性检查，不在不合法时删字段或改成 0。

**字段约束：** `attempted_count == valid_count + failed_count`；`not_run_count == 20 - attempted_count`；`len(results) == attempted_count`。每个 result 仅含 `case_id` 和完整 D1 `metrics`。失败 attempt 必须有 `valid_for_quality=false`，并保留合成完整指标；report failures 使用 `rule_id`、`case_id`、冻结 `error_code` 等安全字段。`evaluation_alignment` 固定为 `paragraph-containment proxy`，`judge_enrichment` 固定为 `gold-answer/context enrichment`。`limitations` 必含 proxy 的局限、报告不代表 Tutor 质量；当前 identity 为 `alias_unpinned` 时也必须明确写出限制。健康低分仍可 completed。

**局部测试要求：** 每种前置 blocked 状态都断言 D3 所有字段完整，并确认未知值为 null；对成功、judge 降级、首题失败、异常、无效 metrics、资产非法、空检索及结果中途失败检查 count 公式、结果 ID 前缀和 `allow_nan=False`。向异常路径注入假 SQL URL/API key/异常秘密，断言 JSON 内无敏感文本；向 metrics 注入 NaN/Infinity、bool 数值、交叉字段矛盾，确认 fail closed 并保留安全失败 attempt。

**红绿步骤：**

- [ ] 先新增 `test_baseline_report_full_contract_and_strict_json`、`test_baseline_report_blocked_fields_are_explicit_nulls`，断言 D3 字段/blocked-null/count/strict JSON；运行这两个明确测试确认现有 `_envelope` 缺字段时失败。
- [ ] 实现统一 UUID/UTC 报告 context、blocked envelope、completed envelope 和 report 校验函数；不得改变 D1 metrics 字段含义。
- [ ] 以 `-k baseline_report` 定向组和新的 pytest tmp 运行 report tests，确认全部状态完整、安全且计数一致。

### Task 3：将 gate 接入单次 20 题运行并锁定状态语义

**文件：** 修改 `benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py`；测试 `tests/eval/test_rag_d.py`。

**生产接口：** 当前 `run_baseline(agent, settings_obj, asset_dir, attestation, corpus_isolation, source_path=None, dialect_getter=_default_dialect) -> dict[str, Any]`。新增 keyword-only `expected` 与 `snapshot` 可选输入，完整转交 `validate_admission`；另外把已校验 `assets.manifest["source"]["sha256"]` 通过既有 `expected_source_sha256` 参数传入，作为 proof source SHA 的独立比对值。任一项缺失时兼容地生成 blocked 报告，不允许开始题目循环。既有 `corpus_isolation` 参数继续保留签名，但只能作为兼容性输入；`mode`/`verified` 不再是准入证据，报告以受控解析得到的 `isolation_evidence_ref` 为准。

**运行时 identity 固定与漂移规则：** gate 前记录 vector provider 与其 `_embedding` 实例对象；在每题 `evaluate` 调用前和调用后，重新确认 coordinator 仍注册同一个 provider、provider 仍持有同一个 embedding service，并对该实例重跑 `describe_embedding` / `fingerprint_embedding`，要求身份仍等于准入时 identity 与独立 expected。T04 的单次 `describe_embedding` 会两次读取 model/dim/cached endpoint；T09 的题前/题后采样补足运行期间监控。配置变更但服务对象相同、服务对象被替换、endpoint/model/dim/fingerprint 不符均视为漂移。

漂移在题前发现：不调用该题，既有 attempted 不变、该题及后续题计入 `not_run_count`，报告增加无 case 的安全 failure rule `identity_changed_before_attempt`。漂移在题后发现：当前题已 attempted，当前正常 metrics 不得进入有效结果；以完整 D1 合成 failed metrics 替换，使用既有 `error_code=backend_unavailable` 和 `safe_summary="检索服务当前不可用"`，`valid_for_quality=false`、所有质量值为 null、来源为空、judge 三项 unavailable、degraded 为 true；`failed_count` 加一，failure 使用私有/报告安全 rule `identity_changed_during_attempt`，保留当前 case ID 后停止。无论 `evaluate` 返回还是抛异常，执行路径都必须在退出当前 attempt 前重读 identity；若 evaluator 异常且 identity 同时漂移，只保留一个完整失败 attempt 和一次计数，同时在安全 failures 附加漂移 rule。题后漂移的整体状态按 `infrastructure_inconclusive`；不得增加第七个 error code，也不声称能够判断 evaluator 在题内具体哪一毫秒读取了配置。

**运行流程：** 先资产校验，再上下文和正式 gate；通过后固定读取 20 个 verified cases，按原顺序调用 `to_evaluate_input(case, corpus)` 与 `agent.evaluate(...)` 各一次。运行中只接受符合 T03 `_validate_evaluation_metrics` 的完整输出且题前/题后 identity 均稳定。timeout/未知执行异常/坏结构均通过 `_failed_attempt_metrics` 形成完整失败指标，保留当前 case 并停止。所有 healthy/empty 且 identity 稳定的结果可跑满；任何 failed/degraded retrieval、invalid request 或 identity drift 停止。judge score missing/non_numeric/non_finite/out_of_range 只将报告状态转为 `completed_judge_degraded`，不令 `failed_count` 增加。

**源摘要与语料摘要分离：** `expected_source_sha256` 和证明的 `source_sha256` 必须与已校验 manifest 的 EPUB源摘要相等；`assets.corpus_sha256` 仅填报告的 `asset_sha256.corpus`。新增受控回归令两者刻意不同，断言合法源证明仍通过，误把corpus摘要当源摘要的expectation被拒；报告source/corpus分别保留正确值，不重读正式资产。

**状态与 error mapping：** `blocked:asset_invalid` 对应 `asset_validation`；真实非 pgvector/确认 SQLite 对应 `blocked:not_real_pgvector`；独立证明/资源/目标/identity/隔离缺失或不符对应 `blocked:unattested_product_index`；无从确认实时环境或 evaluator 基础设施故障对应 `infrastructure_inconclusive`。评测异常只记录 `evaluator_exception`/`evaluator_invalid_metrics` 与冻结码；成功全 judge 有效为 `completed`，成功但存在 judge 降级为 `completed_judge_degraded`。不要将 `degraded` 单字段当作判断检索是否健康的充分条件。

**局部测试要求：** 保留 T03 已有 one-call、首失败停止、低分可完成、empty 机械零分、judge degraded、无效 metrics 安全替换、cross-field validation、corpus isolation 投影安全和 run ID 安全用例；升级它们的 `_run_report` 受控上下文。使用**独立可信 fixture context 作参照**，断言旧 attestation、缺注册、expectation/context 不同、snapshot 与可信 target/rows 不同、隔离文件引用错误均阻断且 evaluator 不调用。纯 Python 值检查无法区分“可信来源”与“攻击者构造出字节完全相同的对象”；不写“拒绝所有 caller 自造 rows/伪 expectation”的不可验证承诺，生产信任取决于 T12 只从经授权的 T07/T11 adapter 构造 wrapper 和 snapshot。另加真实 service identity 的正向 20 题离线完整路径，不能让本包仅以全 blocked 测试验收。报告题目 ID 必须是题单的精确前缀，不能重复、跳号或超 20。

**红绿步骤：**

- [ ] 先把现有 `_run_report` 与 gate 成功 fixture 改为显式 controlled context；保留一个 legacy 缺参数用例并断言阻断。
- [ ] 补一组 20 题调用计数、健康低分、empty、judge unavailable 和首个 retrieval failure 的报告断言。
- [ ] 新增 `test_runner_rechecks_identity_before_and_after_case`、`test_runner_marks_current_attempt_failed_on_post_call_identity_drift`、`test_runner_stops_before_next_case_when_identity_changes_between_cases`，覆盖配置在题间改变、evaluate 内改变、provider/service 对象替换；断言题前漂移不发起新题、题后漂移将当题改记失败而非有效，D1 指标完整且六码未变。
- [ ] 先仅运行以上三个新 runner tests 形成可归因红灯；实现后用 `-k runner` 选择本文件实际已有 `test_runner_*` 回归及新增漂移用例，确认旧 T03 路径与新契约兼容。
- [ ] 将严格 gate 与 report envelope 接入现有循环，不改 `app/agents/retriever.py`、Coordinator outcome 或 T03 evaluator 语义。
- [ ] 定向组转绿后运行整个 `tests/eval/test_rag_d.py`，确认旧的 T03 回归和新增边界一同通过。

### Task 4：加强离线围栏并准备主控组合回归交接

**文件：** 修改 `tests/eval/test_rag_d.py`；执行时新增唯一证据 `docs/rag-work/evidence/t09/2026-10-16-t09-verification.md`。本步骤不改任何 `conftest.py`。

**局部外联陷阱：** 在该测试模块局部 fixture 中增加 Python socket `connect`/`connect_ex`/`create_connection` 与当前测试依赖中实际可触达的 HTTP 连接入口拒绝陷阱和调用计数；保留现有 PG provider 构造/连接、OpenAI/ChatOpenAI SDK 构造陷阱与默认禁用 judge；fixture teardown 必须确认网络、PG、embedding create/embed、judge 外联计数为零。只在 T09 测试模块 monkeypatch，避免改变其他测试域。

**包内与组合验证边界：**

- Task 0 安全 smoke 先于任何新测试；Task 1～3 红绿阶段在本包仅选 `tests/eval/test_rag_d.py` 中明确列出的测试。`-k admission` 对应现有 `test_admission_blocks_backend_provider_dialect_and_mixed_provider_set`、`test_admission_blocks_missing_attestation_and_unverified_corpus`、`test_admission_prioritizes_backend_truth_and_keeps_all_failed_checks` 以及新加的 admission case；`-k runner` 对应已存在的 `test_runner_*` 用例和新加的 identity drift case；报告新测试命名为 `test_baseline_report_*`，统一用 `-k baseline_report`，不再使用无法对应既有命名的 `-k report`。
- T09 完成包内完整 `tests/eval/test_rag_d.py`、Ruff 和 diff 检查后，向主控交接并说明 fixture 仅做模块局部 monkeypatch。主控先复核本包/ComponentBench/T04 相关 fixture 无冲突、没有并发测试进程、共享文件处于稳定状态并确认唯一组合 tmp 不存在，再串行运行组合回归。该组合覆盖 T09 文件、`tests/eval/test_component_bench.py`，以及 T04 三个纯逻辑测试文件：`tests/unit/infrastructure/test_rag_contracts.py`、`tests/unit/infrastructure/test_embedding_identity.py`、`tests/unit/harness/test_ingestion_attestation.py`。T09 子任务不运行该跨包组合，也不把本包绿灯表述为跨包兼容已验证。
- 缓存 Ruff 仅检查 `benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py` 与 `tests/eval/test_rag_d.py`；运行 `git diff --check` 也仅限这两个文件和 T09 证据文件。组合回归结果由主控写入其主执行证据，T09 证据只记录包内结果和交接边界。

**受控命令示例：** 命令只在实现阶段执行；调用前确认本轮 tmp 目录不存在，并为每次红、绿、全量回归使用互不相同的目录。遇同名目录已存在时改为新唯一后缀并写入证据，不删改旧目录。

```text
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py::test_assets_validate_and_adapter_uses_full_paragraphs --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-fixture-smoke-20261016 -q -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py::test_admission_requires_independent_context_before_evaluate tests/eval/test_rag_d.py::test_admission_rejects_mismatched_context_and_isolation_file --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-admission-red-20261016 -q -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py -k admission --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-admission-green-20261016 -q -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py::test_runner_rechecks_identity_before_and_after_case tests/eval/test_rag_d.py::test_runner_marks_current_attempt_failed_on_post_call_identity_drift tests/eval/test_rag_d.py::test_runner_stops_before_next_case_when_identity_changes_between_cases --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-runner-red-20261016 -q -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py -k runner --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-runner-green-20261016 -q -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py::test_baseline_report_full_contract_and_strict_json tests/eval/test_rag_d.py::test_baseline_report_blocked_fields_are_explicit_nulls --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-report-red-20261016 -q -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py -k baseline_report --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-report-green-20261016 -q -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-full-20261016 -q -p no:cacheprovider
C:/Users/A1985/AppData/Local/uv/cache/archive-v0/QcnXSOJpzJovd_JVU2u2H/ruff-0.15.7.data/scripts/ruff.exe check --no-cache benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py tests/eval/test_rag_d.py
git diff --check -- benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py tests/eval/test_rag_d.py docs/rag-work/evidence/t09/2026-10-16-t09-verification.md
.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py tests/eval/test_component_bench.py tests/unit/infrastructure/test_rag_contracts.py tests/unit/infrastructure/test_embedding_identity.py tests/unit/harness/test_ingestion_attestation.py --basetemp docs/rag-work/evidence/t09/.pytest-tmp-t09-combined-handoff-20261016 -q -p no:cacheprovider
```

最后一条命令仅是**主控交接命令**：必须在主控完成上述隔离确认后由主控执行并登记结果；T09 计划作者不得运行，也不得先占用该 tmp 目录。其余命令也仅为获批实现阶段的示例，不表示本计划阶段已经运行。

实际 pytest 命令若被平台阻挡，按全局纪律记录原因；同动作每轮最多重试一次，第 2 次阻挡即停止，不更换环境、不安装包、不删 tmp。最终证据逐条记录命令、退出码、实际 pass/deselect 数、Ruff 版本与文件范围、网络/SDK/PG调用计数、spec SHA、红灯原因及其绿灯覆盖。记录中明确离线 boundary，不产生真实产品成功证明。

## 依赖与后置门

T09 的**离线代码与测试**只有已验收的 T03 和 T04 为硬前置；可在 T08 之前独立完成，不导入 T08 `scripts/rag_ingest.py`，不要求先运行 T08。T09 可按冻结接口接收外部 `expected` 与 `snapshot`，但不能自行冒充这些输入的生产者。

需要在正式真实 gate / T12 baseline 前后置满足：

- **T01**：盘点实际 PG/embedding 资源、可用资产与无密钥资源来源；为 resource record、目标标识、公开映射与受控 binding 适配提供事实，不泄密。
- **T07**：在 G1 和 T01/T05 前置满足后，实测真实 PostgreSQL dialect、database/schema/target 映射、权限与排他性证据；登记由谁验证 resource record 和 binding 及其实际载体。
- **T11**：在 G2/T08 后实际摄入，生成真实目标 snapshot、完整隔离文件和成功 attestation；只有实际外部资源证据可进入产品 expectation。
- **T12**：在 G3 和 T09 后单次执行真实 20 题 baseline，向 `run_baseline` 提供由批准来源组装的独立 expectation、真实 snapshot、binding context 与隔离证据；审核其 raw 结果后才可声明 G4。
- **T08**：不是 T09 实现或离线测试的硬依赖。若后续正式资源事实选用 T08 `snapshot_index`，则 T12 调用方负责在运行时提供它的 `IndexSnapshot`；T09 不导入 runner，也不改 T08 文件。
- **G1**：T09 只是 T02/T03/T04/T10 集成门的一个组件；本计划完成、全部本地测试通过或受控 fake 通过都不等于 G1 已放行。

## 已知决策缺口

1. **生产数据源与实际格式尚未就绪。** 冻结 spec 未给 resource record 的 schema/读取器、公开 target 到 database/schema 的权威映射、受控 binding 注册位置或历史排他记录的格式。上文已给出可审阅、可本地实现的私有 context 字段与 T12 装配顺序，但这是推荐的适配边界，不代表仓库已有 provider、正式注册表或真实数据。主控需在 T01/T07/T11/T12 事实到位后指定这些来源的权威 reader；reader 缺失、无权限、读取失败、记录多重/冲突或无法把字段映射到本表时，生产 adapter 必须不返回准入 wrapper，T09 在首题前 `blocked:unattested_product_index`，调用 `evaluate` 次数为零。不新增公共 Setting、环境变量或共享 schema。
2. **`AttestationExpectation` 的生产组装者与信任来源尚未绑定。** 推荐由 T12 调用边界的私有 adapter 组装，规则固定为：source SHA 来自已校验 benchmark/source 资产；target/database/schema 来自 T07 核准 resource mapping；embedding fingerprint 来自注册 binding 与实际运行 service 的独立比较；manifest/count/完整重复保留 rows 来自实际只读快照；scope/owner 来自受控摄入意图/资源；isolation evidence 来自可信本 run 记录。attestation 的值只用于最终比对，绝不可作为任何上述输入的来源。Python 无法追踪数值相同对象的历史来源；production trust 边界是经批准的 T12 adapter，离线用例只以独立 context 交叉核验缺失/伪值/不匹配，不承诺识别字节相同的 caller 数据。
3. **隔离证据的生产根目录与实际文件位置需 T11 确认。** 本计划给出的本包解析规则是推荐且具体的：context 只授权 `run_dir`，T09 只读固定 `run_dir / "isolation-evidence.json"`，拒绝 symlink/越界/额外 JSON 键，ref 仅作登记值比较、不用于拼路径。当前 spec 没有冻结 T11 证据目录名/具体文件载体，因此 T11/T12 必须确认该固定文件确实由受控 run record 指向；若生产产物不同，应由主控批准另一个固定相对路径策略，不能退回任意 attestation URI。确认前生产 adapter 对隔离来源缺失一律不准入，离线逻辑仍可按该推荐路径完整验证。
4. **运行中真实 dialect 的判定来源需沿用受控实际 provider。** 现有 `_default_dialect` 通过 `provider._get_conn().dialect.name` 真实建连；离线测试必须替换 getter。无法连通不能伪装为已确认 SQLite 或 PG，按冻结状态报告 infrastructure inconclusive。

这些是正式资源 adapter 的后置装配决策，不是把本地 resolver 留成抽象 placeholder：T09 的私有输入/输出类型、字段比较、路径授权、历史/当前保护语义和缺源拒绝行为均已在本计划中具体规定，可以用受控 fake 实现与验证；但在主控批准真实来源 reader 前，真实 adapter、真实 target/snapshot 与 G1 仍未就绪，任何离线绿灯都不能声称其已存在或已通过。

## 自查清单

- [ ] 契约 SHA 与 spec 覆盖经执行前重核；如不一致，停止写码并交主控确认新版本。
- [ ] 所有 D3 报告字段、六状态、null 前置行为、严格 JSON 与计数不变量均有对应的 T09 任务及断言。
- [ ] 六项旧 gate 均经新规则覆盖；`verified=True`、最小旧证明、caller 自造 expectation 或无 snapshot 不再能放行。
- [ ] expectation 各字段来源与 attestation 清晰区分；测试检查 source、target、actual identity、manifest rows、scope/owner、resource/exclusivity/isolation 引用。
- [ ] 完整 rows 及重复项受到核验；环境绑定到真实 service instance、SDK endpoint、deployment/version 和维度；endpoint、密钥与异常原文不输出。
- [ ] retrieval failure、judge unavailable、empty、first failure、低分健康输出和错误 metrics 分别有测试；每题调用次数与停止位置可数。
- [ ] 新本地围栏覆盖裸 socket / HTTP、PG、SDK 和 judge；全程局部 fixture，无共享 `conftest.py` 修改。
- [ ] 不改 T08/T05/T10、新 provider/retriever、正式资产或 README/索引；唯一实施证据路径和唯一执行 tmp 路径清晰。
- [ ] 真实资源/binding/snapshot 的不确定来源明确记录为决策缺口；未拿离线测试、T03/T04 离线结果或计划文档替代正式验收。

## 主窗口文档复核状态

已完成一轮定向修订与主窗口复读，具体发现、关闭说明及实施前待确认设计见[第二批计划审阅记录](2026-10-16-second-wave-plan-review.md)。当前仍为待用户确认的计划，未开始实现或运行测试。

## 2026-10-17 最新正式审阅状态

**需修订，暂不派发实现。** [正式审阅问题与修订顺序](2026-10-17-second-wave-plan-review.md)更新本计划先前初读状态；当前未处理的问题须定向修订并复核关闭，再确认计划。此次仅追加审阅状态，未代为修改设计或实施。
