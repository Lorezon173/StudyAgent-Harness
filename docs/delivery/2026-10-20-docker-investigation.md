# Docker 部署目录故障专项调查

调查日期：2026-10-20。历史 Release 基准 `6324b9442b6f1671ccb4a19cdacb42bb91597187`；当前 feature-rag 基准 `d0584d993b8293a2333acc35f3f5753a08068230`。按 systematic-debugging 从错误回溯组件边界。本报告没有实施修复。

## 一页定位卡

**实际故障**：Dockerfile:25 把 alembic 目录内容平铺到 backend 的 `/app`；Dockerfile:38 却要求复制 `/app/alembic`。生产者与消费者路径契约不同，导致两次真实 Release 构建失败。

**定位入口**：运行日志的 `/app/alembic: not found` → runtime COPY 源 → backend COPY 目的地和 WORKDIR → context/ignore → workflow。随后检查 Alembic/Compose，但不能把尚未执行的启动问题说成本轮原因。

**影响**：完整镜像没有构建完成；不能声明推送、启动、迁移、部署成功。`failed to compute cache key` 是缺失输入的摘要计算错误；其他节点的 CANCELED 不等于独立失败。

**常规修复方向**：分别复制配置文件与迁移目录，显式交付 `/app/alembic.ini` 和 `/app/alembic/**`。需真实构建和隔离数据库验证才能关闭。

**验证限制**：本机有 Docker CLI，但 Docker Desktop Linux daemon 不存在可连接的命名管道。已尝试真实最小构建，止于 daemon 连接；没有用复制模拟替代 Docker 验证。

**版本纠偏**：旧历史 MVP `d83c505` 的 mastery 缺表风险不得套用到 `6324b94`。6324b94 与当前分支的 init 迁移已补建两表。已过旧 init 的存量库是另一种有条件升级风险，尚未检查真实库。

## 1. 原始错误与证据

最新真实运行：[Release 33612200695 / job 100189728538](https://github.com/Lorezon173/StudyAgent-Harness/actions/runs/33612200695/job/100189728538)。本地原始日志 `.pytest_cache/cicd-rootcause-20261019/33612200695.log`：

```text
1082 #22 [backend 7/8] COPY alembic.ini alembic/ ./
1083 #22 DONE 0.0s
1093 #23 [backend 8/8] RUN uv sync --extra rag --no-dev
1096 #23 DONE 1.2s
1100 #21 CANCELED
1108 #26 [runtime 6/8] COPY --from=backend /app/alembic ./alembic
1109 #26 ERROR: failed to calculate checksum of ref ...: "/app/alembic": not found
1116 Dockerfile:38
1124 ERROR: failed to build: failed to solve: failed to compute cache key:
     failed to calculate checksum of ref ...: "/app/alembic": not found
```

长内部 ref 以省略号压缩，错误路径不变，可回日志查看完整行。2026-08-03 的 `.pytest_cache/cicd-rootcause-20261019/30810152932.log:1090,1107-1121` 同样显示 backend COPY 成功、runtime 找不到目录。[历史运行](https://github.com/Lorezon173/StudyAgent-Harness/actions/runs/30810152932)

已有任务证据确认 GHCR 登录成功；不是已证明的登录失败。前端构建和 runtime 的虚拟环境复制被取消，是整个构建退出后的连锁现象，不足以诊断前端或依赖另有错误。

## 2. 整体输入输出链及阶段对照

构建上下文是提供给构建器的输入文件集合；stage 是独立文件系统；runtime 是最后交付的镜像。三个 FROM 的 `/app` 不会自动共享文件。

分层识别：宿主层是本机 Windows 仓库或 Actions runner 的 checkout；上下文层是 ignore 过滤后的构建输入；backend 层是构建中间文件系统；runtime 层是最终镜像文件系统；运行挂载层是在启动容器时才叠加的 volume/bind mount。本次报错属于 backend → runtime 的构建边界，不属于宿主目录不存在，也不属于运行挂载覆盖。Compose 只给 db 挂 pgdata，app 无源码挂载，不能修补构建时已经缺失的路径。

| 边界/阶段 | 输入和路径规则 | 输出或消费要求 | 证据 |
|---|---|---|---|
| workflow | main push/v* tag，checkout@v4 | 仓库根目录 | release.yml:3-6,15 |
| build context | build-push-action@v5 显式 `context: .`，没有另选 file | 根 Dockerfile 及允许文件；不是默认 Git context | .github/workflows/release.yml:38-46 |
| ignore | 排除 .git/.github/.venv/tests/docs 等；没有排除 alembic/ini | 迁移输入可进入构建 | .dockerignore:1-35；未发现专属 Dockerfile ignore；真实 COPY 成功佐证 |
| frontend | WORKDIR /build；COPY web/ ./ | 期望 /build/dist → runtime /app/web/dist | Dockerfile:3-10,40；该次前端节点被取消，不能断言完成 |
| backend 依赖 | WORKDIR /app；pyproject/lock；uv sync | /app/.venv | Dockerfile:13-22；日志安装 DONE |
| backend 应用 | COPY app/ ./app/ | /app/app/** | Dockerfile:24；目标明确保留 app 层级 |
| backend 迁移，错误生产者 | COPY alembic.ini alembic/ ./ | /app/alembic.ini，以及 /app/env.py、/app/script.py.mako、/app/versions/**、/app/README | Dockerfile:25；目录清单据官方语义推导，本机未实测 |
| runtime，错误消费者 | WORKDIR /app；从 backend 根读取绝对路径 /app/alembic | 要求 /app/alembic/**，构建失败 | Dockerfile:33,38；真实日志证实源缺失 |
| Alembic | ini 在 /app；script_location 为 %(here)s/alembic | 要求 /app/alembic/env.py 和 versions | alembic.ini:8；Dockerfile:37,45 |
| Compose | deploy profile；build: .；PG healthy 后启 app | 同一 Dockerfile；没有 app 源码挂载补救路径 | docker-compose.yml:30-39 |

Docker 对目录源复制内容，相对目的地受 WORKDIR 影响，跨阶段源从来源阶段根目录解析。因此 `alembic/` 不会自动保留源目录名，删掉源尾斜杠也不会修复。[Docker 官方 COPY 规则](https://docs.docker.com/reference/dockerfile/#copying-from-the-build-context)

runtime 的 `/app/alembic` 尚不存在时就失败，根本没有进入 CMD。仅删除第38行会把错误推迟到 Alembic 查找 script_location；仅 mkdir 空目录也缺 env.py/versions。配置和文件目录必须一起满足契约。

## 3. 历史对照与后续迁移问题

### 3.1 版本依据

只读执行以下两条命令：第一条 diff 输出为空，表示所列文件在两个基准间没有差异；第二条 ls-tree 输出历史受跟踪迁移文件列表，输出不是空：

```powershell
git diff 6324b9442b6f1671ccb4a19cdacb42bb91597187 HEAD -- Dockerfile .dockerignore .github/workflows/release.yml docker-compose.yml alembic/env.py alembic.ini pyproject.toml alembic/versions
git ls-tree -r --name-only 6324b9442b6f1671ccb4a19cdacb42bb91597187 alembic
```

第二条确认历史迁移文件受跟踪，不是本机才存在的输入。Dockerfile 最近路径历史为 `ddb0838`（初建流水线和镜像）。mastery 的历史 init 内容可用 `git show 6324b9442b6f1671ccb4a19cdacb42bb91597187:alembic/versions/d48d7137f57f_init_schema_with_messages_and_session_.py` 复核，第78-106行已有建表。比较 d83 时须显式使用 d83，不能混用主线名称作为版本证据。

本轮另实际执行 `git diff d83c505 6324b9442b6f1671ccb4a19cdacb42bb91597187 -- alembic/versions/d48d7137f57f_init_schema_with_messages_and_session_.py`，输出在原第75行之后新增 mastery_nodes/mastery_edges 的 create_table，并在 downgrade 新增对应删除。这是“d83 有缺口、6324 已补”的直接版本差异证据。

### 3.2 同步驱动契约不一致：修目录后的后续问题

Compose:39 给 `postgresql+asyncpg`，alembic/env.py:21-22 删除后缀得到裸 `postgresql`，43-47行用同步 engine_from_config。pyproject.toml:19 安装 psycopg 3；uv.lock 有 psycopg，没有 psycopg2 条目。

已有本地环境 SQLAlchemy **2.0.49** 无库解析实测：裸 `postgresql` 的 dialect.driver 是 **psycopg2**，显式 `postgresql+psycopg` 是 **psycopg**。没有连接数据库，已经证明选型不一致；尚未在实际镜像中运行迁移，不能写成历史已经发生的异常。同步引擎需要与实际安装的 DBAPI 驱动一致。[SQLAlchemy 驱动文档](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#psycopg)

常规方案是用 URL 结构化 API 显式设置 PG 同步 drivername，保留 SQLite 分支；替代是明确维护 psycopg2 依赖，但会重复驱动选型。本地虚拟环境两个驱动均未安装，不能用它证明镜像也没安装 psycopg；镜像安装集需独立检查。

### 3.3 mastery：当前干净库与旧存量库不能混淆

6324b94 和当前 d0584d9 的 init:78-106 已建两表，m3_unify_user_id_type.py:26-28 才预检 SELECT，随后改类型和外键。不能再把“当前干净库必然缺表”写成事实或重复补建。

如果某存量库已经执行旧版 init、版本标记已前进但表缺失，后来编辑历史 init 不会重跑。必须读取版本和 schema 后才决定向前修复迁移。本轮未连接任何真实库，不清楚其实际状态。app/core/database.py:38-44 在 PG 只创建 vector 扩展，不用 ORM create_all；CMD 先迁移、后应用启动，也不能依靠应用初始化补救。

未知风险包括完整前端构建、镜像导入、扩展权限、迁移链实际执行、非 root 权限和业务就绪；都不能据 COPY 故障推定通过或失败。

## 4. 修复替代方案与建议

| 方案 | 优点 | 代价与限制 |
|---|---|---|
| A. backend 分别复制 ini 与目录，目标显式 /app/alembic.ini、/app/alembic/ | 最小改动，保留所有下游契约，清楚可维护 | 多一条 COPY；仍要实际 build |
| B. runtime 从 context 分别复制配置与目录 | 最终消费者直接收集资源 | backend 的重复错误布局也应统一处理 |
| C. 专用 migrations stage | 多应用共用迁移包时职责清楚 | 当前单应用增加复杂度 |
| D. COPY --parents 保留多源父目录 | 一次表达路径层级 | 需要固定支持该特性的 frontend 版本 |
| E. 整仓 COPY 到 /app | 保留仓库布局简单 | 缓存耦合、无关文件与输入范围扩大，需严审 ignore |
| F. 平铺后搬回目录或 runtime 按文件重组 | 可兼容错误中间布局 | 易漏模板/versions，修补结果维护成本高 |
| G. 接受平铺并改 script_location/所有消费者 | 理论能形成一致布局 | 迁移文件污染根目录，扩大变更面 |

常规推荐 **A**；团队若定义 backend 仅管理依赖和应用，可选 B。不要堆叠方案。改缓存、再装 Alembic、删 COPY、跳过迁移、改源尾斜杠、只建空目录都不能交付完整迁移契约。

## 5. 实际验证与复用命令卡

已完成：两份日志读取、workflow/context/ignore 回溯、阶段路径分析、历史/当前比对、迁移审查、SQLAlchemy 无数据库方言解析。

`docker version` 返回 Client 29.3.1、Context desktop-linux，随后：

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

实际最小 build 第一次遇用户 buildx `.lock` 权限；按沙箱权限要求提升后再次执行，止于同一 daemon 缺失。未启动 Docker Desktop、数据库或容器，未将模拟当实测。

以下命令均从项目根目录 `D:\backup\basic_file\Program\LearningAgent\StudyAgent-Harness` 执行。可先复制以下命令定位目录，再运行只读诊断卡中的检查：

```powershell
Set-Location -LiteralPath 'D:\backup\basic_file\Program\LearningAgent\StudyAgent-Harness'
```

只读诊断卡：

| 命令 | 预期与异常解释 | 下一步 |
|---|---|---|
| `docker version` | Client 与 Server 都出现才说明 daemon 可用；命名管道缺失表示连接不到 | 在正常 Docker 环境继续，不靠反复重试证明目录 |
| `git show <SHA>:Dockerfile` | 读取指定运行版本，而非当前分支猜测 | 核对 WORKDIR/COPY |
| 下方日志检索命令 | 查看原错误和上下文 | 从失败消费者倒查生产者 |
| `git diff <基准SHA> HEAD -- <明确文件>` | 空输出表示这些文件相同 | 不把其他分支修复套到此版本 |
| `rg --files -g '*dockerignore'` | 检查根与专属 ignore | 核对上下文是否真有源文件 |

```powershell
rg -n 'alembic|checksum|not found|CANCELED' .pytest_cache/cicd-rootcause-20261019/33612200695.log
.venv/Scripts/python.exe -c "import sqlalchemy; from sqlalchemy.engine import make_url; print(sqlalchemy.__version__); print(make_url('postgresql://u:p@db/d').get_dialect().driver); print(make_url('postgresql+psycopg://u:p@db/d').get_dialect().driver)"
```

第二条预期输出版本、psycopg2、psycopg；不连接 db，也不读取凭据。

以下为供后续验证的真实最小 build **写操作**，本轮已尝试但未能执行构建。仅构建无业务镜像、无 RUN、无数据库、无需基础镜像下载；会使用 Docker 本地构建缓存：

```powershell
@'
FROM scratch AS backend
WORKDIR /app
COPY alembic.ini alembic/ ./
FROM scratch
COPY --from=backend /app/alembic /alembic
'@ | docker build --progress=plain --no-cache -f - .
```

预期负例复现源缺失。另一个证明平铺的检查阶段可依次复制 `/app/alembic.ini`、`/app/env.py`、`/app/versions` 到 `/proof`；正例只把第一阶段原 COPY 改为分别复制到 `/app/alembic.ini`、`/app/alembic/`，保留第二阶段消费要求不变。负例失败、平铺检查成功、正例成功才形成真实语义闭环；本轮三者均不能标记通过。

修后完整验证也会创建镜像/临时容器，须在后续授权的验证环境执行。显式覆盖 CMD，避免触发数据库迁移和应用启动：

```powershell
docker build --progress=plain -t studyagent-harness:directory-check .
docker run --rm --network none --entrypoint sh studyagent-harness:directory-check -c 'test -f /app/alembic.ini && test -f /app/alembic/env.py && test -d /app/alembic/versions && test -f /app/web/dist/index.html && alembic heads'
```

`alembic heads` 是迁移图检查，不代表在线迁移成功。构建耗时期间主动检查进程/输出，不用 sleep；后续 PG 验证必须用隔离空库和测试凭据，不能连接业务库试错。

## 6. 关闭检查单与故障变体

- [ ] 最小负例/平铺检查/正例有真实 Docker 结果；完整镜像构建成功并记录 SHA/digest。
- [ ] runtime 的 ini/env.py/versions/前端产物存在，迁移图正确。
- [ ] 同步方言和 DBAPI 加载符合选型；隔离 PG 空库 upgrade head 成功。
- [ ] 已有版本库升级保留数据，mastery 两表、类型及约束正确；不能以空库成功替代。
- [ ] 同 SHA 软件检查通过才发布；推送、部署、健康和业务冒烟各有证据。

变体练习（是调试练习，不代表新发现故障）：

1. 如果 backend COPY 本身报源文件找不到，应先查 context、ignore 和 checkout SHA，而不是先改 runtime。为何与本次不同？本次 backend COPY 已 DONE。
2. 如果 build 成功但 Alembic 报 script_location 不存在，应查最终 runtime 布局、ini 位置和容器挂载。为何不能只查 backend？stage 文件系统彼此独立。
3. 如果目录检查通过但启动报 psycopg2 缺失，应检查 URL 解析与镜像驱动安装。为何不能归因缓存？错误阶段已从构建输入变为运行时驱动加载。

综合判断：直接故障是跨 stage 的目录契约不一致，明确且有重复真实证据；同步驱动是后续配置问题，mastery 是需按版本/库状态区分的风险。当前本地 daemon 限制使新 build 验证未完成，应公开保留该未知，不能借文档推导宣布修复关闭。

本次仅新增本文；未改业务代码、Dockerfile、workflow、README 或 Git 分支，未提交、推送、部署，未启动数据库或真实模型，未删除容器数据。
