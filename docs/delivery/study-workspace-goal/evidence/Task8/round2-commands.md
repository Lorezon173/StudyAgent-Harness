# Task8 round2 实际验证命令与终态

以下命令均在仓库根目录以原生require_escalated执行，使用已有.venv，不安装依赖。原始输出保存在同目录。所有运行句柄均已取得终态；唯一次主动中断为主会话明确授权的隔离pytest session3250单次Ctrl+C。

## 1. 独立业务RED → 初次GREEN

实际两次相同测试命令（外层分别重定向round2-red.log、round2-green.log，随后读尾并exit $LASTEXITCODE）：

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py -k 'retry_real_asgi_disconnect or retry_disconnected_before_generation or retry_task_cancel_after_management_commit or retry_management_commit_unknown' -q -s
```

- cell5→session31058：exit1，4failed/1passed/65deselected，7.81s。真实状态/业务断言失败，不是收集错误。
- cell7→session76498：exit0，5passed/65deselected，6.86s。

## 2. 原主要组挂起、只读诊断与唯一中断

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/unit/api/test_workspace_sessions_api.py -q -s *> docs/delivery/study-workspace-goal/evidence/Task8/round2-affected-primary.log
```

cell9→session3250，PID60728。日志推进后停于observer normal清理。只读cell19/21读取原日志、该PID和测试/Starlette源码；未重发pytest。cell23有界诊断exit0：实际stdin脚本逐字归档在round2-observer-diagnostic.py，执行形式为PowerShell here-string管道给`.venv/Scripts/python.exe -`；诊断前还实际执行：

```powershell
Get-CimInstance Win32_Process -Filter 'ProcessId=60728' | Select-Object ProcessId,CommandLine | Format-List
Get-Content .venv/Lib/site-packages/starlette/requests.py | Select-Object -Skip 318 -First 22
```

诊断输出见round2-observer-diagnostic.log：2秒时work等__aexit__、watcher cancelling1/eventFalse，释放诊断自己的event后任务0。经主会话双重明确授权，实际仅调用`write_stdin(session_id=3250, chars="\u0003")`一次，terminal exit1；原日志保留，不记为通过或断言RED，没有杀其他进程。

## 3. 有界observer真实断言RED

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py -k http_disconnect_observer -q -s *> docs/delivery/study-workspace-goal/evidence/Task8/round2-observer-red.log
```

cell25→session55935，exit1：3failed/78deselected，6.68s。先观测未自然退出，之后才set本例event救援，最后明确断言失败。原helper当时尚未加finally退出信号。

## 4. 最终受影响及PG三组（同一顺序脚本）

```powershell
$priorTask8Process=Get-Process -Id 60728 -ErrorAction SilentlyContinue
if ($priorTask8Process) { throw '原隔离pytest PID60728仍存在，停止启动新回归' }
.venv/Scripts/python.exe -m pytest tests/api/test_conversation_transactions.py tests/unit/api/test_workspace_sessions_api.py -q -s *> docs/delivery/study-workspace-goal/evidence/Task8/round2-affected-primary-final.log
$primaryExit=$LASTEXITCODE
Get-Content docs/delivery/study-workspace-goal/evidence/Task8/round2-affected-primary-final.log -Tail 65
if ($primaryExit -ne 0) { exit $primaryExit }
.venv/Scripts/python.exe -m pytest tests/unit/api/test_chat_anonymous.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_persist.py tests/api/test_chat_stream_error.py tests/api/test_chat_stream_realtime.py -q *> docs/delivery/study-workspace-goal/evidence/Task8/round2-affected-routes.log
$routeExit=$LASTEXITCODE
Get-Content docs/delivery/study-workspace-goal/evidence/Task8/round2-affected-routes.log -Tail 30
if ($routeExit -ne 0) { exit $routeExit }
$env:WORKSPACE_TEST_DATABASE_URL='postgresql+asyncpg://goal_test:goal_test_local_only@127.0.0.1:55440/goal_workspace'
.venv/Scripts/python.exe -m pytest tests/integration/test_workspace_concurrency.py -m integration -q -s *> docs/delivery/study-workspace-goal/evidence/Task8/round2-pg.log
$pgExit=$LASTEXITCODE
Get-Content docs/delivery/study-workspace-goal/evidence/Task8/round2-pg.log -Tail 65
exit $pgExit
```

cell27→session54238，terminal exit0。97passed/50.53s；12passed/7.71s+1既有warning；20真实PG passed/45.92s。所有观察窗口均保原句柄poll，未sleep、未重复活跃测试；本轮PG没有重启。

## 5. 最终范围、语法、清库与全源冻结

cell31实际将round2-final-verification.py所归档的全文作为PowerShell here-string stdin传给`.venv/Scripts/python.exe -`，重定向round2-final-verification.log，再读原日志与report尾并exit该Python结果；exit0，wall4.16s。该归档是原stdin执行记录，不表示再次执行文件。

结果：7文件py_compile通过；限定git diff --check exit0（仅CRLF提示）；维护连接只读确认测试库[]；原25文件只允许6文件变化；原HEAD/branch不变；生成含新增helper的26文件round2-code-freeze-manifest.json。冻结UTC 2026-10-26T06:13:11.161084+00:00，之后未再改源码/tests。
