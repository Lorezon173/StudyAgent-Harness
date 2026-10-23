# StudyAgent 工作区 Task0 基线（2026-10-24）

本报告执行已批准的 [核心实施计划 Task0](../superpowers/plans/2026-10-23-study-workspace-core.md)。仅冻结事实与建立执行清单，未实施 Task1 或产品代码，未推送、部署、提交或修改全局配置。

## 分支、终稿与原有变化

- 实际分支：`codex/frontend-ui-optimization`。
- 实际 HEAD：`d0584d993b8293a2333acc35f3f5753a08068230`，与批准基准一致。
- 终稿：`docs/designs/frontend-paper-study.html`，SHA256 为 `9EDC828D7A2D7BDB40C0B5FD6D254250C932E754F1DD2723425D8D73BEABB91B`，与 raw 中声明一致。
- 三层设计：`superpowers/frontend-ui/2026-10-23-final-implementation-raw.md`，SHA256 为 `AC8DC587230464F5B2B46B288EFB89ED3496E241E3E2CDD765363EF85C9F7957`。
- 核心计划执行前 SHA256：`3231B8A16F5AD99B2A76A29A63B98BE752B6462C7F593EC601FB5A89CC0B108D`。
- 原有 tracked 修改为 `README.md` 与 `docs/asset-inventory.md`（检查时分别新增 140 行、34 行）；未改写、还原或提交这两份内容。
- 原有未跟踪文件包括测试临时目录、AGENTS.md、Learned 文档、delivery 证据、页面设计与截图、规划及 raw 等，完整列表见 [执行前状态](study-workspace-goal/evidence/Task0/git-status-before.txt)。未清理这些文件。

分支和 HEAD 原始输出、哈希详情、现有文档检查时哈希保存在 [Task0 证据目录](study-workspace-goal/evidence/Task0/)。执行前状态在创建本任务证据目录后记录，故其中 `docs/delivery/` 也包含本任务文件；Git 默认按目录折叠未跟踪文件。

## 实际验证结果

运行时间为本机时间 2026-10-24 00:02（Asia/Shanghai）。四项命令均实际执行一次，未因失败擅自安装依赖、改动锁文件或更换命令声称通过。

| 命令 | 退出码 | 实际结果与事实归因 | 日志 |
|---|---:|---|---|
| `uv run alembic heads` | 1 | uv 同步依赖时下载 `watchfiles==1.2.0` 失败，`files.pythonhosted.org` DNS 错误，Windows 11001；没有获得 Alembic heads 输出 | [输出](study-workspace-goal/evidence/Task0/alembic.log)、[时间与退出码](study-workspace-goal/evidence/Task0/alembic.result.txt) |
| `uv run pytest tests/ -q` | 1 | uv 同步依赖时下载 `langgraph-checkpoint==4.1.1` 失败，同域名 DNS 错误 11001；没有进入 pytest 收集或测试执行，不能给出通过数 | [输出](study-workspace-goal/evidence/Task0/pytest.log)、[时间与退出码](study-workspace-goal/evidence/Task0/pytest.result.txt) |
| `npm --prefix web test` | 1 | 脚本进入 `vitest run` 后提示找不到 `vitest`；`web/node_modules` 实际不存在，未运行测试 | [输出](study-workspace-goal/evidence/Task0/web-test.log)、[时间与退出码](study-workspace-goal/evidence/Task0/web-test.result.txt) |
| `npm --prefix web run build` | 1 | 脚本进入 `tsc && vite build` 后找不到 `tsc`；`web/node_modules` 实际不存在，未生成本轮构建 | [输出](study-workspace-goal/evidence/Task0/web-build.log)、[时间与退出码](study-workspace-goal/evidence/Task0/web-build.result.txt) |

这些结果只能证明当前依赖/网络环境阻塞，不能归因为测试断言失败或业务代码缺陷。uv 输出的“3 retries”为工具内部网络重试，本轮没有再次发起相同命令。全部命令在 30 秒内结束，无需长进程轮询，未使用 sleep。未触发沙箱嵌套或自动审批故障。

环境：Windows PowerShell；uv `0.7.21`，项目虚拟环境 Python `3.12.11`，Node `v24.11.0`，npm `11.12.1`，Git `2.50.0.windows.1`。环境与依赖文件存在性见 [环境记录](study-workspace-goal/evidence/Task0/environment.txt)。本报告未声称依赖全部安装。

恢复处理：主会话已启动原生审批路径下的 `uv sync --extra dev --frozen` 和 `npm --prefix web ci --no-audit --no-fund`，沿用现有锁文件；本执行者未重复安装，等待其完成后原样重跑四项命令并另存最终记录。初次失败不意味着环境无法恢复；未修改索引或全局网络配置。

### 前端依赖恢复后的复测

主会话确认 npm ci 已成功（新增 180 个依赖包，锁文件未变）后，于 00:05 原样复测；初次日志未覆盖。

| 命令 | 退出码 | 恢复后实际结果 | 日志 |
|---|---:|---|---|
| `npm --prefix web test` | 1 | Vitest 2.1.9 执行 4 项，1 通过、3 失败，1 个测试文件失败 | [输出](study-workspace-goal/evidence/Task0/web-test-recovered.log)、[时间与退出码](study-workspace-goal/evidence/Task0/web-test-recovered.result.txt) |
| `npm --prefix web run build` | 0 | TypeScript 与 Vite 5.4.21 构建完成，204 个模块，生成 dist 产物 | [输出](study-workspace-goal/evidence/Task0/web-build-recovered.log)、[时间与退出码](study-workspace-goal/evidence/Task0/web-build-recovered.result.txt) |

三个失败位于 `web/src/api/client.test.ts`：两个成功响应测试得到“连接失败”，401 测试预期业务错误/status=401，却得到连接失败/status=0。源码交叉检查：`vite.config.ts` 指定 `environment: "node"`，测试仅 stub fetch；`client.ts` 在 fetch 参数求值时无条件读取 `localStorage.getItem`，该步骤位于转成“连接失败”的 catch 范围内。本机独立 Node 检查证实 `localStorage` 与 `window` 均为 undefined，见 [浏览器全局对象检查](study-workspace-goal/evidence/Task0/browser-globals-check.log)。因此测试环境缺少客户端要求的浏览器对象；本轮没有将失败视为真实网络连接错误。另有静态契约不一致：401 用例期待服务端“用户名或密码错误”，现有客户端统一返回“登录已过期，请重新登录”。本轮只记录，不改源码或断言。

### 备用现有 Python 运行时补充诊断

为在锁定依赖恢复期间获取代码基线，主会话授权只读使用已有解释器 `C:/Users/A1985/.codex/worktrees/mvp-cicd/StudyAgent-Harness/.venv/Scripts/python.exe`，设置 `PYTHONDONTWRITEBYTECODE=1`，未向该环境安装或同步依赖。运行目录仍为本项目；实际 `app.__file__` 指向本项目 D 盘路径，见 [解释器与模块来源](study-workspace-goal/evidence/Task0/existing-runtime-info.log)。Python 3.12.11、pytest 9.0.3、Alembic 1.18.4。该补充路径与标准 `uv run` 分开记录，不证明当前项目锁定环境恢复成功。

| 补充命令（上述解释器） | 退出码 | 实际结果 | 日志 |
|---|---:|---|---|
| `python -m alembic heads` | 0 | `20260729_chunk_id (head)` | [输出](study-workspace-goal/evidence/Task0/alembic-existing-runtime.log)、[时间与退出码](study-workspace-goal/evidence/Task0/alembic-existing-runtime.result.txt) |
| `python -m pytest tests/ -q` | -1 | 运行约 312 秒后由主会话确认并终止本次测试进程；仅有 `...`，无测试总结，不能给出通过数 | [输出](study-workspace-goal/evidence/Task0/pytest-existing-runtime.log)、[时间与退出码](study-workspace-goal/evidence/Task0/pytest-existing-runtime.result.txt)、[轮询](study-workspace-goal/evidence/Task0/pytest-existing-runtime-progress.txt) |

全量 pytest 于 00:08:02.705 启动、00:13:14.563 结束；session 88805 最终退出码 -1。期间主动检查日志与会话，不使用 sleep；早期日志为 0B，终止后仅 `...`。主会话通过原生审批只读核对两个本次 Python 进程 PID 49272/50488 的名称和启动时间，超过五分钟且 CPU 无增长后定点终止；本执行者没有重复启动或自行终止。此为超时/人工终止实录，根因未知，不等于测试断言失败或通过。

主会话另用同一备用解释器执行 `python -m pytest tests/unit/orchestration/test_assembly.py --collect-only -q`，实际退出 0、12 项收集成功、0.24 秒（总命令约 4 秒）；这是主会话提供的补充诊断，只证明该模块可收集，不能代替全套测试或 Task1 行为验收。标准 `uv sync --extra dev --frozen` 仍由主会话后台恢复，本报告不认定其成功或失败。

Task0 的事实冻结与基线实录已完成；当前通过证据仅为前端构建和备用 Alembic heads，前端三项失败、后端全量超时均继续保留。后续由 Task9 跟进前端测试契约、Task13 完整回归及按需定点诊断；未降低最终验收标准。

## RAG 开关检查

配置检查只读取 `.env.example`、`pyproject.toml` 和源代码，未直接读取或打印真实 `.env`，未为配置检查实例化 Settings。pytest 等项目命令可能按其正常流程加载配置，本报告不提取或展示这些配置值。

- `app/core/config.py:21` 仅声明 `rag_backend="fake"`；该文件及 `.env.example` 均未声明 `rag_enabled` / `RAG_ENABLED`。
- `.env.example` 提供 LLM、数据库和可观测模板，未提供 RAG 开启开关；模板数据库缺省为 SQLite。
- `pyproject.toml` 主依赖含 `pgvector`，另有 `rag` 可选依赖；这不等于默认无检索教学已实现。
- `app/orchestration/assembly.py:157` 校验在线 backend 必须为 `pgvector`，`:194` 的 `run_online_agent_session` 无条件构建在线检索协调器；源码说明仍要求 PostgreSQL。
- `app/api/chat.py` 与 `app/api/chat_stream.py` 均调用上述在线入口，未见独立的关闭开关传入。

结论：当前分支仍需 Task1；本轮未修改或验证无检索教学能力。真实进程当前环境值未检查，不能据源码默认值推断线上实际配置。源代码命中摘要见 [RAG 检查证据](study-workspace-goal/evidence/Task0/rag-source-check.txt)。

## 任务需求与验收清单

状态仅反映本轮 Task0，后续状态由主会话维护；所有需求追溯至 [三层设计 raw](../../superpowers/frontend-ui/2026-10-23-final-implementation-raw.md) 及对应核心计划任务。

| 任务 | 原始需求/设计归属 | 核心验收 | 本轮状态 |
|---|---|---|---|
| Task0 | 已批准终稿、执行基准、证据留存 | 分支/HEAD/终稿哈希、原有变更与四项命令实录 | 实录完成；构建通过、备用迁移头通过、前端3失败、后端全量超时 |
| Task1 | 默认无检索普通教学 | 缺省不装配检索，显式开启保持鉴权与严格验证 | 待实施，源码缺口确认 |
| Task2 | 主题共享画像、旧资产保留 | 用户/画像外键隔离、同名稳定 ID、可重复历史迁移 | 未实施 |
| Task3 | 可恢复会话、请求和 UI 状态 | 请求幂等/attempt/租约、版本冲突、pending 原文恢复 | 未实施 |
| Task4 | 私有文本知识库 | 持久化 CRUD、跨账号拒绝、资源归属 | 未实施 |
| Task5 | 画像知识点与真实摘要 | null 掌握度、覆盖率、同 revision 与真实证据来源 | 未实施 |
| Task6 | 多会话切换与工作区恢复 | 空会话保存、稳定分页、snapshot、版本冲突 | 未实施 |
| Task7 | 连续上下文和稳定知识点 | 对应会话最近问答进入提示、快照恢复、限制长度 | 未实施 |
| Task8 | 原子教学与显式重试 | 一次提交、失败回滚、幂等与真实 PG 并发 | 未实施 |
| Task9 | 终稿 React 壳与独立会话状态 | 账号/会话桶隔离、真实 DTO、DOM 与构建通过 | 未实施 |
| Task10 | 发送/退出/重新登录恢复 | 草稿保存、晚响应隔离、失败提示、显式 retry | 未实施 |
| Task11 | 真实画像页与知识库页 | 真实 CRUD、摘要一致、来源链接、错误恢复 | 未实施 |
| Task12 | A 环形浮卡、拖动和响应式 | 各尺寸正式 HTTP 浏览器、pointer/键盘与可达性 | 未实施 |
| Task13 | 跨层真实使用闭环 | 两账号/真实模型/PG 重启、persisted=true、全量检查 | 未实施 |

## 交接边界

本执行者仅新增本报告和 `docs/delivery/study-workspace-goal/evidence/Task0/` 日志。README 及资产清单维护、Goal 状态表、明确文件暂存/提交由主会话审阅后处理。未触碰产品代码、真实数据库或原始终稿/raw；没有真实模型、PostgreSQL、浏览器验收或部署完成结论。

### 主会话补充证据索引

编排模块12项collect-only的实际工具输出摘要已补存：[原工具结果记录](study-workspace-goal/evidence/Task0/assembly-collect-only-controller.log)。该文件复制既有结果，不是重新运行，也不代表全量回归通过。
