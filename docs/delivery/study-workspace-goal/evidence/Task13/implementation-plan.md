# Task13 跨层真实验收三层实施计划

> 执行按每轮“三层计划 → 独立计划审查 PASS → 编码 → 独立代码审查 → 功能验收”推进。本文为实施前计划，所有验收项待执行。

**目标**　基于当前第一阶段候选分支，证明正式工作区在真实模型与隔离 PostgreSQL 下可恢复教学、持久保存并隔离账号，形成可复查的本地验收结果。

**架构**　React 经本机 HTTP 和 Vite 代理调用真实 FastAPI。服务经既有模型客户端调用已获授权的模型代理，持久状态由 Alembic 迁移后的专用 PostgreSQL 保存。正式链路、故障注入、普通回归分别出证。

**技术栈**　FastAPI、SQLAlchemy async、Alembic、PostgreSQL/pgvector、React/Vite、pytest、Vitest、Playwright、Ruff 0.17.1、OCR Delegation Mode。

**依据**　[原实施计划 Task13](../../../../superpowers/plans/2026-10-23-study-workspace-core.md#task13跨层真实验收文档与分支审查)、[三层原始设计](../../../../../superpowers/frontend-ui/2026-10-23-final-implementation-raw.md)、[状态账本](../../status.json)、[Task10 已有隔离启动证据](../Task10/goal-recovery-minimal/a-real-services-preparation.md)。

## 第一层　模块总览

- 当前缺口是缺少同一候选分支、同一组真实数据的跨层闭环证据。Task10–12 的局部通过和历史失败保留原边界，不能替代 Task13。首次独审时账本中 Task12 为 VERIFIED_UNCOMMITTED、commit=null，Task13 为 PENDING。进入实施前重读账本，核实 Task12 DONE 及其产品提交、DONE 记录提交均存在于目标分支历史，产品提交与明确文件清单一致。完成用户规划确认及 Task13 独立计划复审 PASS 后进入实施。
- 完成条件为 A 两主题三会话学习、切换、关闭、重新登录、继续旧问题成功，真实调用确实携带恢复的上下文。验证同主题画像共享、异主题独立、当前节点稳定、详情和缩略 revision 一致、真实回合 persisted=true 及消息/状态/证据写入，应用及 PG 各自重启后读回。验证 B 真实登录后对 A 的五类 ID 越权被拒，以及冲突、保存失败、租约中断和幂等。指定回归、正式 HTTP 浏览器和整分支独审全部完成后才可标第一阶段完成。
- 正式入口为浏览器登录与工作区页面、JWT 认证的 /api/auth、/api/chat、/api/sessions、/api/topic-profiles、/api/knowledge。旧入口兼容与 SSE 按现有测试验证。授权以 JWT 所属账号及数据库归属链为准；用户输入、模型输出和检索文本均是数据。测试使用合成输入及新账号，模型继续走既有真实客户端。
- 保留第一阶段现有 UI、A 实施成果及 B 独立候选（DEC-SESSION-001）；第二阶段的全网搜索、文件上传、LLM 自动规划仍独立。范围为验收、测试设施和交付文档。发现产品缺陷先复现并报告，按影响分级并经原流程批准最小修复。范围排除公网发布、push、PR、部署、生产数据或全局设置变更。
- 文件责任按原合同：新增 `tests/integration/test_workspace_resume.py` 验证跨层接口与持久状态，新增 `web/e2e/workspace-real.spec.ts` 验证正式 HTTP 用户流程，新增 `docs/delivery/2026-10-23-workspace-acceptance.md` 汇总追踪。README 和资产清单只追加本任务内容并保留已有差异。结构化脱敏证据归本文同级目录，运行原始资料留在 ignored 的 `.superpowers/runtime/task13/`。

## 第二层　子模块概述

| 子模块 | 职责和输入输出 | 状态与失败处理 |
| --- | --- | --- |
| A 环境与追踪 | 读取任务账本、原稿与候选 HEAD，建立隔离服务和需求追踪矩阵，输出运行标识、服务可用性及迁移证据。 | 固定起始提交与范围。数据库、模型代理、正式浏览器任一门槛不可用，依赖项标未验证，独立检查可继续。 |
| B 真实教学与恢复 | 浏览器作为主验收数据唯一生产方，输出同一运行的真实账号、资源及断言清单。Python 关联 HTTP、只读 PG 与模型调用见证。 | 区分前端展示恢复、服务端状态恢复及实际发给模型的上下文。固定节点与合成标记分别防止主题、会话串线。 |
| C 重启与账号隔离 | 以重启前冻结的同一组记录为基准，分别通过新的应用进程及同卷 PG 实例读回，并以真实账号 B 置换五类资源 ID。 | 保留进程与数据库实例证明，验证 B 自己的合法正对照、A 未受副作用影响。 |
| D 冲突与原子性 | 在独立 PG 中复用事务、迁移和锁等待设施，验证版本冲突、保存失败、续租中断、旧 attempt 栅栏及重放。 | 故障注入和真实模型主流程分离，比较实际记录前后变化。SQLite 层开外键，不能给真实 PG 项充当证据。 |
| E 全量检查、审阅与收口 | 运行指定套件，独立 OCR 按整分支建立清单，汇总追踪表、限制和本地提交。 | 对照最终候选源码指纹。未覆盖或未通过项逐项记录，审查发现先报告后决策。 |

## 第三层　详细实施计划

### A 环境与追踪

主会话只读预检已观察到 `127.0.0.1:8317` 监听 PID 61116，专用测试容器 `studyagent-goal-test-pg` 仍运行且映射本机 55440。正式执行前复核。当前观察仅证明本地监听与容器状态，真实模型生成、PG 数据读写和重启仍待验证。环境满足门槛后优先推进真实链路。

- [ ] 核对当前 worktree、分支、HEAD、空暂存区或其既有状态，记录账本的分支基线 `d0584d993b8293a2333acc35f3f5753a08068230`，核 Task12 提交及 DONE。以原设计、原计划 Tasks0–13、当前账本和 B 候选裁决建立追踪表，字段包含需求、实际入口、预期状态、证据层、运行标识、结果与限制。保留 Task12 L1–L4 和独立 Node E2E 类型检查限制的实际裁决。
- [ ] 复用 Task10 启动路径。先核 Docker、PG 与 8317 本机模型代理是否可用。Task10 曾使用 `studyagent-goal-test-pg`、本机 55440、维护库 `goal_workspace` 和角色 `goal_test`。验收库用新的 `task13_acceptance_<随机标识>`，与旧数据和并发测试子库分开。重启应使用本轮专用且可确认无其他任务依赖的 PG 容器和卷，避免重启共享测试实例。若要复用上述容器重启，必须先确认当前无其他任务依赖，并记录容器、卷、绑定和当前库的安全边界。其余 PG 并发与迁移测试保留其 fixture 对维护地址、角色和库名的硬校验。
- [ ] 用专用库的同步 `postgresql+psycopg` URL 执行 `uv run alembic upgrade head`，核唯一 head、当前库、vector 扩展及当前版本。应用进程独立注入 `postgresql+asyncpg` URL、专用 JWT 密钥、`RAG_ENABLED=false`。仅向进程环境加载 Task10 已获授权的 deploy.env 模型项，必要时将模型地址中的 `host.docker.internal` 在内存映射到 `127.0.0.1`。保持原文件；模型代理未监听或真实请求失败时按实际错误停止该链路，不自行启动未知程序。
- [ ] 在 ignored 运行目录准备仅 Task13 使用的 Python 启动器。输入为本机监听配置、运行 ID、合成标记和专用环境变量。安装 B 阶段的只读见证包装后，用 `uvicorn.run` 启动 `app.main:app`，单进程且不开 reload，留 PID/启动时刻与脱敏见证文件。普通启动方式仍为原 Uvicorn 入口。Playwright 复用 `web/playwright.config.ts`、系统浏览器和 Vite 本机 4178，设置 `TASK12_ISOLATED_API` 指向该隔离后端，现有配置将其映射为 `VITE_API_TARGET`。检查前端首页、后端及 Vite 代理的 /health 和响应来源。为真实模型场景在用例级设置明确超时，使用有截止时间的状态轮询。配置值、令牌、账号口令、原始请求头、DSN、浏览器存储和原始模型提示词留在私有运行边界。

### B 真实教学与恢复

- [ ] 主运行顺序为迁移并启动观察版正式应用 → Playwright 真实场景创建数据、保存清单 → Python 在重启前比对该运行的 HTTP、PG 和模型见证 → C 阶段分别重启与越权。Playwright 的清单写入助手接收已通过浏览器断言的主场景，原子写出 ignored JSON，字段包括格式版本、run_id、候选提交、A/B 用户 ID、T1/T2、S1–S3、节点与知识条目 ID、旧问题/续答对应的消息 ID、请求 ID/attempt、草稿及历史标记摘要、版本、画像基线及所需断言结果。用户名与口令由同一启动环境单独注入浏览器和 Python，JWT 分别通过公开登录取得并仅在各自进程内存使用。清单中不写凭据。
- [ ] Python 集成用例的环境助手输入隔离 API、PG 及主场景清单，核对 run_id、候选提交、数据库和资源归属后输出只读 PG 连接与 A/B 已认证 HTTP 客户端。读回助手输入主场景 ID，输出消息 ID/turn_index/角色与正文摘要、会话状态、活动节点、state_version、画像 revision、证据关联、request_id/attempt/status 和 persisted。缺清单、见证或运行关联不符则真实用例明确失败，禁止新建主场景数据补证。并发、故障和迁移夹具另用不同库或运行标识，其结果独立归档。
- [ ] Playwright 使用相互隔离的 A/B 浏览器上下文，由真实 UI 注册登录。A 建立 T1/T2、T1 下 S1/S2 及 T2 下 S3，并创建带合成标记的知识条目，B 创建用于正对照的自有资源。S1 从 UI 选择非空节点，发起真实教学；先通过快照和历史读回证明有可评分的待答题，确认持久的 awaiting_response 状态、旧问题和助手消息关联。切换至 S2、S3，各提交独特合成标记，验证对应请求 persisted=true 且历史可读回，作为串线负对照。
- [ ] UI 切回 S1，编辑合成草稿。等待 `GET /api/workspace-state` 返回 last_session_id=S1，同时捕获 S1 `PATCH /api/sessions/{id}/view-state` 成功回包的目标草稿与版本，并用 snapshot 独立读回。关闭原浏览器上下文，在全新上下文经默认登录入口进入 `/chat`。断言实际 workspace-state 读取、应用自动选中 S1、加载其快照并恢复历史、当前节点和草稿，再以不包含旧标记的短回答继续原问题。新上下文阶段不手选会话，不直接打开深链，不预置本地存储；整条真实流程禁用 route mock 与模拟结果。模型未形成所需场景时保留失败及原因，按合成输入方案有界重试。
- [ ] 在观察版进程包装同步 `ConversationService.run_turn(loaded, on_event)`。该方法由 `run_claim` 经 `asyncio.to_thread` 执行；包装在生成线程内从 `loaded.prepared` 读取 user_id、session_id、request_id、attempt，在调用原方法前以测试专用 ContextVar 绑定，最后清理。旁路在 `LLMService._call_with_span` 包装原函数，覆盖 `invoke_json` → `invoke` 主模型及配置回退进入 `ChatOpenAI.invoke` 的实际路径。观察输入为客户端类型、node/intent、session_id 和 system/user prompt，参数原样传给原函数，只有真实客户端调用成功返回才记录成功见证。为已有历史、旧问题、短回答和 S2/S3 负对照分别记录命中布尔值或受控摘要，关联上述同一个完成的恢复请求与 agent；仅将合成旧问题的消息摘要与历史段匹配并检查短答位于当前输入段。证据必须来自 Tutor 或 Critic 实际调用。禁止写原始提示词或替换响应；若 ContextVar 缺失、模型是替身或必需证据未命中，真实用例失败。使用私有记录辅助定位，归档仅留脱敏结果。
- [ ] 观察器在同一线程内用 `parse_teaching_state(loaded.snapshot, loaded.messages)` 获取实际持久状态，核旧问题与上一助手消息匹配。按真实渲染格式检查历史段的 `上一问题引用=<id>` 与对应助手消息，或 `上一问题=` 对应文本，以及 S1 的已提交历史标记和 `【当前输入】` 中的短答；记录消息 ID 和匹配结果。用 Python 主场景清单复核旧题消息 ID/摘要和续答请求 ID/attempt，另核 S2/S3 标记在实际两类提示参数均缺席。比较过程在内存进行。
- [ ] 核对真实回合 status=completed、persisted=true、非空 reply，HTTP 消息内容与回包一致，PG 存在同一请求对应的两条消息、持久会话状态及画像证据。续答必须触发真实评分，证据须关联恢复请求、原问题、S1 节点和对应回合。缺证据则该项未通过。评分前后比对 T1/T2 画像内容与 revision，核 S1/S2 读取相同 T1 最新画像、S3 的 T2 画像未因 T1 教学改变。同一无并发写入窗口内比较详情、summary、snapshot 和浏览器缩略实际读到的 revision，并核缩略显示内容。验证恢复与续答遵循当前节点合同，区分 session 的 active_node_id 与 profile 的 revision。

### C 重启与账号隔离

- [ ] 使用同一运行清单和 Python 的读回助手冻结重启前基线。由外部运行控制逐次重启本轮应用与隔离 PG，再在每个阶段单独调用读回断言，阶段标识为 baseline、app_restarted、pg_restarted；启动失败或数据断言失败即保留对应阶段缺口。记录 PID 或进程启动时刻变化、PG postmaster 启动时刻变化、同一容器数据卷、同一库名和迁移 head。每次重新登录并通过正式 HTTP 读取 workspace-state 的 S1 与版本、快照、历史消息、节点、请求、画像详情/summary 和库条目，从新 PG 连接查消息、状态、证据、草稿及版本。重启过程禁止重建库、重新迁移后回填、重新注册代替读回。
- [ ] 在重启后由真实 B 用户先访问自有资源成功，再向相同入口替换 A 的五类标识。session 用 snapshot/messages，profile 用详情/summary 和适用写入，node 用 B 自有 profile 或空闲 session 配 A 的 node 并用 B session 当前 state_version，library 用详情及修改或删除，request 同时试 A 的 session/request 组合及 B 自己的 session 配 A 的 request ID，覆盖读取和重试。重试写路径先用 B 自有可重试请求作同入口正对照，通过受控 HTTP 断连建立真实 interrupted 请求并读回其有效 expected_attempt 与 expected_state_version，提交正对照并验证结果。断连用例若抢在领取前或完成后则重新准备，不能记为已验证；标为隔离矩阵的受控断连前置。预期状态码和错误码按各路由合同预先列矩阵，区分 403、404 等资源不可见情况，避免无效 UUID、错误版本或未登录造成假阳性。检查响应不泄漏 A 的合成标记与敏感内容，A 本人重读及 PG 比对确认无副作用。核对账号 B 仅是验收数据，和独立候选方案 B 分别记录。

### D 冲突、保存失败、租约中断和幂等

- [ ] 复用 `tests/integration/test_workspace_concurrency.py` 及 `tests/api/test_conversation_transactions.py` 的真实锁、可控断连、最终提交和旧 attempt 覆盖。新跨层用例只补缺失的状态证据，接受受控模型/故障输入但连真实专用 PG。争用用例输入同一基准版本的两个提交，验证一项推进，另一项明确冲突且不覆盖新版；检查教学 state_version、界面 expected_version、画像 expected_revision 的实际适用边界。浏览器保存失败用现有测试设施核可恢复操作与用户提示，服务端事务故障与浏览器网络故障分开。
- [ ] 保存故障分两个独立场景。写入中途失败时，用户/助手消息、教学状态、画像证据及最终完成标记整轮回滚，映射 `test_all_business_writes_rollback_at_each_failure_boundary` 的分阶段覆盖与真实 PG 的 `test_commit_connection_error_reads_actual_completed_before_failure` 未提交分支。实际提交成功后连接结果丢失时，按后者的已提交分支验证从真实 PG 查回已完成结果并维持一次写入。观察字段含各表目标行数、ID、版本、持久状态和错误码。
- [ ] 以现有真实 PG 续租/中断机制验证 180 秒租约、30 秒续租、300 秒最大运行的约束。利用可控时钟或已有真实锁等待设施重现临界点，映射 `test_renew_30_lease_180_deadline_300_and_late_worker_fence`、`test_real_pg_clock_renew_deadline_and_old_attempt_fence`、`test_real_pg_final_lease_after_actual_database_wait` 与 `test_real_pg_interruption_wins_before_old_worker_returns`，公开读取或重试路径触发恢复，确认超时旧 attempt 无法覆盖新结果。相同 request_id 和相同负载重放仅返回原结果、消息和证据不重复；同 ID 变更负载被拒；可重试的中断请求以新 attempt 仅成功提交一次。记录运行中的竞争证据和完成后持久状态。

### E 全量验证、整分支审查与本地交付

- [ ] 记录当前候选提交、运行指纹、命令、工具版本、退出码、实际通过/失败/跳过/筛除数。运行 `uv run pytest tests/ -q`。按当前默认 addopts，该命令排除 integration。另以 `WORKSPACE_TEST_DATABASE_URL` 指向核准维护库显式运行 `uv run pytest -m integration -q tests/integration/test_workspace_migrations.py tests/integration/test_private_library_migrations.py tests/integration/test_topic_profiles_service.py tests/integration/test_workspace_sessions_service.py tests/integration/test_workspace_concurrency.py`。按 B/C 阶段顺序在同一真实主运行上以 `uv run pytest -m integration -q tests/integration/test_workspace_resume.py` 运行基线、应用重启、PG 重启及隔离各阶段，通过私有运行配置传入阶段与同一清单，分阶段记收集与实际结果。测试模块所需环境各自校验，按原计划核对其他已列集成项，分别登记 SQLite 分支、真实 PG 和真实模型证据。
- [ ] 运行 `uvx --from ruff==0.17.1 ruff --version` 和 `uvx --from ruff==0.17.1 ruff check .`（已有固定工具可直接用其已核版本），以及 `npm --prefix web test`、`npm --prefix web run build`。运行 `npm --prefix web run e2e` 在正式 HTTP 配置下覆盖新真实组和现有 Task12 用例，输出每组数量并核真实组无跳过。Ruff 以真实退出状态记载，若有既有诊断，对账基线与候选并由主会话裁决范围，不能把无新增写作全绿。平台故障按项目规则同动作最多重试一次，长命令每 30 秒主动检查。
- [ ] 独立审阅者读取原合同与项目 OCR 规则，以已确认分支基线和实际候选引用执行 `ocr delegate preview --format json --from <基线> --to <候选>`，核 merge base、排除原因与逐文件清单，再按清单批量 `ocr delegate rule --format json <paths>`。若最终证据或代码未进入该候选引用，以工作区增量审阅补齐，最后核对整分支范围。每个文件检查 Git diff 与完整源码上下文，记录准确行号、问题证据、实际影响、严重度及修复建议，报告 total_files、reviewed_files、skipped_files、coverage_rate。先报告，主会话判定本轮必须修复项，修复后复核受影响的行为及候选覆盖。OCR 不可用或覆盖缺失时公开记录原因。
- [ ] 将追踪表、真实成功链路、重启和隔离矩阵、注入结果、命令及报告索引写入 `docs/delivery/2026-10-23-workspace-acceptance.md`。README 补当前能力、API、启动步骤、迁移和恢复边界、已知限制及第二阶段未实施。资产清单追加本轮证据。账本与进展仅在门槛满足且可核真实提交后标 DONE，工作区无关改动、历史证据与候选 B 保留。用明确文件列表本地提交，复查 staged diff、最终提交及索引状态。验收失败时保留成果并记录具体门槛、影响和复验入口。

## 审阅重点

- 恢复的成功条件同时覆盖新登录、真实请求上下文、回复及数据库副作用，避免把其中一层当成整条链路。
- 使用同一容器 ID 不能单独证明重启，使用新容器也不能单独证明持久化，核同卷及新启动时刻。
- 跨账号的有效 ID、正对照及重启后 readback 防止把参数校验或匿名拒绝当归属检查。
- 并发的失败分支需要检查最终数据和旧 attempt 栅栏，确保可重试路径无重写、无双写。
- 当前分支的最终候选与命令输出、代码审阅和本地提交必须相互对应，历史执行数只作为参考。
