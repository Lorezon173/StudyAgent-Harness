# Task3 实现报告：会话、请求与界面状态数据层

状态：实现及本轮指定验证已完成，产品 diff 冻结，等待主会话独立代码审查；未提交、未推送。不能据此声明 Task3 已通过最终审查或完整续聊产品已上线。

基准：`7f04d1c`，分支 `codex/frontend-ui-optimization`。范围依据主计划 Task3 与 `superpowers/frontend-ui/2026-10-23-final-implementation-raw.md`，本轮收尾严格依据已独立 PASS 的 `docs/superpowers/plans/2026-10-24-task3-round1.md` v1.1，SHA256 `bb8a0a7a1a881446e9b63be510f0b5ea45b3a749b097e92f0f3087c72944f593`。审查证据 `docs/delivery/study-workspace-goal/evidence/Task3/round1-plan-review.md`。

## 已实现契约

- sessions 增 `profile_id/active_node_id/state_version/next_turn_index/active_request_id`。数据库复合外键限制本人画像、画像内节点、同一会话的活动请求；历史 NULL owner 不可 claim。
- `chat_requests` 使用 `(user_id,session_id,request_id)` 身份，保存 payload hash、原始 request_payload、base_state_version、attempt、status、lease、error、response。首次领取先 flush 请求，再占用 session；尚无 messages 时原文已能恢复。
- `ChatRequestStore.claim/get/renew/complete/interrupt/retry` 不 commit。Claim 返回 status/attempt/lease_until/acquired/request_payload/base_state_version/response_json/error_code，并提供 lease 别名。同请求同原文读现状，不同 hash 或不同原文冲突；failed/interrupted 普通 claim 不重新领取。新请求遇占用为 session_busy，基准版本不同为 stale_context。
- complete/renew 校验本人 session、当前 request、running、attempt 与未过期租约。interrupt 释放占用并递增栅栏，旧 attempt 不能完成；完成后相同 attempt 重复 complete 返回已存结果。expired_only interrupt 对未过期运行保持现状。
- 显式 retry 必须提供 expected_attempt 和 expected_state_version，仅 failed/interrupted、无别的活动请求、当前 session 仍为原 base_state_version 时递增 attempt，保留原 payload。租约默认180秒；30秒续租调度、300秒总运行限制属于 Task8，尚未实现调度器。
- `profile_evidence` 在请求表之后创建；数据库保证 request/user/profile/session/node 链、真实同 session 的 message 外键及同 request/node 唯一性。user_id 是实施归属链所需的附加列，不用历史 mastery 分数伪造消息证据。
- `SessionViewStore.save(user_id,session_id,expected_version,state)` 保存 draft/reading_anchor；`WorkspaceStore.save(user_id,expected_version,state)` 保存最后会话、侧栏及 progress_y_ratio。界面版本与教学 state_version 分离；过期版本抛带 status_code=409/code 的 WorkspaceConflict，Task6 再映射 HTTP。
- 工作区位置拒绝越界、NaN、Infinity，DB CHECK 限制0–1；最后会话只能引用本人 session。Store 允许 partial state 更新，保留未提供字段。
- `SessionStore` 读取保留旧字段并增画像、节点、版本和请求占用；写入允许旧无版本 state，显式 schema_version 仅允许1，并拒绝非 JSON/NaN。完整教学 schema 字段恢复及构建属于 Task7，本任务不提前新增 DTO。
- `MessageStore` DB/内存读取增加稳定 id，保留 role/content/turn_index/created_at。旧两项 exact-key 测试按明确新增字段契约加入 id，并新增稳定性断言。
- Store 全部由 caller commit/rollback。既有 SessionStore.delete 移除内部 commit，新增测试验证 caller rollback 保留、caller commit 删除；当前 sessions API 无删除路由，无需扩展 API。

## 迁移与真实事务

新迁移 `20261023_session_workspace_state` 依赖 Task2。保留旧表和所有消息，旧有效 owner 会话只绑定本人唯一 legacy 画像；缺少旧图谱但存在会话的用户也创建 legacy。UUID5 命名与 Task2 完全一致：`studyagent:legacy-profile:{user_id}`。旧 NULL owner 保持未绑定。next_turn_index 用每 session 最大 turn_index+1 回填，空会话0，不按消息条数推算。

会话与请求存在活动请求循环引用：先增加会话字段/候选键，创建请求，再补会话约束，消息候选键先于证据。PG 使用正常 ALTER/复合约束；首轮临时候选索引触发 PG 依赖错误后已改为 PG 先创建永久 UNIQUE，未使用 DROP CASCADE。

SQLite 重建有旧 messages 的父表采用 ADJ007 策略：确保真实事务已开启，foreign_keys 全程 ON，事务内临时开启 defer_foreign_keys，全部重建后执行全库 foreign_key_check；非空则抛错，由事务拥有方 rollback；仅空结果才解除 defer，以清除 SQLite 对已重建父表保留的删除计数。迁移不擅自 commit 调用方事务。注入 profile_evidence 创建前故障，在 sessions/messages 重建后验证旧 schema、消息与 Alembic head 完整回滚，SQLite/PG 均用新连接确认。

本轮按已审查计划最小修改 env.py：prepare_connection 输入同步 SQLAlchemy Connection、无返回；仅 SQLite 走 DBAPI cursor 读/设置 PRAGMA，避免为准备连接引入 SQLAlchemy autobegin。FK 已开直接保留事务；FK OFF 且 DBAPI 真实事务已开始明确拒绝，不 commit/rollback caller。安全阶段先启 FK、核实1，再交给 Alembic 开始事务。PG 不执行 PRAGMA。

默认 env 自建连接路径两项测试覆盖成功 upgrade head 与重建中失败；迁移期间 FK=1，实际提交后新连接读取历史/版本，并由新连接自行在事务前开启 FK，检查全库 foreign_key_check、坏消息引用及跨归属 view 写入真实被拒。provided FK OFF 用例显式 BEGIN、写未提交用户、断言 DBAPI in_transaction=True；拒绝后同事务仍活跃、原写入仍可见，caller 自行 rollback 后新连接确认写入不存在、旧 schema/head 不变。

有任何新请求/证据/view/workspace 数据，或 session 已绑定画像/节点、有新 state_version/版本化 state 时，downgrade 拒绝丢失；空工作区可降级，原 NULL owner 会话与消息仍保留。Task2 测试固定升级到自己的 CURRENT，避免未来 head 改变其原有“此步尚无证据表”断言。

## 实际命令与证据

所有命令在项目根目录用已有 `.venv/Scripts/python.exe`；DB/API 均走原生审批执行路径，没有安装依赖或关闭沙箱。日志目录：`docs/delivery/study-workspace-goal/evidence/Task3/`。

1. `.venv/Scripts/python.exe -m pytest tests/unit/storage/test_workspace_state_stores.py -q`
   - `red-stores.log`：16 failed，缺少扩展模型/新 Store；`green-stores-1.log`：16 passed in 9.30s。
2. 设置独立 `WORKSPACE_TEST_DATABASE_URL=postgresql+asyncpg://goal_test:goal_test_local_only@127.0.0.1:55440/goal_workspace` 后运行迁移文件。
   - `red-migrations.log`：6 failed、10 passed，目标迁移未实现。
   - `green-migrations-1.log`：3 failed、13 passed；失败为 PG 请求外键依赖临时候选索引，正常修正依赖顺序后继续验证。
   - `green-migrations-2.log`：18 passed in 16.93s，含 SQLite/PG 重建失败恢复与提交后独立连接归属验证。
3. `.venv/Scripts/python.exe -m pytest tests/unit/storage tests/api/test_persist_turn.py -q`
   - `regression-storage-1.log`：2 failed、62 passed；两处旧 exact-key 断言拒绝新增 id 字段。
   - 最小更新明确新增字段契约并增加 caller 事务测试后，`regression-storage-final.log`：65 passed in 18.06s。按 round1 计划未重复此组；其中新增 Task3 Store 测试17项。
4. `.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_migrations.py -m integration -k default_sqlite -q`
   - `red-default-sqlite-cli.log`：2 failed、18 deselected；默认 env 自建连接 FK OFF 导致目标迁移前置拒绝。该日志在暂停前已完成；恢复后复用红灯，未重复造红。
5. `.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_migrations.py -m 'integration or not integration' -k provided_sqlite -q`
   - `red-provided-sqlite.log`：1 failed、20 deselected。原实现在目标迁移内报泛化 FK 前置错误，缺少 env 连接准备阶段对调用方真实事务的明确拒绝。
6. env.py 最小修复后：`.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_migrations.py -m 'integration or not integration' -k 'default_sqlite_alembic or provided_sqlite' -q`
   - `green-default-sqlite-cli.log`：3 passed、18 deselected in 3.20s，收集为默认2项、provided1项，未漏选。
7. 显式设置上述独立测试 PG URL：`.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_migrations.py -m 'integration or not integration' -q`
   - `migration-final.log`：21 passed in 16.99s，无 skip。共用 env 更改后重新验证 Task2/3 SQLite+真实PG完整迁移路径，包含新增默认/provided3项。
   - PG 仍用共享测试 fixture 每例创建随机 `workspace_task2_<uuid>` 独立子库，结束仅删除本例生成的子库；未访问另外三个业务容器。
8. `.venv/Scripts/python.exe -m pytest tests/unit/api/test_chat_new_stack_e2e.py tests/unit/api/test_chat_stream_new_stack_e2e.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_persist.py tests/api/test_persist_turn.py -q`
   - `api-compatibility.log`：25 passed、1 warning in 8.79s。warning 为既有 Starlette TestClient/httpx 弃用提示。验证原 HTTP/SSE 新会话、归属、persisted、失败持久化边界，不提前接入新请求编排。
9. `git diff --check -- app/models/tables.py app/models/workspace_tables.py app/infrastructure/storage/session_store.py app/infrastructure/storage/message_store.py alembic/env.py tests/unit/storage/test_message_store.py tests/integration/test_workspace_migrations.py`
   - `diff-check.log`：无空白错误，仅 Git 提示两个文件后续会规范化为 CRLF。本轮未运行 Ruff。

没有重复全套。已知上轮基线为1060 passed、1 failed、18 deselected，失败 `tests/integration/test_retriever_integration.py::test_evaluate_produces_valid_metrics` 的 context_precision=None，Task2 报告记录旧 Retriever 源码对照同样失败；本任务不修改无关评估契约，也不宣称当前全套全绿。Task13前仍需处理该验收问题。

## 文件清单与交付边界

修改产品：`app/models/tables.py`、`app/models/workspace_tables.py`、`app/infrastructure/storage/session_store.py`、`app/infrastructure/storage/message_store.py`、`alembic/env.py`。

新增产品（审查须纳入未跟踪文件）：`app/infrastructure/storage/chat_request_store.py`、`app/infrastructure/storage/session_view_store.py`、`app/infrastructure/storage/workspace_store.py`、`alembic/versions/20261023_session_workspace_state.py`。

测试：新增 `tests/unit/storage/test_workspace_state_stores.py`，修改 `tests/unit/storage/test_message_store.py`、`tests/integration/test_workspace_migrations.py`。报告与上述 Task3 证据一并交付。

未修改 README、asset inventory、status、raw、plan；主会话维护其既有改动并补充真实迁移入口/三类 Store 契约/删除 caller commit/尚未接入页面的边界。未提交、推送、部署、自派 reviewer。无未轮询执行会话；先前23388已确认65 passed并关闭。

Task6才实现会话/工作区API与快照聚合，Task7才恢复完整教学上下文，Task8才执行在线原子业务回合、续租调度及真实PG并发验收。本任务没有真实模型或浏览器验收，不能用以上 Store/迁移测试替代这些交付门槛。
