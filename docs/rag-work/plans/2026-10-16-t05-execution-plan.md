# T05 Alembic 迁移目标注入与变更前守卫执行计划

> **For agentic workers:** 执行时使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按任务逐项实施。本计划只描述接口、步骤和命令，不含实现代码或测试代码。

**当前状态：草案，待主控复核和用户确认。** 本文件是 T05 的唯一执行计划入口；不得将草案写成已实施或已验证。

**Goal：** 让 Alembic 测试迁移使用调用方已打开并预检的同步连接，在任何迁移动作前核对目标身份；保留普通 CLI 的现有 settings 路径。

**Architecture：** `alembic/env.py` 读取 `Config.attributes`，把显式注入连接作为迁移唯一连接，并在 `context.configure` 和 `context.run_migrations` 前运行 allowlist 资源解析和只读目标守卫。普通命令只有在三个注入键全部缺席时才继续使用当前 settings→同步 URL→Alembic Engine 流程；显式空连接或任何半套属性都失败关闭。T05 只实现入口和受控离线配置验证，真实 PostgreSQL 迁移留给 T07。

**Tech Stack：** 当前已依赖的 Alembic、SQLAlchemy 同步 Engine/Connection、pytest；不新增依赖。

**Spec：** [`2026-10-16-rag-mvp-contracts-v1.md`](../specs/2026-10-16-rag-mvp-contracts-v1.md)，SHA-256 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。

**设计来源：** [2026-10-15 MVP raw](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan.md) 的 R25、S0-06、S2-01/S2-05、E4；[同日 review](../../../superpowers/rag-foundation/2026-10-15-rag-mvp-execution-plan-review.md) 的 RV-03；[2026-10-16 DAG](../../../superpowers/rag-foundation/2026-10-16-rag-mvp-dag-and-scheduling.md) 的 T05/T07 分工与文件写权；[就绪核查](../../../superpowers/rag-foundation/2026-10-16-execution-readiness-audit.md)；[首批执行证据](../evidence/2026-10-16-first-wave-execution.md)。T00 已完成，T02/T03/T04 已验收；T05 不依赖 T08/T09 实现。

## 全局约束

- 冻结参数名为 `Config.attributes` 中的 `rag_test_mode=true`、`connection`（fixture 已打开的同步连接）、`rag_test_target`（目标记录，字段为 `target_index_id`、`database_id`、`schema_name`、`resource_record_ref`）。
- 测试模式缺少连接或目标记录必须拒绝，不能回退到 `settings`；收到显式连接必须直接用该连接迁移，不能再创建迁移 Engine 或连接 settings URL。
- 在任何 DDL 前，使用注入连接只读核对实际 database/schema、目标记录及其与业务/基线目标的隔离关系。SQLite 文件目标必须解析后位于指定测试目录，或使用内存连接。
- settings 指向 A、fixture 指向 B 的受控对抗中，只允许 B 进入迁移调用链；A 不得执行迁移或清理。受控 fake 只证明调用边界，不能作为真实资源证据。
- 保持现有 Alembic revision 及迁移语义不变；不改 `app/core/database.py`、`alembic/versions/`、`alembic.ini`、`pyproject.toml`、共享 `tests/conftest.py`、provider/RAG 文件或 README/索引。README、状态和索引由主控维护。
- 本包不连接真实 PG、embedding 或其他 SDK，不执行真实迁移，不运行 `tests/integration/test_pgvector_real.py`。T01 未盘点，正式资源/真实 PG 验收由 T07 在 T01 与 G1 前置满足后负责。
- 所有 pytest 使用项目既有 `.venv`，每轮使用不复用的本包独占 `--basetemp`（例如 `.pytest-tmp-t05-red-20261016-01`、`.pytest-tmp-t05-final-20261016-04`）；重跑时递增末尾序号，不清理临时目录，不用 `sleep`，不自动安装工具或依赖。
- 实施完成后的唯一证据入口建议为 `docs/rag-work/evidence/t05/2026-10-16-execution.md`，只记录实际执行过的命令、结果、限制与未决项；本计划编写阶段不创建该证据文件。

## 第一层：模块总览

T05 的边界是 Alembic 环境入口对迁移连接的选择和迁移前目标守卫。现有 `alembic/env.py` 同时定义离线与在线路径：在线路径用 `engine_from_config` 创建同步 Engine 并 `connect()`；离线路径读取 `sqlalchemy.url` 生成 SQL。模块导入时从 `app.core.config.settings` 读取 URL，并导入 `app.core.database.Base` 与模型元数据；`app.core.database` 当前会在模块导入时构造 settings 对应的异步 Engine。这个导入副作用不等于 Alembic 测试分支建立了连接，也不授权 T05 重构 database 模块。

仓库内没有发现 `alembic.command.upgrade`、项目自建 migration runner 或可复用目标注册表。正常入口是标准 Alembic CLI 加 `alembic.ini`；`env.py` 当前将 `+asyncpg`、`+aiosqlite` 替换为同步驱动可用 URL。生产迁移使用同步 SQLAlchemy；应用数据库模块的异步 Engine 不作为 T05 的迁移连接。版本脚本目前有七个，均不在 T05 写权范围内。

与冻结契约的衔接方式为：测试调用方把已打开的同步 Connection 和目标 claim 放入 `Config.attributes`；环境脚本先通过独立 allowlist 解析为受信记录，再核对实际连接，最后将同一 Connection 交给 `context.configure`。三个注入键全部缺席时普通在线 CLI 保留 settings 路径。普通离线 SQL 生成继续使用 settings URL；建议任何注入属性与离线调用同时出现时在配置 Alembic context 前失败，因为离线模式不消费已打开连接，也无法证明执行目标。该建议属于 E3 未明确的边界，见“决策缺口”。

### 现有文件路径与可插桩点

- `alembic/env.py`：Alembic 加载后读取 `context.config`；当前在 `context.configure`、`context.begin_transaction`、`context.run_migrations` 执行实际迁移。这里是在任何 revision 运行前选择连接和放置只读守卫的唯一已确认入口。
- `alembic.ini`：标准脚本位置和默认 URL；`env.py` 当前会覆写 URL。T05 不修改此文件，以免改变标准 CLI 配置契约。
- `alembic/versions/*.py`：正式迁移 revision；不作为测试插桩点，不修改其 upgrade/downgrade。
- `tests/unit/test_alembic_env.py`：拟新增的局部测试文件。测试通过内存 SQLite 同步 Connection 或 mock Alembic context 隔离验证连接选择；禁止调用正式版本脚本执行 DDL。
- `tests/conftest.py`：已有异步 SQLite fixture 通过 `Base.metadata.create_all` 建表，不经过 Alembic；T05 不改共享 fixture，也不把该 fixture 当迁移验证。
- `tests/integration/test_pgvector_real.py`：fixture 会执行 `CREATE EXTENSION`、创建/清空 `vector_chunks` 并调用真实 embedding API，属于破坏性/联网测试；T05 禁止运行。

## 第二层：子模块概述

### A. 配置解析与连接分流

职责：读取 `config.attributes`，区别测试模式、显式连接注入和既有 CLI 默认路径。数据流是 `Config.attributes` → 参数完整性检查 →（测试时）目标守卫 → 同一同步 Connection 进入 Alembic context。测试模式任一必需输入缺失或类型错误，都应在 Engine 建立、连接和迁移前以安全、无秘密异常拒绝。普通 CLI 没有相关 attributes 时继续旧 settings URL 路径。

状态仅在本次 Alembic Config 中生效，不写全局 settings、不缓存跨调用目标。错误信息不得包含 URL、凭证、原始异常中的秘密或连接对象 repr。不得因注入连接检查失败而重试 settings。

### B. 迁移前目标守卫

职责：只用传入同步 Connection 检查真实连接身份，并对照 `rag_test_target` 的记录字段；任一缺字段、实际 database/schema 与声明值不一致、无法判定隔离身份或 SQLite 路径不满足允许条件时，在 `context.run_migrations` 前拒绝。目标字段是描述性目标信息，`resource_record_ref` 不是已经存在的注册表 API。

建议私有接口 `_load_test_target_allowlist(path) -> TargetRegistry`、`_resolve_trusted_test_target(claim, registry) -> TrustedTarget` 和 `_validate_injected_target(connection, trusted_target, sqlite_test_root: Path | None) -> None`：先从独立 allowlist 按 `resource_record_ref` 解出唯一获批记录并比对全部冻结字段，再用同步 Connection 只读读取实际 database/schema 与受信记录对照。PostgreSQL 建议只读查询 `current_database()` 与 `current_schema()`；SQLite 建议读取 `PRAGMA database_list`，文件型目标再将实际路径与受信 root 规范化比较，内存型目标不需要文件根。缺少 allowlist、记录缺失/重复/未批准、业务/基线重合或实际连接不匹配都必须拒绝；四字段 fake mapping 不是可信记录。

### C. Alembic 在线/离线兼容分支

职责：在线注入分支在可信资源解析和连接身份守卫后将同一 `connection` 传给 `context.configure(connection=...)`，沿用 `target_metadata`、事务和 `context.run_migrations`；不得调用 `engine_from_config` 或 `.connect()` 获取第二条迁移连接。只有三个注入键全部缺席时，在线普通 CLI 才保留当前 settings 转换和 `engine_from_config` 路径。离线普通 CLI 保留当前 URL 与 `literal_binds` 行为；任何注入属性与离线模式组合都建议在配置 context 前拒绝，待主控确认。

可能的错误出口为配置属性半缺失、缺连接、缺目标记录/allowlist、非同步/已关闭连接、allowlist 来源不可信/记录不唯一/未批准、目标字段错配、实际身份不匹配、SQLite 文件越界、任何注入属性与离线模式冲突。契约只规定拒绝与 fail-closed，没有冻结异常类或文字；实施中用一个明确的环境配置异常类型或现有 `RuntimeError` 家族承载，不扩展对外 API，异常文案只包含规则类别，不含连接细节。

### D. 局部隔离测试

职责：在新增的单个测试文件中用真实内存 SQLite 同步 Connection 验证连接对象透传；通过 fake/mock `Config.attributes`、settings A 和注入目标 B 验证错误分流及变更前拒绝；拦截 `context.run_migrations` 证明拒绝分支不会触发 migration callback。PostgreSQL SQL 查询分支只能用受控 fake/mock 单测做分支覆盖，不能报告成 PG 验证。

测试 harness 加载 `env.py` 时可能触发 `app.core.database` 的全局异步 Engine 对象构造。需要时只在这个局部测试文件隔离 Alembic context、Base/metadata 或导入副作用；不得改 `app/core/database.py`。验收断言聚焦 Alembic 迁移调用链没有对 settings A 执行 `engine_from_config`/连接/迁移/DDL，而不宣称模块导入从未构造 Engine 对象。

## 第三层：子模块详细实施计划

### 任务 1：建立 Alembic 测试插桩与红灯

**文件写权：** 仅新建 `tests/unit/test_alembic_env.py`。实现阶段该文件是 T05 独占测试文件；不修改共享 fixture。隔离时可使用 `sqlite://` 内存同步连接，所有 Alembic migration callback 均替换为 spy/mock。

**接口与数据：** 测试输入为 Alembic `Config` 的 `attributes`：`rag_test_mode`、`connection`、`rag_test_target`。目标 mapping 暂按冻结字段传递：四项均有值，类型/规范化边界以主控对决策缺口的答复为准。断言观察对象为传入 Connection、`engine_from_config` 调用次数、`context.configure` 参数、`context.run_migrations` 调用次数；不依赖 PG 或 revision 的实际 DDL。

- [ ] 新增 `test_test_mode_without_connection_rejects_before_engine_creation`：测试模式没有 connection 时拒绝；Alembic Engine factory、`connect` 和 `run_migrations` 均为零次调用。
- [ ] 新增 `test_test_mode_without_target_record_rejects_before_engine_creation`：有 connection 而无 `rag_test_target` 时拒绝，不回退 settings。
- [ ] 新增 `test_connection_attribute_none_never_falls_back_to_settings` 与参数化的 `test_partial_injection_attributes_reject`：`connection=None`、仅有 `rag_test_mode` 或仅有 `rag_test_target` 均在 factory/connect/migration 前拒绝。
- [ ] 新增 `test_explicit_connection_without_test_flag_still_uses_injected_path`：显式提供 connection 时必须走注入路径且要求目标记录，不得因 `rag_test_mode` 未设置而改用 settings。
- [ ] 新增 `test_injected_sync_connection_is_forwarded_unchanged`：对有效受控 SQLite 内存目标，`context.configure` 收到对象身份相同的连接，迁移 Engine factory 不调用。
- [ ] 新增 `test_injected_target_mismatch_rejects_before_migration_callback`：实际身份与目标 mapping 不一致时拒绝，`context.run_migrations` 为零次。
- [ ] 首轮红灯命令：`.venv/Scripts/python.exe -m pytest tests/unit/test_alembic_env.py -q -p no:cacheprovider --basetemp .pytest-tmp-t05-red-20261016-01`。预期新测试因当前 `env.py` 不读取 attributes、无目标守卫而失败；不得以导入错误、真实数据库连接或调用 migration revision 作为预期红灯。

### 任务 2：实现显式注入与 fail-closed 配置分流

**文件写权：** 仅修改 `alembic/env.py`。不创建新生产模块、不修改 database settings 或 migration revisions。

**建议内部接口：** `_classify_migration_config(config_attributes) -> bool`，输入 Alembic Config 的 attributes；只有三个冻结注入键 `rag_test_mode`、`connection`、`rag_test_target` 全部缺席时返回 false 并进入普通 CLI 分支。只要出现其中任一键，就必须解析为完整有效注入：`rag_test_mode` 若存在必须是 bool；`connection` 键必须存在且非 None；目标声明必须存在；任一属性残缺、值为 None 或类型非法时抛安全异常，不得回退 settings。此 helper 不认证目标、不返回可供迁移的 Connection。任务 2 阶段完整但尚未验证来源的 claim 也必须 fail closed；任务 3 完成可信解析器后，才允许有效显式连接进入受守卫分支。测试模式 true 缺少任一项时必拒绝。该严格分流是为满足 fail-closed 的执行建议，待主控/用户确认。

**字段与状态：** 不增加公共 Alembic Config attribute。Connection 必须是同步 SQLAlchemy Connection 且可用；AsyncConnection、None、已关闭连接不允许进入显式迁移。普通 CLI 仅在三个冻结注入键全部缺席时使用 settings；若 `connection` 键存在而值为 None、target 单独出现或其他属性残缺，一律在创建迁移 Engine 前拒绝。`rag_test_target` 四字段由后续私有可信资源解析器逐项核验，不从 URL、settings 或 CLI 字符串补默认目标。

- [ ] 先实现配置分类 helper，并确保测试模式缺 connection/record、`connection=None`、只出现部分属性时在 `engine_from_config`、connection 建立和 migration callback 前退出。
- [ ] 对完整但尚未经过可信资源解析器的 injected claim 也暂时拒绝，确保不会在任务 3 前将其误归为普通 CLI。
- [ ] 为三个注入属性全部缺席的普通 CLI 保留当前 settings URL 同步转换和 `engine_from_config`/`connect` 路径，避免改变迁移部署入口。
- [ ] 第二轮仅验证配置分类的选择性绿灯命令：`.venv/Scripts/python.exe -m pytest tests/unit/test_alembic_env.py -k "without_connection or without_target_record or attribute_none or partial_injection" -q -p no:cacheprovider --basetemp .pytest-tmp-t05-config-20261016-02`。预期只有缺/坏属性拒绝用例通过；显式连接透传、目标不匹配、allowlist 与 SQLite 根用例在任务 3 前仍保持未验收，不报告整文件通过。

### 任务 3：实现变更前只读目标身份检查

**文件写权：** 仅修改 `alembic/env.py` 和任务 1 的 `tests/unit/test_alembic_env.py`。

**建议内部接口：** `_resolve_allowlist_path(root_value, path_value, workspace_root, basetemp_root) -> Path`、`_load_test_target_allowlist(path) -> TargetRegistry`、`_resolve_trusted_test_target(claim, registry) -> TrustedTarget` 与 `_validate_injected_target(connection, trusted_target, sqlite_test_root: Path | None) -> None`。前两个输入来自受控进程环境 `RAG_TEST_TARGET_ALLOWLIST_ROOT/PATH`；`_resolve_allowlist_path` 解析规范绝对路径并验证文件在配置 root 内、root/file 均不在工作区或 pytest basetemp、文件对运行身份可读且不可写，返回唯一可信路径或安全拒绝。`_load_test_target_allowlist` 只读解析该文件；`claim` 是 attributes 中不可信的四字段 mapping。解析器按 `resource_record_ref` 查唯一登记项，核对 claim 的四字段完全等于登记值，并确认其用途为隔离迁移测试、登记状态有效且数据库/schema 不与 business/baseline 登记项重合；成功只返回不可变的内部 `TrustedTarget`，找不到记录、重复 ref、状态不符、隔离身份重合或来源缺失时安全拒绝。生产 allowlist 路径绝不从 `rag_test_target` 或任意 CLI 参数读取，无法确认来源/权限则 fail closed。`_validate_injected_target` 再用同步连接只读读取实际身份，与 `TrustedTarget` 逐字段比对；仅文件型 SQLite 目标需要从受控进程环境解析 `RAG_TEST_SQLITE_ROOT`，内存目标传入 `None`。所有 resolver/guard 都必须在 `context.configure` 与 `context.run_migrations` 前完成；不得执行 DDL/DML、清理、metadata.create_all 或连接探测写入。该解析器和三个环境配置名尚未冻结，执行前需确认本计划中的最小推荐格式。

`TargetRegistry` 保存版本值、按唯一 `resource_record_ref` 索引的不可变记录集合，以及全部 `business`/`baseline` 的 `(database_id, schema_name)` 身份集合。不可变 `TrustedTarget` 的字段为四个冻结字段加经校验的 `role`、`status`、`purpose`、`exclusive`。`_resolve_trusted_test_target` 的输入 claim 类型建议为 `Mapping[str, object]`，输出仅可能为该结构或 fail-closed 异常；`_validate_injected_target` 对 PG 比对实际 database/schema 字符串，对 SQLite 比对 schema 与 root 内 canonical file identity，成功返回 `None`、失败不返回可执行迁移连接。

**目标字段：** `target_index_id` 用于绑定受控索引身份，`database_id` 与 `schema_name` 对照连接只读返回的实际身份，`resource_record_ref` 必须存在且作为审计引用保留。不得在日志或公开错误中输出原 URL、密码或目标记录原文。目标字段匹配只能证明连接与调用方提供的记录相符，不能单靠 mapping 宣称资源注册来源已认证。

- [ ] 为缺失/重复/未批准/角色错误的 allowlist 记录、声明与 allowlist 字段不一致、连接 database/schema mismatch 增加拒绝用例；所有拒绝时 `context.run_migrations` 为零次。
- [ ] 新增 `test_allowlist_missing_record_rejects_before_migration`、`test_claim_must_match_allowlist_record`、`test_allowlist_business_or_baseline_collision_rejects`、`test_allowlist_source_outside_trusted_root_rejects`：fake allowlist 可放在 basetemp 并直接测 parser；只有来源路径检查的单测会 monkeypatch workspace/basetemp/trusted-root 边界，把 fake 临时目录设为测试信任锚点。此例外只为隔离单测，生产 `RAG_TEST_TARGET_ALLOWLIST_ROOT/PATH` 仍必须在工作区和 pytest 临时目录外且满足只读 ACL。证据标明 fake 不是正式资源登记。
- [ ] 为 PostgreSQL 身份比较增加 fake Connection 只读分支用例；用例和证据标为 mock，不称真实 PG 迁移通过。
- [ ] 新增 `test_sqlite_file_inside_test_root_passes_readonly_identity_check` 和 `test_sqlite_file_outside_test_root_rejects_before_migration`：通过 `tmp_path_factory.getbasetemp()` 在本轮 basetemp 子目录创建本地文件目标，打开同步连接后只执行 `PRAGMA database_list`；正确目标断言同一连接进入 `context.configure`，并把 `context.run_migrations` 替换为不加载 revision 的惰性 spy；越界目标断言拒绝发生在 `context.configure` 前。不得执行真实 revision 或 DDL；有效分支的 spy 边界调用次数应如实记录，不能误写成零次。
- [ ] 覆盖相对路径、`..` 越界、符号链接越界、`file:` URI、未知 URI 参数、空数据库路径、未存在路径及业务目录文件；只有规范化后处于 `RAG_TEST_SQLITE_ROOT` 内的本地文件或明确支持的标准内存连接才通过。该根由受控测试 launcher 提供，不从 SQLite URL、`rag_test_target` 路径或 CLI 任意参数推导。若 Windows 权限不允许创建 symlink，仍对规范化 helper 输入 canonical root 外路径进行拒绝断言，并将 OS symlink 本身未实测记为限制，不跳过 containment 逻辑测试，也不谎称文件系统 symlink 已验证。
- [ ] 每轮使用新 `--basetemp` 跑任务 1～3 已有用例：`.venv/Scripts/python.exe -m pytest tests/unit/test_alembic_env.py -k "without_connection or without_target_record or attribute_none or partial_injection or injected_sync_connection or injected_target_mismatch or allowlist or sqlite_file" -q -p no:cacheprovider --basetemp .pytest-tmp-t05-guard-20261016-03`。预期当前阶段所有拒绝矩阵与同一连接守卫通过；普通离线/A-B 测试留到任务 4。

### 任务 4：覆盖 A/B、离线分支与普通 CLI 兼容

**文件写权：** 仅修改 `alembic/env.py` 和 `tests/unit/test_alembic_env.py`。settings A、注入 B 均使用测试替身；测试不得连接任何数据库地址。

- [ ] 新增 `test_settings_a_is_not_used_when_connection_b_is_injected`：将 settings URL 配置为 A、attributes Connection 配置为 B，并在 fake allowlist 中将 A 登记为 business、B 登记为独立 approved migration_test；断言 B 以同一对象传入 Alembic，`engine_from_config` 不调用，A 没有迁移 Engine connect/migration/DDL 调用。报告只称“受控调用边界通过”，不称 A/B 两个真实库已证明未变化。
- [ ] 新增 `test_normal_online_cli_without_injection_keeps_settings_factory_path`：无 test mode、无 connection 时断言沿用当前同步 URL 与 `engine_from_config`；不实际建立外部连接或运行 revision。
- [ ] 新增 `test_normal_offline_uses_controlled_settings_url_without_running_revisions`：在执行/加载 `alembic/env.py` 前，将该测试模块的 `settings.database_url` monkeypatch 为 `sqlite+aiosqlite:///:memory:`，配局部 Alembic Config 和受控离线 context，spy `context.configure` 与 `context.run_migrations`；断言配置 URL 为同步 `sqlite:///:memory:`、保留 `literal_binds`/`target_metadata`，migration callback 仅被 spy 捕获、不加载 revision、不连接数据库。
- [ ] 新增 `test_any_injection_attribute_offline_rejects_before_context_configuration`：任一注入键出现（包括完整注入、`connection=None` 或半套 attributes）与离线模式组合均在 `context.configure` 前拒绝；这是本计划的 fail-closed 建议，待主控/用户确认。
- [ ] 运行 `.venv/Scripts/python.exe -m pytest tests/unit/test_alembic_env.py -q -p no:cacheprovider --basetemp .pytest-tmp-t05-final-20261016-04`。预期所有分流、拒绝顺序、受控离线配置和 A/B mock 断言通过；测试输出不得含真实 settings URL、凭证或原始异常内容。

### 任务 5：限定回归、证据和交接

**文件写权：** 代码执行者只修改 `alembic/env.py` 与 `tests/unit/test_alembic_env.py`；T05 证据只写入唯一入口 `docs/rag-work/evidence/t05/2026-10-16-execution.md`。README、plan index、总状态由主控更新。

- [ ] 使用已缓存 Ruff 0.15.7 检查上述两个文件：`C:/Users/A1985/AppData/Local/uv/cache/archive-v0/QcnXSOJpzJovd_JVU2u2H/ruff-0.15.7.data/scripts/ruff.exe check --no-cache alembic/env.py tests/unit/test_alembic_env.py`。不自动安装 Ruff 或修改依赖。
- [ ] 做 Ruff 基线对照：`git show HEAD:alembic/env.py > .pytest-tmp-t05-final-20261016-04/alembic-env-baseline.py`，再运行 `C:/Users/A1985/AppData/Local/uv/cache/archive-v0/QcnXSOJpzJovd_JVU2u2H/ruff-0.15.7.data/scripts/ruff.exe check --no-cache .pytest-tmp-t05-final-20261016-04/alembic-env-baseline.py`；比较基线与改后 `alembic/env.py` 的诊断。新增测试文件没有 HEAD 基线，单独记录检查结果，不声称有历史对照。临时基线副本留在唯一 basetemp，不清理。
- [ ] 运行 `git diff --check`，并逐项核对只有约定两个代码/测试文件及 T05 证据有改动；不得暂存、提交或清理既有临时目录。
- [ ] 证据记录实际命令、退出码、实际通过/失败数量、mock 与 SQLite 内存/本地文件 PRAGMA 验证边界、未加载或执行正式 revision 的事实（若惰性 spy 被 Alembic 调用，记录该边界调用次数）、目标资源真实性限制、allowlist 来源及任何既有 lint 基线问题。不得填入未运行结果。
- [ ] 向主控交接：函数/分支行为、修改文件、测试边界、SQLite 与目标记录决策、真实 PG 尚未执行。T05 通过不等于 T07/G2 通过，不可据此执行正式迁移或真实资源清理。

## 决策缺口与安全建议

冻结 E3 没有定义 `rag_test_target` 的 Python 类型、`resource_record_ref` 权威来源/验证 API，也没有定义 `database_id` 的平台规范。当前仓库未发现资源注册表。仅比对 attributes 的四个自报字段与数据库实际身份，不能证明目标不是业务库或基线库，因此不满足 E3 的非业务/非基线守卫。

**建议的最小私有 allowlist 格式（未冻结，实施前需用户确认）：** 由受控测试 launcher 设置进程环境变量 `RAG_TEST_TARGET_ALLOWLIST_ROOT`（OS 管理的只读目录）和 `RAG_TEST_TARGET_ALLOWLIST_PATH`（其下具体 JSON 文件）。resolver 对两者执行严格绝对路径解析，确认文件在该 root 内、root/file 不在工作区或 pytest basetemp、文件对执行身份可读且不可写；不能从 `Config.attributes`、`resource_record_ref` 或任意 CLI 参数取得路径。文件采用 `schema_version: "rag-test-target-allowlist-v1"` 和 `records` 数组；每条记录至少有 `resource_record_ref`（不透明唯一 ID，不是路径）、`target_index_id`、`database_id`、`schema_name`、`role`（`migration_test`、`business` 或 `baseline`）、`status`。所有 ref 必须唯一且 `status` 为 `approved`；`migration_test` 记录另外必须有 `purpose: "alembic_test"` 和 `exclusive: true`。建议 `database_id` 对 PG 固定等于只读查询得到的 database 名称；SQLite 文件使用在批准 root 下规范化后的绝对文件路径，内存库使用 `:memory:`；schema 使用实际查询值（SQLite 为 `main`）。私有 `_load_test_target_allowlist(path) -> TargetRegistry` 只读并校验版本/字段/唯一 ref；`_resolve_trusted_test_target(claim, registry) -> TrustedTarget` 用 ref 查唯一获批记录、精确比对四个冻结字段、确认 test 角色/用途/排他状态，并拒绝与 registry 中任一 business/baseline 的 database/schema 相同。缺少任一 allowlist 环境配置、路径不受信、JSON 非法、重复/未知 ref、字段错配、目标未批准或与业务/基线重合，一律在 `context.configure` 前 fail closed；`RAG_TEST_SQLITE_ROOT` 仅对文件型 SQLite 目标必需，内存 SQLite 用已批准的 `:memory:` 记录和空 database_list 文件路径进行核对，不需要文件根。`TrustedTarget` 是 env.py 内部不可变结构，不扩展共享契约。

这个 allowlist 是建议的新私有测试资源格式，不是仓库中已有的注册机制，也不是冻结 spec 已批准的接口。外部资源拥有者应在受控位置维护它；T05 的单测可用临时 fake allowlist 验证解析拒绝矩阵，但必须标作 fake，不能当真实登记或真实 A/B 证据。若用户不批准该格式，主控须指定另一独立权威查询来源；不得退回四字段自报即可迁移。T07 只有接入 T01 盘点后实际受控的资源记录，才能验证登记文件/查询是否真实、business/baseline 是否完整。

**SQLite 文件路径建议（未冻结，实施前需用户确认）：** 新增私有进程环境配置 `RAG_TEST_SQLITE_ROOT`，只允许由受控测试 launcher 从该轮唯一 `pytest --basetemp` 设置；不得从连接 URL、`rag_test_target` 或 CLI 输入推导根。pytest 单测通过 `tmp_path_factory.getbasetemp()` 设置该值，测试数据库必须建在 basetemp 的子目录；每轮使用新目录且不清理。文件型目标的 guard 先将 root `resolve(strict=True)` 并要求是目录，再只读执行连接上的 `PRAGMA database_list`。`database_id` 若为相对路径，只相对 root 解析；绝对路径必须解析到 root 内。路径在 `Path.resolve(strict=True)` 后用 `commonpath`/`is_relative_to` 检查 containment，以涵盖 `..` 与 symlink；拒绝 `file:` URI、query/fragment、未知 URI 参数、NUL、空路径和不存在文件。文件连接的实际路径必须与 allowlist 路径规范化后相等，schema 必须为 `main`。标准内存连接仅在 `PRAGMA database_list` 文件路径为空且 SQLAlchemy URL 明确为内存形式时接受，`database_id` 使用建议哨兵 `:memory:`，不要求文件根。`RAG_TEST_SQLITE_ROOT`、`RAG_TEST_TARGET_ALLOWLIST_ROOT/PATH` 都是新私有启动配置而非冻结接口；无 allowlist 配置、文件目标缺少 SQLite 根、格式不明或越界时拒绝。

路径验证用例应包含 pytest basetemp 下的真实临时 SQLite 文件：建立已打开同步连接，只运行只读 `PRAGMA database_list`；有效目标确认同一连接进入配置并由惰性 `context.run_migrations` spy 截断，越界目标在配置前拒绝。spy 若被调用，记录调用次数，但不得执行它代表的正式 revision。另覆盖相对路径、绝对路径、`..` 越界、符号链接越界、`file:` URI、未知参数、空/不存在路径、工作区业务文件，以及 `:memory:` 哨兵。不得在这些用例调用 Alembic revision 或执行 DDL。只在 `Config.attributes` 三个注入键全部缺席时才走旧 CLI settings 分支；出现任一注入键但值为 None/缺项/类型错误均 fail closed。特别是显式 `connection=None`、只有 target 声明或只有 `rag_test_mode` 的半套 attributes 不得回退 settings。任何注入属性与离线模式组合都建议在 `context.configure` 前拒绝；仅完全没有注入键的普通离线 SQL 回归可继续走旧 settings 路径。

## 派发门与验收边界

当前 `env.py` 已有 `run_migrations_offline()`、`run_migrations_online()` 及模块末尾按 `context.is_offline_mode()` 的分派；计划不新增对外 CLI 参数或改 revision。T05 可在 T01 尚未完成时实现局部代码和 fake/内存离线验证，但真实资源记录来源仍是待决策项。T07 必须等待 T01、G1 与主控复核，使用独立登记资源执行真实 PG 迁移；本计划和 fake A/B 用例均不解锁真实运行。

## 主窗口文档复核状态

已完成一轮定向修订与主窗口复读，具体发现、关闭说明及实施前待确认设计见[第二批计划审阅记录](2026-10-16-second-wave-plan-review.md)。当前仍为待用户确认的计划，未开始实现或运行测试。

## 2026-10-17 最新正式审阅状态

**需修订，暂不派发实现。** [正式审阅问题与修订顺序](2026-10-17-second-wave-plan-review.md)更新本计划先前初读状态；当前未处理的问题须定向修订并复核关闭，再确认计划。此次仅追加审阅状态，未代为修改设计或实施。
