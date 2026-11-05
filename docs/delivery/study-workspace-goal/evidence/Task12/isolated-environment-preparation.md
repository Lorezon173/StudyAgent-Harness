# Task12 独立验收环境准备（2026-11-04）

此前只读确认 `studyagent-goal-test-pg` 为已授权专用验证容器、仅本机 55440 映射，pg_isready 接受连接。通过 `goal_workspace` 维护连接创建全新随机子库 `task12_acceptance_0c37d000d2e3408d9927bede699c38cd`；未修改 Task11 子库或其服务。

在新库执行正式 Alembic upgrade head，迁移进程显式使用 psycopg；只读查询确认 current_database 为该随机库、current_user 为 goal_test、vector 扩展存在、版本 `20261023_private_library`。后端进程使用 asyncpg，RAG关闭、随机JWT，沿用已授权模型配置但仅放在进程内；未发模型请求，密钥和连接串不记录。

本机隔离后端监听 `127.0.0.1:52161`，启动句柄/PID 79500，实际监听子进程 PID 24084；`/health` 返回 HTTP 200。Playwright 配置要求 `TASK12_ISOLATED_API` 指向该后端，固定前端端口 4178 在准备时未监听，前端由 Playwright 自己启动，不预先启动或复用 Task11 Vite。

本记录只证明环境和迁移准备，尚未运行 Task12 真实 HTTP/浏览器功能验收；必须等待产品 OCR PASS 后按计划运行并确认真实组非 skip，受控网络与真实持久化证据分开。未删除数据库或卷、未修改产品源码或测试。
