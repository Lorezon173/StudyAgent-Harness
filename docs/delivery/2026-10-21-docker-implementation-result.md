# Docker 方案 A 实施结果与验收边界

日期：2026-10-21。工作分支 `codex/docker-deployment-fix`，起点 `433b33695436647fe2bfec441ab49d7ec8268e1a`。本地交付包含代码与工作流实现，尚未推送、合并 main、推送 GHCR 或部署服务器。

设计来源：[执行计划 v2](../superpowers/plans/2026-10-21-docker-deployment-fix.md)、[原始规划](../../superpowers/docker-deployment-next-step-raw.md)。独立审阅见 [代码审查报告](2026-10-21-docker-code-review.md)。本报告区分实现、主机验证和实际容器验收；不能把单元测试视作镜像部署通过。

## 已实现

1. Dockerfile 分别复制配置文件与迁移目录，backend 明确产生 `/app/alembic.ini`、`/app/alembic/`；runtime 继续消费既有路径。
2. `app/core/database_url.py` 用 SQLAlchemy URL 对象转换：PostgreSQL 显式 psycopg，SQLite 同步驱动；保留用户名、密码、端口、路径、重复查询参数。Alembic 保留密码并转义 ConfigParser 百分号，应用异步驱动不变。
3. `scripts/verify_docker_image.py` 实现 structure、migration、api-auth、api-teaching、all；阶段结果独立，退出码 passed=0、failed=1、blocked=2、not_run=3。缺项、错误候选身份和脏工作树不得通过正式聚合。
4. 容器验收入口检查资源/head/驱动/非 root，准备隔离空库、代表性存量及三类异常迁移样本；API 检查真实认证、教学、消息保存、重启后读取与跨用户隔离。每次只清理本次唯一名称的资源，随机数据库与 JWT 密钥只经环境传递，日志脱敏。
5. Compose/.env.example 增加 JWT、RAG 和 embedding 配置透传；验收检查运行容器有效 JWT 非空且不是公开默认值。默认 db-only 用法仍可解析。
6. `scripts/docker_candidate.py` 校验归档 SHA256、源码 SHA、image ID 和源码标签；发布门禁独立强制固定必要检查集合，all 必须绑定四阶段、候选身份及同一归档。
7. CI 保留固定 Ruff 和默认回归，增加技术镜像验收及候选归档；Release 分 validate、business-gate、publish。缺真实教学、缺配置或必要证据均不得更新任何 GHCR 标签；发布载入同一已验收归档，不重新构建。只有 publish job 拥有 packages 写权限。

`uv.lock`、`pyproject.toml`、历史迁移和业务 API 未改；未安装额外依赖。

## 已真实验证

| 项目 | 结果 | 证据及限制 |
|---|---|---|
| 同步 URL 与 Alembic 接入回归 | 11 项通过 | 先取得原驱动断言及百分号插值错误，再修复转绿 |
| 发布归档与门禁测试 | 35 项通过 | 含 13 项新增固定检查/归档绑定回归，先红后绿 |
| 验收入口与状态/清理测试 | 24 项通过 | 含 TCP 就绪、错误结果重试及超时清理；不等于真实容器运行 |
| 最终默认全仓测试 | 677 passed、1 skipped、9 deselected、7 subtests passed | 37.96 秒，exit 0；原始 `artifacts/docker/final-tests.log`、JUnit `.xml` |
| 固定 Ruff 0.17.1 全仓 | 0 诊断，204 个扫描文件 | `artifacts/ruff/docker-final-v2/`，保留当时工作树 dirty 状态 |
| 主机临时 SQLite 升级 | 通过 | d50 revision + 合法数据 → head → 重复 head；前后快照一致；不代表镜像内 SQLite 已执行 |
| Compose 配置解析 | 通过 | 默认 services 为 db；deploy profile 为 db、app；不需要运行引擎 |
| 工作流 YAML | 可解析，静态复核通过 | CI 2 个 job；Release 3 个 job；未执行 GitHub Actions |
| 独立代码复核 | 未发现剩余代码阻塞项 | 初审 1 项 P1、1 项 P2 均修复并定向复核 |

默认测试的 1 项 skip 是未安装 ragas 的可选测试；9 项 integration 按默认 marker 排除。1 项已有 Starlette/httpx 弃用 warning 保留，未扩大任务去升级依赖。新增迁移 integration 在没有 `DOCKER_VERIFY_IMAGE` 时显式跳过，不计为真实迁移通过。

## 独立审查促成的修复

- **发布固定检查缺口（已修复）：** 初版 helper 只信任证据自报的 required_checks。现在独立核对每阶段固定集合，拒绝任意伪检查替代；all 强制四阶段、candidate_identity 与归档哈希匹配。
- **PostgreSQL 初始化竞态（已修复）：** 无 host 的 pg_isready 可能连到临时 socket-only 初始化服务。现在使用 TCP、实际测试账号和数据库执行 SELECT 1，只有结果为 1 才进入后续验收。密码不放命令参数。此竞态由上游启动路径和代码确认，未宣称在本机真实 Docker 复现。

## 当前真实阻塞

### 本机 Docker Desktop 仍不可用

启动 Desktop 后出现进程与引擎管道，但 Server 探测超时。当前 host 日志明确记录：

```text
backend crashed: starting services: initializing Inference manager
.../Docker/run/dockerInference: The file cannot be accessed by the system.
```

目标是 Desktop 的本地运行时套接字，不是项目 alembic 路径。已只读确认该对象为 ReparsePoint；没有删除套接字、恢复出厂设置、重置 WSL、修改服务设置或删除数据卷。

真实最小 scratch 负例已发起，但 Docker 命令没有返回，随后中断；它不能证明原 COPY 负例已在本机复现。环境记录为 `artifacts/docker/environment-20261021/manifest.json`。正例、完整镜像、候选镜像内结构检查、PG 容器迁移和容器 API 均没有通过证据。

### 真实教学与远端门禁尚未运行

当前调用进程未显式启用测试模型，也缺完整模型/embedding 配置。本轮未读取宿主 .env 自动发起模型调用，没有消耗真实模型或 embedding 服务。

远端需要先配置受保护的 `docker-acceptance` 测试环境及测试秘密，再设置仓库变量 `DOCKER_ACCEPTANCE_ENABLED=true`。当前没有设置这些远端配置，也没有运行 Actions、推送镜像或切换服务器。仓库变量默认未启用时 business-gate 不会执行，依赖它的 publish 不会放行。

## 后续关闭顺序

1. 恢复可连接的 Docker Linux 引擎，重跑最小负例/平铺证明/正例。
2. 用最终干净源码提交构建带 revision label 的候选镜像，跑 structure、migration、api-auth；当前代码的单元结果不能替代这些运行。
3. 在明确测试配置下跑 api-teaching 和 all，证明同一候选镜像的真实回复、保存、重启及所有权。
4. 按授权推送功能分支并创建 PR，验证 Linux CI；配置受保护测试环境后验证 Release 的拒绝与放行路径。
5. 发布同一验收归档对应的 registry digest。服务器只读盘点、备份/恢复和业务复验完成后再切换。

目前可交付的是修复实现、自动验收入口和默认回归结果；完整 Docker/CI/CD 部署验收仍未关闭。
