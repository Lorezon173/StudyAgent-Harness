# T01 环境与版权资产只读盘点执行计划

> **当前状态：** 用户于2026-10-17明确授权“先执行t1”，只读盘点覆盖已完成，[执行证据](../evidence/t01/2026-10-17-inventory.md)分别记录实际观察及未探测原因。资源就绪blocked，PG/embedding未探测；下文保留原执行设计，不作为资源已验证声明。

**目标：** 对 RAG MVP 所需的本地书籍、corpus、题集、运行时/CI 条件、受控 PostgreSQL 资源和 embedding binding 做有来源的只读盘点，并完整记录缺失、未知、不可探测项及责任方。

**架构：** 先从仓库内有据可查的清单、静态配置和合法本地资产形成声明记录，再核对文件元数据、哈希和无正文结构；只有找到可信、唯一且用途获准的受控 PG 资源绑定后，才允许对该连接执行一次有超时的只读身份查询。embedding 只盘点无密钥 binding/公开配置元数据，不创建 SDK client、不发请求。所有结论进入单一 T01 证据文件，逐条区分声明、观察、未知和下游门禁影响。

**技术范围：** 现有文件系统元数据、SHA-256、项目静态配置及既有 YAML/JSON 解析能力；不新增生产代码、脚本、依赖或资源注册格式。未来执行可用标准文件查看、哈希及只解析元数据的一次性受控动作；不导入业务应用/settings 模块。

**冻结依据：** [RAG MVP 共享契约 v1.0.1](../specs/2026-10-16-rag-mvp-contracts-v1.md)，SHA-256 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`；[原始三层执行方案](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan.md) 的 S0-04、E4；[依赖 DAG](../../../superpowers/rag-foundation/2026-10-16-rag-mvp-dag-and-scheduling.md) 的 T01/T05/T07/T08/T09 边界。本文是原始规划的 T01 执行细化，不修改冻结契约。

**设计来源与相关状态：** [第二批计划复核](2026-10-17-second-wave-plan-review.md)确认 T05/T08/T09 仍有 9 项阻断问题，G1～G6 均未通过。[T05 计划](2026-10-16-t05-execution-plan.md)、[T08 计划](2026-10-16-t08-execution-plan.md)和[T09 计划](2026-10-16-t09-execution-plan.md)消费 T01 的事实，但本计划及未来 T01 证据都不关闭 RV2 缺陷、不代替 T07，也不修改共享 schema、资源标识规范或锁协议。

## 全局边界

- 只检查仓库明确引用或登记的资产与配置来源，以及用户受控提供的合法本地资产路径；不遍历用户磁盘寻找书籍，不下载、上传、重建或改写 EPUB、corpus、题集。
- 不打印 EPUB、corpus、题干、答案、正文片段或凭据。文件内容只可用于本地哈希或内存中的无正文结构计数；证据仅写相对路径/安全引用、文件大小、摘要、计数和状态。
- 将“声明 SHA-256”与“本次对本地文件计算的 SHA-256”分别记录；不得把 corpus 哈希等同于源 EPUB 哈希，也不得将历史 README 中的外部路径当成本机资产存在证明。
- 不导入 `app.core.config.settings`、业务 app、`benchmarks/.../rag_d.py`、`validate_assets` 或任何可能间接加载 settings/连接服务的模块；`.env` 始终不读取。进程环境仅可按已批准的公开键名检查是否存在，不取值、不输出。默认不实例化模型或数据库客户端；唯一例外是步骤 4 的 PG 探测：前置登记核验通过后，由可信工厂为本次 T01 提供新建、专用的同步 PostgreSQL 连接。该连接不得来自业务默认 settings，不得带有调用方已有事务；T01 自己建立只读事务并负责 rollback、close。连接或事务来源不满足这些条件时拒绝探测。
- 不执行 pytest、集成测试、CI 工作流、Alembic、迁移、fixture、摄入、索引、embedding 或 judge 请求；尤其不导入或运行 `tests/integration/test_pgvector_real.py` 及其可能调用的破坏性 fixture。历史的 547 passed / 1 deselected 等结果仅可作为带日期的历史证据引用，不能写成本次验证。
- 不访问未经登记的业务默认库，也不先试连再查找登记。PG 只有在连接前已有可信登记能将受控连接唯一绑定到获准盘点目标、能确认不是业务/基线默认目标且无 settings fallback 时，才可向可信工厂请求步骤 4 所述的新建专用连接；条件缺一即记录“未探测/阻断”，不尝试任何地址。
- PG 探测的连接超时上限为 5 秒，单条元数据 `SELECT` 的语句超时上限为 10 秒。可信工厂必须在建立连接前应用连接超时，并在第一条查询前建立只读事务、应用语句超时；若任一超时或只读边界不能保证，则不探测。查询只通过该新连接执行；完成后无论成功失败均 rollback 并关闭该连接。不得执行 DDL、DML、迁移、扩展、清理、表扫描或写入探针。查询可连通只表示本次只读身份查询完成，不证明 writer 权限、权限排他、锁有效、事务提交或 T07/G2 通过。
- 本计划不选择 PostgreSQL 服务唯一标识的最终格式，不决定锁/lease 机制，也不把 database 名、schema 名、host/port 或当前角色的单一值宣称为足够唯一。若登记无法提供可审计的唯一服务实例绑定，保留为待 T07/主控裁定的阻断事实。

## 盘点状态定义

T01 用两个互相独立的状态回答不同问题：

| 维度 | 取值 | 含义 |
|---|---|---|
| 盘点覆盖 | `covered` / `partial` / `not_applicable` | `covered` 表示该类别已按步骤核对，并为每项记录观察值、未观察原因或不适用依据；它不表示资源存在或可用。`partial` 表示计划范围内仍有未核对类别。`not_applicable` 必须说明为何该类别对本项目不适用。 |
| 资源就绪 | `ready` / `blocked` / `unknown` / `not_applicable` | `ready` 只用于已由该类允许的只读证据验证满足盘点前置条件；`blocked` 表示缺失或不符合；`unknown` 表示来源或能力无法判定；`not_applicable` 必须附明确理由。 |

当所有规定类别均已覆盖，即使资产缺失、可信登记不存在、PG/embedding 无法探测或 T07 必需字段未知，也可以报告“**盘点覆盖完成**”；相应资源仍标 `blocked` 或 `unknown`，并继续阻断 T07、T11/T12 及其依赖的真实门。不得把“覆盖完成”写成“资源已就绪”。

## 第一层：模块总览

### 边界、依赖与产物

T01 是只读事实采集与交接包，依赖冻结契约、原始规划、DAG 和现有 T05/T08/T09 计划。它不生产资源、不修改产品配置、不实现 adapter；其结果供 T05 判断真实目标守卫需要哪些登记事实，供 T08 绑定安全的 writer/resource/binding 来源，供 T09/T12 组装独立 expectation、目标映射和实际 binding 来源。

执行顺序是：仓库来源清点 → 资产声明与本地文件核对 → 测试/运行时/CI 静态盘点 → 受控 PG 登记审查及有条件的只读身份核对 → embedding binding 元数据审查 → 交叉核对、归属和阻断交接。前四类均可在缺外部服务时完成盘点；缺失信息必须落入证据，不得据此推造资源事实。

**唯一未来执行证据：** `docs/rag-work/evidence/t01/2026-10-17-inventory.md`。该文件由未来获准执行的 T01 记录实际观察、声明来源、查询是否执行及原因、阻断项和责任方；本次计划编写阶段不创建它。

### 本次禁止变更与交付边界

本轮唯一规划文件为本文。未来 T01 唯一新增/修改文件应为上述执行证据；资产、配置、测试、README、冻结 spec、T05/T08/T09 计划和共享资源文件均保持只读。证据不得保存 secret、DSN、完整 endpoint、版权正文或完整环境转储。

## 第二层：子模块概述

| 子模块 | 职责与输入 | 数据流与记录接口 | 状态、失败与交接 |
|---|---|---|---|
| A. 资产来源与本地可用性 | 从仓库现有 README、资产清单、配置文档或批准来源引用，识别 source EPUB、独立 corpus 和 20 题集；只访问有合法来源的已登记本地路径。 | 声明引用 → 文件存在/类型/大小 → 实际 SHA-256 → 无正文结构计数；记录每项声明摘要与实测摘要，不输出内容。 | 路径未提供、文件缺失、来源不明或哈希不符均记录为 blocked/unknown；不下载、修复或代替正式 validator。交给 T11/T12 决定合法恢复与产品验证。 |
| B. 运行时、依赖、测试与 CI 条件 | 输入限于 `pyproject.toml`、存在的锁文件、pytest/lint 配置和仓库 CI workflow 文件，以及既有历史执行证据引用。 | 静态声明 → Python/依赖约束、测试/CI 命令与触发条件摘要 → 禁止动作清单。可读已安装包元数据但不 import 业务模块、不安装依赖。 | 文件缺失、配置互相不一致、当前环境无法只读取得包元数据时记录 unknown；不运行命令验证配置，不将历史测试结果外推为当前通过。交给主控/T14 规划必要验证。 |
| C. PostgreSQL 受控资源与身份映射 | 输入必须是可信登记/主控指定引用、目标用途和唯一绑定来源；没有该来源时不读取 settings、不解析 `.env`、不连接默认 DB。 | 受控登记声明 → 唯一性/用途审阅 →（仅满足前置时）同一连接 read-only transaction 的目标/角色/search_path 元数据 → 安全化身份记录。 | 无登记、冲突、多条匹配、无法确认实例唯一性、业务/基线碰撞或无法保证只读/超时均为 blocked/unknown 并跳过连接。可连接不代表授权、排他或锁有效；T07 负责真实权限/事务/迁移验收。 |
| D. Embedding 配置与 binding 来源 | 输入为明确指定的公开 binding/模型部署元数据来源及允许检查的配置键名。 | 登记引用 → service/deployment/model/version/维度/参数声明及来源状态 → 是否可与实际服务绑定对应的待核验字段清单。 | 不创建 client、不发请求、不揭示 endpoint/key；binding 缺失或无法独立对应实际服务则 unknown/blocked。T07/T09/T12 负责受控实例核验、配置指纹和真实向量行为。 |
| E. 事实审计与阻断交接 | 输入为 A～D 的记录及 T05/T08/T09/T07 的已知需求。 | 声明、观察、推断（如有且明确标注）、未知、证据引用与责任人形成一张审计表及阻断摘要。 | 信息不足不补猜；保留每项下游任务与门禁影响。覆盖完整可结项盘点，但 required unknown 保持真实门阻断。 |

## 第三层：子模块详细实施计划

### 步骤 1：建立受控来源索引

**输入：** 冻结 spec、原始 S0-04/E4、DAG、T05/T08/T09 当前计划，以及仓库内这些文档明确引用的资产或配置清单。

**动作：** 只读列出引用中实际存在的仓库相对路径；逐项记录该引用是规范、声明、历史线索还是当前权威来源。历史 README 中的外部 macOS source path 仅登记为历史线索，不据此声称 Windows 当前文件存在。对没有明确来源的项目记录 `source_unresolved`，停止沿任意路径扩散搜索。

**输出：** 来源索引行，字段为 `item_id`、`category`、`source_ref`、`source_kind`、`current_authority`、`allowed_read_scope`、`status`、`owner`。不复制来源文件正文。

**完成/异常：** A～D 每项都有权威来源或明确的 `unknown`/`missing` 行才算本步骤覆盖完成；来源引用冲突交主控裁定，不自行选一个覆盖其他来源。

### 步骤 2：核对 EPUB、corpus 与题集资产

**输入：** 步骤 1 确认的仓库相对路径或用户明确给出的合法本地来源；已有 manifest/README 中声明的 SHA、文件类型和数量约束。

**动作：**

1. 对每个 `source_epub` 只读取文件系统元数据并计算完整文件 SHA-256；记录相对路径、是否存在、普通文件标记、字节数、实际摘要。对照 manifest 中声明的 source SHA 和声明出处，分别记下相等/不同/无声明。
2. 对 `corpus` 作为独立资产单独登记；只按已有文件格式解析所需的无正文结构字段，计算其自己的 SHA-256 与记录数/条目数。不得将 corpus 内容打印到终端或证据，也不得以 source SHA 替代 corpus SHA。
3. 对正式题集只解析 JSON/YAML 结构和字段名，记录总条数、唯一题目 ID 数、重复/缺失 ID 数，以及逐条 `status` 分布计数 `verified_v1`、`draft`、`unknown`。状态缺失或不属于这三类的条目计入 `unknown`，并另记异常状态数；同时记录声明的 source/corpus 引用及其无正文摘要。不输出 question、answer、reference text 或正文内容。题目总数达到 20 不等于 20 条均为 `verified_v1`；若总数不是 20 或 `verified_v1` 计数不是 20，必须记录为 T12 前置缺口。合法格式解析失败时记录安全错误类别，不复制异常中的内容。
4. 比较 source、corpus、题集声明之间的引用关系和已记录 SHA；缺 asset、声明 SHA 不匹配、授权来源不明、结构不完整均作为明确缺口，不调用 T09 `validate_assets`（它所在模块存在 settings/PG 导入链），也不重建文件或问题。

**记录字段：** `artifact_kind`（`source_epub`/`corpus`/`question_set`）、`artifact_ref`、`declared_sha256`、`declaration_ref`、`observed_sha256`、`exists`、`size_bytes`、`structure_counts`、`question_status_counts`（分别记录 `verified_v1`、`draft`、`unknown`）、`unrecognized_status_count`、`t12_prerequisite_gap`、`source_relation`、`legal_source_ref`、`status`。无值用 `unknown`/`null`，不可用空字符串伪装已核实。

**完成/异常：** 本地已登记资产均有声明与观察的逐项对照，缺失者有责任方及 T11/T12 阻断影响即算覆盖完成。`verified_v1` 状态计数只反映现有题目元数据标签；即使计数为 20，也不代表完整 T09 资产 validator、EPUB extractor、corpus 版权或题目有效性通过，T12 仍须执行其正式准入校验。T01 不实现完整 validator。

### 步骤 3：静态盘点运行时、依赖、测试和 CI

**输入：** 仓库根 `pyproject.toml`、实际存在的 lock 文件、pytest/lint 配置、`.github/workflows` 中实际存在的 workflow 文件和可引用的历史测试证据。

**动作：** 逐个读取静态声明，记录 Python 版本范围、依赖及锁定来源、测试/lint 命令、CI 触发条件、runner/系统要求、依赖服务所需配置键名和已有测试目录边界。当前已知 `.github/workflows/ci.yml` 声明 `uv sync --extra dev`、`uvx ruff check .` 与 `uv run pytest tests/ -v`；计划执行时仍须以工作区静态文件复核这些命令及触发条件，不访问 GitHub、不运行 CI。默认跳过 integration 的依据是 `pyproject.toml` 中 pytest `addopts` 对 integration marker 的排除，不是排除 `tests/integration` 目录；pytest 收集仍可能导入该目录模块并执行模块顶层代码，因此 T01 不运行也不触发 pytest 收集。这个 marker 排除也不构成网络或数据库隔离保证。若当前本地虚拟环境存在且读取包元数据不需执行项目代码，可只读登记关键发行包的已安装版本；不运行其安装入口，不调用 `pip install`。`.env` 始终不读取；进程环境只按已批准的公开键名做存在性检查，不取值、不输出。

**禁止动作：** 不执行测试或 workflow，不导入应用模块，不运行 `rag_d.py`/`validate_assets`，不触发 `tests/integration`；尤其不运行 `tests/integration/test_pgvector_real.py`。该模块可能探测真实 PG、执行 DDL 和清理 fixture。任何既有 547 项结果都作为带来源日期的历史事实，不作为本次 CI/测试通过证据。

**记录字段：** `runtime_constraint`、`dependency_source_ref`、`declared_version`、`installed_version`（仅可读到时）、`test_command_declared`、`ci_workflow_ref`、`trigger_summary`、`required_config_key_names`、`historical_evidence_ref`、`not_executed_reason`、`status`。

**完成/异常：** 已存在的配置来源均已读取或明确标出无法读取，测试/CI 事实与历史结果已分栏即可覆盖完成。声明命令不等于当前命令成功；不一致和不可读取均交主控，不自动安装/修复。

### 步骤 4：审查 PG 资源登记并有条件执行只读身份查询

**输入：** 主控/T07 指定的受控 resource record 来源、唯一 `resource_record_ref`、用途标签、公开 `target_index_id`，以及由获准装配方提供的目标连接。若上述来源当前不存在或不能唯一匹配，本步骤到登记审查为止，不建立连接。

**动作：**

1. 只读检查可信登记能否唯一解析目标并区分 `permission/transaction test` 与 `book baseline` 资源，核对其是否声明实例级身份来源、数据库/schema、目标用途和实际登录角色审计来源。两个 PostgreSQL 实例即使 database/schema 同名也必须能从可信登记/绑定来源区分；若仅有 database/schema 或未经审计的字符串 ID，记为“实例唯一性未证”，不得探测业务默认目标。
2. 确认连接来自该登记的受控装配路径，且没有从 `settings`、`.env`、默认 DB URL 或 benchmark 隐式 fallback；只记录安全 `resource_record_ref`、公开 ID、配置变量/绑定来源引用和“有/无”状态，不读取或记录 URL/密码/host 完整值。
3. 仅在步骤 1～2 全部满足、资源用途获准后，才向可信工厂请求为本次 T01 新建的专用同步连接；拒绝接收调用方已有连接或已处于事务中的连接。连接建立前配置最多 5 秒的连接超时；首条查询前建立只读事务并配置最多 10 秒语句超时。无法在首条查询前确认这些边界时，不发查询、关闭连接并记录未探测原因。
4. 在上述边界已经生效后，通过同一新连接发出一条只读身份 `SELECT`，收集 `current_database()`、`current_schema()`、`current_user`、`session_user`、`inet_server_addr()`、`inet_server_port()` 和 `current_setting('search_path')`。查询结果只用于和可信登记逐字段比较；其中地址、角色和 search_path 不是实例唯一性、权限排他或 T05 revision 对象解析安全的充分证明。
5. 查询返回、超时、拒绝或任一字段不符后均 rollback 并关闭 T01 创建的连接；不尝试第二个 endpoint，不试其他 role，不回退到 business settings。若已批准的唯一实例标识需要该只读角色无法读取的额外元数据，记为 `not_probeable_with_current_role`，由 T07/资源 owner 提供可审计绑定来源或重新安排授权审计。

**记录字段：** `resource_record_ref`、`target_index_id`、`resource_purpose`、`database_id_claim`、`schema_name_claim`、`instance_identity_source_ref`、`instance_identity_verified`、`login_role_claim_ref`、`permission_audit_ref`、`query_attempted`、`query_result_safe_fields`、`search_path_observed`、`readonly_timeout_outcome`、`rollback_close_outcome`、`status`、`downstream_owner`。不保存 URL、密码、SQL 异常原文或返回对象 repr。

**完成/异常：** 若可信登记不存在、目标不能唯一绑定、目标可能是业务/基线库、查询超时能力不能保证或只读边界不清，明确记为 `not_probed` 和原因，即可完成该类别盘点覆盖；这些 required unknown/blocker 继续阻断 T07/G2。只读查询成功最多证明该连接可返回所列身份元数据，不能关闭 T05 的 RV2-05/06/07、T08 的 RV2-01/02 或 T09 的 RV2-08/09，也不证明真实 PostgreSQL 迁移、授权、独占 writer、baseline lock、embedding 或 G2。

### 步骤 5：审查 embedding 元数据与绑定来源

**输入：** 有明确来源引用的公开 embedding binding/部署登记、静态配置字段定义及 T04 `EmbeddingBinding` 所要求的公开身份字段。

**动作：** 不加载业务 settings、不读取 `.env`、不调用 SDK/client，也不触发 create/embed。按公开登记只记录 service ID、provider、model、deployment、可用的版本来源、声明维度、参数身份来源和配置键名/是否配置。若文档列出 endpoint 字段，仅记录是否有非空配置及来源引用；不读取/输出 endpoint 原值。区分“有 binding 声明”“配置键存在”和“绑定到本次实际 service 实例”；后者必须留给 T07/T09/T12 的授权核验。记录服务端别名版本不能固定等限制，不按维度相等推断模型相同。

**记录字段：** `binding_record_ref`、`service_id`、`provider_id`、`model_id`、`deployment_id`、`version_source_ref`、`version_pinnable`、`dimension_declared`、`parameter_identity_source_ref`、`config_key_names`、`configured_presence`、`endpoint_value_redacted`、`remote_request_made=false`、`status`、`downstream_owner`。

**完成/异常：** 无 binding、版本/参数来源未知、配置仅存在但无法映射实际 service，均作为独立缺口；不发请求，不声称维度实测、指纹匹配、向量有效或真实 embedding 就绪。

### 步骤 6：合并事实表、分配责任并作覆盖判定

**输入：** 步骤 1～5 的记录、冻结 spec 与 T05/T08/T09/T07 已列出的字段需求。

**动作：** 对每项输出区分 `claim`（文档/登记声明）、`observation`（本地文件元数据或允许查询的返回）、`unknown`、`not_probeable`、`conflict`；每个阻断项对应负责的资源 owner、主控决策或下游 task 和被阻断的门。对 T05 所需实例唯一性、search_path 和事务/守卫问题，T08 所需资源、登录 role 与 writer/binding 来源，以及 T09 所需 source SHA、公开映射、实际 binding/snapshot 来源逐字段列出“已有来源/缺失来源/尚待 T07 验证”。

**审计表字段：** `finding_id`、`category`、`claim_or_observation`、`safe_value`、`source_ref`、`method`、`observed_at`、`coverage_status`、`readiness_status`、`blocker_reason`、`owner`、`downstream_task_or_gate`。推断必须显式标记 `inference` 并列出依据；证据不足时填写 `unknown`，不以推测补齐。

**完成标准：** 所有计划类别及子项均有 `covered`、`not_applicable`（含理由）或具体未观察原因，责任人和下游阻断已登记时，T01 盘点覆盖可标完成。另设资源就绪结论：只有各自规定证据确实存在才标 `ready`；否则按事实标 `blocked`/`unknown`。盘点完成不要求资源 ready，也不得解除任何依赖真实验证的门。

## 盘点验收与交接

- 唯一执行证据文件包含资产声明/实际 SHA 对照、source/corpus/题集拆分与无正文计数、静态依赖及 CI 事实、PG 登记/是否安全探测及同连接元数据状态、embedding binding 元数据、未知/缺失/冲突项及责任方。
- 每条记录可回溯至来源引用和具体读取/查询方法；没有来源的值不得写为事实。无凭据、正文、题干、答案、endpoint 原文、DB URL、SQL 异常原文。
- 报告分别给出 `inventory_coverage` 和 `resource_readiness`；后者列出所有阻断 T07/G2、T11/G3、T12/G4 的 required unknown。不得报告“PG可连”即“PG已验证”，不得报告 binding 元数据存在即“embedding已验证”。
- 交接主控更新任务状态并决定缺失来源的责任方/授权来源；T05/T08/T09 原计划仍需按 RV2 逐项修订、复核和用户确认。T01 只提供事实，不擅自修改这些计划、共享契约或最终资源/锁设计。

## 执行前检查

- [ ] 再次确认共享契约文件 SHA-256 与本文一致；不同则停止使用旧字段并请主控确认新依据。
- [ ] 用户已确认本计划及只读探测边界；未来执行权限覆盖的路径/资源已明确，证据文件唯一且目标不存在。
- [ ] 合法 source/corpus/题集来源引用已经给出或从仓库内权威清单定位；无来源时不扩大磁盘搜索。
- [ ] PG 探测前已取得可信且唯一的 resource record、允许用途、无 fallback 的连接装配来源及查询超时/只读事务条件；任一缺失则跳过连接并记录 blocker。
- [ ] embedding 检查不需要读取密钥/endpoint 原值、不构造 SDK client、不发送请求。
- [ ] 本轮只读盘点无命令会导入 settings、运行测试、执行迁移、访问默认业务 DB 或输出敏感值。

## 主窗口文档复核状态

已完成本轮主窗口定向复核，四处首读意见及本批关系见[第二批审阅记录中的T01追加说明](2026-10-17-second-wave-plan-review.md)。该段为计划复核历史；随后用户已授权并完成T01盘点覆盖，具体结论见执行证据。原T05/T08/T09的9项问题和G1～G6状态保持不变。
