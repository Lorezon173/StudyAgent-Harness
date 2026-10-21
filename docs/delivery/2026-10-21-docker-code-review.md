# Docker v2 独立整体审查

审查日期：2026-10-21。工作区：`C:/Users/A1985/.codex/worktrees/mvp-cicd/StudyAgent-Harness`；基准：`433b336`。设计依据为主仓库 `docs/superpowers/plans/2026-10-21-docker-deployment-fix.md` v2。

## 结论

共发现 1 项 P1 和 1 项 P2，最新实现均已修复并通过本代理静态收口复核。除这两项外，没有发现新的实质缺陷。没有运行真实 Docker 验收，不能据此宣称镜像构建、PostgreSQL 容器验收、真实模型教学或 GitHub Actions 发布通过。

## 发现与处理状态

### P1：发布 helper 必须验证固定必要检查，而非只信任证据自报的检查列表

初审位置：`scripts/docker_candidate.py` 的 `check_phase()` / `gate()`。

初版只要求 manifest 中的 `required_checks` 非空，且所列检查存在并通过，因此五个 phase 各放一个任意 `verified=passed` 检查即可通过最终发布门禁；无需 `runtime_resources`、真实迁移、教学重启持久化或 all 的四阶段聚合。原 `tests/test_docker_candidate.py` 的成功 fixture 恰好如此，成功用例会接受不完整证据。这与 v2 的必要检查缺失即阻止正式发布契约冲突。

已交回实现代理修复。最新静态复核已看到：固定 `REQUIRED` 包含四阶段 canonical checks；`all` 需要四阶段和 `candidate_identity`；每阶段同时校验 required、checks、重复项；`all.archive_sha256` 与 candidate 校验和绑定。最新代码位置约为 13–20、63–83。新测试覆盖五阶段任意 check 替换、all 逐项缺失、archive hash 缺失/错误/错误类型；原成功 fixture 已改为完整 canonical 证据。主会话提供实现代理结果：13 个新增红灯转绿、定向 35 passed、Ruff 0。本发现关闭。

### P2：PostgreSQL readiness 会在临时 socket-only 初始化服务器上提前通过

初审位置：`scripts/verify_docker_image.py:229`，`Sandbox.__enter__()` 的 `pg_isready -U verify -d verify` 未指定 host。

每次验收均使用空 tmpfs，官方 PostgreSQL 入口会先启动只监听 Unix socket 的临时服务器，用于建立数据库与运行初始化，再停止它，最后启动监听 TCP 的正式服务器。当前探针默认连接 Unix socket，因此可能在临时服务器阶段返回成功，随后 `createdb` / 远程 `alembic` 撞上初始化停机或尚未开放的 TCP 端口，导致正确候选镜像出现迁移或 API 假失败。

该行为有上游事实依据：

- [pgvector Dockerfile](https://raw.githubusercontent.com/pgvector/pgvector/master/Dockerfile) 继承官方 postgres 镜像。
- [官方 PostgreSQL 16 入口源码](https://raw.githubusercontent.com/docker-library/postgres/master/16/bookworm/docker-entrypoint.sh) 264–280 行将临时服务器设为 `listen_addresses=''`；330–353 行依次执行临时启动、初始化、临时停止、正式启动。
- [pg_isready 文档](https://www.postgresql.org/docs/16/app-pg-isready.html) 说明该工具只判断服务连接状态，正确的用户名、密码和数据库名不是获得 ready 的必要条件。

建议使用显式 TCP 探针（至少 `-h 127.0.0.1`），更完整的方案为实际测试账号连接测试库执行 `SELECT 1`，且凭据仅通过环境变量传入并纳入现有脱敏。增加定向测试，拒绝以 socket-only ready 放行。当前 Docker daemon 不可用，因此这是上游启动路径与本地代码确定存在的竞态，未声称已在本机真实容器上复现。

已交回验收实现代理修复，最终静态复核：229–236 行改为 `docker exec --env PGPASSWORD` 调用 `psql -h 127.0.0.1 -U verify -d verify -tAc SELECT 1`，仅结果为 `1` 放行。密码通过调用环境传递，已被 Sandbox 加入脱敏值；没有出现在命令参数或证据中。新测试执行实际 Sandbox 就绪循环，在连接拒绝/错误结果后要求重试，并覆盖探针超时清理自有资源。主会话提供实现代理结果：3 个新增测试红灯转绿、定向 24 passed、Ruff 0。本发现关闭。

## 已核对范围

- Dockerfile 单独交付 ini 和完整 alembic 目录，最终 runtime 消费路径一致；应用 prompt/spec 等资源位于 app 下，由现有 COPY 包含。
- URL 转换只调整 drivername；Alembic 序列化保留密码并转义 ConfigParser 百分号；依赖已含 psycopg binary。
- 阶段固定 image ID 执行；状态聚合顺序 failed > blocked > not_run > passed；缺模型配置为 blocked；CI teaching 明确 not_run。
- API 验收字段符合当前 `/api/auth`、`/api/chat`、`/api/sessions` 契约，教学沿当前真实在线调用链；应用重启后复查消息，并验证另一用户读写均为 403。
- 每轮 JWT/数据库密码随机生成，容器有效 JWT 只输出布尔值；端口绑定 loopback 随机端口；已创建资源用唯一名称追踪，失败与超时路径执行清理。
- PG seed 与历史 revision schema 相符；缺表、非数字、孤儿引用三个异常样本由真实 Alembic 迁移拒绝；SQLite 数据样本包含旧 revision、升级与重复升级。
- CI 打包同一候选 archive，Release 下载后验证 checksum、image ID 与 revision label，业务验收使用受保护 environment，再次聚合，publish 在 registry login 前检查全部门禁；没有重新 build 发布镜像。
- business evidence 多路径上传的公共根为 `artifacts/docker/candidate`，下载后保留 api-teaching/all 子目录，与 publish 的复制路径匹配。

## 验证边界

本代理进行了只读代码、迁移、测试与工作流交叉核对，未重复运行全量测试。主会话提供的验证结果：默认 suite 661 passed、1 skipped、9 deselected、7 subtests；真实宿主 SQLite 旧 revision seed → head → repeat 保留数据；Compose 配置解析默认仅 db、deploy 为 db+app。以上不能替代容器镜像实际验收。

当前 Docker Desktop backend 在初始化 Inference manager / dockerInference socket 处崩溃，daemon 不可用。真实构建、COPY 负例/正例、镜像结构、容器 PG、认证、真实模型教学、Actions 与 GHCR 尚不能填写通过。最终 README 和交付报告更新由主会话负责，本审查没有修改实现或提交。

主会话最终复核补记：审查修复后重新运行默认全套，677 passed、1 skipped、9 deselected、7 subtests passed；固定 Ruff 0.17.1 全仓零诊断。审查中的 661 为修复前阶段快照，最终状态以实施结果报告为准。
