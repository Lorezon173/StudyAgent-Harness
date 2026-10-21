# Docker 下一步决策与三层实施计划（待确认）

2026-10-21 更新：方案 A 已获用户确认；用户最新要求先编写具体执行计划，见 [Docker 修复执行计划](../superpowers/plans/2026-10-21-docker-deployment-fix.md)。下文待确认和未授权表述属于 10 月 20 日快照；当前实际进度以执行计划为准。

日期：2026-10-20。本文是方案交付，**尚未授权 Docker 修复编码、启动服务、容器验证或部署**。目标为现有单机 Docker 路线：先本机验证，再迁移到服务器。README 由主会话统一维护。

## 一页总结

推荐选择 **A：修正迁移文件复制目录，同时显式统一 Alembic 的 PostgreSQL 同步驱动**。目录修复解决已经发生的构建故障；驱动修复处理代码和依赖之间已经核实的契约不一致，但不能将其描述成已发生的容器运行故障。

现有 Dockerfile backend 第25行将目录内容复制到 /app，runtime 第38行却读取 /app/alembic。两次真实 Release 日志均在该跨阶段 COPY 失败。上下文、ignore、Compose 挂载均不能解释或修复这一阶段的路径缺失。不要删消费者 COPY、建空目录、改尾斜杠、清缓存或跳过迁移来掩盖问题。

本轮只读重核独立工作树 C:/Users/A1985/.codex/worktrees/mvp-cicd/StudyAgent-Harness，读取时 HEAD 为 6324b9442b6f1671ccb4a19cdacb42bb91597187，分支上的 Ruff 修改尚未提交；后续执行必须重新记录提交 SHA，不能将本文读取时版本当作最终发布版本。Dockerfile、Compose、ignore、Release 无工作区差异；env.py 仅有 Ruff 导入与注释整理，URL 裸化仍在。

主会话提交后补核：Ruff 提交为 `5162bceb4af32de303aba045e569fa1bd70b3365`，工作区干净。与 `6324b94` 比较，Dockerfile、Compose、ignore、Release 与 uv.lock 均无差异，env.py 只有导入/注释整理；本报告目录与驱动结论仍适用。推送两次因 TLS 失败，未发布到远端或触发新 CI。

随后仅 README 补正产生最新 HEAD `433b33695436647fe2bfec441ab49d7ec8268e1a`，不涉及 Docker 代码。提交后验证记录见 [Ruff 后续验证](2026-10-20-ruff-post-commit-verification.md)。

本轮 docker version 仍只有 Client 29.3.1，desktop-linux 缺失 dockerDesktopLinuxEngine 命名管道，无 Server。因此本机真实构建仍受环境阻塞；没有启动 Docker Desktop、服务、容器或数据库，没有执行新 build，也没有新增已证实的容器启动错误。

## 失败阶段与事实依据

| 阶段 | 已知事实 | 结论边界 |
|---|---|---|
| 历史 Release 构建 | 33612200695 日志1082-1083行 backend COPY DONE；1108-1109行 runtime COPY /app/alembic 报 not found；30810152932 同样失败 | 已发生，直接根因是生产者/消费者目录契约不一致 |
| 构建上下文 | Release 显式 context 为仓库根；ignore 未排除 ini/迁移目录；backend COPY 成功 | 不是已证明的漏 checkout 或 ignore 排除 |
| 依赖与前端 | uv sync 曾 DONE；其他节点 CANCELED | 不能据取消推断前端另有故障或完整镜像通过 |
| 容器启动 | CMD 先 upgrade head 后启动 uvicorn；此前镜像构建已失败 | 历史失败尚未进入此阶段 |
| 驱动 | Compose 输入 postgresql+asyncpg；env.py 删除后缀；依赖/锁安装 psycopg、psycopg-binary，无 psycopg2 锁条目 | 配置不一致已核实；镜像中异常尚未实测 |
| 数据迁移 | init 已建 mastery_nodes/mastery_edges；当前迁移链终点静态读取为 20260729_chunk_id | 不能再称6324b94空库必然缺 mastery 表；迁移链实际执行未验证 |
| 本机环境 | 本轮 docker version 命名管道不存在 | 环境阻塞仍在，不能声明修复或部署完成 |

历史原日志与完整回溯见 [故障专项调查](2026-10-20-docker-investigation.md)。[Release 33612200695](https://github.com/Lorezon173/StudyAgent-Harness/actions/runs/33612200695/job/100189728538) 与 [30810152932](https://github.com/Lorezon173/StudyAgent-Harness/actions/runs/30810152932) 是既有真实构建证据。

目录源复制内容、跨阶段绝对源路径的解释沿用旧报告核验的 [Docker COPY 官方规则](https://docs.docker.com/reference/dockerfile/#copying-from-the-build-context)；裸 PostgreSQL 与 psycopg 显式驱动选择沿用旧报告的 SQLAlchemy 2.0.49 无库解析实测及 [SQLAlchemy psycopg 官方文档](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#psycopg)。本文没有声称新联网核验。

## 方案选择

| 方案 | 做法 | 优点 | 代价和适用边界 |
|---|---|---|---|
| A（推荐） | backend 分别交付 ini 与完整 alembic 目录，runtime 保持现有路径；同步驱动显式选 psycopg | 最小变更，保留现有三阶段构建和启动契约；容易独立验证 | 需要真实最小及全镜像验证 |
| B | runtime 直接从 context 分别复制配置和迁移目录；backend 删除不再需要的迁移复制 | 最终消费者直接接收资源，构建职责清楚 | 改动面稍大，需要重新明确 backend 是否仍需要迁移资源；驱动问题仍须独立修复 |
| C | 引入专门 migrations stage 统一交付迁移资源 | 多镜像共用迁移包时边界明确 | 当前单应用增加阶段和维护成本，收益不足；驱动问题仍须独立修复 |

不推荐整仓 COPY、平铺后搬回或修改所有消费者接受平铺；这些会扩大输入或变更范围。A/B/C 选择一个，不叠加。

驱动策略：应用连接继续保留 asyncpg；迁移同步连接用 SQLAlchemy make_url 解析 URL，对 PostgreSQL 显式 set drivername 为 postgresql+psycopg，对 SQLite 显式转为同步 sqlite，其他数据库不擅自套 PostgreSQL 规则。使用结构化 URL，保留用户名、密码、主机、端口、数据库和查询参数；输出给 Alembic 时须验证密码不被默认隐藏，并检查 ConfigParser 对百分号的处理。日志不得输出凭据。替代选择是显式安装 psycopg2，但会增加一套 PostgreSQL 同步驱动，当前锁已有 psycopg，故不推荐。SQLite 回归必须保留。

## 第一层：模块总览

目标：使现有单机部署路径能够构建、迁移、启动并支持登录、普通教学和会话持久化；以提交 SHA 与镜像 digest 串联证据。

边界：本轮拟修复 Docker 迁移目录和 Alembic 同步 URL；只在验证发现确定问题时提出附加修复。保留 React/Vite 前端、Python 3.11、uv、FastAPI、PostgreSQL/pgvector 与现有迁移架构。无业务 API 或教学策略改造。

依赖：可连接的 Docker Linux daemon、现有锁文件、基础镜像/依赖可获取、隔离数据库、测试账号和可用模型配置。RAG extra、pgvector 和迁移中的向量表属于现有依赖；本轮不以“普通教学冒烟”为由移除 rag extra，不改变 RAG 功能范围，也不宣称完成 RAG 隔离。RAG 专项功能验收另行定义。

衔接：保持 backend → runtime 的 /app 路径契约，Compose 的 db healthy → app 迁移 → uvicorn 顺序，先本机再服务器。发布门禁设计与独立 Ruff 提交区分，只有用户确认后才修改 workflow。

## 第二层：子模块概述

| 子模块 | 职责和接口契约 | 数据流与状态 | 错误处理 |
|---|---|---|---|
| 镜像资源交付 | runtime 必须包含 ini、env.py、versions、模板及前端 dist | checkout/context → backend/frontend → runtime；产物用 SHA/digest 标识 | 缺资源立即构建/验收失败，不跳过迁移 |
| 同步迁移 URL | settings.database_url 输入，输出匹配已安装同步 DBAPI 的 URL | 不修改应用异步 URL；转换无数据库副作用 | 无效 URL/驱动加载失败应保留具体错误且隐藏凭据 |
| 数据迁移兼容 | 空库与代表性存量库都到唯一 head，保留数据与约束 | 版本号+schema+行数/样本作为前后快照 | 不改历史 init 冒充存量升级；发现旧库缺表先出向前修复方案 |
| 业务验收与发布 | 证明健康、认证、教学、持久化来自同一镜像 | 本机隔离环境 → SHA镜像 → 服务器候选 →正式切换 | 任一门禁失败停止发布，保留日志与旧镜像；不删除持久卷 |

## 第三层：子模块详细实施计划（文字设计，无代码）

### 1. 镜像资源交付

无需新增业务函数。调整 Dockerfile 的两项复制操作：配置文件输入 alembic.ini，输出 /app/alembic.ini；迁移目录输入 alembic/，输出 /app/alembic/，保留其内部结构。runtime 消费路径不变。

验证资源清单作为字符串路径集合：ini、env.py、script.py.mako、versions、web/dist/index.html。记录每项存在性、镜像 SHA/digest、构建退出码。资源不存在即失败，不用宿主路径存在替代镜像存在。

### 2. 同步 URL 转换

计划新增一个小型纯转换函数（建议名 build_sync_database_url），输入数据库 URL 字符串，输出显式同步 URL 字符串；不连接数据库、不读取额外环境变量。局部变量包括 parsed_url、backend_name、sync_url；核心数据结构使用 SQLAlchemy URL 对象，避免字符串全局替换误伤密码或查询参数。

PostgreSQL 后端选择 psycopg，SQLite 后端去除异步驱动并保留相对/绝对路径和查询参数。输出序列化保留原始认证信息；写入 Alembic config 时处理百分号转义。其余后端按明确支持策略报错或保留同步 URL，实施前以现有配置支持范围确认，不无声猜测。

测试输入至少覆盖 asyncpg、裸 PostgreSQL、已显式 psycopg、aiosqlite、同步 SQLite、URL编码密码、百分号、查询参数；断言 drivername 与其他组件逐项一致，不在测试输出泄露密码。保留现有 run_migrations_offline/online 职责，仅替换其 URL 来源。

### 3. 数据迁移验收

不预先新增迁移修复函数或 revision。验收读取 current/head、表名、mastery user_id 类型/外键、vector_chunks 及 chunk_id，并记录迁移前后计数与关键行样本。空库、已有当前 init 的库、已有旧版 init 但缺 mastery 表的库分开准备。

旧版异常库仅在副本复现；若证实存在缺表、非数字 user_id 或孤儿外键数据，停止该样本升级并报告精确状态，另做向前迁移与数据处置设计。不得删除数据、盲目 stamp head 或重复改历史 init。正式库存量状态尚未知。

### 4. 业务与发布验收

优先复用现有测试与 API 路径，不预先发明新业务接口。输入为候选镜像、隔离数据库、测试账号、模型配置；输出为按步骤记录的状态码、session标识、持久化结果与脱敏日志。

登录后发起普通教学轮次，检查可用回答/事件终止，再读取会话和消息，必要时在受控重启后复查保存。health 成功只证明该端点响应，不能替代上述业务结果。

发布证据记录采用明确字段：commit_sha、image_digest、gate_name、status、timestamp、artifact_path；状态仅允许通过、失败、环境阻塞、未执行。服务器使用同一已验收 digest，核对数据库连接、端口、持久卷、配置和备份/恢复可用性后部署；不使用新的未验收构建顶替。

## 分层验收与通过条件

1. **最小 COPY 语义闭环**：scratch 负例复现原路径失败；平铺检查确认 env.py/versions 落点；正例保留原消费路径并成功。三者均须真实 Docker 结果。无业务镜像/数据库副作用，但创建构建缓存，待授权执行。
2. **完整镜像结构**：完整 build 成功，覆盖前端与依赖；覆盖启动入口、断网检查资源、迁移图与 psycopg 导入。此步不连接数据库，记录唯一 head 与 digest。
3. **迁移**：隔离空 PostgreSQL/pgvector 库升级到 head；代表性存量副本升级并校验数据与约束；SQLite 转换与既有适用迁移回归。不能用空库成功替代存量成功。
4. **业务**：本机 Compose 环境中 /health、登录、普通教学、会话与消息保存均通过；模型失败、迁移失败和健康失败分阶段保留证据。
5. **发布门禁**：候选 SHA 的项目检查和 Docker验收先完成，再发布对应 SHA/digest 镜像；服务器使用已验收 digest，复做健康与业务冒烟。现 Release main/tag 直接触发 build/push，未在该文件中看到对 CI 成功的依赖，也未看到迁移/业务验收；不能当作已有门禁。具体增加方式待用户确认，不在 Ruff 提交夹带修改。

耗时操作后按用户要求约30秒主动检查进程、输出或产物，不使用 sleep 强制等待。验证使用独立项目名、卷和测试凭据；不得对现有 pgdata 执行 down -v。

## 未知项和当前阻塞

- Docker Linux daemon 连接仍不可用；本轮未尝试启动或更改配置。
- 完整镜像、迁移连接、向量扩展权限、非root运行、前端产物、业务就绪均尚无本轮运行结果。
- 不清楚服务器的 Docker/Compose 版本、网络可达性、端口占用、数据卷与存量 schema；服务器阶段前须只读盘点。
- 不清楚真实存量库是否经历旧 init 或含不兼容 user_id，不能预设需要补表。
- Ruff 本地提交已确认 `5162bce`，开始实施 Docker 前仍须重新核对 HEAD 和相关 diff；本机提交不是远端发布或 CI 成功证据。

## 决策与授权边界

请确认 A 方案及上述分层验收范围后再编码。用户提供的 AGENTS.md 明确要求“三层详细规划”且“规划必须经用户确认后，方可进入编码阶段”；brainstorming 同样要求批准设计后实施。本文仅准备可审阅方案；未修改 Dockerfile、Compose、workflow、迁移或业务代码，未提交、推送、启动或部署。

完整原始计划归档见 [superpowers/docker-deployment-next-step-raw.md](../../superpowers/docker-deployment-next-step-raw.md)；后续 spec 必须追溯该 raw，并在实施前注明确认版本。
