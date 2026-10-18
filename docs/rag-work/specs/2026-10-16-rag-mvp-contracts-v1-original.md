# RAG MVP 共享契约 v1

契约集标识：`rag-mvp-contracts-v1`。日期：2026-10-16。维护者：RAG 主控；实现方按 T02～T14 划分。状态：**T00 主控自查与子代理独立审阅、修订后定点复核通过，接口冻结**；不代表实现通过。[冻结与审阅记录](../../../superpowers/rag-foundation/2026-10-16-t00-contract-freeze-record.md)。本文只定义文字、字段和接口，不提供实现代码。

## 0. 设计来源与适用范围

原始设计：[2026-10-15 MVP raw](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan.md)，[RV-01～05 review](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan-review.md)，[DAG raw](../../../superpowers/rag-foundation/2026-10-16-rag-mvp-dag-and-scheduling.md)。用户已确认方案并明确要求执行 T00；本次是在该范围内固定接口，无需重复请求整套批准。

沿用 [DEC-001～012](../plans/2026-07-27-rag-p0-confirmed-decisions.md) 和原三份 EPUB/Chunking/在线 spec。本文对本轮新增接口与已有候选值形成共享增量基线；旧 spec 的实施前事实不作为当前状态。若与 DEC 的业务边界冲突，保留 DEC，不允许实现者自行改语义。变更本文冻结字段需主控记录新版本和影响任务，不能各包独立改字段。

**非目标**：新上传 API、ingestion_runs 表、Event schema 一等字段、替换/删除/幂等、shared/course 权限、额外回答器、query expansion、严格 identity recall。依赖保持单向。新接口是待实现约定，现有代码没有这些函数不构成归档失败。

## 第一层：模块总览及版本

| 契约 | 固定版本 | 生产者 → 消费者 |
|---|---|---|
| 本契约集 | rag-mvp-contracts-v1 | T00 → 全部执行包 |
| 准备结果与无正文准备清单 | prepared-ingestion-v1 / prepared-manifest-v1 | T02 → T08 |
| 运行意图/计划清单 | ingestion-intent-v1 / ingestion-manifest-v1 | T08 → 恢复/证明核验 |
| 摄入证明 | ingestion-attestation-v1 | T08/T11 → T09/T12/T13 |
| embedding 身份与指纹 | embedding-identity-v1 | T04 → T08/T09/T13 |
| 评测输出 | retriever-evaluation-v1 | T03 → T09/T12 |
| 基线报告 | rag-baseline-report-v1 | T09/T12 → T14 |
| 在线证据投影 | evidence-projection-v1 | T06 → Tutor/T13 |

旧 doc-v1/doc-norm-1/chunk-v1/chunk-policy-1 不重命名。chunking_version 在新证明中必须等于实际 chunking_spec_version，不能用 chunk-v1 代替策略版本。默认 chunk_size=500、overlap=50、hard_limit=8192 为策略值，不冒充模型实测上限。

数据流：产品 service 一次提取/准备 → runner 持久化计划 → 产品 provider 原子写入 → 实际产物快照 → 成功证明 → gate → 一次检索评测/在线受控投影。benchmark 禁止生成产品索引或伪造证明。

## 第二层：模块归属与冻结接口表

本节函数参数按名称/类型/默认值约束，采用文字表，不含实现代码。除明确扩展外保留现有公开签名与 import 路径。

| 模块/任务 | 接口 | 输入 | 返回/错误 |
|---|---|---|---|
| knowledge_ingestion.py / T02 | prepare_file | file_path:str；关键字 import_namespace:str、scope:str=global、user_id:int或null=null、chunking_spec_version:str=chunk-policy-1、policy:ChunkPolicy或null=null | PreparedIngestion；预期准备失败抛 IngestionPreparationError |
| 同上 / T02 | ingest_prepared | prepared:PreparedIngestion | IngestResult；写入故障抛原有内部异常，不能伪造成功 |
| PreparedIngestion / T02 | to_intent_metadata | 无参数；只读自身准备快照 | dict；仅A1规定的preparation元数据，不含documents正文 |
| 同上 / T02 | ingest_file | 保持当前完整参数与默认值 | 兼容 IngestResult；内部调用一次 prepare_file/ingest_prepared |
| pgvector_provider.py / T02 | index | 现有 docs:list[dict] | 保留 int或null 协议；自身成功返回真实确认条数，失败 rollback并抛异常 |
| 新 infrastructure/rag/embedding_identity.py / T04 | describe_embedding | service:EmbeddingService；binding:EmbeddingBinding | EmbeddingIdentity；绑定不可信抛 ValueError，不调用远端API |
| 同上 / T04 | fingerprint_embedding | identity:EmbeddingIdentity | 64位小写十六进制SHA-256字符串 |
| 新 harness/ingestion_attestation.py / T04 | validate_attestation | attestation:dict；关键字 expected:AttestationExpectation、snapshot:IndexSnapshot | ContractCheck；拒绝不抛原始异常，不写库 |
| 同上 / T04 | build_attestation | 关键字 intent:dict、manifest:dict、result:IngestResult、snapshot:IndexSnapshot、identity:EmbeddingIdentity | dict；不一致抛 ValueError，不生成成功证明 |
| 新 infrastructure/rag/contracts.py / T04 | ContractCheck、EmbeddingBinding、EmbeddingIdentity、IndexSnapshot、AttestationExpectation、RAGRequestContext、RunRecord | 纯数据契约，字段见下文 | 不导入 Harness、benchmark或数据库配置；不执行IO |
| pgvector_provider.py / T08 | snapshot_index | 关键字 target_index_id:str | IndexSnapshot；只读实际本轮专用目标，数据库故障抛内部异常 |
| 新 scripts/rag_ingest.py / T08 | run_ingestion | source_path:str；关键字 import_namespace:str、scope:str、owner:int或null、run_dir:Path、target_index_id:str、resource_record_ref:str、binding:EmbeddingBinding、policy:ChunkPolicy或null=null | RunRecord，明确成功/失败/未决；不重试写库 |
| 同上 / T08 | recover_ingestion | run_dir:Path；关键字 target_index_id:str、binding:EmbeddingBinding | RunRecord；只读库并补文件，不调用准备或index |
| retriever.py / T03 | evaluate | 保持 test_case:dict，query/golden_chunks/golden_answer/top_k 四键 | dict 满足 retriever-evaluation-v1；所有分支键稳定 |
| rag_d.py / T09 | validate_admission | 保留现有参数；新增关键字 expected:AttestationExpectation或null=null、snapshot:IndexSnapshot或null=null | 保留 AdmissionResult；缺真实验证上下文则拒绝，不能以兼容默认值放行 |
| rag_d.py / T09 | run_baseline | 保留现有参数；同样新增 expected/snapshot 两个关键字 | rag-baseline-report-v1；旧调用不崩签名但可能被更严格gate拦截 |

run_ingestion/recover_ingestion 由受控项目配置装配 service/provider，不接受用户正文生成数据库目标。snapshot_index 放在 T08 而不是 T04，避免 T04 与 T02 并发修改 provider；T08须等待T02释放该文件，T10审计同文件修改仍串行交接。精确逐包实施步骤不属于本 T00 产物，另行形成各包 plan。

## 第三层A：摄入准备、写入与恢复

### A1. PreparedIngestion

类型唯一定义位置：app.harness.knowledge_ingestion.PreparedIngestion、app.harness.knowledge_ingestion.IngestionPreparationError，由T02维护；其他包只能导入，不得在scripts或T04模块复制定义。现有IngestResult仍留在同一原位置。

PreparedIngestion为不可变快照。schema_version:str固定prepared-ingestion-v1；source_sha256/source_format/import_namespace/doc_id/normalizer_version/chunking_version/doc_protocol/chunk_protocol均为非空str；scope:str为global/private；owner为正int或null；chunk_policy为精确三键只读mapping；documents为有序只读ChunkDocument序列；manifest为下述准备级dict的只读快照；warnings为安全字符串tuple；除owner外均不允许null。

to_intent_metadata返回preparation对象，精确包含schema_version、source_sha256、source_format、import_namespace、doc_id、scope、owner、normalizer_version、chunking_version、doc_protocol、chunk_protocol、chunk_policy、warnings。warnings在JSON中转字符串list。该对象必须在写库前保存到intent.preparation；恢复构建证明从这里读取原运行值，禁止用当前默认值补齐缺失字段。

documents 是有序产品 ChunkDocument 快照，保留现有 content/doc_id/scope/user_id 和 metadata.doc_id/chunk_id/chunk_index/normalizer_version/chunking_spec_version/source_format/source_locator。准备结果的 documents 和 manifest 必须一致，不能只冻结外层而让内层 dict 在写入前被改写；ingest_prepared 校验摘要与预期身份，不接受被改动的准备结果。

prepare_file 只通过现有工厂/Extractor/ChunkingService 完成一次提取切块，无 embedding/index/commit。准备前后校验输入字节SHA一致，检测文件变化则失败。所有产物属于同一 doc_id，chunk_index 从0连续，chunk_id 不重复，计数>0。

IngestionPreparationError 继承 ValueError，包含 status 与预定义安全摘要；status 仅 unsupported、extraction_empty、invalid_request。ingest_file 对 unsupported/extraction_empty 映射为现有非成功 IngestResult；无效参数仍为 ValueError，不把数据库编程错误吞成空文档。

### A2. 写入与计数

index 接受空列表返回0。非空时，embedding 数量必须等于docs数量，每个向量长度等于当前绑定维度，元素为非bool有限数值；短/长列表、错维度、NaN/Infinity 在任何insert之前拒绝。成功返回已commit条数，不允许zip截断后返回计划数。任一insert或commit异常整体rollback后抛出。无法证明commit结果时标未决，不能靠返回0假称从未写入。

IngestResult 现有字段/非成功状态保留；status=ok要求planned=written>0。provider返回null/不符时index_unconfirmed，不生成成功证明。bool不是合法计数或用户ID。global owner=null；private owner为正整数；其他组合拒绝。写入层现有dict用user_id，新证明使用owner，两者一对一映射。

### A3. 计划清单和实际快照

准备级清单由T02生成，精确字段schema_version=prepared-manifest-v1、doc_id、rows、row_count、manifest_sha256；不含run ID、目标或embedding身份。rows按chunk_index展示，每项doc_id/chunk_id/content_sha256为非空str、chunk_index为非负int、scope/owner满足授权组合、source_locator为可序列化JSON对象；不含正文。row_count为正int且等于rows长度，摘要定义见C。

运行级清单由T08将准备级清单装配为envelope，精确字段schema_version=ingestion-manifest-v1、ingestion_run_id(UUID字符串)、target_index_id、doc_id、source_sha256、embedding_fingerprint、rows、row_count、manifest_sha256。rows/row_count/manifest_sha256必须原样消费准备结果，仅加入运行绑定；不重新提取切块。prepare_file不需要也不得猜run ID/实际目标/embedding配置。

IndexSnapshot包含target_index_id、database_id、schema_name、row_count、rows、manifest_sha256。rows为与计划相同的完整行多重集合，必须保留重复行，禁止用set掩盖重复。快照由实际绑定provider只读查询产生，不由调用者仅填写row_count。manifest_sha256只对规范化rows计算；run_id另行绑定，避免计划和实际库没有run列时无法比较。

快照只用于明确隔离的产品验证目标。读取原始行正文仅在provider内部用于SHA，不把正文放入快照、日志或证明；权限对抗库不得作为本书成功快照。

### A4. 意图、运行记录和恢复状态

写入前持久化intent.json与plan-manifest.json；成功写入采用同目录临时文件、完成刷新/关闭后原子替换，半文件不作为已持久化证据。intent字段：schema_version=ingestion-intent-v1、ingestion_run_id、created_at、target_index_id、database_id、schema_name、source_sha256、manifest_sha256、embedding_fingerprint、embedding_config（完整原运行EmbeddingIdentity）、preparation（A1完整元数据）、before_row_count=0、resource_record_ref、exclusivity_record_ref、isolation_evidence_ref、exclusive_target=true、phase=prepared。除preparation.owner及identity中明确可空字段外不允许null，时间为UTC ISO8601，引用为不含秘密的可定位字符串。

resource_record_ref由T07/受控环境配置提供，runner在写库前只读验证目标记录，不能凭CLI字符串直接相信；exclusivity_record_ref由runner记录排他锁/租约与本run的持有证据。isolation_evidence_ref固定指向本run目录下isolation-evidence.json，预意图只记录未来输出路径，不把未生成文件当已验证证据。T08在commit或恢复后重新核对实际快照、资源记录和排他证据，生成该文件：mode、target_index_id、manifest_sha256、row_count、verified_at、resource_record_ref；T09再消费它并核对引用/摘要/目标。恢复仍从intent中的原版本/策略/namespace/warnings和identity构建证明；证明created_at为本次核验时间，run ID保持原值，计数来自实际快照。

exclusive_target是受控运行排他管理记录，不以一个bool自行证明无其他writer；runner对目标持有排他锁/租约，未决意图未处理前所有受控写入者不得启动新run；外部writer无法排除则不准成功恢复。

同一run目录新增只读证据，不覆盖其他run。RunRecord唯一定义位置为app.infrastructure.rag.contracts.RunRecord，由T04定义，T08只消费。精确字段：schema_version:str固定ingestion-run-v1、ingestion_run_id:UUID字符串、phase:枚举、error_code:六安全码或null、safe_summary:str、failures:tuple[str,...]、attestation_path:str或null。phase只取prepared、committed_unattested、completed、failed、inconclusive。failed必须已确认回滚/未写入，结果不明用inconclusive；只有completed允许非null attestation_path，且必须指向已验证成功证明。

error_code仅复用backend_unavailable/db_error/embedding_failed/provider_degraded/invalid_request/timeout；契约拒绝或文件记录故障未对应已确认操作码时为null，通过failures安全规则ID表达（例如intent_missing、manifest_mismatch、record_io_failed、isolation_unproven），不扩展对外错误码集合。RunRecord摘要按phase固定为“摄入计划已准备”“写入待证明”“摄入已核验”“摄入未完成”“摄入状态待核验”；规则ID按字典序去重，禁止将异常原文作为规则ID、error_code或摘要。

MVP仅支持空库首次摄入恢复。recover_ingestion校验预意图/计划、空前态、目标独占证据、实际全部行多重集合、source/config一致；完全吻合才补成功证明。恢复不依赖上次IngestResult或重新提取，只读实际行重建确认计数。全部行为空且无commit不明问题可保留未摄入诊断，不自动重导；部分行、重复、非空前态或无法唯一归属，保持inconclusive/未准入，交人工处置。新目标另run不删除旧库，不引入幂等或upsert。

## 第三层B：成功证明与准入

### B1. AttestationExpectation与JSON字段

AttestationExpectation包含expected_source_sha256、expected_target_index_id、expected_embedding_fingerprint、expected_scope、expected_owner、expected_manifest_sha256、isolation_evidence。字段均显式给出，不从证明本身复制来假装独立核验。isolation_evidence包含mode=isolated_db、target_index_id、manifest_sha256、row_count、verified_at、resource_record_ref；验证实际目标/清单一致，不只看verified=true。MVP不接受provenance_filter模式，后续实现另修版本。

ingestion-attestation-v1 所有下列键必需，无额外未声明顶层键。字符串非空，SHA是64位小写十六进制，整数字段拒绝bool/null；时间为UTC ISO8601。

| 字段 | 类型及约束 |
|---|---|
| schema_version / contract_version / status | 固定ingestion-attestation-v1 / rag-mvp-contracts-v1 / ok |
| ingestion_run_id / created_at | UUID字符串 / UTC时间 |
| source_sha256 / source_format / import_namespace / doc_id | 输入SHA / epub / 非空字符串 / 产品稳定ID |
| normalizer_version / chunking_version / doc_protocol / chunk_protocol | 实际版本；当前doc-norm-1 / chunk-policy-1 / doc-v1 / chunk-v1，未经协议升级不能冒用版本 |
| chunk_policy | 精确键chunk_size、chunk_overlap、hard_limit；正整数及现有策略约束 |
| planned_chunk_count / written_chunk_count / failure_count | 成功planned=written>0，failure=0 |
| backend / provider / dialect / target_index_id | pgvector / PgVectorProvider / postgresql / 无密钥目标标识 |
| scope / owner | global和null，或private和正整数 |
| embedding_config / embedding_fingerprint | C节EmbeddingIdentity JSON / 其规范化SHA |
| artifact_manifest_sha256 / isolation_evidence_ref | 清单SHA / 可核验记录引用 |
| error_code / safe_summary / warnings | null / 固定“摄入已核验” / 安全字符串列表 |

embedding版本/别名限制包含在embedding_config中，不在证明顶层重复另一份。首次版本未知证明、缺字段、非法类型、非法owner、计数不符、指纹不符、目标或清单不符均拒绝；旧证明不得自动补字段升级为成功。

### B2. ContractCheck与失败分类

ContractCheck字段：allowed:bool、failures:tuple[str,...]。failures按schema/version/types/source/target/identity/count/scope/isolation顺序汇总安全规则ID，不带SQL、堆栈或秘密。allowed只在failures为空时true。build_attestation只接受成功IngestResult和匹配快照；无匹配不输出status=ok。

六项gate保持backend/provider/dialect/provider-set/attestation/corpus-isolation。backend等失败优先blocked:not_real_pgvector；证明/隔离缺失或不符为blocked:unattested_product_index；资产非法为blocked:asset_invalid；实时探测因连接/embedding/IO异常不可判定为infrastructure_inconclusive。已查明dialect是SQLite是blocked，无法连接不是查明SQLite。gate前真实上下文缺失拒绝，测试可以显式注入受控快照但不产生产品验收结论。

## 第三层C：embedding 身份规范

新纯数据结构 EmbeddingBinding：service_id、deployment_id、model_version、expected_endpoint。service_id/deployment_id为已配置无密钥公开标识；deployment_id与model_version允许null；expected_endpoint为仅内存使用的实际目标匹配信息，禁止序列化、日志或参与指纹。绑定由受控环境装配，不由benchmark或用户文本提供。

describe_embedding检查实际service.model、实际SDK client端点、实际service.dim以及实际请求参数；初始化SDK client不等于调用远端API。endpoint与binding不符拒绝，不直接把完整URL写进摘要。只对明确允许的公开service/deployment标识建指纹；若端点无法唯一映射公开标识则配置错误，不静默丢弃部署差异。

EmbeddingIdentity字段精确为schema_version=embedding-identity-v1、service_id、deployment_id、model、dimension、parameters、model_version、version_binding。dimension为正整数且与实际产生向量一致；parameters为影响向量生成的规范化标量mapping，当前实际请求只有model/input，input不入身份，默认状态用值“service_default”明确表示，不编造当前不存在的temperature等参数。parameters含dimensions与encoding_format两键，值分别为显式请求值或service_default；将来新增影响向量的参数必须同时加入身份，不得忽略。version_binding取pinned（有可信不可变版本）或alias_unpinned（model_version=null）。

公开规范JSON：UTF-8，键按Unicode码点排序，分隔无多余空白，非ASCII不转义，null/true/false按JSON，无NaN/Infinity；不做会改变既有字段语义的Unicode/URL归一化。标识在装配时规范化并验证，不能用两个别名表示同一声明后随意互换。fingerprint=此JSON字节SHA-256的小写十六进制。相同维度但model/deployment/参数不同必须不同指纹并拒绝旧索引；同一证明的自报fingerprint还须与重新计算及实际查询identity相等。

摄入与查询在run内固定实例配置；当前EmbeddingService.dim依赖可变settings，实现时必须确保实际维度与记录一致，发现漂移拒绝，不把配置快照当远端证据。远端别名原地变更但无版本时，指纹只能证明可观察配置一致；所有证明/报告保留alias_unpinned限制，不宣称完全锁定向量空间。

计划/实际manifest、intent摘要也使用上述规范JSON；计算manifest_sha256时输入仅rows，不包含自身摘要字段，不含runid。rows对外可按chunk_index展示，但计算摘要/比较时必须先按每项完整行规范JSON字节排序，再对保留重复项的数组规范JSON取SHA；所有生产者/消费者采用同一规则。正文摘要对产品实际content的UTF-8字节直接SHA，不重做normalizer。

## 第三层D：评测与报告

### D1. evaluate稳定输出

四键输入保持，默认top_k=5。正式baseline固定5、恰20题，其他部件调用可用合法top_k。query非空，top_k为1～10非bool整数。无gold仅允许普通部件调用，正式baseline必须asset validator通过；无gold相关指标为null、不再给满分。

所有返回分支包含：schema_version=retriever-evaluation-v1；retrieval_status（ok/empty/degraded/failed/invalid-request）；error_code（六个安全码或null）；safe_summary；sources_used/attempted_providers/failed_providers（字符串列表）；latency_ms（本次search耗时非负有限数）；top_k；valid_for_quality:bool；recall_at_k、recall_at_1、recall_at_3、recall_at_5、context_precision_proxy、redundancy（有限[0,1]数或null）；faithfulness/answer_relevancy/context_precision（judge数或null）；judge_scores；judge_degraded:bool；degraded:bool；degraded_reason（安全字符串或null）。

judge_scores精确含上述三个judge指标，每项有value（数或null）、available:bool、safe_reason（null或missing/non_numeric/non_finite/out_of_range/unavailable）。拒绝bool及非有限数；faithfulness/context_precision范围[0,1]，answer_relevancy允许[-1,1]以兼容余弦型实现，不擅自把负相似度当系统失败；具体采用的RAGAS版本若声明更窄范围可在实现包记录，但不能无依据改变本输出。缺失值写null，合法0仍是有效分数；部分缺失使judge_degraded=true，保留其他有效项与机械指标。degraded兼容值等于judge_degraded或retrieval_status不在ok/empty；runner不得只看该旧字段。

机械指标沿用DEC-011全文段落containment proxy：gold去重后分母为gold数量，若gold包含于某返回正文或反之视为命中；Recall@k由同一次有序返回的前k项派生。top_k<k则对应固定k字段为null，不能再搜索补足；返回不足top_k但查询本身合法可用全部返回派生，不视为基础设施失败。重复正文沿用Coordinator去重语义；context_precision_proxy不被RAGAS同名值覆盖。failed/degraded（来源故障）/invalid-request的质量字段null且valid_for_quality=false，不冒充零召回；健康empty有gold时recall/precision/redundancy为0。

### D2. 完整baseline不变量

validator必须恰20条且ID非空唯一、全部verified_v1；question/gold/locator/excerpt/SHA继续原校验，任何draft/重复/缺ID都阻断。每题最多一次evaluate和search，无隐式重试、无为多k重跑。

runner仅对valid_for_quality=true计有效结果；遇首个检索故障或非法请求/输出结构立即停止，保留诊断而不混入均值。正式题合法但首题数据库失败：有效0、失败1、未跑19、状态infrastructure_inconclusive。judge无效不增加检索失败数，所有20题健康检索可completed_judge_degraded。completed要求有效20/失败0/未跑0/全部judge有效；completed_judge_degraded同样要求20/0/0。结果ID与准入集合严格一一对应，零题执行绝不能completed。

### D3. 报告字段

rag-baseline-report-v1统一字段：schema_version、status（沿用六状态）、contract_version、run_id(UUID)、created_at、backend、provider、dialect、target_index_id、embedding_config、embedding_fingerprint、attestation_id、artifact_manifest_sha256、isolation_evidence_ref、asset_sha256（source/corpus）、expected_count=20、attempted_count、valid_count、failed_count、not_run_count、results、failures、evaluation_alignment、judge_enrichment、limitations。

运行前blocked报告尚不可得字段必须显式null，而非虚构；results=[]，attempted/valid/failed=0、not_run=20。每条results为case_id与metrics；失败尝试也保留但metrics.valid_for_quality=false；attempted=valid+failed，not_run=20-attempted。invalid assets不创造题ID，expected_count仅表示正式基线要求。

report failures是安全规则ID/题ID/分类码，不存原始异常。evaluation_alignment固定paragraph-containment proxy，judge_enrichment固定gold-answer/context enrichment。limitations必须包含proxy局限、不代表Tutor质量、alias_unpinned（如适用）。严格JSON禁止NaN/Infinity。健康低分不阻断完成，不新增教学质量分数阈值。

## 第三层E：在线、上下文与迁移

### E1. 已批准候选值归档

保留run_online_agent_session为在线入口；配置pgvector、实际PgVectorProvider、实际PostgreSQL三条件；普通API失败HTTP503，SSE分类事件沿用现有RAG_BACKEND_UNAVAILABLE。top_k默认5、上限10。六安全码及文案以当前SAFE_SUMMARIES为精确基线：backend_unavailable“检索服务当前不可用”；db_error“知识库服务暂时不可用”；embedding_failed“知识索引服务暂时不可用”；provider_degraded“部分知识来源不可用”；invalid_request“当前请求无法检索知识”；timeout“检索超时，请稍后重试”。

RAGRequestContext为纯不可变结构：retrieval_id非空、attempt=1、trace_id可空、session_id可空。Coordinator.search与Provider.search仅增加可选关键字context=null，不破坏现有调用；其他provider不支持context时非受限旧路径保留原签名，不在旧OCR/code强塞参数。Retriever从受信任事件构造context，规则/Conductor不可改写身份。新增上下文不扩展Event dataclass。

### E2. 投影与引用

EvidenceProjection精确字段：schema_version=evidence-projection-v1、retrieval_id、retrieval_status、attempt=1、quality（high/low/acceptable/unavailable）、chunks、citations、sources_used、error_code（六安全码或null）、safe_summary、truncated:bool。

chunks和citations每项精确为content/source/score，沿用原spec，不新增强制产品ID字段。保序最多5项，每content最多2000 Unicode字符；正文预算6000按chunks正文之和计算，citations与chunks一一对应、复用同一份文本且最多5项。Tutor只渲染一次正文，引用不重复渲染content，因此不会把6000预算翻倍。截断只作用投影副本，设置truncated=true，不改产品chunk/稳定ID。score必须有限数；无权限或关联不符拒绝，不靠截断修补权限。

Orchestrator在动作payload键evidence_projection中传完整对象；retrieval_id也在动作payload并与对象相等。缺失/错ID投影不能走无证据最终教学旁路。empty/failed/invalid-request投影无chunks/citations；degraded只含成功授权来源并标安全降级，低quality的ok仍保留状态。safe_summary来自既定安全文案，正常ok可为空字符串、empty固定“未找到可用课程证据”，不把异常文本拼入摘要。

每retrieval状态request/result/attempt/quality/direct_parent/final_tutor_action_emitted仅会话内存在；Tick屏障最多发一次最终Tutor动作，无quality继续unavailable，迟到观察不重发。不从共享evidence_pool猜当前轮。普通/SSE同核心链路，新增run查询前实际embedding指纹与证明比较，不同即拒绝旧索引。

日志schema固定event、retrieval_id、attempt、trace_id、session_id、provider、outcome、error_code；缺可用ID时null，不能编造。歧义行审计只含数据库行ID/类别/目标和context，无正文/秘密；受限provider收到context才能做完整关联，未提供context的兼容调用不伪造ID。原异常堆栈只进受控内部日志且敏感字段需脱敏，不把连接串密钥作为可公开诊断。

### E3. 迁移注入

冻结测试参数名：Config.attributes的rag_test_mode=true、connection为fixture已打开的同步连接、rag_test_target为目标记录（target_index_id/database_id/schema_name/resource_record_ref）。测试模式缺连接/记录即拒绝，不能回退settings。env.py仅在非测试且无显式注入时用原settings路径；收到connection按显式连接迁移，不再用settings创建第二连接。

任何DDL/清理前从该连接只读核对真实database/schema、资源记录以及非业务/非基线目标。SQLite测试文件必须解析后落在指定测试目录或为内存连接。settings=A/fixture=B只允许B变化；A绝不先迁移再验证。不在T00启动迁移，也不更改生产迁移revision。

## 4. 任务所有权、兼容与验收交接

| 任务 | 写入边界与消费契约 |
|---|---|
| T02 | knowledge_ingestion.py、embedding.py、pgvector_provider.py与对应写入测试；产出A1/A2；不写schema模块 |
| T03 | retriever.py评测、rag_d.py题集/完成规则及对应测试；产出D；不写T04模块 |
| T04 | 新contracts.py、embedding_identity.py、ingestion_attestation.py及新纯逻辑测试；产出B/C数据结构与函数 |
| T05 | env.py、迁移守卫及新测试；产出E3 |
| T06 | assembly/orchestrator/tutor/critic及对应测试；消费E1/E2，不并改retriever.py |
| T08 | 等T02/T04后写runner及provider快照接口，与T10串行交接provider |
| T09 | 等T03/T04后对接共享schema和rag_d报告gate，不另造产品schema |
| T10 | 等T02/T03释放provider/retriever后加context、审计和错误边界；不得与T08抢provider |

旧签名兼容不等于旧无效输入仍放行；schema消费者必须显式新版本。历史普通evaluate调用允许输入兼容，新字段增加、无gold/失败指标改null属于本轮明确的纠偏，测试需同步，不宣称数值输出完全向后兼容。

放行材料：T00必须有raw血缘、版本表、上述接口/错误/数据字段、RV追溯、自查和独立review及记录。T00完成后仅表明共享契约可引用；T02/T03/T04仍各需独立plan和文件精确清单，经审阅后才能派发。T01资源盘点不在T00范围，不能据此勾选全部S0。

## 5. 核验矩阵与冻结验收

| 来源 | 冻结位置 | 实现时必需验收 |
|---|---|---|
| R01/13 | D1～D3 | 数据库故障传播至报告，非质量0分；安全来源可审计 |
| R02/09 | A2 | 数量/维度失败写库前拒绝，insert/commit失败rollback；PG另实测 |
| R03/04 | B | 版本/非空/类型/owner/count/target/isolation有效，不只verified布尔 |
| RV-01/R23 | D2/D3 | 20draft、部分draft、重复/空ID拒绝；首题失败0/1/19；完整低召回可完成 |
| RV-02/R24 | C/B/E2 | 同维不同模型/部署拒绝，实际实例与证明匹配，别名版本限制披露 |
| RV-03/R25 | E3 | settings=A/fixture=B仅B变化，漏注入/错目标变更前拒绝 |
| RV-04/R26 | A1/A3/A4 | 预计划先落盘；提交后退出只读核验补证；重复/缺行不准入 |
| RV-05/R27 | D1/D3 | judge缺失/非数值/非有限/越界按项降级，严格JSON，机械指标保留 |
| C §F/G/H | E | 三条件/六码/top_k/投影上限/身份保真/当前轮关联/最多一次动作 |

本文没有运行任何实现或真实服务测试。冻结只对接口和设计生效，真实PG/embedding/20题及在线验收继续由G1～G6证据判定。
