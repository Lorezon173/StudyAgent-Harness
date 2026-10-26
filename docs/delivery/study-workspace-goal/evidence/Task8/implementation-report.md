# Task8 实施与验证报告

状态：**代码冻结可审，等待主会话独立代码审查**。未提交，未推进 Task9；README 依分工由主会话在独立审查 PASS 后更新。

依据：`task8-brief.md` v1.4，实核 SHA256 `17f8f861954d178378abd706a4f60ce5ffee411d99a6b3b11a0b571c6399b92d`。编码授权及独立计划审查 PASS 由主会话交接。基线为 `codex/frontend-ui-optimization` / `75be601`，Task1–7 未重做。

## 最终实测结果

| 验证 | 实际结果 | 原始证据 |
|---|---|---|
| 受影响 API、legacy、DirtyFlag、Task6 Store、Task7 context | **268 passed，1 个既有 Starlette warning**，44.06s | `docs/delivery/study-workspace-goal/evidence/Task8/final-affected.log` |
| Task8 独立 PostgreSQL 并发/锁/时钟/ASGI | **18 passed**，34.90s | `.../Task8/final-pg.log` |
| Task8 + Task6 真实锁联合回归（前一轮） | **32 passed**，45.39s | `.../Task8/phase5-final-pg-task6.log` |
| 第二次真实专用容器重启、新进程读取、清理随机库 | **exit 0**，completed/消息/证据/expired/unexpired/跨账号全通过 | `.../Task8/restart-verify-second.log` |
| 项目完整默认 pytest（最终栅栏增补前运行） | **1325 passed，1 failed，67 deselected，1 既有 warning**，105.30s | `.../Task8/full-suite.log` |
| Python 编译、限定已改文件 diff-check | **exit 0 / exit 0** | 实施工具终态及 `.../Task8/diff-check.log` |

完整默认 pytest 的唯一失败是既有 `tests/integration/test_retriever_integration.py::test_evaluate_produces_valid_metrics`：`context_precision=None` 与 `0.0 <= ...` 比较触发 TypeError。未修改该失败及旧 Starlette warning。最终功能改动后跑上述受影响范围和真实 PG，不把前一轮完整套件说成最终全绿。

所有 DB/API 命令都走原生 `require_escalated`，使用现成 `.venv/Scripts/python.exe`，未安装依赖。SQLite 为独立文件、NullPool、每个连接 FK ON；完整套件的默认 `DATABASE_URL` 指向 Task8 证据目录的隔离文件，未升级用户默认库。PG 每例创建并清理自己的 `workspace_task8_<uuid>` 子库，维护库 `goal_workspace` 不承载业务测试。

完整验证命令与中间结果索引见 `docs/delivery/study-workspace-goal/evidence/Task8/commands.md`；冻结源文件清单和 SHA256 见同目录 `code-freeze-manifest.json`。

## 实际产品变化

1. `ConversationService` 持 session factory，统一 prepare/claim、普通重发、显式 retry、过期恢复、纯数据加载、真实摘要/context/online runner、续租/截止/取消与最终结果。HTTP/SSE 不再各自装配第二套教学流程。
2. `turn_commit.commit_turn` 是 workspace 唯一业务提交核心：session→profile 锁序，核 owner/base/request/attempt/status/lease，先父 flush 后消息与证据；最新画像值上应用去重后的本轮增量。空 delta 不改节点或 profile revision；业务状态、两消息、证据、完整 response_json 同一事务一次 commit。
3. 旧 `api._persist` 保留公开签名并单向委托 legacy 核心；严格 legacy 仍 int/None、403 传播、重试一次、全回滚。已绑定 profile、任何 schema_version 键及坏 JSON 均在写入前拒绝旧整图保存，owner 检查在准入检查之前。
4. infra DirtyFlag 持唯一 `(user_id, profile_id)` 字典/锁/TTL，API 仅 reexport。None 是独立旧用户 key。成功/失败仅清/标本画像，unknown commit 已实际成功的恢复分支也清本画像。
5. main lifespan 装配真实 Service，关闭时 best effort 中断；缺装配明确 503。JWT 依赖的读事务也在委托前 rollback，生成与真实摘要不持该连接。
6. schema1 切点实际变化时原管理事务清 last_question、stage=init，保留 count/summary/mode/扩展/view；same-node 不清待答。legacy 首次保留原文历史，但不声明旧节点待答、不产旧题评估。

没有改 Agent、prompt、Task7 NewStackResult、前端、迁移历史、新表/列、raw、主计划、账本或全局设置。ProfileMasteryStore 不反向 import harness；Service/core 不 import API。

## 新增文件：打包审查不能只看 git diff

以下当时为未跟踪文件，普通 `git diff` 不包含：

- `app/orchestration/conversation_service.py`
- `app/orchestration/turn_commit.py`
- `app/infrastructure/storage/dirty_flag.py`
- `tests/api/test_conversation_transactions.py`
- `tests/integration/test_workspace_concurrency.py`

已修改产品文件：`app/api/{chat.py,chat_stream.py,sessions.py,_persist.py,_dirty_flag.py}`、`app/models/schemas.py`、`app/main.py`、`app/orchestration/session_service.py`、`app/infrastructure/storage/{chat_request_store.py,profile_mastery_store.py}`。已修改测试为 brief 允许的十个 API/legacy 测试文件，详见迁移表及 manifest。

## 8.1–8.5 需求 → 测试 → 结果

下表 API 测试未写全路径者位于 `tests/api/test_conversation_transactions.py`，PG 测试位于 `tests/integration/test_workspace_concurrency.py`。所有表内最终测试均实际运行通过；不是以模块存在、import 检查或 mock 返回值替代业务红灯。

| 阶段/需求 | 实际测试或证据 | 最终结果 |
|---|---|---|
| 8.1 严格字符串、4000/4001、空 sid/rid、UUID、bool/负版本拒绝、浮点评分 | `test_reject_invalid_teaching_request`、`test_original_message_and_finite_fractional_score` | PASS |
| JWT 唯一身份、body user_id 忽略、缺认证/NULL/异主模型零调用、本人未绑定409 | `test_real_http_lifespan_atomic_state_and_replay`、`test_unauthenticated_never_calls_model`、`test_model_never_runs_for_inaccessible_or_unbound_session`；原三 ownership 测试 | PASS |
| 新自定 sid、默认容器无旧图拷贝 | `test_new_client_id_gets_owned_default_container_without_old_graph` | PASS |
| 默认画像真实唯一竞争、两用户默认画像不冲突 | PG `test_default_profile_unique_race_is_separate_from_session_claim`、`test_two_users_default_legacy_profiles_do_not_conflict` | PASS，真实不同 PID、唯一约束等待 |
| 同一未知 sid 首发同 rid 仅一次 acquired/runner；不同 rid busy；异主403 | PG `test_unknown_session_pk_race_rechecks_owner_payload_and_busy` 三参数分支 | PASS，真实 PK 等待及完整事务重读 |
| 原文 UTF8 与确定 JSON/hash、同 id 完成后 state/node 已前进仍重放、显式原 base 可重放/不同 base/profile 冲突 | `test_payload_hash_uses_exact_original_utf8_canonical_json`、`test_two_real_turns_then_old_http_and_sse_replay` | PASS；真实 PATCH 切点后 HTTP/SSE 仍重放旧完整响应，模型数不增 |
| 普通 failed 重发仅读、显式 retry 保留 payload/hash/base；CAS与旧 attempt 不覆盖新 attempt | `test_failed_resubmit_is_read_only_and_explicit_retry_keeps_original_payload`；PG `test_retry_attempt_cas_and_old_owner_cannot_interrupt_new_attempt` | PASS |
| retry 预检之后实际状态竞争仍409 | `test_retry_rechecks_real_state_race_and_returns_conflict_http` | 真实 RED→GREEN，stale_context 不再漏成500 |
| profile/version/schema/graph 预检分类且模型零调用 | `test_preflight_profile_version_schema_graph_errors_are_before_model` 六分支 | PASS |
| GET/snapshot/同 id 恢复过期，未过期不改、异主不改 | `test_get_snapshot_and_same_request_recover_expiry_in_real_transactions`；真实 restart probe | PASS |
| 8.2 真 lifespan、真实 SessionService/Agent/LLMService/_call_with_span，两轮 HTTP/SSE连续历史 | `test_real_http_uses_previous_question_in_actual_agent_prompt`、`test_two_real_turns_then_old_http_and_sse_replay` | PASS，仅替最底层受控 client |
| 超50完整历史、真实 teaching_summary、候选边界/扩展、摘要及Agent调用无物理连接checkout | `test_full_history_summary_uses_real_llm_and_preserves_extensions` | PASS，62条历史→50条连续省略前缀；实际最低层 client 前检查 checkout 集合为空 |
| 节点全集与20展示分离，draft/pending不入历史，成功不清draft/version | `test_graph_full_nodes_are_loaded_but_prompt_shows_only_twenty`、`test_pending_text_and_draft_never_enter_actual_llm_prompt` | PASS，30/30/20，draft及view version保留 |
| v1.3 摘要失败安全缩减、元数据随response原子保存，后续状态前进后HTTP/SSE逐值重放 | `test_summary_failure_metadata_is_persisted_and_http_sse_replay_is_exact` | PASS，真实低层 client 仅摘要抛错，summary_failed 持久化，边界不推进 |
| v1.4 A→B回答旧A题时B零评分/零证据/零revision，成功往返仍增；新B题下一轮才评分 | `test_switch_b_old_a_answer_has_no_delta_until_b_new_question` | PASS，真实 PATCH/API/DB/Agent |
| same-node保持待答；legacy首次无旧题评分，历史原文保留 | `test_switch_node_invalidates_pending_question_only_when_changed`、`test_legacy_first_turn_has_history_but_never_old_node_assessment` | PASS |
| 计数区分：legacy一完整对、孤立turn3、next_turn4，API count2而非内部99/索引+1 | `test_legacy_first_turn_has_history_but_never_old_node_assessment`、原 `test_chat_turn_count_is_teaching_round` | PASS |
| 8.3 第二消息/evidence/delta/snapshot/request complete/commit六点失败全回滚 | `test_all_business_writes_rollback_at_each_failure_boundary` 六参数分支 | PASS，重开连接逐项核两消息/证据/分数/count/state/nextturn/response；管理failed另事务 |
| 0/100/浮点评分，重复同node delta只+1保留最终项、唯一证据、业务commit恰1 | `test_incremental_scores_once_and_only_one_final_business_commit`、`test_duplicate_node_delta_uses_final_item_and_one_evidence` | PASS |
| 伪造 question/answer引用、bool/NaN分数、外node拒绝且无半写 | `test_forged_delta_never_partially_saves` 五分支 | PASS |
| workspace旧persist保护、坏JSON不重置、原strictlegacy父flush/一次commit/回滚/owner重验 | `test_legacy_wrapper_cannot_replace_workspace_state`、`test_strict_legacy_invalid_json_is_never_reset_or_written`、`tests/api/test_persist_turn.py` | PASS，旧图save与业务写零调用 |
| DirtyFlag同类/同状态及画像隔离、旧TTL兼容 | `tests/api/test_dirty_flag.py`、`test_dirty_profiles_do_not_clear_other_profile_or_legacy` | PASS |
| 8.4 真实Store的30续租/180lease/300最大预算、旧线程晚回拒提交 | `test_renew_30_lease_180_deadline_300_and_late_worker_fence` 及 PG 同名包装 | PASS，不 mock claim/renew/interrupt/complete |
| 最终DB等待后使用当前clock校验lease，最终commit前再核300，超预算不派发新线程 | `test_final_store_lease_validation_uses_clock_after_actual_database_wait`、`test_final_business_commit_cannot_cross_300_second_deadline`、`test_context_load_crossing_deadline_never_dispatches_generation`；前两项另有PG包装 | 各真实 RED→GREEN，超限/过期无业务保存 |
| 载入旧attempt即使active rid相同也拒绝 | `test_context_load_rejects_old_attempt_even_same_active_request` | 真实 RED→GREEN |
| HTTP实际http.disconnect、SSE工作线程刚启动后断开，中断先胜后1000晚事件丢弃、无晚写/未取回异常 | `test_real_asgi_disconnect_interrupts_and_closes_late_worker_events`；PG `test_real_pg_interruption_wins_before_old_worker_returns` 两路径 | PASS，SQLite与真实PG均运行 |
| SSE首yield前、未启动生成的纯数据载入屏障；重复running订阅不能取消原owned claim | `test_sse_disconnect_before_generation_with_explicit_loaded_barrier`、`test_sse_disconnect_before_first_yield_fences_only_owned_execution` | PASS，尚未启动与刚启动分别用明确屏障 |
| commit先持session锁→真实ASGI断开→中断等待真实行锁→commit胜出completed不覆盖 | PG `test_commit_lock_wins_real_asgi_disconnect_and_completed_is_preserved` HTTP/SSE两路径 | PASS，pg_blocking_pids/pg_locks实证 |
| commit抛连接结果未知：实际提交后读completed重放；提交前故障全回滚 | PG `test_commit_connection_error_reads_actual_completed_before_failure` 两分支 | PASS；actual commit后的DirtyFlag清理有独立业务红灯修复 |
| 8.5 同profile不同session同node两真实并发、最新值各+1、最后提交分数、其他node逐列不变 | PG `test_same_profile_parallel_assessments_use_latest_node_and_real_profile_lock` | PASS，count/revision/profile revision各+2、两消息证据；生成阶段第三物理连接能NOWAIT取得session/profile锁 |
| 两JWT同名画像/节点互不污染、外用户读/写/retry拒绝 | PG `test_two_jwt_users_same_named_profiles_are_isolated` | PASS，实际JWT与API |
| 归档发生在生成后，最终提交整轮拒绝 | PG `test_archived_node_after_generation_rejects_whole_commit`；Task6双向锁回归 | PASS |
| 真实容器重启后消息/response/证据仍在，expired恢复/unexpired仅读，外账号拒绝 | `restart_probe.py prepare` → 主会话核独占restart → 新Python进程 `verify` | 第二轮全PASS；不是仅重建engine替代重启 |

## 重启事实与首轮夹具失败

专用容器实际有仅本容器使用的私有 Docker volume，与最初“无卷”交接不符。主会话先因无卷断言中止，后只读核专用 label、仅127.0.0.1:55440、卷独占、无其他 client，才执行 restart 与 pg_isready。未动业务 PG5432/app8000/sites55439；没有删 Docker volume。

首轮库 `workspace_task8_512abfae5c9847199a5d3a12c0a4427a` 的 future lease 仅1小时；checkpoint UTC15:57:43，首次 verify UTC17:14:57，已经77分钟。服务正确把该记录当过期请求恢复，因而“仍running”夹具断言失败。只读诊断时已6056秒。原 metadata、失败verify、诊断日志保留，首轮自建库随后单独 drop。

第二轮新库 `workspace_task8_bffb3577ae00485d9d9503639f00f752` 明示 **测试夹具 future lease=24h**，仅用于跨审批等待验证重启耐久/未过期仅读，绝不是生产租约设置。生产180/30/300另由可控clock + 真实Store/PG验证。主会话再次核独占并restart后，新进程实核：postmaster UTC16:42:54→18:46:38；消息4、证据1、原completed response逐值相同；expired interrupted/attempt2；unexpired running/attempt1且active保留；外用户403。verify exit0后 drop 第二轮自建库。两轮库都已清理。

原始材料：`restart-controller.log`、`restart-controller-second.log`（主会话）、`restart-prepare.log`、`restart-verify-first-expired.log`、`restart-time-diagnostic.log`、`restart-checkpoint-first-expired.json`、`restart-prepare-second.log`、`restart-verify-second.log`、`restart-checkpoint-verified.json`、`restart_probe.py`。

## 旧测试断言迁移映射

| 原文件/断言 | 新落点和保留方式 |
|---|---|
| `test_persist_turn.py` 原公开API、int/None、父flush、一次commit、graph、rollback、owner重验、日志 | 仍调用 `app.api._persist.persist_turn`；只把实现内部patch目标迁至 `app.orchestration.turn_commit`，原断言保留。workspace/badJSON另加真实DB零写保护。 |
| `test_dirty_flag.py` 原API入口、TTL与清理 | 仍测兼容入口；时间patch指向唯一infra真实owner，原行为/状态断言保留；新画像隔离另测。 |
| `test_chat_persist_happy_path` 标题、owner、reply、两消息角色/原文/turn0 | 同名测试现用真实JWT/Service/隔离DB，完整逐值断言保留，移除旧路由三段共用AsyncSession假设。 |
| `test_chat_persist_second_turn` 四消息、0/0/1/1、第二轮原文、标题不改 | 同名实际HTTP/Service测试完整保留。 |
| `test_chat_persist_error_resilience` 第二消息失败、200/persisted=false、零消息 | 从旧MessageStore.add mock迁至实际第二条INSERT故障；完整回滚保留。**原“失败仍返回生成reply”按已批准新契约改为reply空串/status=failed**，未伪装兼容。六处更深失败另有真实DB测试。 |
| `test_chat_turn_count_is_teaching_round` API1不等于内部11 | 同名实际HTTP测试保留；异常旧历史索引4但count2另测，未把内部协作次数当教学次数。 |
| ownership原三测试名、NULL/异主403、精确旧detail、模型零调用、零消息 | 三个原名全部恢复，使用真实JWT/Service/DB的共享fixture；403精确`无权写入该会话`也保留，并真实RED→GREEN恢复措辞。SSE仍在生成前以403返回。 |
| anonymous三测试401、graph不构造、无消息 | 原名与断言保留；MasteryGraph patch迁至当前真实owner，不让无JWT进入业务。 |
| HTTP/SSE new_stack e2e原真实Agent/LLM mock、RAG开关与fail-fast、55分、默认sid | 装配真实Service及隔离DB；55分fixture改为真实绑定节点+待答问答，保留原55断言，不伪造无节点评分；默认sid/RAG断言保留。 |
| SSE incremental原agent_event/TutorAsked/final/reply/教学count1≠内部11 | 同名测试改为具备真实候选的runner，事件投影断言保留并加persisted=true。真实Agent两轮链另有低层受控client测试。 |
| SSE error原AGENT_ERROR、通用message、retryable=false、无final | 同名完整保留，另加status/attempt/persisted真实状态断言；不泄露agent boom或未提交回复。 |
| Task6 workspace snapshot/重试spy原纯读接口与短事务断言 | fixture增加真实Service。原过期running补齐真实active占用；GET新契约改断言interrupted/lease_expired=false/active清空，纯SessionService读逻辑不变。retry spy补真实恢复委托，仍验证owner前置/事务结束/参数与未修改业务状态。 |

## Task9只读核对用准确DTO与错误形状

`ChatRequest`：`message` 必填严格str/最长4000/原文不strip；`session_id` 严格str 1..64、默认`s-<uuidhex>`；`user_id:int|null`兼容但忽略；`request_id:str|null`可选、非空1..64、缺省由Service UUID；`profile_id:str|null`规范UUID；`expected_state_version:int|null`严格非bool非负。请求不能覆盖active node，选点仍走已有PATCH。

`ChatResponse` 旧字段：`reply:str`、`session_id:str`、`mastery_score:finite float|null`、`turn_count:int|null`（已提交完整教学往返）、`mode_path:list[str]|null`、`cost_est_usd:float|null`、`stack:'new'|null`、`persisted:bool`。新增可选：`request_id`、`state_version`、`profile_revision`、`active_node_id`、`status`、`attempt`、`error_code`、`context_reduced`、`reduction_reasons:list[str]|null`。

- 完成：status=completed、persisted=true，完整JSON与业务同事务保存；HTTP/SSE final/GET response_json/同rid重放保留原值。
- 未确认：running/failed/interrupted，reply=""、turn_count=null、persisted=false；缩减元数据null，不把未测量伪称false。HTTP200仅表示读取状态成功。
- 401：JWT/OAuth依赖；403：owner拒绝，detail为字符串（写入口保留`无权写入该会话`）。404：会话/本人画像不存在，detail字符串。422：Pydantic格式/约束错误。
- 409：`{"detail":{"code":"payload_conflict|stale_context|session_busy|profile_context_mismatch|legacy_session_unbound|attempt_conflict|lease_expired|..."}}`，沿原WorkspaceConflict分类。未知/非法schema不降级无context重跑。
- 缺Service503：`{"detail":{"code":"conversation_service_unavailable"}}`。composition503：`{"detail":{"error_code":"backend_unavailable","message":"检索服务当前不可用"}}`。
- SSE：预检403/409发生StreamingResponse前；开始后保留agent_event，running为type=status，failed/interrupted为type=error并含code/error_code/message/retryable/request_id/status/attempt/persisted=false；只有确认已提交才type=final。completed重放仅一条final，没有耐久事件重放承诺。

## 实施差异、已知边界与待办

- 时间注入具体化为 `Clock.monotonic_now/utc_now/wait_until`。Store `now` 保持可传datetime且新增支持clock provider，在真实锁/查询之后取当前UTC，避免最终事务沿用进入时的旧时间；Service还在载入后、生成循环、实际commit前检核预算。这是同一已批准30/180/300契约的实现，不是新增生产超时参数。
- Python线程取消不等于物理停止；关闭callback/订阅并以attempt/status/lease/base阻挡晚写。取消清理使用AnyIO shield，最终commit和中断以真实session行锁次序裁决，已发出的未知提交结果优先用新连接读completed。
- DB管理/加载等待未配置独立的数据库锁超时或300秒HTTP响应SLA；当前300秒是教学预算及提交准入栅栏。数据库调用本身不返回时，管理清理/响应结束可能等待数据库。此边界不以clock测试冒称“任何DB故障下300秒必返回”，请独立review明确评估。
- 初次超长批处理在创建进程前被Windows os206拒绝，**没有执行其中任何产品写入或测试**；改用短批次/native apply_patch后执行。一次新增PG测试括号SyntaxError是测试作者错误，不算业务红灯。首轮SSE“无屏障立即断开必零模型”断言过强，后拆为明确的未启动/刚启动屏障；相关原日志保留。
- 未跑真实模型、未部署公网、未宣称教学效果/完整MVP。真实模型验收仍Task13，前端Task9未编码。本代理未提交、未更新README/账本/计划/raw、未改既有README142行和资产34行脏改动。
- **待主会话**：包含五个新增未跟踪源码文件打包fresh review；审查PASS后维护README、按明确文件提交。完整套件既有retriever失败和Starlette warning仍在，未顺手修复。

## Round2：I1 显式retry HTTP断连修复（code fix 1 of 5）

本节追加记录本轮事实，不改写前轮记录。唯一需求为 `task8-round2-brief.md` v1.1，实核SHA256为 `74d5dadc6fba3906412a98be86799e9254cf58160f5a99c92b6ecb755fa463c5`；主会话已交接三层计划独立PASS及编码授权。修复对应 `task8-code-review.md` 唯一Important I1。实现侧验证通过；独立代码复审仍由主会话安排，不在此自记审查PASS。

### 实际变更范围与实现

仅新增 `app/api/_disconnect.py`，修改 `app/api/chat.py`、`app/api/sessions.py`、`app/orchestration/conversation_service.py`、`tests/api/test_conversation_transactions.py`、`tests/integration/test_workspace_concurrency.py`、`tests/unit/api/test_workspace_sessions_api.py`，共7文件。原25文件中仅上述6个既有文件SHA变化，其余19个逐一哈希不变。没有修改Store、turn_commit、main、SSE实现、DTO、schema或迁移，也没有改README、账本、计划、raw、前端或提交。

- 共用异步contextmanager先顺序调用Request.is_disconnected；已断则设置同一event，否则只建立一个watcher，循环仍按0.1秒观察。正常、异常和取消退出均设置该局部event使循环结束，再cancel并在AnyIO shield中await watcher。shield仅覆盖局部清理。
- 普通/chat和retry共用此contextmanager；retry仍先JWT/owner/version/attempt预检及能力503，再rollback依赖事务后委托。事件是observer产生的同一asyncio.Event，没有新增HTTP字段或错误形状。原chat.watch_disconnect未发现外部实际引用，故没有保留第二实现。
- `retry_turn`原五个必需关键字不变，仅追加可选`disconnect_event=None`，原样传run_claim。PreparedTurn存在后，管理commit与run_claim入口共同受CancelledError边界保护；退出原AsyncSession后，用shield中的独立连接核对user/session/request、running、attempt及active_request，再复用cancel_owned锁下复核。未提交、completed、新attempt或其他占用不被旧取消覆盖；独立确认异常只记录，留既有租约恢复，不伪造成功。
- 原180/30/300、最终业务commit、未知业务commit确认、线程晚结果隔离与锁次序保持。ChatRequest/ChatResponse及401/403/409/503形状均未变，前节DTO说明继续适用。

### 红绿、挂起与诊断的实际经过

1. `round2-red.log`：真实ASGI生成屏障断连、生成前已断、管理commit后run_claim入口前取消、管理commit实际完成但await未知时取消均出现真实状态断言失败；**4 failed / 1 passed，7.81s**。未提交对照保持原failed2通过，非模块存在性或导入红灯。
2. 首次最小接线后 `round2-green.log`：同5项 **5 passed，6.86s**。独立DB读数为中断先胜interrupted4/active=None/消息2；未提交仍failed2，实际提交后取消为interrupted4。
3. 首个主要组 `round2-affected-primary.log` 在新增observer正常退出场景未收尾；这不是测试通过，也不记为断言RED。保原session3250/PID60728及日志，唯一只读诊断见 `round2-observer-diagnostic.log`：polled=True/stopped=False，work等__aexit__，watcher cancelling=1仍在watch_disconnect→wait_for→event.wait，event=False。Starlette的is_disconnected内先取消CancelScope再await receive；外部cancel在该时点被合并，循环没有退出信号。只释放诊断自身捕获event后root完成、剩余任务0，证明等待关系。经主会话明确授权，仅原隔离测试session单次Ctrl+C，终态exit1；没有泛杀进程或重启PG。最终组启动前还核原PID已不存在。
4. 保留真实Request和单receive检查，将夹具改为有界观测：先等0.5秒，记录是否自然退出，失败后才set本例event收尾，最后断言exited_before_rescue。`round2-observer-red.log` **3 failed，6.68s**，正常/异常/取消均明确因“watcher未自行退出、需要救援”失败。没有在断言前设置event伪绿。
5. 在已批准的helper清理范围内，finally先set同event再cancel/await。最终主要组中三场景均无需救援，watcher_done=True、receive最大并发1、实际间隔约0.110/0.109/0.109秒。测试要求清理在0.5秒观测内完成，不把0.1秒轮询节奏宣称为任意故障下的响应SLA。

### 本轮需求—实际测试—结果矩阵

| 需求/边界 | 实际测试名（省略共同test_前缀） | 原日志与事实 |
| --- | --- | --- |
| retry生成中真实http.disconnect先胜，晚线程无写 | retry_real_asgi_disconnect_interrupts_before_worker_release | primary-final与PG；释放前interrupted4/active=None/消息2，业务快照逐值不变；释放后1000晚callback无loop错误、仍不变 |
| body正常解析后已断，runner零调用 | retry_disconnected_before_generation_never_starts_runner | primary-final；interrupted4/消息2、runner=[] |
| 管理commit已完成、run_claim未进入时task.cancel | retry_task_cancel_after_management_commit_before_run_claim | primary-final；新连接先证running3，再取消为interrupted4，runner零调用，业务逐值不变 |
| 管理commit未知取消，实际前/后两对照 | retry_management_commit_unknown_then_cancel[False/True] | primary-final；前者failed2/无active，后者先证running3再interrupted4；都零runner/业务写；未mock Store/cancel_owned/_read_claim |
| 清理读取后至再次session锁之间已有完成/新attempt | retry_cancel_cleanup_rechecks_after_read_before_session_lock[completed/new_attempt] | primary-final；completed3/消息4或running5/原active/消息2均保持；实际Store与commit，未放宽原attempt栅栏 |
| observer正常/异常/取消清理、单receive、100ms节奏 | http_disconnect_observer_awaits_watcher_with_single_receive[normal/error/cancel] | observer-red→primary-final；真实Request、有界失败后才救援，GREEN无需救援，watcher已await |
| 正常retry只完成一次、原payload、精确重放 | retry_connected_completes_once_and_replay_is_exact | primary-final；completed3/persisted=true/教学count2，消息4、证据1，保存response逐值相等、重放不再runner |
| 401/异主403/attempt409/base409/busy409在模型前 | retry_precheck_errors_never_start_generation（5例） | primary-final；runner与observer均零调用，原request/会话/业务不变 |
| 预检503、owner优先、同event、依赖事务释放、原参数 | retry_precheck_unavailable_is_unchanged_and_spy_releases_transaction | primary-final；原断言保留，新增核observer同一Event、委托时所有依赖db无事务；失败预检不另建observer |
| Service重验冲突409后observer收尾 | retry_rechecks_real_state_race_and_returns_conflict_http | primary-final；真实切点竞态，原409断言保留，观察task均done |
| retry最终事务先持session锁，断连不能覆盖成功 | commit_lock_wins_real_asgi_disconnect_and_completed_is_preserved[retry] | PG；真实backend blocker1163/waiter1165、granted=False，放行后completed3/persisted=true/消息4/证据1；原HTTP与SSE变体均保留 |
| PG中断先胜及原未知commit/旧owner保护 | real_pg_interruption_wins_before_old_worker_returns[retry]；原commit_connection_error_reads_actual_completed_before_failure、retry_attempt_cas_and_old_owner_cannot_interrupt_new_attempt | PG；retry在worker放行前interrupted4/消息2；原HTTP/SSE、真实commit前后、旧attempt不能覆盖新retry断言全部保留并通过 |

### 最终命令与结果

完整测试命令、日志及句柄见证据目录 `round2-commands.md`。所有DB/API测试使用原生require_escalated和既有.venv；SQLite仍为独立文件、NullPool、逐连接FK ON，PG仍每例随机workspace_task8_uuid数据库、只删本例；本轮未重启容器，未触业务PG5432/app8000/sites55439。

| 最终组 | 结果 | 原日志 |
| --- | --- | --- |
| transactions + workspace_sessions_api | **97 passed，50.53s** | round2-affected-primary-final.log |
| anonymous / ownership / persist / stream error / realtime | **12 passed，7.71s，1既有Starlette warning** | round2-affected-routes.log |
| 真实PG integration（原18+retry两变体） | **20 passed，45.92s** | round2-pg.log |
| 7个本轮文件py_compile、限定git diff --check | **7编译通过 / diff-check exit0**，仅CRLF提示 | round2-final-verification.log |
| 独立PG维护连接只读检查 | **剩余workspace_task8测试数据库[]** | round2-final-verification.log |

最终三组共129项执行全部通过；初次5项绿灯为阶段证据，不重复相加。按本轮明确范围未重跑全库旧失败；前轮已记录的retriever context_precision=None与旧warning未修。没有安装依赖、真实模型、线上部署或Task9编码。

### 全源最终冻结与交接

**全源（包含所有tests）已冻结可审**：`2026-10-26T06:13:11.161084+00:00`，完整26文件SHA在 `round2-code-freeze-manifest.json`。HEAD仍 `75be6015c331185dea34dc8910e5646c6663f29e`，分支仍 `codex/frontend-ui-optimization`。该时点后不再修改源码/tests；本节及round2命令证据是随后追加的文档记录。

当前全部未跟踪产品/测试共6个（前节“五个”为round1历史）：`app/api/_disconnect.py`（本轮新增）、`app/infrastructure/storage/dirty_flag.py`、`app/orchestration/conversation_service.py`、`app/orchestration/turn_commit.py`、`tests/api/test_conversation_transactions.py`、`tests/integration/test_workspace_concurrency.py`。打包不能只看git diff。待主会话基于round2-base与最终manifest做精确fixdiff并独立复审；本代理未提交，README仍由主会话在审查PASS后维护。300秒预算/DB等待、物理线程不保证停止、真实模型及部署等前节边界继续有效。

## Round3：R2-N1 首次探测隔离父任务取消（code fix 2 of 5）

唯一需求为 `task8-round3-brief.md`，实核SHA256 `437df2114f1ed3f8791f6cd7ae1e19e16b0f1af27ced3e6f4b3806213a7dafcc`；主会话已交接三层计划独立PASS和执行授权。`task8-round2-code-review.md` 已判原I1为ADDRESSED，本轮仅修新P2 R2-N1。以下为实现侧验证事实，独立代码复审仍待主会话安排。

### 范围与最小实现

仅修改 `app/api/_disconnect.py` 和 `tests/api/test_conversation_transactions.py`。与round3真实snapshot及round2最终26文件manifest比对，只有这两文件变化，其他24份源码/tests逐字节哈希不变；没有改Service、Store、turn_commit、chat/sessions路由、SSE、DTO、schema/main、README、账本、计划、raw或前端，没有提交或派子代理。

首次 `Request.is_disconnected()` 由独立一次性probe task执行，父handler只`await asyncio.shield(probe)`。probe创建、等待、watcher创建和yield全部位于同一try/finally；probe返回后才可创建watcher，因此receive不并发。finally先set局部同一event，再对尚未完成的owned probe/watcher各cancel一次，并在既有AnyIO shield中gather全部已创建task，包含已完成task结果。没有直接await未shield的probe，没有shield业务体，没有Task.uncancel或取消计数改写，没有新全局注册表/取消状态机。原100ms循环及已断开event语义保持。

### 精确RED与GREEN

新增 `test_initial_disconnect_probe_propagates_parent_task_cancel_before_business` 使用真实Starlette Request：先正常消费完整body，handler在调用observer前保存父task；首次探测receive通过loop.call_soon取消该闭包父task，明确不使用current_task作为取消目标。receive内当前task仅用于记录真实probe/观察任务引用。1秒有界等待，只有失败后才允许夹具救援，并要求最终rescue_used=False，不能把Timeout或救援后的完成当成功。

- `round3-red.log`：**1 failed / 81 deselected，4.39s**。父cancel返回True后，旧helper仍返回`business body ran`，失败在“应传播CancelledError”的真实行为断言；不是收集、模块缺失或超时红灯。
- `round3-helper-green.log`：**6 passed / 78 deselected，2.39s**。精确用例记录`cancel_requests [True]`、`business_entered []`、`outcome CancelledError`、`owned_done True`、`single_receive 1`、`rescue_used False`。修复后取消目标仍是显式捕获父handler，不因current_task已变为probe而形成假绿。
- 首次probe异常对照保留同一个ValueError对象传播、业务未进入、owned task均done；首次已断开对照在yield前event=True、只观察一次，不启动长期观察。此helper对照没有DB，不将其表述成已实测数据库回滚；真实retry已断开零runner由原API测试另证。
- 原normal/error/cancel三模式全部保留旧断言，并从真实receive记录probe与watcher，核父handler不参与receive、两个owned任务均done、最大receive并发1、原异常类型保持、rescue_used=False。配置仍0.1秒，本次主要组采样约0.094秒，不宣称任意故障下绝对响应时限。

### 本轮需求—测试—证据矩阵

| 需求 | 实际测试 | 结果/日志 |
| --- | --- | --- |
| 首次Request内部checkpoint取消父任务，业务零进入 | initial_disconnect_probe_propagates_parent_task_cancel_before_business | RED→GREEN；父cancel=True、CancelledError传播、业务[]、真实owned task均done、无救援 |
| 首次等待阶段异常及已断开 | initial_disconnect_probe_failure_and_already_disconnected[error/disconnected] | helper-green与primary；错误原样，已断开event在yield前True，单receive/任务完成/无救援 |
| 正常/业务异常/业务期取消及owned任务生命周期 | http_disconnect_observer_awaits_watcher_with_single_receive[normal/error/cancel] | helper-green与primary；原三模式断言保留，probe/watcher均done，父task不是receive消费者 |
| 真实retry生成前已断、生成中http.disconnect、管理commit确认/未知取消 | 原retry_disconnected_before_generation_never_starts_runner、retry_real_asgi_disconnect_interrupts_before_worker_release、retry_task_cancel_after_management_commit_before_run_claim、retry_management_commit_unknown_then_cancel | primary；runner零调用/中断先胜、未提交仍failed2、实际提交后interrupted4；未用精确无DB探针代替真实API/Store事务 |
| completed与新attempt不被旧取消覆盖，鉴权/预检与事务释放 | 原retry_cancel_cleanup_rechecks_after_read_before_session_lock、retry_precheck_errors_never_start_generation及workspace_sessions_api | primary；completed3/消息4与新running5/消息2保留；原403/409/503、同event与依赖无事务断言保持 |
| 真实PG retry提交先胜、中断先胜、未知commit及旧attempt | 原test_workspace_concurrency全部20例 | PG；retry blocker1772/waiter1774、granted=False后completed3/persisted=True/消息4，另生成中interrupted4/消息2；原HTTP/SSE和未知commit/attempt对照均保留 |

### 实际最终验证

完整命令与运行句柄索引见 `docs/delivery/study-workspace-goal/evidence/Task8/round3-commands.md`，原日志均为round3-*。DB/API走原生require_escalated、既有.venv，无依赖安装、无sleep、无活跃命令重发或进程中断。本轮未重启PG，仍只用127.0.0.1:55440每例随机workspace_task8_uuid数据库，SQLite仍独立文件/NullPool/FK ON；未触用户默认DB、业务PG5432/app8000/sites55439。

| 最终组 | 实际结果 | 原日志 |
| --- | --- | --- |
| 事务API + workspace_sessions_api | **100 passed，44.75s** | round3-affected-primary.log |
| 原anonymous/owner/persist/stream error/realtime | **12 passed，10.24s，1既有Starlette warning** | round3-affected-routes.log |
| 原真实PG全部20例 | **20 passed，45.94s** | round3-pg.log |
| 两文件语法、真实snapshot差异及26哈希范围 | **2文件编译通过；仅2允许变化/其余24不变** | round3-final-verification.log |
| PG维护连接只读查残留 | **workspace_task8测试数据库[]** | round3-final-verification.log |

两份文件仍未跟踪，因此本轮没有用空的tracked git diff --check冒充检查：分别对round3真实snapshot运行git diff --no-index --check，两次实际exit1表示存在差异，stdout均无whitespace-error；helper仅有CRLF提示。另逐条检查实际新增行尾随空白，通过。snapshot自身SHA亦逐一等于round2冻结manifest。

最终三组共132项执行通过；6项helper专项为先行阶段验证，不重复相加。遵从本轮范围未重跑全库；前轮已记录的retriever context_precision=None旧失败和旧warning没有修，也不宣称本轮完整套件全绿、真实模型或部署已验收。原300秒教学预算/DB等待及物理线程边界不变。

### 全源（含tests）最终冻结

冻结UTC **2026-10-26T11:25:03.259537+00:00**，26文件SHA清单为 `round3-code-freeze-manifest.json`；HEAD仍 `75be6015c331185dea34dc8910e5646c6663f29e`，分支仍 `codex/frontend-ui-optimization`。该时点后源码/tests没有再变更，本节及命令索引仅为随后追加文档。

本轮没有新增产品/测试文件，全部未跟踪产品/测试仍为前节所列6个（manifest逐项标注）。`round3-final-verification.py`仅为evidence中的实际核验脚本，不属于产品/测试。**全源含tests已冻结可审**；待主会话从round3-base生成两文件精确fixdiff交原审阅者，独立PASS后由主会话维护README/账本。本代理未提交，不再追加测试或源码。
