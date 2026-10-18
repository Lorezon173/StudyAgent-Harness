# T04 证明契约与 embedding 身份执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现不执行文件、数据库或远端请求的共享数据契约、身份描述/摘要、成功证明构造与独立核验。

**Architecture:** infrastructure 层只承载纯数据和规范化；Harness 层消费现有 IngestResult，交叉核对意图、运行清单和实际快照。T08负责实际读取与持久化，T09/T13负责以独立配置构造消费侧预期，禁止由证明回填预期。

**Tech Stack:** Python >=3.11、现有 dataclass/typing、标准库 json/hashlib/uuid/datetime；pytest，沿用现有环境，不增加依赖。

**Spec:** [冻结共享契约](../specs/2026-10-16-rag-mvp-contracts-v1.md)，版本 `rag-mvp-contracts-v1.0.1`，字节 SHA-256 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。计划审阅历史：**复查意见已修订，主窗口文档复核通过**。[当前复查及关闭记录](2026-10-16-first-wave-plan-rereview.md)。当时仅修兼容回归执行边界；当前实现验收见下一段。

**当前实施状态：实施完成、定向复审及主窗口组合离线回归通过。** [执行证据](../evidence/t04/2026-10-16-t04-verification.md)；[主窗口验收](../evidence/2026-10-16-first-wave-execution.md)。当前三文件213项通过，限定Ruff通过。下文批准时快照和步骤保留用于追溯，不再作为当前状态；不表示G1/G2或真实环境通过。

## 全局约束、来源与当前事实

设计来源为 `superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan.md`、同日 review、`2026-10-13-review-verification.md`、`2026-10-16-rag-mvp-dag-and-scheduling.md`、`2026-10-16-execution-readiness-audit.md`、`2026-10-16-t00-contract-freeze-record.md`。spec的A3/A4/B/C/E1以及冻结修补记录是本包直接依据；RV-02/R24、RV-04/R26及R03/R04是主要回归来源。

- 固定 `embedding-identity-v1`、`ingestion-attestation-v1`、`ingestion-run-v1`；旧 `doc-v1/doc-norm-1/chunk-v1/chunk-policy-1` 不重命名。
- global owner=null；private owner为正整数；所有整数拒绝bool。新结构不可变，内部mapping/序列也要复制冻结。
- 六安全码仅backend_unavailable/db_error/embedding_failed/provider_degraded/invalid_request/timeout；禁止添加对外错误码。
- 不增加上传、数据库表、Event字段、幂等、upsert、清库、严格identity recall或远端版本保证。
- 本包执行只新增三个产品文件、三个测试文件和一个证据记录文件；不改 `embedding.py`、`pgvector_provider.py`、`knowledge_ingestion.py`、benchmark及其测试，不实施snapshot_index。
- PreparedIngestion及IngestionPreparationError唯一定义属于T02；T04只使用当前已存在的IngestResult，测试不得要求T02先实现新接口。
- 以文字描述设计和测试，不提供实现/测试代码。所有测试命令是后续执行说明，本次未执行。
- README由主控单写维护，本代理不改。执行阶段不commit/push，不使用sleep；长命令每30秒主动检查会话/进程进展。

代码核对：EmbeddingService实例保存model/base_url/api_key，SDK client懒加载并缓存；dim每次读取可变settings.embedding_dim；实际create只传model/input。IngestResult现有字段仅status、doc_id、planned_chunk_count、written_chunk_count、warnings。现有rag_d gate只做较弱字段/计数及verified布尔判断，接受provenance_filter；现有测试用run-1、chunk-v1、不完整证明，不能作为新协议合法fixture。它们由T09接续修改，本包不抢写。历史99 passed不是本包证据。

## 第一层：模块总览

目标边界：将“相同公共配置”“同一目标的完整行多重集合”“满足成功字段契约”转成确定的纯逻辑结果；不声称配置摘要能证明远端别名从未变化，也不声称调用者填写的snapshot就是实际数据库事实。

依赖方向：contracts不导入Harness、benchmark、数据库配置或settings；embedding_identity读取受控服务实例的公开可观察属性，不发embedding请求；ingestion_attestation导入contracts以及原路径IngestResult，绝不反向让infrastructure导入Harness。纯数据导入不得触发SDK初始化；describe允许SDK初始化但不得调用远端。

输入链：T02准备元数据 → T08意图/运行manifest/实际IndexSnapshot → build → T08落盘；消费链：受控查询配置describe/fingerprint + 独立源/目标/隔离证据 → AttestationExpectation + 实际snapshot → validate → T09 gate或T13在线准入。恢复只消费原intent.preparation/embedding_config和实际全部行，不需要PreparedIngestion或上次IngestResult。

## 第二层：子模块、归属与数据流

| 新增文件 | 职责、接口、状态与错误 |
|---|---|
| app/infrastructure/rag/contracts.py | 定义七个冻结数据类型；保存复制后的不可变字段；构造错误ValueError（安全规则ID），无外部状态。为规范JSON和多重集合摘要提供共享纯函数供T08/T09复用；T02本批内部实现相同规范并以固定向量验证一致，不依赖尚未落地的T04模块；这些辅助函数不改变spec冻结接口。 |
| app/infrastructure/rag/embedding_identity.py | describe_embedding(service,binding)返回EmbeddingIdentity；fingerprint_embedding(identity)返回64位小写SHA；拒绝非法绑定、端点不符、配置不可观察，以安全ValueError返回。 |
| app/harness/ingestion_attestation.py | build_attestation关键字intent/manifest/result/snapshot/identity/verified_at返回dict；不一致ValueError。validate_attestation(attestation,*,expected,snapshot)返回ContractCheck，不泄露原异常、不写库。 |
| tests/unit/infrastructure/test_rag_contracts.py | 类型、不可变性、版本、RunRecord、规范JSON/摘要固定向量。 |
| tests/unit/infrastructure/test_embedding_identity.py | 实际实例/缓存client/绑定、默认请求参数、指纹、秘密边界；SDK完全替身。 |
| tests/unit/harness/test_ingestion_attestation.py | 完整合法fixture、构造/消费交叉核验、拒绝矩阵、确定性、无IO和安全输出。 |

允许清单另包含唯一证据记录 `docs/rag-work/evidence/t04/2026-10-16-t04-verification.md`，记录基线、逐步红绿结果、命令退出码、覆盖矩阵、限制及交接；因此实施阶段允许六个实现/测试文件加此一个证据文件，其他文件不由T04写入。不新增共享conftest或fixture文件；三个测试文件各持有所需最小fixture，避免改变全仓fixture。必要的私有实现辅助函数不作为跨包调用接口。

## 第三层：字段与逐函数实施设计

### 3.1 纯类型及边界

除下述明确nullable外均不可null；必填字符串非空，SHA为64位小写hex，UUID为可解析UUID字符串，时间UTC ISO8601。元数据中的JSON值限null/bool/有限数/字符串/数组/字符串键对象，不接受对象repr或非字符串键。

| 类型 | 精确字段与语义 |
|---|---|
| ContractCheck | allowed:bool；failures:tuple[str,...]；allowed等价于failures为空。失败按schema/version/types/source/target/identity/count/scope/isolation分类顺序，类内稳定去重。 |
| EmbeddingBinding | service_id:str；deployment_id:str或null；model_version:str或null；expected_endpoint:str。端点仅内存，repr/导出排除，不参与fingerprint。公开ID由受控配置提供，拒绝带URL/凭证的公开标识，不从端点截取字符串“猜”部署。 |
| EmbeddingIdentity | schema_version固定embedding-identity-v1；service_id:str；deployment_id:str或null；model:str；dimension:正int；parameters:只读标量mapping；model_version:str或null；version_binding为pinned或alias_unpinned。当前parameters精确dimensions/encoding_format，未传请求值均service_default。model_version=null只允许alias_unpinned，有可信不可变版本才pinned。 |
| IndexSnapshot | target_index_id/database_id/schema_name:str；row_count:非负int；rows:完整行不可变序列；manifest_sha256:SHA。每行精确doc_id/chunk_id/content_sha256:str、chunk_index:非负int、scope:str、owner:正int或null、source_locator:JSON对象。保留重复；row_count等于实际序列长度，摘要重算。空快照可用于T08前态，但不可成功证明。 |
| AttestationExpectation | expected_source_sha256/expected_target_index_id/expected_embedding_fingerprint/expected_manifest_sha256:str；expected_scope:str；expected_owner:正int或null；isolation_evidence:只读对象。后者精确mode=isolated_db、target_index_id、manifest_sha256、row_count:正int、verified_at:UTC时间、resource_record_ref:非空安全str。 |
| RAGRequestContext | retrieval_id:非空str；attempt:int固定1且非bool；trace_id/session_id:str或null。纯不可变；不新增Event字段。 |
| RunRecord | schema_version固定ingestion-run-v1；ingestion_run_id:UUID str；phase五枚举；error_code:六安全码或null；safe_summary:str；failures:tuple[str,...]；attestation_path:str或null。failures字典序去重，禁止异常原文。 |

RunRecord phase→摘要精确映射：prepared→“摄入计划已准备”；committed_unattested→“写入待证明”；completed→“摄入已核验”；failed→“摄入未完成”；inconclusive→“摄入状态待核验”。仅completed允许非null attestation_path；完成记录必须有非空路径。路径的文件存在/证明成功由T08先核验，纯类型不访问文件。failed的已确认回滚/未写入前提由T08持有；未知提交必须inconclusive。类型不从error_code猜测事务结果，不新增状态转换引擎；其他phase不擅自追加spec未要求的failures非空限制。

共享纯函数导出名称已经本次主控审阅确认：canonical_json_bytes(value)接收上述合法JSON值，返回UTF-8 bytes；manifest_sha256(rows)接收完整行序列，返回摘要；错误统一安全ValueError。contracts内可定义JSON值类型别名和ManifestRow只读类型别名，不新增一套产品ChunkDocument。identity的JSON导出精确八键，不使用包含binding的通用asdict；若提供to_json_dict(identity)辅助函数，仅接受Identity，返回防御性副本，不能接受Binding。

### 3.2 规范JSON/摘要

canonical_json_bytes：先验证类型/有限值/字符串键，再按Unicode码点排序键、无额外空白、ensure_ascii=false、禁止NaN/Infinity、UTF-8；不做Unicode或URL归一化。manifest_sha256：逐行规范化成字节，按完整行字节排序，保留重复，再将排序行数组规范化并SHA256。正文SHA是实际content UTF-8直接摘要，不再次normalizer。不使用集合比较，不把runid、摘要字段或envelope混入rows摘要。

固定向量（本次只用标准库生成核对，非业务测试）：

- identity规范字符串：`{"deployment_id":null,"dimension":2,"model":"model-a","model_version":null,"parameters":{"dimensions":"service_default","encoding_format":"service_default"},"schema_version":"embedding-identity-v1","service_id":"svc-public","version_binding":"alias_unpinned"}`；SHA=`005a79e156e97b05af18abadbadeda7c40bab8418a0152e7f36ee08b19aa798a`。
- 单行规范字符串：`{"chunk_id":"chunk-0","chunk_index":0,"content_sha256":"77832764857e8fcdce15190896ad985c913fb791dc79a17ac51729dc31755f4a","doc_id":"doc-fixture","owner":null,"scope":"global","source_locator":{"paragraph":0}}`。content为ASCII `fixture content`；单行数组manifest摘要=`7b737b09b633fd4dc6edc7eb904e60a1ea6959408d7e1151bd4a1fa9547c1176`。
- `{"a":"甲","z":null}` UTF-8规范字节SHA=`815d7d75761381ceee22ca5c208ba165a97158ae816d7e968c885f41f1605634`；覆盖非ASCII不转义。调整键插入顺序不变摘要，改变Unicode组合形式不得自动等同。

### 3.3 describe_embedding与fingerprint_embedding

describe_embedding输入为实际EmbeddingService及受控EmbeddingBinding，输出Identity。读取service.model、service.dim和service.client.base_url（SDK实际端点），不能仅看当前settings或service.base_url；已缓存client指向A而实例base_url改B时以实际client为准并拒绝与binding不符。绑定端点采用实际SDK解析后的字符串进行严格相等比较；受控装配提供相同实际endpoint作为expected_endpoint，不做尾斜杠、路径、query、大小写或Unicode宽松归一化，任何不相同均拒绝endpoint_mismatch。

当前代码只有model/input请求，parameters两项为service_default；不伪造temperature。读前后dim/model/client端点若漂移拒绝identity_config_drift；一次描述无法证明随后写入/查询配置未变，T02负责向量实际维度检查，T08/T13固定实例并在操作边界重新描述比较。维度必须正int非bool。SDK初始化故障归安全ValueError，调用方再做基础设施分类；不把异常原文拼到错误。

公开service/deployment标识与端点一一对应的可信性是装配前提，函数只核对传入绑定和实际端点，不能替代配置注册审计。model_version来源需不可变版本证据；无版本必须alias_unpinned，报告保留限制。fingerprint_embedding只验证并序列化Identity的八键，返回规范SHA；API key、URL、headers、组织凭证不得流入Identity、repr、错误、hash输入或证明。

### 3.4 build_attestation

输入关键字严格为intent:dict、manifest:dict、result:现有IngestResult、snapshot:IndexSnapshot、identity:EmbeddingIdentity、verified_at:str（本次核验UTC ISO8601）；返回完整成功dict，不返回半成品。逐项验证：intent/preparation版本、A1精确字段、UUID/UTC、before_row_count=0、exclusive_target=true和三个非空引用；运行manifest精确envelope与全部rows；intent/manifest/identity source/target/manifest/fingerprint相同；snapshot的database/schema与intent相同、目标相同、全部行多重集合一致、row_count=manifest计数>0；result.status=ok、doc_id一致、planned=written=快照行数、warnings安全且与准备记录一致。所有行doc_id相同、chunk_index从0连续、chunk_id不重复、scope/owner与preparation相符。

产物顶层精确键：schema_version、contract_version、status、ingestion_run_id、created_at、source_sha256、source_format、import_namespace、doc_id、normalizer_version、chunking_version、doc_protocol、chunk_protocol、chunk_policy、planned_chunk_count、written_chunk_count、failure_count、backend、provider、dialect、target_index_id、scope、owner、embedding_config、embedding_fingerprint、artifact_manifest_sha256、isolation_evidence_ref、error_code、safe_summary、warnings。值来自原intent.preparation/manifest和经重算快照，不取当前默认；固定backend=pgvector/provider=PgVectorProvider/dialect=postgresql、status=ok、failure_count=0、error_code=null、safe_summary=摄入已核验，warnings为安全list。没有额外version别名字段。

不一致ValueError只含安全规则ID；函数不生成UUID、不读取引用文件、不持久化、不调用index。created_at严格使用经校验的verified_at，不读取时钟、不用旧intent.created_at代替；contract_version固定rag-mvp-contracts-v1.0.1。

### 3.5 validate_attestation

输入attestation:dict、关键字expected:AttestationExpectation、snapshot:IndexSnapshot；返回ContractCheck。无任何IO。外层不是dict、缺/多顶层键、嵌套类型非法时按对应规则拒绝；不得因某字段坏值提前造成KeyError或泄露原异常。

依次检查固定版本/状态、字段类型/UTC/UUID、安全文案/码、版本策略、source、target、identity重算指纹、counts、scope、isolation。证明source/target/fingerprint/manifest/scope/owner同时与独立expected及snapshot对应字段比较；快照database/schema只能由可信生产者保证，本Expectation无这两个字段，不从证明补造。核验snapshot rows摘要、数目、唯一chunk和连续index、各行doc/scope/owner与证明一致。embedding指纹既等于证明重算，也等于expected中实际查询身份摘要。同维不同模型/部署/参数拒绝。

isolation必须isolated_db，目标/manifest/正row_count与expected/snapshot/证明一致，verified_at合法、resource_record_ref非空；仅verified=true及provenance_filter拒绝。isolation_evidence_ref必须非空安全引用，引用实际解析/内容来源由调用方完成，不在纯验证器中打开路径。失败按冻结分类顺序稳定汇总；规则ID可采用schema_missing/schema_extra/version_unsupported/types_invalid/source_mismatch/target_mismatch/identity_mismatch/count_mismatch/scope_mismatch/isolation_unproven等内部安全标识，不作为对外六码扩展。

## 4. 完整合法fixture及拒绝矩阵

fixture统一固定UUID=`00000000-0000-4000-8000-000000000004`，核验时刻=`2026-10-16T00:00:00Z`；source为ASCII `fixture epub`，source SHA=`1a89e8c34a455cfadab9c5730f68a2669a3ac1db4f8b490065353e261f2cb6e8`；identity与单行/摘要采用3.2固定向量；target=`rag-t04-fixture`，database=`rag_fixture`，schema=`public`，namespace=`fixture-book`。

合法preparation精确字段：schema_version=prepared-ingestion-v1、上述source_sha256、source_format=epub、import_namespace=fixture-book、doc_id=doc-fixture、scope=global、owner=null、normalizer_version=doc-norm-1、chunking_version=chunk-policy-1、doc_protocol=doc-v1、chunk_protocol=chunk-v1、chunk_policy精确500/50/8192三键、warnings=[]。intent精确采用A4：schema_version=ingestion-intent-v1、固定run/time/target/database/schema/source/manifest/fingerprint、embedding_config为完整identity、preparation为上述对象、before_row_count=0、resource_record_ref=`fixture/resources/t04`、exclusivity_record_ref=`fixture/leases/t04`、isolation_evidence_ref=`fixture/run-t04/isolation-evidence.json`、exclusive_target=true、phase=prepared。

manifest精确采用A3运行九键：schema_version=ingestion-manifest-v1、ingestion_run_id、target_index_id、doc_id、source_sha256、embedding_fingerprint、rows（3.2单行）、row_count=1、manifest_sha256。snapshot使用相同target/database/schema、row_count=1、同rows/摘要。result为现有IngestResult(status=ok,doc_id=doc-fixture,planned_chunk_count=1,written_chunk_count=1,warnings=[])。isolation对象精确mode=isolated_db、同target/manifest、row_count=1、verified_at固定时刻、resource_record_ref同intent。expected七字段均从fixture受控配置独立构造。成功证明为3.4全部键对应上述值，created_at=verified_at=上述固定核验时刻，contract_version=rag-mvp-contracts-v1.0.1；不得用build结果本身构造expected。另设private owner=7的合法变体，重算rows/manifest与所有关联摘要。再设合法oversized warning变体：preparation/result/证明的warnings同时为单项 `chunk_index=0 超过 embedding 安全阈值（hard_limit），已整块保留（atomic 不切裂）`，确认build/validate均接受该产品既有无正文诊断模板；对应真实超限产生过程仍由T02验证。

每个拒绝案例从合法fixture只改一项；多错案例另测分类顺序与去重。build应ValueError且没有status=ok产物，validate应allowed=false且无原异常。覆盖全集如下：

| 类别 | 必测变体 |
|---|---|
| schema/version | 每个必填键逐一缺失、任意额外顶层键、旧证明、未知schema/contract/identity版本、非ok、协议混用chunk-v1冒充chunking_version。 |
| types | null逐字段替换（只放行声明nullable）；空字符串；UUID/UTC非法或非UTC；bool替代全部整数；浮点计数/维度/owner；JSON非字符串键、对象、NaN/±Infinity；嵌套精确键缺/多。 |
| policy | size<=0、overlap<0或>=size、hard_limit<size、bool；overlap=0为合法边界。 |
| source/target | source SHA/format/namespace/doc_id缺失或漂移；intent/manifest/snapshot目标、database/schema任一不符；snapshot来自其他目标。 |
| identity | 同维不同model、service、deployment、参数、model_version；伪造fingerprint、大小写SHA、端点不符、缓存端点漂移、dim漂移、未知请求参数、pinned且无版本、alias且冒用版本。 |
| count/rows | planned/written=0、None、负数、不等；failure_count非0；result非ok或doc不同；行缺失、额外行、相同行重复、chunk_id重复、index断裂/负数、row_count与rows不符、自报摘要错误；调换完整行展示顺序应同摘要且可核验。 |
| scope | global+owner、private+null/0/负/bool、未知scope、expected/行/证明权限不一致；private正owner合法。 |
| isolation | 缺证据、verified布尔替代完整对象、provenance_filter、错误target/manifest/count、缺resource ref/时刻、空证明ref、before_row_count非0、exclusive_target非true或无锁引用。 |
| safety/状态 | 非六码、非固定summary、warnings带异常/秘密样本；RunRecord未知phase、错摘要、非completed带path、completed无path、failed与未决责任混淆由T08用例承接。 |
| 纯逻辑/独立性 | 文件打开、数据库连接、SDK create、embed_one/embed_many设为一调用即失败；重复验证结果相同、输入不被修改、嵌套输入修改不反改快照；证明自报值自洽但expected或实际snapshot不符仍拒绝。 |

秘密边界测试使用明确标记的假api_key/含凭证URL/请求headers/异常消息；断言repr(binding)、Identity JSON、证明、ContractCheck/ValueError输出和捕获日志均不含标记。不能靠断言固定真实秘密值做测试，也不读取用户环境凭证。

## 5. 编号执行步骤与红绿循环

执行派发时核对主窗口review结论及第7节勘误同步，读取karpathy-guidelines和实际AGENTS；文件越界或spec SHA变动即停。以下每步均为独立动作，实施代理据真实结果勾选，不预勾。**每一步的产物、输入版本、检查结果及实际命令/退出码均记录到固定证据入口 `docs/rag-work/evidence/t04/2026-10-16-t04-verification.md` 的同编号条目；不另建日志证据文件。**

- [ ] **01 核对基线。** 产物：证据中的spec SHA、允许文件列表、工作区初始状态。命令：`Get-FileHash docs/rag-work/specs/2026-10-16-rag-mvp-contracts-v1.md -Algorithm SHA256`、`git status --short`。期望SHA完全一致，其他任务修改只记录、不撤销。
- [ ] **02 编写contracts失败用例。** 产物：test_rag_contracts.py，完整七类型、3.2向量、嵌套不可变与RunRecord矩阵；先写固定预期，禁止以被测函数生成expected。
- [ ] **03 确认红灯。** 命令：`.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_rag_contracts.py -q -p no:cacheprovider`。期望新增模块/接口未实现导致收集或断言失败；环境/缺依赖故障单列，不当作有效红灯。
- [ ] **04 实现纯类型和规范化。** 产物：contracts.py，仅实现3.1/3.2，函数输入输出与安全ValueError遵守上表；不导入settings。
- [ ] **05 确认contracts绿灯。** 重跑03相同命令；期望全部通过，固定摘要不更新以迁就实现。若失败留在本步修复。
- [ ] **06 编写身份失败用例。** 产物：test_embedding_identity.py，构造真实EmbeddingService搭配SDK替身，不发请求；覆盖实际model、dim、缓存client端点与秘密边界。
- [ ] **07 确认身份红灯。** 命令：`.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_embedding_identity.py -q -p no:cacheprovider`。期望缺describe/fingerprint或行为错误失败。
- [ ] **08 实现身份函数。** 产物：embedding_identity.py；从实例读实际配置并做绑定/漂移检查，序列化复用共享算法；不能为此修改T02持有文件。
- [ ] **09 确认身份绿灯。** 重跑07；期望全部通过且外部请求次数0。
- [ ] **10 编写证明失败用例。** 产物：test_ingestion_attestation.py，4节完整fixture、每字段参数化拒绝矩阵、build/validate往返及独立expected对抗；使用现有IngestResult，不引入PreparedIngestion依赖。
- [ ] **11 确认证明红灯。** 命令：`.venv/Scripts/python.exe -m pytest tests/unit/harness/test_ingestion_attestation.py -q -p no:cacheprovider`。期望模块/构造/核验缺失导致失败；旧gate测试通过不替代红灯。
- [ ] **12 实现证明构造和核验。** 产物：ingestion_attestation.py；先校验所有输入再组装成功对象；validate汇总安全规则ID，使用3.4/3.5契约。verified_at缺失、非法或非UTC必须拒绝；传入核验时间与旧intent.created_at不同，产物使用前者。
- [ ] **13 确认证明绿灯。** 重跑11；期望全部通过；反复调用无状态污染，所有IO陷阱未触发。
- [ ] **14 包内联合验证。** 命令：`.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_rag_contracts.py tests/unit/infrastructure/test_embedding_identity.py tests/unit/harness/test_ingestion_attestation.py -q -p no:cacheprovider`。期望所有新增纯逻辑用例通过，收集路径无外部资源要求。
- [ ] **15 独立离线边界验收与组合回归交接。** T04代理不运行旧 embedding/knowledge_ingestion/rag_d 测试，亦不等待T02完成才验收本包。在本包三个允许测试文件各自定义局部fixture：先把settings.rag_backend设为pgvector以模拟不利配置，SDK工厂仅用固定无凭证替身，embeddings.create、embed_one/embed_many及SQLAlchemy同步/异步引擎工厂和PgVectorProvider._get_conn均设为调用即失败的计数陷阱；不创建真实客户端或数据库连接。纯逻辑文件打开陷阱只包围被测函数调用，不拦pytest收集。重跑14的三个测试文件，期望通过且外部调用为0，记录T02新接口/fixture不存在时的独立性；只使用现有IngestResult，不导入PreparedIngestion。所有patch在fixture结束后恢复，不改全局环境/共享conftest。原跨包命令交主控集成阶段：`.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_embedding.py tests/unit/harness/test_knowledge_ingestion.py tests/eval/test_rag_d.py -q -p no:cacheprovider`；仅在T02/T03离线fixture已交付并复核、三个包文件稳定、外部连接/SDK陷阱覆盖该命令全部路径后运行，条件不满足记“组合回归未执行”而非T04独立失败。主控将组合版本、前置核查、命令退出码与结果追加至本包唯一证据记录的“主控组合回归”条目，T04代理只交接，不自行放行组合验收。
- [ ] **16 自查并交主控。** 命令：`git diff --check`、`git status --short`。产物：证据、接口覆盖矩阵及限制，精确列六个实现/测试文件及一个证据记录文件；由主控审阅后维护README并释放T08/T09/T13，不将T04单独通过写成G1/G2通过。

## 6. 证据、接口覆盖与交接

固定唯一执行证据入口为 `docs/rag-work/evidence/t04/2026-10-16-t04-verification.md`，由T04实施代理写入：基线部分记录SHA/初始状态，逐步记录部分保存01～16每条命令/退出码/结果/零外部请求边界，覆盖部分逐项映射拒绝矩阵，交接部分记录七文件清单、阻断处置、消费者责任与剩余真实验收。本次仅计划，不生成该“已通过”记录，也不运行上述pytest。

| 接口/规则 | 本包测试 | 消费方与释放条件 |
|---|---|---|
| 七纯类型、JSON/manifest摘要 | test_rag_contracts.py | T02本批内部遵守同一规范并用固定向量核对，不导入未落地T04模块、不被要求先新增接口；T08/T09复用canonical_json_bytes/manifest_sha256，T08获得唯一定义RunRecord与Snapshot。 |
| describe/fingerprint、binding秘密边界 | test_embedding_identity.py | T08同实例固定与操作边界复核；T13从实际查询实例描述并与证明比较，不能仅对settings hash。 |
| build_attestation | test_ingestion_attestation.py | T08原子落盘/成功状态，T11真实摄入补证；使用显式verified_at且主控review后交接。 |
| validate_attestation、独立预期/多重集合 | test_ingestion_attestation.py | T09调用共享validator并落实六项gate/报告；T13查询准入复用，均不能从证明复制expected。 |
| RunRecord恢复语义 | contracts单测只验字段状态 | T08负责真实事务状态、资源/锁校验、snapshot_index、恢复只读、实际计数构建IngestResult供build，不调用准备/index。 |
| 隔离证据/引用 | 纯参数矩阵 | T07提供可信资源记录；T08实际生成isolation-evidence.json并核对排他；T09打开引用核对实际文件/来源后传入，不把路径存在等同可信。 |

T08必须消费intent中的完整旧preparation/identity，不用新默认补齐；成功manifest保留rows及重复项。T09不得调用build生成产品证明，不能以可选expected/snapshot默认值放行；T13必须披露alias_unpinned限制。真实PG/远端维度/本书索引/恢复落盘与双入口检索属于T07/T08/T11/T13后续证据。

## 7. 已处理边界与阻断纪律

1. **时间输入缺口已由主控勘误闭合。** v1.0.1显式新增verified_at:str关键字，由T08在正常摄入/恢复核验时取得并传入，T04只校验UTC ISO8601并映射证明created_at。原v1历史快照保留；schema_version不变，contract_version升级。固定向量的Identity/rows不含contract_version，故3.2摘要不受升级影响。测试须覆盖恢复时旧intent时间与新verified_at不同，证明保留run ID且使用新时间；不自行读取时钟。
2. **安全字符串规则精度。** spec要求warnings/引用/公开标识安全，未定义全部字符与脱敏语法；本包允许已知产品预定义warning模板及受控非密引用，必须覆盖T02现有oversized warning：`chunk_index={非负整数} 超过 embedding 安全阈值（hard_limit），已整块保留（atomic 不切裂）`，这是无正文的chunk_index及硬限制诊断摘要，不能另换模板使产品合法证明被拒。未知异常原文和秘密样本拒绝。若需支持其他warning格式，先主控确认生产/消费同一规则；不能以简单URL正则声称能识别所有秘密。
3. **端点表示已按主控要求收紧。** expected_endpoint由受控装配依据实际SDK解析后端点提供，describe仅严格相等比较。不strip尾斜杠/路径/query，不允许通用宽松匹配；差异拒绝且不输出原URL。测试中仅原字符串带斜杠差异也拒绝。
4. **纯核验信任前提。** 当前接口无法独立证明snapshot来自真实库、binding来自可信注册或引用文件已读；这由T08/T09/T13负责，不是增加一个verified布尔就能闭合。本包不增加隐式IO或越权扩展Expectation字段。

遇spec SHA不符、字段冲突或共享文件写入权冲突：停止受影响步骤，记录差异与影响任务并报告主控；不改冻结spec。平台故障同动作本轮只重试一次，第二次受阻停止变更并给出可手动运行的原命令；可继续只读核验。测试/依赖失败保留实际诊断，不转为成功，不绕过真实里程碑。

## 8. 计划自查与主窗口review状态

首轮已检查字段归属、冻结SHA、现有service/result/gate事实、三层设计、精确文件清单、红绿步骤、完整fixture及拒绝矩阵、无IO边界、消费者交接与阻断。时间缺口已按主控v1.0.1勘误同步；[逐份复查及关闭记录](2026-10-16-first-wave-plan-rereview.md)要求的兼容回归隔离已在步骤15修订，主窗口文档复核通过。未写产品代码、未运行业务测试、未连接服务、未commit/push。




