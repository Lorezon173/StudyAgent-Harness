# Task10 A 真实验收环境准备（2026-11-03）

范围：独立环境准备与服务健康检查；不代表真实浏览器、真实模型、持久化闭环或 Task10 验收通过。

- 容器 `studyagent-goal-test-pg`：运行中，仅本机 55440 映射；`pg_isready` 接受连接。维护库仅用于创建全新子库。
- 专用库：`task10_acceptance_0a18749452c047689fb7e0f95f033323`；`current_database()` 与库名一致，`current_user` 为 `goal_test`，`vector` 扩展存在，Alembic 版本 `20261023_private_library`。
- 使用项目 `.venv` 执行 `python -m alembic upgrade head`，迁移进程的 `DATABASE_URL` 显式采用 `postgresql+psycopg`；应用进程采用 `postgresql+asyncpg`。数据库连接值不记录。
- 后端运行 `python -m uvicorn app.main:app --host 127.0.0.1 --port 57543`，启动句柄 16936、实际监听进程 61032；前端在 `web/` 运行 `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 57544 --strictPort`，PID 42908；`VITE_API_TARGET` 指向隔离后端。
- 三项模型配置从既有获授权 deploy.env 只加载到启动进程环境，Docker 主机名转换成本机地址；`RAG_ENABLED=false`，JWT 为随机值。无配置值记录。
- 通过 `curl.exe --noproxy '*'` 分别检查后端 `/health`、前端 `/`，均 HTTP 200；前端代理 `/health` 最终 HTTP 200 且响应 `status=ok`。前面服务启动初期检查失败、首次代理检查超时；最终复查通过。PowerShell 默认请求也失败，但不能据此认定原因。
- 本记录未进行真实模型调用、浏览器交互、写入读取、跨账号或数据库重启；没有重启或删除数据库、卷或其他服务。启动私有日志及运行句柄位于 ignored `.superpowers/runtime/task10-a-real/`，日志不应公开。

脱敏命令索引：`docker inspect studyagent-goal-test-pg`；`docker exec ... pg_isready -U goal_test -d goal_workspace`；`docker exec ... psql -U goal_test -d goal_workspace -v ON_ERROR_STOP=1 -c "CREATE DATABASE <随机库>"`；在随机库中 `SELECT current_database(), current_user`、查询 `pg_extension` 的 vector 与 `alembic_version`；迁移及服务命令如上；健康检查使用 `curl.exe --noproxy '*'` 访问对应本机端口和路径。
