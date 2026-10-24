# Task1 实现报告

日期：2026-10-24。基准提交：0657718；分支：codex/frontend-ui-optimization。仅实现已批准 Task1，未提交，未部署，未更改 README、任务状态、raw 或 plan。

## 结果

- Settings 新增 `rag_enabled=False`；`.env.example` 和 Compose 默认关闭，显式提供 `RAG_BACKEND=pgvector`。
- 在线入口按设置显式传递开关。关闭时不创建 Coordinator、Retriever、Provider 或 embedding，也不订阅外部注入的 Retriever。
- 规则及 Conductor 派发共用动作限制：检索动作或 retriever 目标转换为 `tutor_ask/target=tutor`；受控真实协作环能正常结束，不靠最大回合熔断。
- 显式开启保留既有 PgVectorProvider/PostgreSQL 严格校验与 fail-fast；低层 `build_new_stack/run_new_agent_session` 末尾参数默认 True，保持离线兼容。
- 在线创建 `VisibilityContext(user_id)` 并注入 Retriever。事件中的 visibility 字段一律拒绝（包括显式 None），其他身份或 workspace 与可信身份不一致、bool/float 身份均拒绝。没有 visibility 字段的正常在线动作始终使用可信上下文。离线原有可选 visibility 契约保留。
- 使用真实 PgVectorProvider 的 SQLite SQL 分支验证公共、本人的两个不同主题均可见，他人和无主私有文档不可见；受限请求不调用 OCR/code，也不在向量空结果时回退这些来源。
- ADJ-004：主会话明确授权最小扩展 `_persist.py`，在首轮与 IntegrityError 重试分支的 session save 后各 flush 一次，父先于消息，原 commit 次数不变。没有提前实施 Task8 的新状态、API 或幂等架构。

## 实际修改文件

产品与配置：

- app/core/config.py
- app/orchestration/assembly.py
- app/harness/orchestrator.py
- app/agents/retriever.py
- app/api/_persist.py（ADJ-004）
- .env.example
- docker-compose.yml

测试：

- tests/unit/orchestration/test_rag_switch.py（新增）
- tests/unit/orchestration/test_online_composition.py（旧在线失败测试显式启用开关）
- tests/unit/api/test_chat_new_stack_e2e.py
- tests/unit/api/test_chat_stream_new_stack_e2e.py
- tests/api/test_persist_turn.py（ADJ-004 定点外键/回滚测试）

两个 API E2E 文件使用各自独立临时 SQLite factory、外键开启与真实 user1。新增关闭路径用例明确使用已保存的本人会话，验证 `persisted=true`；原 `e2e-1` 仍是新会话，保留原 turn_count 断言，未用预存会话掩盖缺陷。

## 红灯证据与过程事实

证据根目录：docs/delivery/study-workspace-goal/evidence/Task1/。

1. `red-unit.log`：初始 `test_rag_switch.py` 14 failed / 3.02s。关闭入口触发检索构造哨兵、缺少 rag_enabled 参数，构成有效基础红灯。可见性测试当时被辅助函数中缺少 captured rag_enabled 的 KeyError 提前阻断，不能把这些准备期失败称为已证伪安全行为。
2. `red-visibility-differential.log`：补充限定差分验证，在独立 Python 进程中读取 `git show HEAD:app/agents/retriever.py`，仅将当前类的 handle 方法替换成基准 HEAD 实现，再运行可见性测试。未改动产品文件，进程退出即恢复。结果 7 failed、1 passed、7 deselected / 3.10s；真实 SQL 结果包含他人及无主私有文档，集合断言直接失败，OCR/code 哨兵也被调用。该证据验证新增安全断言确实能捕获旧行为。
3. `red-identity-types.log`：新增 float 身份边界后 2 failed、4 passed、11 deselected / 2.61s；再补严格 int 校验。
4. `green-focused.log`：首次原生执行回归 208 passed、1 failed、1 deselected / 23.18s。唯一失败为原 `test_chat_new_stack_e2e`：外键开启后新 session 的消息先写入，`FOREIGN KEY constraint failed`，turn_count 为 None。未删除或放宽断言，报告主会话后获得 ADJ-004。
5. `red-parent-flush.log`：修复前定点测试 2 failed、8 deselected / 4.11s。真实 SQL 消息写入前父 session 不存在；后置故障注入到达标记为空，避免仅凭“无数据”伪造完整回滚覆盖。

普通沙箱中的 API 运行被中断，`red-api.log` 只记录收集阶段，不视为有效业务结果。主会话的空 FastAPI/TestClient 探针对照证明普通沙箱挂起、原生审批路径正常，记录见 testclient-execution-path-probe.log；因此此前“API 挂起可能由本机 DB 导致”只是未证实猜测，不能作为根因。隔离 DB 夹具保留以消除环境耦合。另一个普通沙箱异步 SQLite 定点运行也在收集后挂起，已中断并改用原生路径。

## 最终验证

所有 Python 测试命令均使用项目 `.venv/Scripts/python.exe`，设置 `PYTHONDONTWRITEBYTECODE=1`；最终及差分日志设置 `PYTHONIOENCODING=utf-8`。API/异步 SQLite 回归通过工具原生 require_escalated 路径执行，未改权限配置。

最终命令（原生路径）：

```text
.venv/Scripts/python.exe -u -m pytest tests/unit/orchestration tests/unit/harness/test_orchestrator.py tests/unit/agents/test_retriever.py tests/unit/infrastructure/test_pgvector_provider.py tests/unit/api/test_chat_new_stack_e2e.py tests/unit/api/test_chat_stream_new_stack_e2e.py tests/unit/api/test_chat_session_ownership.py tests/unit/api/test_chat_persist.py tests/api/test_persist_turn.py -vv --tb=short
```

实际结果：**229 passed、1 deselected、1 warning，13.25s，exit 0**，完整输出 green-final.log。唯一 deselected 是 `tests/unit/agents/test_retriever.py::test_evaluate_ragas_real_judge`（第457行），原本标记 integration，需要真实 OpenAI judge/RAGAS；被 pyproject.toml 默认 `-m 'not integration'` 排除，并非为本任务新增 skip。warning 是原 Starlette/httpx TestClient 弃用提示，未升级依赖掩盖环境问题。

覆盖包含全部 orchestration 单测、原 Orchestrator/离线 Retriever、真实 PgVectorProvider SQL 单测、HTTP/SSE 新旧入口、跨账号和 NULL owner 拒绝、原持久化用例。新增父顺序测试在首次消息写入处主动注入 IntegrityError，验证 retry 分支仍父先写、最终两条消息、业务 commit 恰好一次。新增图谱失败测试确保两条消息已 flush 后再抛错，使用新连接确认 session/messages 均不存在。

限定安全差分命令逻辑：

```text
source = subprocess.run(['git', 'show', 'HEAD:app/agents/retriever.py'], capture_output=True, text=True, encoding='utf-8', check=True).stdout
previous = {'__name__': 'task1_baseline_retriever'}
exec(compile(source, 'baseline_retriever_from_HEAD.py', 'exec'), previous)
RetrieverAgent.handle = previous['RetrieverAgent'].handle
pytest.main(['tests/unit/orchestration/test_rag_switch.py', '-vv', '--tb=short', '-k', 'online_visibility or online_rejects or online_never_falls'])
```

`git diff --check` 对全部已跟踪任务文件通过。新增测试文件亦为补丁创建，未发现尾部空白。项目环境未安装 Ruff，`python -m ruff --version` 返回 No module named ruff，全局未找到命令；未为此联网安装或变更依赖。

## 验收边界

- 未重复无界全套测试，按主会话指令仅运行聚焦回归。
- 本轮 LLM 使用受控替身，真实编排、SQL/事务与隔离数据库实际执行；没有宣称真实模型或公网/部署验收。
- 可见性覆盖使用真实 Provider 的 SQLite 分支及已有 PG composition 严格校验，没有将其称为真实 PostgreSQL owner 查询集成验收。
- 新 library_items 文本卡未接入教学检索，也未实施文件上传、网络规划、UI、迁移或 Task2。
- 主会话负责 README、状态账本、独立审查及最终提交；此报告不表示整项 Goal 完成。
