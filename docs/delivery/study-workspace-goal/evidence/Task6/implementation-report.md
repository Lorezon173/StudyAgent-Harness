# Task6 round1 实现报告（等待独立审查）

实施依据：`docs/superpowers/plans/2026-10-24-task6-round1.md` v1.1；SHA256 `a7f81e384b4b622208682e8388f8a792106d1b3330c692a040394eb1455365ed`，独立计划审查 PASS 见 Task6/round1-plan-review-final.md。已读取 AGENTS.md、CLAUDE.md、Karpathy 与 TDD 技能。仅 Task6；没有实现 Task7/8，没有提交、推送、安装依赖或启动服务。README、账本、原始设计及计划未修改。产品与测试 diff 现冻结，等待独立 code review。

## 文件

新增产品：
- `app/orchestration/session_service.py`
- `app/api/workspace.py`

修改产品：
- `app/api/sessions.py`
- `app/models/workspace_schemas.py`
- `app/models/schemas.py`
- `app/main.py`

新增测试：
- `tests/unit/api/test_workspace_sessions_api.py`
- `tests/integration/test_workspace_sessions_service.py`

修改旧测试：`tests/unit/api/test_sessions_api.py`，仅每物理 SQLite 连接 FK ON、真实父 user seed、父 session flush、兼容同进程新 API 测试关闭默认事件循环后的旧 `_run` fixture；旧鉴权和响应边界断言保留。`test_chat_session_ownership.py` 未改。

## 行为

- POST `/api/sessions` 创建本人画像下的真实空会话，可选有效节点；UUID、初值 schema1、无消息、无伪造分数。SQLite 在归属/节点检查前真实 BEGIN；PG 共享画像锁保持至调用方提交。
- GET `/api/sessions` 无 group_by 保持旧数组；`group_by=profile` 提供主题游标与独立组内游标、空组、首组页真实 unassigned。组内 `(updated_at DESC NULLS LAST,id DESC)`；严格作用域游标，owner 过滤在分页前。
- GET `/api/sessions/{id}/messages` 无分页参数保持旧数组并添加可选 id/turn_index；显式分页返回 MessagePage，数据库按 `(turn_index,role_order,id)` 倒序有界取页，返回页内正序。
- GET snapshot 恢复 session、teaching_state/source、legacy_state、messages page、profile/summary、view、pending_requests。PG session 共享锁先于 profile；SQLite 确认真实 driver.in_transaction。view 直接只读查询，没有调用会升级 session 锁的 SessionViewStore.get。旧无 schema 状态保留；坏 JSON/未知 schema/active_node 元数据不一致返回 409。
- PATCH view-state、workspace-state 复用 Store CAS，未给字段不覆盖；草稿、阅读锚点和工作区偏好不推进教学版本。严格写 DTO、有限比例、拒布尔冒充版本或比例、拒只读与额外字段。
- PATCH active-node 先锁 session、检查占用/状态版本，再共享锁画像检查节点；同节点不增版本，schema1 同步节点，legacy 原文保留。
- GET request 只读返回真实请求原文、attempt/status/base/lease/error/response 与 lease_expired，不重跑或 claim。
- POST retry 先 owner、状态、attempt、base/session 版本、active_request_id 必须 NULL 的只读预检，再解析 `app.state.conversation_service.retry_turn`。缺能力明确 503 `conversation_service_unavailable`，请求/会话完全不变。能力存在时先 rollback 释放路由纯读事务，再以可信 user_id/session_id/request_id/expected_attempt/expected_state_version 委托，不传 db。测试 spy 只证明调用契约及事务释放，不代表真实教学重试完成；Task8 真实能力装配与闭环验收仍 PENDING。

## 命令及结果

日志目录：`docs/delivery/study-workspace-goal/evidence/Task6/`。所有 DB/API pytest 通过原生 require_escalated 执行，未使用 sleep。耗时句柄主动读取日志/进程与 poll。

1. 红灯：`.venv/Scripts/python.exe -m pytest tests/unit/api/test_workspace_sessions_api.py -q` → **12 failed**，行为失败为空会话 POST 405、工作区端点缺失等，没有收集错误，见 `api-red.log`。之后才写产品实现。
2. 首绿尝试同命令 → **11 passed/1 failed**，见 `api-green-first.log`。失败是测试租约使用本地 UTC+8 naive datetime，生产按 UTC 比较；fixture 改为 UTC naive，未改产品时间比较。UTF-8 源文件经 Python `ascii()` 核验原文为 `\u672a\u5b8c\u6210\u539f\u6587`，不是日志转码中看到的乱码。
3. 旧/新 API 组合首次 → **15 passed/7 failed**，见 `api-first-combined.log`；7 个旧 test_sessions fixture 依赖关闭后的默认事件循环。只修 `_run` 建立缺失循环。
4. 最终 API 命令：新建系统临时随机 SQLite 文件设置 DATABASE_URL；同一 Python 进程先 `asyncio.run(init_db())` 用当前 Base 建表，再 `pytest.main(['tests/unit/api/test_workspace_sessions_api.py','tests/unit/api/test_sessions_api.py','tests/unit/api/test_chat_session_ownership.py','-q'])` → **22 passed, 1 warning / 9.23s**。见 `api-final.log`（亦保留 `api-final-restored.log`）。唯一 warning 为旧 Starlette TestClient 的 httpx 弃用提示，没有为此安装依赖。用户旧默认数据库未使用。
5. 服务命令：设置 WORKSPACE_TEST_DATABASE_URL 为既有独立 55440 测试 PG，执行 `.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_sessions_service.py -m 'integration or not integration' -q -s`。
   - 首句柄 26896 被实施者在定位初期中断，exit1，没有完整结果；`service-first.log` 只有首个 SQLite 独立连接记录，**不算通过**。
   - 单例诊断 `-k 'distinct and sqlite' -vv -s -o faulthandler_timeout=15` → **1 passed / 2.34s**，`sqlite-diagnostic.log`。
   - 第二组合（加 `-o faulthandler_timeout=20`）句柄 50863，faulthandler 确认卡在 fixture 的 psycopg maintenance.connect；只读 docker 检查证实 LinuxEngine 命名管道不存在、55440 无连接，尚未建随机子库。主会话恢复已授权的既有 Docker 测试运行时后，**保持原句柄**继续运行至 terminal：**15 passed, 1 error / 147.16s**；唯一 error 是恢复前首个 PG 建库连接 ConnectionTimeout，见 `service-second.log`。环境诊断另见主会话 `environment-diagnostic.md`。
   - 不依赖 PG 的 SQLite 完整选择：`-k sqlite -m 'integration or not integration' -q -s` → **8 passed, 8 deselected / 5.23s**，`service-sqlite.log`。
   - 确认组合 terminal 后，仅补跑环境失败用例 `-k 'distinct and postgresql' -m 'integration or not integration' -q -s` → **1 passed, 15 deselected / 3.49s**，`service-pg-restored.log`。因此 16 个服务用例均取得真实成功记录；没有将早先环境 error 或中断改写成绿灯。
6. `git diff --check -- app tests` exit0；仅 Git 的既有 LF→CRLF 提示。没有运行全套/迁移：本轮经主会话明确限定定向范围，遵守任务授权。

## 物理连接与锁证据

全部新 SQLite fixture 为临时文件 + NullPool，每次物理 connect 执行 PRAGMA foreign_keys=ON。独立读连接持有 driver 强引用，与 caller/writer 做对象身份比较；PG 另比较 backend PID。Service 不 commit，caller 未提交用户名/会话/view 的 rollback 整体消失；父 flush 错误与节点 UPDATE 注入错误后独立连接确认无半会话/版本变化。

`service-pg-restored.log` caller PID98；独立读取 PID99/100/102，driver 与 PID 均不同，空会话/草稿/工作区/节点状态在新连接恢复。

`service-second.log` 的真实第三 observer `pg_stat_activity` + `pg_blocking_pids` 记录：

| 场景 | blocker | waiter | observer | 数据库实际等待 |
|---|---:|---:|---:|---|
| snapshot session 共享锁阻挡 writer | 57 | 58 | 59 | Lock / transactionid，blockers=[57] |
| 归档先锁，create 等待后读 archived 并 404 | 66 | 67 | 68 | Lock / transactionid，blockers=[66] |
| 归档先锁，set-node 等待后读 archived 并 404 | 74 | 75 | 76 | Lock / transactionid，blockers=[74] |
| create 校验先行，归档等待会话提交 | 83 | 82 | 84 | Lock / transactionid，blockers=[83] |
| set-node 校验先行，归档等待会话提交 | 91 | 90 | 92 | Lock / transactionid，blockers=[91] |

不是以 event-before-SQL、timeout 或任务未完成充当行锁证明。归档先行时独立读确认仅原会话、active_node=null、state_version0；反向顺序确认会话/节点提交后归档才能提交。

SQLite 日志 `SQLITE_REAL_BEGIN_SNAPSHOT ... True` 与 `SQLITE_REAL_BEGIN_NODE_CHECK create/set_node True` 直接读取 driver.in_transaction；JWT 模拟普通 SELECT 后先确认 driver false，再由 Service BEGIN。快照同时断言旧 session/state/messages/pending/view/profile revision，一次 session-first 写事务提交后新连接读取到全部新值。

PG fixture 每例创建 `workspace_task6_<随机UUID>` 子库，限定 127.0.0.1/localhost:55440；finally 仅 DROP 本例子库。未访问 main5432/app8000/sites55439，未运行迁移。

## 自审与未完成项

核对了 session→profile 锁序、view 只读、双游标范围/NULLS LAST、消息正序返回/向前有界、legacy 状态保留、owner 先于 retry 能力解析、rollback 后才委托、写入一次 commit/异常 rollback。未发现本轮实现内的已知阻断；独立审查尚未发生，不能提前标 Task6 DONE。

Task8 retry 真实执行仍未提供，当前默认安全返回503；spy响应 persisted=false 明确只是委托契约。Task7上下文恢复/摘要仍未实现。README/账本更新、独立 code review、提交与完成标记由主会话后续负责。没有把单接口测试当公网部署或完整产品验收。

## Round2：P2 旧消息顺序兼容修复（等待范围复审）

独立 round1 审查发现：`load_messages` 无 cursor/limit 分支使用回合/角色/id 排序，而旧 `MessageStore.list_by_session` 为 id ASC，非单调写入的合法历史会被重排。已读取 receiving-code-review 技能并实际核对旧实现，发现成立。

修复依据：`docs/superpowers/plans/2026-10-25-task6-round2.md` 三层计划，独立 PASS 证据 `Task6/round2-plan-review.md`，SHA256 `9b51846b2bff9c3955c7b1c7b42f99cb38c103740ee23d702d6fbcc1f9a0708c`。

本轮仅两处产品/测试变更：
- `app/orchestration/session_service.py`：无 cursor 且无 limit 分支的 order_by 一行改为 `MessageTable.id.asc()`。鉴权、事务、显式分页和 snapshot 分支未改。
- `tests/unit/api/test_workspace_sessions_api.py`：新增 `test_legacy_message_order_preserves_insertion_while_pagination_uses_turn_order`。真实 JWT/FK SQLite 依次 flush assistant turn1、user turn0、assistant turn0，记录实际递增 ID。无参 HTTP 断言原始 ID/内容插入顺序；显式 limit=2 分页断言新规范顺序、游标向前翻页、集合完整无重复。

验证命令及真实结果：

1. 产品修复前：`.venv/Scripts/python.exe -m pytest tests/unit/api/test_workspace_sessions_api.py::test_legacy_message_order_preserves_insertion_while_pagination_uses_turn_order -q` → **1 failed / 3.26s**，`round2-red.log`；实际 HTTP ID `[2,3,1]` 与插入期望 `[1,2,3]` 不等。是行为断言红灯，没有收集/环境错误。
2. 一行修复后同命令 → **1 passed / 2.66s**，`round2-green.log`；同一测试确认显式分页仍按回合/角色顺序。
3. 组合：新建系统临时随机 SQLite 设置 DATABASE_URL；`.venv/Scripts/python.exe -c "import asyncio,pytest; from app.core.database import init_db; asyncio.run(init_db()); raise SystemExit(pytest.main(['tests/unit/api/test_workspace_sessions_api.py','tests/unit/api/test_sessions_api.py','tests/unit/api/test_chat_session_ownership.py','-q']))"` → **23 passed, 1 warning / 10.97s**，`round2-api-final.log`，原生执行句柄78187已确认 exit0。warning 仍为旧 TestClient/httpx 弃用提示。
4. `git diff --check -- app/orchestration/session_service.py tests/unit/api/test_workspace_sessions_api.py` → exit0。

未重跑不受影响的 PG 锁/归档、迁移或全套；未改 README/账本、未提交。Round1 其余结果仍保留。本轮 diff 已冻结，等待同一独立审阅者确认原 P2 已解决及修复范围无新问题；本报告不提前标 Task6 DONE。
