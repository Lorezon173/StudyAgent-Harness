# Task8 验证命令与原始日志索引

工作区：`D:\backup\basic_file\Program\LearningAgent\StudyAgent-Harness`。全部DB/API命令原生require_escalated；现成.venv，无安装、无命令sleep。HEAD `75be6015c331185dea34dc8910e5646c6663f29e` / `codex/frontend-ui-optimization`。

## 环境边界

PG命令环境：`WORKSPACE_TEST_DATABASE_URL=postgresql+asyncpg://goal_test:goal_test_local_only@127.0.0.1:55440/goal_workspace`；维护连接只创建/清理每例自己的workspace_task8_uuid子库。

完整默认套件单独设置：`DATABASE_URL=sqlite+aiosqlite:///D:/backup/basic_file/Program/LearningAgent/StudyAgent-Harness/docs/delivery/study-workspace-goal/evidence/Task8/full-suite-isolated.db`。

以下为实际执行的测试命令；每次PowerShell以 `*> docs/delivery/study-workspace-goal/evidence/Task8/<log>` 保留完整原输出，保留退出码再读取尾部。中间失败按当时事实保留，后续文件已有新增测试，重跑同一命令的计数可能不同。

## phase1-red.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py -q
```

原日志：[phase1-red.log](phase1-red.log)；末尾结果：`13 failed, 1 passed in 5.49s`。

## phase1-green.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/api/test_persist_turn.py tests/api/test_dirty_flag.py -q
```

原日志：[phase1-green.log](phase1-green.log)；末尾结果：`7 failed, 25 passed in 8.21s`。

## phase2-red.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/api/test_persist_turn.py tests/api/test_dirty_flag.py -q
```

原日志：[phase2-red.log](phase2-red.log)；末尾结果：`6 failed, 28 passed in 10.80s`。

## phase2-contract-red.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py -q
```

原日志：[phase2-contract-red.log](phase2-contract-red.log)；末尾结果：`7 failed, 17 passed in 10.14s`。

## phase2-green.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/api/test_persist_turn.py tests/api/test_dirty_flag.py -q
```

原日志：[phase2-green.log](phase2-green.log)；末尾结果：`42 passed in 9.24s`。

## phase3-validation.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/api/test_persist_turn.py tests/api/test_dirty_flag.py tests/api/test_chat_stream_error.py tests/api/test_chat_stream_realtime.py tests/unit/api/test_chat_new_stack_e2e.py tests/unit/api/test_chat_stream_new_stack_e2e.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_anonymous.py tests/unit/api/test_chat_persist.py tests/unit/api/test_workspace_sessions_api.py -q
```

原日志：[phase3-validation.log](phase3-validation.log)；末尾结果：`19 failed, 69 passed, 1 warning, 8 errors in 35.84s`。

## phase3-fixture-migration.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_chat_stream_error.py tests/api/test_chat_stream_realtime.py tests/unit/api/test_chat_new_stack_e2e.py tests/unit/api/test_chat_stream_new_stack_e2e.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_anonymous.py tests/unit/api/test_chat_persist.py tests/unit/api/test_workspace_sessions_api.py -q
```

原日志：[phase3-fixture-migration.log](phase3-fixture-migration.log)；末尾结果：`2 failed, 34 passed, 1 warning in 17.21s`。

## phase3-green.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/api/test_persist_turn.py tests/api/test_dirty_flag.py tests/api/test_chat_stream_error.py tests/api/test_chat_stream_realtime.py tests/unit/api/test_chat_new_stack_e2e.py tests/unit/api/test_chat_stream_new_stack_e2e.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_anonymous.py tests/unit/api/test_chat_persist.py tests/unit/api/test_workspace_sessions_api.py -q
```

原日志：[phase3-green.log](phase3-green.log)；末尾结果：`96 passed, 1 warning in 32.26s`。

## phase4-asgi-summary.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py -q
```

原日志：[phase4-asgi-summary.log](phase4-asgi-summary.log)；末尾结果：`1 failed, 47 passed in 23.12s`。

## phase4-green.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/api/test_chat_stream_error.py -q
```

原日志：[phase4-green.log](phase4-green.log)；末尾结果：`49 passed in 22.45s`。

## phase4-barrier.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py -q
```

原日志：[phase4-barrier.log](phase4-barrier.log)；末尾结果：`49 passed in 17.37s`。

## phase5-pg.log

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_concurrency.py -m integration -q -s
```

原日志：[phase5-pg.log](phase5-pg.log)；末尾结果：`7 passed in 16.29s`。

## phase5-linearization.log

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_concurrency.py -m integration -q -s
```

原日志：[phase5-linearization.log](phase5-linearization.log)；末尾结果：`1 error in 0.91s`。

## phase5-linearization-red.log

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_concurrency.py -m integration -q -s
```

原日志：[phase5-linearization-red.log](phase5-linearization-red.log)；末尾结果：`1 failed, 11 passed in 25.61s`。

## retry-race-red.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py::test_retry_rechecks_real_state_race_and_returns_conflict_http -q
```

原日志：[retry-race-red.log](retry-race-red.log)；末尾结果：`1 failed in 3.78s`。

## retry-race-green.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py::test_retry_rechecks_real_state_race_and_returns_conflict_http -q
```

原日志：[retry-race-green.log](retry-race-green.log)；末尾结果：`1 passed in 2.66s`。

## full-suite.log

```powershell
.venv/Scripts/python.exe -m pytest -q
```

原日志：[full-suite.log](full-suite.log)；末尾结果：`1 failed, 1325 passed, 67 deselected, 1 warning in 105.30s (0:01:45)`。

## final-fence-red.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py::test_final_business_commit_cannot_cross_300_second_deadline tests/api/test_conversation_transactions.py::test_final_store_lease_validation_uses_clock_after_actual_database_wait -q
```

原日志：[final-fence-red.log](final-fence-red.log)；末尾结果：`2 failed in 3.61s`。

## final-fence-green-regression.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/api/test_persist_turn.py tests/api/test_dirty_flag.py tests/api/test_chat_stream_error.py tests/api/test_chat_stream_realtime.py tests/unit/api/test_chat_new_stack_e2e.py tests/unit/api/test_chat_stream_new_stack_e2e.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_anonymous.py tests/unit/api/test_chat_persist.py tests/unit/api/test_workspace_sessions_api.py tests/unit/storage/test_workspace_state_stores.py tests/unit/storage/test_topic_profile_store.py tests/unit/orchestration/test_conversation_context.py -q
```

原日志：[final-fence-green-regression.log](final-fence-green-regression.log)；末尾结果：`259 passed, 1 warning in 46.61s`。

## phase5-final-pg-task6.log

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_concurrency.py tests/integration/test_workspace_sessions_service.py -m integration -q -s
```

原日志：[phase5-final-pg-task6.log](phase5-final-pg-task6.log)；末尾结果：`32 passed in 45.39s`。

## load-fence-red.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py::test_context_load_crossing_deadline_never_dispatches_generation tests/api/test_conversation_transactions.py::test_context_load_rejects_old_attempt_even_same_active_request -q
```

原日志：[load-fence-red.log](load-fence-red.log)；末尾结果：`2 failed in 4.39s`。

## load-fence-green-final.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/api/test_persist_turn.py tests/api/test_dirty_flag.py tests/api/test_chat_stream_error.py tests/api/test_chat_stream_realtime.py tests/unit/api/test_chat_new_stack_e2e.py tests/unit/api/test_chat_stream_new_stack_e2e.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_anonymous.py tests/unit/api/test_chat_persist.py tests/unit/api/test_workspace_sessions_api.py tests/unit/storage/test_workspace_state_stores.py tests/unit/storage/test_topic_profile_store.py tests/unit/orchestration/test_conversation_context.py -q
```

原日志：[load-fence-green-final.log](load-fence-green-final.log)；末尾结果：`261 passed, 1 warning in 49.50s`。

## owner-compat-red.log

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/api/test_chat_session_ownership.py -q
```

原日志：[owner-compat-red.log](owner-compat-red.log)；末尾结果：`3 failed in 4.73s`。

## owner-compat-green.log

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/api/test_chat_session_ownership.py -q
```

原日志：[owner-compat-green.log](owner-compat-green.log)；末尾结果：`3 passed in 3.63s`。

## final-affected.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/api/test_persist_turn.py tests/api/test_dirty_flag.py tests/api/test_chat_stream_error.py tests/api/test_chat_stream_realtime.py tests/unit/api/test_chat_new_stack_e2e.py tests/unit/api/test_chat_stream_new_stack_e2e.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_anonymous.py tests/unit/api/test_chat_persist.py tests/unit/api/test_workspace_sessions_api.py tests/unit/storage/test_workspace_state_stores.py tests/unit/storage/test_topic_profile_store.py tests/unit/orchestration/test_conversation_context.py -q
```

原日志：[final-affected.log](final-affected.log)；末尾结果：`268 passed, 1 warning in 44.06s`。

## final-pg.log

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_concurrency.py -m integration -q -s
```

原日志：[final-pg.log](final-pg.log)；末尾结果：`18 passed in 34.90s`。

## dirty-identity-final.log

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_dirty_flag.py tests/api/test_conversation_transactions.py::test_dirty_profiles_do_not_clear_other_profile_or_legacy -q
```

原日志：[dirty-identity-final.log](dirty-identity-final.log)；末尾结果：`9 passed in 3.79s`。

## 重启探针（真实两个Python进程）

```powershell
.venv/Scripts/python.exe docs/delivery/study-workspace-goal/evidence/Task8/restart_probe.py prepare
# engine/maintenance全部关闭后，由主会话核独占、专用label/55440/卷独占，再restart及pg_isready
.venv/Scripts/python.exe docs/delivery/study-workspace-goal/evidence/Task8/restart_probe.py verify
```

首轮prepare/verify原夹具未来1小时被77分钟审批等待耗尽，服务依法恢复过期，失败原日志/metadata及6056秒诊断保留；自建首轮库单独drop。第二轮重建新随机库，metadata明示测试未来24小时，生产180/30/300另组真实Store clock测试。第二轮主会话restart后verify exit0，全部completed/expired/unexpired/隔离通过并drop自有库。

日志：restart-controller.log、restart-controller-second.log（主会话原生工具）、restart-prepare.log、restart-verify-first-expired.log、restart-time-diagnostic.log、restart-prepare-second.log、restart-verify-second.log。metadata：restart-checkpoint-first-expired.json、restart-checkpoint-verified.json。探针源文件restart_probe.py保留供复核。

## 不应误计的失败与静态检查

- Windows os206在创建进程前拒绝过长批处理，该批没有写入或运行测试；改用短批次/native apply_patch，不能算作一次业务测试。
- phase5-linearization.log为新增测试括号SyntaxError收集失败，不能算业务红灯。修正测试后真实PG11pass/1dirty失败，随后真实修复通过。
- 首轮SSE即时断连“全局零模型”无屏障假设过强，后改为显式未启动/刚启动两个真实屏障，保留原日志。
- 全套唯一既有失败为test_evaluate_produces_valid_metrics/context_precision=None；未修。
- Python compileall工具终态COMPILE_EXIT=0；限定已改文件git diff --check终态DIFF_CHECK_EXIT=0，原输出diff-check.log。未安装任何格式/检查依赖。

## 冻结文件

code-freeze-manifest.json列25个产品/测试文件、SHA256和git_tracked标记。五个未跟踪源码文件必须显式进入review package；不包含原有README/资产/交付账本脏改动。
