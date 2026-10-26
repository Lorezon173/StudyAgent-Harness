# Task8 round3 实际命令、原日志及终态

工作目录为仓库根目录，全部DB/API执行使用原生require_escalated及既有.venv。brief SHA已实核为437df2114f1ed3f8791f6cd7ae1e19e16b0f1af27ced3e6f4b3806213a7dafcc。未安装依赖、未sleep、未中断进程、未重发活跃命令，未重启PG。

## 1. 精确真实Request父取消RED

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py -k initial_disconnect_probe -q -s *> docs/delivery/study-workspace-goal/evidence/Task8/round3-red.log
$result=$LASTEXITCODE
Get-Content docs/delivery/study-workspace-goal/evidence/Task8/round3-red.log -Tail 75
exit $result
```

cell2→session98676→terminal exit1：1failed/81deselected，4.39s。失败为真实业务体已进入且正常返回str，没有传播父CancelledError；不是Timeout/导入错误。产品helper此时未改。

## 2. 最小修复后helper专项→主要API→旧路由→PG20

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py -k 'initial_disconnect_probe or http_disconnect_observer' -q -s *> docs/delivery/study-workspace-goal/evidence/Task8/round3-helper-green.log
$helperExit=$LASTEXITCODE
Get-Content docs/delivery/study-workspace-goal/evidence/Task8/round3-helper-green.log -Tail 65
if ($helperExit -ne 0) { exit $helperExit }
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/unit/api/test_workspace_sessions_api.py -q -s *> docs/delivery/study-workspace-goal/evidence/Task8/round3-affected-primary.log
$primaryExit=$LASTEXITCODE
Get-Content docs/delivery/study-workspace-goal/evidence/Task8/round3-affected-primary.log -Tail 50
if ($primaryExit -ne 0) { exit $primaryExit }
.venv/Scripts/python.exe -m pytest tests/unit/api/test_chat_anonymous.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_persist.py tests/api/test_chat_stream_error.py tests/api/test_chat_stream_realtime.py -q *> docs/delivery/study-workspace-goal/evidence/Task8/round3-affected-routes.log
$routeExit=$LASTEXITCODE
Get-Content docs/delivery/study-workspace-goal/evidence/Task8/round3-affected-routes.log -Tail 18
if ($routeExit -ne 0) { exit $routeExit }
$env:WORKSPACE_TEST_DATABASE_URL='postgresql+asyncpg://goal_test:goal_test_local_only@127.0.0.1:55440/goal_workspace'
.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_concurrency.py -m integration -q -s *> docs/delivery/study-workspace-goal/evidence/Task8/round3-pg.log
$pgExit=$LASTEXITCODE
Get-Content docs/delivery/study-workspace-goal/evidence/Task8/round3-pg.log -Tail 20
exit $pgExit
```

cell4→session2987→terminal exit0。按顺序实际结果：helper6passed/78deselected/2.39s；primary100passed/44.75s；routes12passed/10.24s及1旧warning；PG20passed/45.94s。三个最终组132项执行均通过，helper6为重叠阶段验证不重复计数。每个观察窗口保原cell/session句柄poll到terminal。

helper-green及primary记录：父cancel_requests[True]、business_entered[]、outcome CancelledError、owned_doneTrue、single_receive1、rescue_usedFalse；首次error/已断和normal/error/cancel也均owned_doneTrue/rescueFalse。PG原日志保真实blocker1772/waiter1774/grantedFalse与retry completed3/msg4及interrupted4/msg2。

## 3. 最终真实snapshot范围、语法、空白、测试库与冻结

```powershell
.venv/Scripts/python.exe docs/delivery/study-workspace-goal/evidence/Task8/round3-final-verification.py *> docs/delivery/study-workspace-goal/evidence/Task8/round3-final-verification.log
$result=$LASTEXITCODE
Get-Content docs/delivery/study-workspace-goal/evidence/Task8/round3-final-verification.log
Get-Content .superpowers/sdd/2026-10-23-study-workspace-core/task8-report.md -Tail 2
exit $result
```

cell7 terminal exit0，wall2.456s。该脚本已作为实际执行文件保留：两允许文件py_compile；原26哈希仅两变化/其余24不变；真实snapshot自身匹配旧manifest；逐份git diff --no-index --check实际exit1且无空白错误（仅helper CRLF提示），另核每一新增行无尾随空白；PG维护只读查workspace_task8残留[]；HEAD/branch及briefSHA不变。

生成round3-code-freeze-manifest.json，UTC2026-10-26T11:25:03.259537+00:00，26源码/tests全部最终冻结。之后仅追加report round3及本索引，未再修改源码或测试。全部未跟踪产品/测试仍6份，无本轮新产品/测试文件。
