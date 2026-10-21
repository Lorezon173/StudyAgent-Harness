# Docker 方案 A 具体执行计划

> **执行代理要求：** 使用 `superpowers:subagent-driven-development`，逐任务实施并由独立代理复核。下面复选框记录完成状态，未勾选不能解释为已通过。

**目标：** 修复镜像迁移目录交付和同步数据库驱动，建立可复现的镜像、迁移、认证与会话验收，再为镜像发布增加门禁。

**架构：** 保留 frontend → backend → runtime 三阶段构建；backend 明确交付配置文件和迁移目录。应用继续使用异步数据库驱动，Alembic 单独选择同步驱动。验收使用隔离容器和测试数据，发布复用经过验收的镜像产物。

**技术栈：** Python 3.11 镜像、uv、SQLAlchemy 2、Alembic、psycopg 3、SQLite、PostgreSQL/pgvector、Docker Compose、GitHub Actions。

**设计依据：** [原始三层规划](../../../superpowers/docker-deployment-next-step-raw.md)；[故障报告](../../delivery/2026-10-20-docker-investigation.md)；[三层方案说明](../../delivery/2026-10-20-docker-next-step-plan.md)。用户已确认方案 A，本文件把它展开为执行步骤；详细实施部分只写文字契约与命令，不预先给出实现代码。

**修订 v2（2026-10-21）：** 根据[独立审查](../../delivery/2026-10-21-docker-execution-plan-review.md)处理发布门禁歧义、验收阶段冲突和 JWT 配置缺口。正式推送采用原始规划的严格口径：真实教学或持久化未通过时，只允许保留候选归档，不更新任何 GHCR 标签。

**实施进度：** 已按用户后续授权完成核心修复、四阶段验收入口和工作流门禁实现，默认回归 677 项通过、固定 Ruff 全仓零诊断；代码独立复核发现均已修复。Docker Desktop 后端启动失败，实际镜像、PG 容器、真实教学和远端 Actions 尚未验收，整体交付不能标为完成。详细矩阵见[实施结果](../../delivery/2026-10-21-docker-implementation-result.md)。下面起点和未勾选步骤保留执行前基线；实际通过情况以结果矩阵为准。

## 当前起点与执行范围

- 基准提交：`433b33695436647fe2bfec441ab49d7ec8268e1a`，包含 Ruff 修复和 README 补正。
- 独立工作区：`C:/Users/A1985/.codex/worktrees/mvp-cicd/StudyAgent-Harness`；已创建分支 `codex/docker-deployment-fix`，保留 `codex/ruff-main-baseline`。
- 本次规划前已启动准备工作：新增 `tests/test_migration_database_url.py` 草稿；没有修改 Dockerfile、生产 Python 模块、迁移或工作流。该草稿尚未完成红绿验收，必须先审查再复用。
- 已执行 `docker desktop start --detach`，命令返回启动成功；后续引擎连接检查未取得结果并已终止等待。不能据此判定 Server 可用。没有启动数据库、构建镜像或部署。
- 本轮交付为执行计划；恢复编码从任务 0 开始。沿用用户偏好的子代理实施、主会话审阅。

## 全局约束

- 不重写远端 main，不改已有 Ruff 提交，不在 feature-rag 工作目录实施业务变更。
- 只修确定问题；不删除 RAG extra、pgvector 或已有迁移，不修改教学策略和业务 API。
- 不通过 ORM `create_all`、`stamp head`、跳过迁移或空目录掩盖故障。
- 不直接编辑历史 init 来修复存量库；异常存量样本要先记录 schema、revision 和数据。
- 测试库、网络、容器名称必须带本次验收唯一前缀；不使用已有 `pgdata`，不执行针对现有项目的 `down -v`。
- 数据库凭据、模型密钥只从环境传入；证据及错误信息脱敏。模型调用需要测试配置，不能自动使用不明生产凭据。
- 隔离容器使用每次生成的专用 JWT 测试密钥；正式部署必须确认有效密钥非空且不是公开开发默认值。检查结果只保存布尔值，不保存密钥或其可复用表示。
- 耗时命令约每 30 秒检查进度，不用 sleep；连接失败与测试失败分别记录。
- 新增依赖非预定事项；沿用 uv.lock。安装前先核对已有环境，不顺手升级工具。
- 本地提交按明确路径暂存，不 amend。推送、合并、GHCR 发布及服务器切换作为后续明确交付动作，不以本计划交付冒充已执行。

## 复核重点

1. 百分号、编码密码、重复查询参数不得在 URL 转换或 Alembic ConfigParser 中损坏，由任务 1 验证。
2. 宿主目录存在不能证明最终镜像资源存在，由任务 2、3 验证跨 stage 与 runtime。
3. 空库成功不能证明存量升级安全，由任务 4 分样本验证。
4. `/health` 成功不能证明教学和持久化成功，由任务 5 单独验收。
5. CI 通过后重新构建一个不同镜像，不能称为发布同一已验收产物，由任务 6 绑定 image ID、归档及 registry digest。

## 第一层：模块总览

本次包含镜像资源交付、同步 URL 转换、隔离验收、镜像发布门禁四个部分。前三者先本机验证，再进入 Linux CI；发布门禁依赖验收结果。服务器配置未知，服务器上线属于本地交付之后的环境阶段，不能提前填写服务器地址、数据卷或成功结论。

## 第二层：子模块职责与接口

| 部分 | 输入 → 输出 | 状态与失败处理 |
|---|---|---|
| 资源交付 | 仓库 ini、alembic/、前端构建结果 → runtime 完整文件集 | 缺文件即失败；不重试缓存掩盖路径错误 |
| 同步 URL | 应用 URL 字符串 → SQLAlchemy URL 对象 → Alembic 字符串配置 | 只改 drivername；异常脱敏；不创建数据库连接 |
| 验收入口 | 候选镜像、隔离环境、阶段参数 → JSON 结果与脱敏日志 | structure、migration、api-auth、api-teaching 独立记录；all 聚合所有必要项 |
| 发布门禁 | 同 SHA 的软件检查与四阶段验收 → 被验收的镜像归档/推送产物 | 失败、阻塞、未执行、证据缺失均拒绝正式推送；服务器另需上线验收 |

## 发布决策表

| 动作 | 必要条件 | 缺模型配置时 |
|---|---|---|
| PR 技术检查通过 | Ruff、默认回归、structure、migration、api-auth 均通过 | 可以通过技术检查，但 api-teaching 明确未执行，不能宣称整体业务通过 |
| 保存候选镜像归档 | 上述技术检查通过，源码 SHA、image ID、归档校验和齐全 | 允许保存在 Actions artifact；不推 GHCR，不更新 latest、sha 或其他标签 |
| 正式镜像推送 | 同一候选的全部技术检查和 api-teaching 通过，含会话重启持久化与跨用户隔离 | 阻塞；凭据缺失、跳过或无结果都不能放行 |
| 服务器切换 | 已发布的同一 registry digest，加服务器配置、恢复与业务复验通过 | 不切换，保留当前运行环境 |

候选归档只是验收输入。使用候选标签、手工批准或重复构建均不能替代正式业务门禁。

## 第三层：详细执行任务

### 任务 0：恢复现场与验证引擎

**涉及文件：** 只读 Git 状态和已有测试草稿；记录至 `artifacts/docker/<run-id>/`。该证据目录加入 `.gitignore`，不进入镜像上下文。

- [ ] 记录分支、HEAD、工作区 diff，确认只有本任务遗留的测试草稿。
- [ ] 审查草稿与任务 1 契约一致，避免重复新增第二套 URL 测试。
- [ ] 检查 `docker version`、Docker context 和 Desktop 状态，记录 Client/Server。启动命令返回成功不作为验收通过。
- [ ] 若 Server 不可连接，保留具体错误；继续不依赖 Docker 的 URL 修复和单元回归，任务 2–5 标记环境阻塞，不伪造构建结论。
- [ ] 明确本次不接触已有数据库和业务容器；清理只允许依据本次创建资源的明确名称。

**完成条件：** 工作区状态可解释，引擎可用性有真实结果；没有“等待中”被误记成成功。

### 任务 1：统一迁移同步 URL，先红后绿

**文件：** 新建 `app/core/database_url.py`；修改 `alembic/env.py`；完善 `tests/test_migration_database_url.py`。

**函数契约：** `build_sync_database_url(database_url: str) -> sqlalchemy.engine.URL`。它只解析和转换，不读环境、不连接数据库。局部字段为 parsed_url、backend_name、sync_url；返回 URL 对象，保留结构字段；最终字符串只由 Alembic 接入处生成。这是原始方案字符串输出的细化：先保留结构，避免转换过程中反复编码。

- [ ] 测试 PostgreSQL 的 asyncpg、裸 URL、显式 psycopg 均得到 `postgresql+psycopg`；加载得到同步 psycopg DBAPI。
- [ ] 测试 aiosqlite、同步 SQLite、相对路径、绝对路径和内存库均保留数据库位置，使用同步 sqlite 驱动。
- [ ] 测试编码用户名、密码中的 `@`、`%`、`/`，端口、查询参数及重复查询参数逐项保留。
- [ ] 测试 env.py 的真实接入：Alembic 配置写入后读回 URL，密码不是 `***`，百分号未触发插值错误，驱动正确。
- [ ] 测试不支持的后端返回明确错误且不包含凭据；现有支持范围限 PostgreSQL/SQLite，不默默支持其他数据库。
- [ ] 执行 `.venv/Scripts/python.exe -m pytest tests/test_migration_database_url.py -v`，记录因原有驱动/转义问题失败的红色证据。
- [ ] 实现纯函数；env.py 调用它，使用显式保留密码的序列化，写入 ConfigParser 前转义百分号，保留 offline/online 原职责。
- [ ] 重跑定向测试，再运行 Ruff 统一收集器；无预期外失败后完成该任务。

**失败回溯：** 函数测试失败查解析/drivername；配置读回失败查序列化与 `%`；驱动加载失败查实际依赖环境，不混成数据库网络失败。

### 任务 2：修正 COPY 并形成真实负例/正例

**文件：** 修改 `Dockerfile`；临时 scratch Dockerfile 放验收证据目录，不进入生产镜像。

- [ ] 用原多源 COPY 生成最小负例，真实 Docker 构建应在读取 `/app/alembic` 时失败。
- [ ] 单独验证原布局的 `/app/env.py`、`/app/versions` 可被复制，证明平铺落点；此阶段无需基础镜像或业务数据库。
- [ ] backend 分别交付 `alembic.ini` 到 `/app/alembic.ini`、完整 `alembic/` 到 `/app/alembic/`。
- [ ] 保留 runtime 原消费路径；不改 `script_location`，不删除迁移 CMD。
- [ ] 同一个最小构建换成修复后的生产布局，正例通过，并保留退出码和日志。

**完成条件：** 原因明确的负例失败、平铺证明成功、修后正例成功；未运行 Docker 时不得勾选。

### 任务 3：完整镜像与运行资源验收

**文件：** 新建 `scripts/verify_docker_image.py`；更新 `.gitignore`、`.dockerignore` 排除本次证据目录。

**入口契约：** 命令行参数 `--image`、`--phase structure|migration|api-auth|api-teaching|all`、`--output`。本任务实现 structure，任务 4 实现 migration，任务 5 实现两个 API 阶段及 all 聚合。manifest 包含 source_sha、dirty、source_diff_hash、image_id、phase、required_checks、checks、status、exit_code、timestamp、log_path；每个 check 独立记录名称、状态和脱敏原因。没有 registry digest 时留空，不拿本地 image ID 冒充 registry digest。

**状态契约：** passed 返回 0，failed 返回 1，blocked 返回 2，not_run 返回 3。单阶段只表示该阶段的结果；api-auth=passed 不能改写 api-teaching 的 blocked/not_run。all 必须消费同一 source_sha/image_id 的完整阶段结果，缺失项按 not_run，优先级 failed > blocked > not_run > passed。必要项出现任何非 passed 时，整体非零。正式发布拒绝 dirty=true、身份不符或缺项的结果。

- [ ] 为资源检查失败和 Docker 不可用的退出状态增加定向测试：未知/阻塞返回非零，不能视作通过；不编写镜像布局字符串快照测试。
- [ ] 真实构建完整镜像，使用唯一候选标签，记录前端 npm 构建、uv 安装和最终 image ID。
- [ ] 覆盖 entrypoint/CMD，断网检查 ini、env.py、script.py.mako、versions 和 `web/dist/index.html`。
- [ ] 运行 `alembic heads`，确认唯一 head，并检查 psycopg 可导入；只做迁移图检查，不宣称数据库已升级。
- [ ] 检查非 root UID、工作目录及应用导入；确认源仓库 Docker 修复和测试证据没有误打包。

**完成条件：** 完整构建和 runtime 检查都通过，同一候选镜像有可追溯 ID。失败时按前端、依赖、COPY、权限、导入分类，不一次改多个无关问题。

### 任务 4：隔离数据库迁移和数据保留

**文件：** 扩展 `scripts/verify_docker_image.py` migration 分支；新建 `tests/integration/test_migration_upgrade.py`，明确 integration 标记。

**数据与状态：** 每轮新建带唯一前缀的网络和 PostgreSQL/pgvector 测试容器；临时存储与现有 pgdata 隔离。使用固定的非生产测试身份，日志不打印 URL。结束时只清理本轮明确创建的容器/网络。

- [ ] 隔离空 PG 库运行候选镜像 `alembic upgrade head`，检查 revision、核心表、mastery 类型/外键、vector_chunks 和 chunk_id。
- [ ] 再次运行 upgrade head，确认无额外升级且已有记录保持。
- [ ] 创建代表性旧 revision 样本，插入合法用户、会话、消息和 mastery 数据；升级后逐项核对标识、数量、内容和约束。
- [ ] 独立准备缺 mastery 表、非数字 user_id、孤儿外键的异常副本；预期阻止升级并记录具体问题，不能默认这些样本可以自动修好。
- [ ] 对临时 SQLite 文件跑适用迁移与已有回归；若发现迁移本身兼容缺陷，单独定位和设计，不以 URL 转换通过替代迁移通过。
- [ ] 遇到需要新增向前迁移的确定问题，记录新任务及数据处置设计后处理，不回写历史迁移冒充存量修复。

**完成条件：** 空库和合法存量升级通过、数据保留；异常样本有可解释失败。真实业务库存量状态仍需后续盘点。

### 任务 5：认证、教学、会话保存分层验收

**文件：** 扩展验收脚本 api-auth、api-teaching 和 all 分支；修改 `docker-compose.yml`、`.env.example` 的配置透传及说明；优先复用 `tests/unit/api/test_auth_jwt.py`、`test_chat_persist.py`、`test_chat_session_ownership.py` 和 `test_sessions_api.py`。

**配置前置检查：** Compose 明确透传 JWT_SECRET_KEY 和 RAG_BACKEND；根据实际调用链透传必要的 embedding/模型配置，不在镜像内写入秘密。api-auth、api-teaching 和服务器预检均检查运行容器的有效 JWT 密钥非空且不等于 `dev-secret-change-me-in-production`，不满足则拒绝验收。隔离测试使用每轮生成的专用随机密钥，证据只记录检查是否通过。配置调整不得因全局变量插值强制检查而破坏默认只启动 db 的用法；真实教学另要求 pgvector/PostgreSQL 和有效测试模型配置。

- [ ] 先写验收脚本定向测试：auth 通过、teaching 缺配置时，两阶段分别为 passed 和 blocked，all 非零；auth 失败必须保留 failed，不能被另一阶段覆盖。
- [ ] 测试空 JWT、公开默认 JWT 均被有效配置预检拒绝，随机测试密钥可通过；测试和失败日志不得泄漏密钥。
- [ ] 测试 all 对缺项、候选镜像身份不一致及 dirty 结果拒绝放行；默认 db-only Compose 用法不因新配置要求失败。
- [ ] api-auth：候选容器启动后检查 `/health` 和前端入口；通过 `/api/auth/register` 建测试用户，再用 `/api/auth/login` 取得 token；错误密码返回 401。此阶段不调用真实模型，也不声称教学或会话保存已通过。
- [ ] api-teaching：使用同一候选镜像和隔离数据库，独立建立测试身份，请求 `/api/chat`，字段使用 `message`、唯一 `session_id`；检查回复、`persisted=true` 和 session 标识。
- [ ] api-teaching：用 `/api/sessions/{session_id}` 与 `/api/sessions/{session_id}/messages` 验证保存的真实内容，再重启仅应用容器并复查。
- [ ] api-teaching：验证另一用户无法读取或写入该会话；不把内存 mock 的单元结果称作候选镜像真实持久化通过。

**已核实的前置缺口：** 当前 `/api/chat` 调用 `run_online_agent_session`，assembly 要求 `rag_backend=pgvector` 和 PostgreSQL；配置默认是 fake，而 Compose 未传入 RAG_BACKEND。原样启动后不能预设普通教学一定可用。执行时先确认环境配置透传，再明确所需 embedding/检索配置；不为了让部署检查通过而静默回退 fake 或改在线教学架构。若需补 Compose 参数，作为有证据的配置修补单独提交，保持应用行为不变。

**外部模型边界：** 请求执行 api-teaching 但缺真实模型/embedding 测试配置时标记 blocked；PR 没有请求该阶段则标记 not_run。已有 mock 回归为独立证据，不能以 health、认证或 mock 替代真实教学。任何一种非通过状态都阻止正式镜像推送及服务器切换。

### 任务 6：把同一候选镜像验收接入 CI 和发布门禁

**文件：** 修改 `.github/workflows/ci.yml`、`.github/workflows/release.yml`；复用验收脚本，不复制第二套检查逻辑。

- [ ] CI 保留 PR、main push，增加 workflow_call，使 Release 可以调用同一检查；保留已固定的 Ruff 和 locked 安装入口。
- [ ] Docker job 构建候选镜像，执行 structure、migration、api-auth；PR 不获取模型秘密，明确记录 api-teaching=not_run。技术检查的 required_checks 只包含技术项，其通过不能当作 all 通过。
- [ ] 任一必要步骤失败，job 失败；always 上传脱敏日志，不使用 continue-on-error 放行。
- [ ] 将通过技术检查的候选镜像保存为镜像归档，记录 image ID、当前 workflow 实际 checkout SHA 和归档校验和；输出唯一 artifact 名，限制保存期限。不混用 PR head SHA 与 merge checkout SHA。
- [ ] Release 增加 validate job 调用 CI；新增独立 business-gate job，在可信 main/tag 运行中下载并核验同一候选归档，load 后执行 api-teaching，并生成 all 的正式门禁结果。
- [ ] business-gate 使用专用受保护测试环境的模型/embedding 配置、随机 JWT 测试密钥和隔离数据库；fork/PR 不获得秘密。环境未配置、缺凭据、业务失败或审批未完成均不得运行 push job；环境审批本身不能替代业务测试。
- [ ] 发布 job 同时依赖 validate 和 business-gate 成功，核对其 source_sha、image_id、归档校验和与 all 必要检查结果；任一身份不一致、记录缺失、非 passed 或 dirty=true 都拒绝发布。下载并 load 同一归档后核对 image ID，才打 GHCR 标签和推送，不重新构建。
- [ ] 记录 registry 返回的 digest 与标签映射；源码 SHA、镜像 ID、归档校验和和 registry digest 分字段保存。
- [ ] 检查 PR 场景无 packages 写权限；Release 只有推送 job 获 packages:write。用失败教学、缺配置、缺证据、候选身份不符四种场景验证 GHCR 推送不会执行；缺模型配置时允许保留归档，但不更新任何镜像标签。

**完成条件：** 工作流配置复核通过；真实 Actions 运行才可认定远端门禁通过。功能分支普通 push 不能替代 PR 触发验证。镜像发布通过不代表服务器业务上线已验收。

### 任务 7：最终回归、审阅和交付

**文件：** 本工作区根 README；新增 `docs/delivery/2026-10-21-docker-implementation-result.md`，记录本次范围和真实结果。

- [ ] 运行完整现有默认 pytest 命令，逐项记录 pass/skip/deselect；新增 integration 另跑，缺依赖不能算通过。
- [ ] 运行 `python scripts/ruff_baseline.py --output artifacts/ruff/docker-final`，要求零诊断；核对 uv.lock 无意外变化。
- [ ] 独立代码复核覆盖 Dockerfile、URL 安全保真、测试真实性、迁移、资源清理、发布产物一致性。
- [ ] 更新 README 使用方式和状态，明确通过、失败、环境阻塞、未执行；修订 HTML 中对应状态时仍保留历史失败事实。
- [ ] 根据实际完成的任务分批本地提交，只暂存明确文件；不把临时日志、测试凭据和不相关主工作区文档混入。
- [ ] 向用户交付提交清单、验收矩阵、剩余阻塞。推送、PR、合并和正式发布按当时授权执行，不自动改 main。

## 后续服务器阶段与停止条件

本计划不填写不存在的服务器配置。服务器阶段先只读确认地址、Docker/Compose、网络端口、数据库版本、现有数据卷、配置和备份；还须检查运行容器有效 JWT 密钥非空且不同于公开默认值，只记录布尔结果。使用任务 6 的同一 registry digest，而不是服务器重新 build；复跑健康、认证、教学、持久化并验证上一兼容镜像恢复。涉及不可逆数据库变更时先确认恢复策略，不能简单把镜像回滚等同于 schema 回滚。

引擎不可用时只推进无 Docker 的修复与验证；真实库样本不兼容时停止该样本；模型配置缺失时阻塞真实教学、正式镜像推送及服务器切换，仅可保留已通过技术检查的候选归档；JWT 不满足前置要求时拒绝 API 验收及部署；服务器信息缺失时停止服务器阶段。每种情况都记录原因，不能把整条链路写成完成。

## 建议提交边界和完成矩阵

| 顺序 | 可独立审阅的交付 | 通过证据 |
|---|---|---|
| 1 | Docker COPY + URL转换 + 回归测试 | URL红绿、真实COPY负例/正例、完整镜像 |
| 2 | 隔离迁移与容器验收入口 | 空库/存量/认证、资源清理和数据保留 |
| 3 | CI/Release门禁 | 工作流审阅、同一归档镜像、Actions真实运行 |
| 4 | README与交付结果 | 事实状态与证据链接一致 |

计划自检：方案 A 的目录、驱动、SQLite、五层验收均有对应任务；新增的教学配置前置缺口来自真实代码，不将其擅自扩展为 RAG 架构重写。执行以任务间接口和完成条件为准，不以预计耗时或测试数量代替结果。
