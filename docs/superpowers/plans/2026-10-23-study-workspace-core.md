# StudyAgent 页面终稿与核心功能补足实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 codex/frontend-ui-optimization 上将纸感书房终稿实现为真实的多会话、可恢复教学、共享主题画像与私有知识库产品。

**Architecture:** 保留 app/ 新栈与短连接分阶段教学；新增用户所属主题画像与版本化会话状态，以请求幂等和原子回合提交保证恢复一致性。React 按会话标识维护独立状态，所有页面与画像浮卡读取同一真实接口。

**Tech Stack:** Python≥3.11、FastAPI、Pydantic V2、SQLAlchemy async、Alembic、PostgreSQL、React18、TypeScript、Vite、pytest、Vitest；浏览器与DOM测试仅新增开发依赖。

**Spec:** [三层实施设计原稿](../../../superpowers/frontend-ui/2026-10-23-final-implementation-raw.md)，由其开头列出的需求及终稿逐项追溯。后续网络/文档自动规划单列于 [第二阶段计划](2026-10-23-knowledge-planning.md)。

## 全局约束

- 当前核查基准为分支 codex/frontend-ui-optimization、HEAD d0584d9；执行前重新检查，不假定另一工作区或main的修复已出现。
- 当前HTML已定稿；不再回到候选方案，不复制模拟数据、固定分数或固定回复进正式页面。
- 全程中文；按任务优先子代理实现、主会话审阅，共享文件任务串行；不创建另一个用户聊天。
- 第一阶段不实现全网搜索、文件上传或LLM自动规划，不以此阻塞核心教学；第二阶段不是被删除的需求。
- 新功能只在 app/；依赖方向及Agent事件所有权保持，Curator不调用LLM。
- JWT归属、数据库外键、版本校验、请求幂等均为后端约束。SQLite事务测试必须 PRAGMA foreign_keys=ON。
- 父会话先flush；两条消息、教学状态、画像证据与完成结果一次commit，注入失败完整rollback。
- 每次完成任务检查更新README。git add只列明确文件，禁止add -A和共享HEAD amend；不推送/部署。
- 长命令每30秒主动轮询进度，不使用sleep强等；平台失败同动作最多重试一次。已知沙箱嵌套按AGENTS处理，不修改全局权限。

## Review Focus

1. 同一主题两个会话同时更新同节点，不丢失增量或重复练习计数——Task8 PG并发测试。
2. 数据库成功后HTTP/SSE断连，重试同request只返回既有结果；旧attempt晚结束不能再提交——Task8故障注入。
3. 草稿异步保存晚于切会话/退出/换账号，不能覆盖其他会话或泄露另一账号——Task10和Task13。
4. 旧NULL owner、同名知识点及已存在legacy数据重复迁移，不误归属或丢图谱——Task2/3迁移测试。
5. 短视口、481px窄面板、展开浮卡和resize叠加，账号、输入框仍可达，鼠标拖后不误点击——Task12浏览器验收。

## 第一层：实施模块总览

顺序：基准冻结 → 无检索普通教学 → 数据与迁移 → 资源/API → 连续上下文 → 原子教学闭环 → React终稿 → 恢复与交互 → 真实验收。

第一阶段产物应能独立使用：用户登录、创建主题画像/知识点、创建多会话、来回切换、重新登录继续之前的问题、查看来源明确的真实画像、管理私有文本知识库。没有上传功能时不保留伪造的上传成功交互。

## 第二层：子模块与文件责任

| 子模块 | 主要文件（新增标“新”） | 契约与数据流 |
|---|---|---|
| 类型与表 | app/models/workspace_tables.py、workspace_schemas.py（新） | 新表统一注册到Base，DTO不依赖前端示例 |
| 画像存储 | app/infrastructure/storage/topic_profile_store.py、profile_mastery_store.py（新） | 按认证用户和profile作用域加载，增量提交 |
| 会话请求 | session_store.py、message_store.py；session_view_store.py、chat_request_store.py、workspace_store.py（新） | 稳定分页、版本、租约、幂等与界面保存 |
| 应用编排 | app/orchestration/session_service.py、conversation_service.py、profile_service.py（新） | API薄层调用；教学不长持DB连接 |
| 上下文 | app/harness/teaching_context.py（新），workspace_state.py、teaching_policy.py、assembly.py及Agent prompts | 历史消息→上下文→本轮评估→版本化快照 |
| 私有知识库 | app/infrastructure/storage/library_store.py（新），app/api/knowledge.py | DB/owner/name/description/text，保留旧外观字段 |
| API | app/api/topic_profiles.py、workspace.py（新），sessions.py、chat.py、chat_stream.py、_persist.py、profile.py、main.py | 归属/版本/状态码/兼容DTO |
| React壳 | web/src/components/workspace/（新），App.tsx、index.css、Sidebar.tsx | 真实路由，双栏独立滚动、右上入口、左下账号 |
| React状态 | web/src/api/{sessions,profiles,knowledge,workspace}.ts；store/workspace.ts、hooks/useDraftPersistence.ts（新） | 按会话分桶，按账号隔离，版本冲突不覆盖 |
| 画像浮卡 | web/src/components/profile/FloatingProfile.tsx、hooks/useFloatingProfile.ts（新） | 同源summary、A环形、hover/focus/touch/纵向拖动 |

表字段、错误策略、版本、接口路径、默认值以raw第二层为准；第三层任务列出函数名、输入输出和验证，不给实现代码。

## 第三层：可执行任务

### Task0：冻结终稿、建立基准与执行清单

**文件**：docs/delivery/2026-10-23-workspace-baseline.md（新）；当前HTML与raw仅纳入明确任务快照，不重绘。

**接口**：输入实际HEAD、状态与终稿；输出基准哈希、原有改动清单、现有测试结果，不创建产品能力。

- [ ] 记录 git branch --show-current、git rev-parse HEAD、git status --short 与终稿 Get-FileHash -Algorithm SHA256；确认当前分支，保护原有README/asset-inventory等变更。
- [ ] 用 uv run alembic heads、uv run pytest tests/ -q、npm --prefix web test、npm --prefix web run build 记录基线；未通过项逐项归因，不把历史测试数当当前结果。
- [ ] 检查 .env.example、pyproject和当前RAG开关；不读取或打印真实.env秘密；记录是否需Task1。
- [ ] 建立任务状态表，每项关联原始需求及验收。仅提交本任务证据、已授权终稿和原始设计的明确文件，不混入他人产物。

### Task1：接通默认无检索真实教学

**文件**：app/core/config.py、app/orchestration/assembly.py、app/harness/orchestrator.py、app/agents/retriever.py、.env.example、docker-compose.yml；tests/unit/orchestration/test_online_composition.py、test_assembly.py及路由器测试。

**接口**：沿用 [已存在的无检索计划](2026-10-23-rag-default-off.md) 的 rag_enabled=False、在线入口显式传值、低层参数默认兼容契约。只适配当前分支，不跨工作区盲目cherry-pick。

- [ ] 先增加测试：缺省不创建Retriever/Provider/embedding；规则和Conductor不能绕过开关；显式开启保留严格pgvector校验；HTTP/SSE两入口均使用同设置。
- [ ] 增加开启路径真实可见性断言：在线Retriever从服务端认证user_id构建VisibilityContext；拒绝payload覆盖和visibility=None，公共＋本人跨主题向量可见、他人私有不可见，不回退无owner过滤OCR/code。文本卡仅管理，不宣称教学检索已接入。
- [ ] 运行 uv run pytest tests/unit/orchestration/ -q 和对应路由器测试，确认新增断言先失败；若当前已等价具备，记录证据跳过实现而非重做。
- [ ] 最小实现开关、装配与动作过滤；复用原有安全错误，不静默把开启失败降为关闭。
- [ ] 同组回归通过；同步README及显式开关使用说明，提交明确文件。

### Task2：主题画像及历史迁移

**文件**：app/models/workspace_tables.py（新）、app/core/database.py的模型注册路径、alembic/versions/20261023_topic_profiles.py（新）；topic_profile_store.py、profile_mastery_store.py（新）；tests/unit/storage/test_topic_profile_store.py、tests/integration/test_workspace_migrations.py（新）。

**接口**：TopicProfileStore.create/get_owned；ProfileMasteryStore(db,profile_id)提供 save_nodes/load_nodes/save_edges/load_edges 的既有user_id签名，内部强制user/profile作用域。node_id采用UUID，不以标题做键。

本任务迁移只创建画像/节点/边；依赖chat_requests的profile_evidence表推迟至Task3创建，避免PG引用尚不存在的表。在线图谱仅推理用，Task8使用apply_assessment_delta，不整图save。

- [ ] 写失败断言：同用户两个画像同名节点互不污染；跨账号/跨画像外键被拒；未评估mastery=null。证据表唯一性在Task3验证。
- [ ] 写迁移断言：旧mastery图谱只进入各本人legacy画像；确定性旧topic→node映射，同名/长名不碰撞；再次执行迁移前置检查不重复复制；原表数据保留。
- [ ] 运行 uv run pytest tests/unit/storage/test_topic_profile_store.py -q 验证红灯；实现表、归属约束、迁移与Store，不修改已有历史表语义。
- [ ] 在临时SQLite外键开启和真实PG执行 upgrade head；节点、边、证据完整。downgrade若会丢新数据必须拒绝或先导出，不把破坏性回滚当日常操作。
- [ ] 更新README的数据模型与历史迁移边界，提交明确文件。

### Task3：会话、请求及界面状态数据模型

**文件**：workspace_tables.py、app/models/tables.py、alembic/versions/20261023_session_workspace_state.py（新）、session_store.py、message_store.py；chat_request_store.py、session_view_store.py、workspace_store.py（新）；tests/unit/storage/test_workspace_state_stores.py（新）。

**接口**：ChatRequestStore.claim/renew/complete/interrupt；Claim含attempt与租约；SessionViewStore.save(user_id,session_id,expected_version,state)；WorkspaceStore.save(user_id,expected_version,state)。具体字段见raw。

本任务在chat_requests和会话扩展之后创建profile_evidence，并验证request/node唯一、消息来源真实、user/profile/session/node归属约束，构成完整FK依赖顺序。

- [ ] 写失败断言：归属匹配；同request同payload重入仅一个claim；不同payload冲突；attempt失效不能完成；界面版本冲突409；位置比例必须0–1。
- [ ] 写未完成原文恢复断言：claim先存request_payload与base_state_version，尚无messages也可恢复用户原问题；pending内容不混入已提交历史、不显示为已保存回合。
- [ ] 写迁移断言：旧会话绑定本人legacy画像、保留消息，NULL owner不可claim；用消息最大turn_index+1回填next_turn_index，不能用len//2推算异常历史。
- [ ] 运行 uv run pytest tests/unit/storage/test_workspace_state_stores.py -q；实现两个版本空间与数据库约束；MessageStore返回稳定id/turn_index，不破坏旧消费者字段。
- [ ] 开启外键重跑并验证可序列化schema1 state；过期租约可标中断，旧完成结果不可写回。
- [ ] 更新README后提交明确文件。

### Task4：知识库真实持久化与账号隔离

**文件**：library_store.py、workspace_schemas.py（新）、workspace_tables.py、alembic/versions/20261023_private_library.py（新）；app/api/knowledge.py；tests/unit/api/test_private_knowledge_api.py（新）。

**接口**：LibraryStore.create/list/get/update/delete均显式消费认证user_id；保留KnowledgeResponse的id/name/description，增profile_id/content_text/source_type等兼容字段。

- [ ] 写失败断言：登录必须；A不能读改删B资源；伪造profile_id拒绝；创建、搜索、编辑、删除能在新DB连接读取；空白名称422。
- [ ] 运行 uv run pytest tests/unit/api/test_private_knowledge_api.py -q 确认红灯；移除API模块级内存Store，接入独立library_items新表，不盲复用KnowledgeTable.content映射。
- [ ] 保留旧知识资产不迁给当前账号；手动文本最大100000字符，name<=128、description<=2000，超限明确422；实现稳定分页及GET详情。
- [ ] 回归相关knowledge旧测试，按新增登录契约调整fixture，不能删掉隔离断言；更新README并提交。

### Task5：主题画像服务、知识点选择与摘要接口

**文件**：app/orchestration/profile_service.py、app/api/topic_profiles.py、workspace_schemas.py（新）；app/main.py、app/api/profile.py；tests/unit/api/test_topic_profiles_api.py（新）。

**接口**：ProfileService.create/add_node/update_node/get_summary；GET summary包含profile_revision、nodes、edges、recent_evidence、assessed_count/total_count、mastery_score(nullable)、metric_kind=assessed_mean。

- [ ] 写失败断言：新主题自动创建同名初始节点且null掌握度；手动节点标题可修改而id不变；不能改成另一用户画像；带证据节点只归档不硬删。
- [ ] 写摘要断言：节点80/null返回80且覆盖1/2；全未评估返回null而非0；只计算未归档节点；来源会话链接确有本人证据；空边不生成假图。
- [ ] 运行 uv run pytest tests/unit/api/test_topic_profiles_api.py -q；实现DTO与真实查询；保留 /profile/ 旧stats但新页面改用主题接口。
- [ ] 验证profile详情与summary同revision；更新README新增API并提交。

### Task6：会话与工作区API

**文件**：app/orchestration/session_service.py、app/api/workspace.py（新），app/api/sessions.py、main.py、workspace_schemas.py；tests/unit/api/test_workspace_sessions_api.py（新）、test_sessions_api.py、test_chat_session_ownership.py。

**接口**：SessionService.create/list_grouped/load_snapshot/save_view_state/set_active_node；原GET列表无group_by仍返回list；新分组分页为对象，profile组summary与组内cursor分开。

- [ ] 写失败断言：空会话立即可恢复；选择知识点必须属绑定画像；活动请求时改节点409；分页30条同更新时间以id稳定去重，空组可见。
- [ ] 写恢复断言：snapshot包含消息id/turn_index、teaching_state/view版本、画像引用和未完成request；消息向前翻页不重复。
- [ ] 增加POST requests/{request_id}/retry请求模型与路由：expected_attempt/expected_state_version；错误身份先拒绝。动作调用Task8服务，同request失败状态普通GET/重发不自动重跑。
- [ ] 写冲突断言：view expected_version过期409且旧草稿仍保留；workspace last_session不能指向他人；非法高度比例422。
- [ ] 运行 uv run pytest tests/unit/api/test_workspace_sessions_api.py tests/unit/api/test_sessions_api.py tests/unit/api/test_chat_session_ownership.py -q；实现并保持旧响应兼容。
- [ ] 更新README路径/字段/错误码并提交。

### Task7：连续上下文、稳定知识点和教学快照

**文件**：app/harness/teaching_context.py（新）、workspace_state.py、teaching_policy.py；assembly.py、app/agents/tutor.py、critic.py、conductor.py、curator.py、app/specs/agents/ 下实际对应文档与prompt对；tests/unit/orchestration/test_conversation_context.py（新）。

**接口**：TeachingContext与TeachingState(schema_version=1)；build_teaching_context(snapshot,messages,current_message,profile_summary)；serialize_teaching_state(workspace,policy,context)。run_online_agent_session末尾可选context；NewStackResult增加teaching_state/assessment_deltas，旧字段保留。

- [ ] 先核对实际prompt目录，记录成对文件；写受控LLM断言：第二轮提示实际包含上一问题、用户原话和上一回答；“刚才的例子”可定位；不得混入同画像另一个session的聊天。
- [ ] 写快照断言：恢复模式/history/stage/last_question；新轮内部协作turn计数重置；提交往返次数连续；坏schema明确失败或兼容迁移，不能静默丢历史。
- [ ] 写知识点断言：相同node多轮更新不新建原问题字符串节点；无法确定node则不写分数；Critic基于对应问答而非主题名称打分。
- [ ] 写长度断言：4000字符输入边界；最多12条、12000字符历史；旧历史摘要有截止消息id；摘要失败仍保留最近问答并标缩减，不产生假摘要。
- [ ] 运行 uv run pytest tests/unit/orchestration/test_conversation_context.py -q；实现共享上下文与prompt，不改变Curator职责；相关Agent/协作环回归通过。
- [ ] 更新README关于多轮恢复与指标含义，提交明确文件。

### Task8：HTTP/SSE共用幂等编排与原子回合提交

**文件**：app/orchestration/conversation_service.py（新）；chat.py、chat_stream.py、_persist.py、_dirty_flag.py、models/schemas.py；tests/api/test_conversation_transactions.py、tests/integration/test_workspace_concurrency.py（新）；test_persist_turn.py等现有持久化测试。

**接口**：ConversationService.submit_turn(user_id,ChatRequest)；claim→load snapshot→run context→commit result；persist_turn兼容包装返回原int/None，新内部commit返回CommitResult。DirtyFlag作用域扩为user/profile，不能清错画像。

- [ ] 写故障断言：父flush先于子插入；最终业务commit计数一次；消息第二条/画像/证据/状态任何一步失败全回滚，persisted=false；request失败管理状态能重新读取。
- [ ] 写幂等断言：同request普通重复提交不新增模型调用，只有显式retry提升attempt才可再次调用；成功提交后断连可查询并复用结果；payload不匹配409；same-session双发一个session_busy；旧attempt超时后晚结果禁止提交。
- [ ] 写显式重试断言：failed/interrupted→running只能经retry接口提升attempt；普通重发不重跑；保存原文原样复用；会话base_state已前进则409 stale_context而不是悄悄改变上下文。
- [ ] 写PG并发断言：不同session同profile同node各有一次证据，practice_count+2，其他节点不丢；两用户同名画像隔离；过期running重启后中断，未过期只显示运行中。
- [ ] 写HTTP/SSE对照：鉴权在模型前；流中失败有统一error；final仅提交后persisted=true；断开客户端不把半截输出确认完成。
- [ ] 运行 uv run pytest tests/api/test_conversation_transactions.py tests/api/test_persist_turn.py -q；实现短事务领取与最终提交、180秒租约/30秒续租/300秒最大运行、attempt栅栏，生成期间不持行锁。
- [ ] 运行 uv run pytest tests/integration/test_workspace_concurrency.py -m integration -q 需真实测试PG；不能用SQLite代替并发通过。更新README并提交。

### Task9：React终稿壳、类型API和按会话状态模型

**文件**：web/src/App.tsx、index.css、pages/Login.tsx、components/Sidebar.tsx、api/client.ts、types.ts；新增 components/workspace/{WorkspaceLayout,SessionSidebar,NewSessionDialog}.tsx、api/{sessions,profiles,knowledge,workspace}.ts、store/workspace.ts。

**测试文件**：web/src/store/workspace.test.ts、components/workspace/WorkspaceLayout.test.tsx（新）；package.json、package-lock.json、vite.config.ts按需加入兼容React18/Vitest2的DOM测试依赖；浏览器测试配置在Task12。

**接口**：SessionClientState按session_id保存messages/draft/request/save/load/version；WorkspaceState保存activeSessionId、profile groups与UI偏好。API client新增PATCH、FormData兼容点、结构化错误文本，不再String(object)。

- [ ] 写状态测试：A/B桶独立，A晚响应不写B，401清账号缓存与generation；新建流程只接受本人profile；异步返回覆盖需匹配account/session/request。
- [ ] 写布局DOM测试：左栏仅会话、主题子框、账号底部；右上入口；固定默认展开，手动收起取消固定，切会话不自动收起。
- [ ] 运行 npm --prefix web test 确认新增断言红灯；把终稿配色、排版、卡片迁入组件与CSS token，使用真实DTO，登录不改邮箱。
- [ ] DOM测试通过；npm --prefix web run build通过；不因重构删除现有api client测试。更新README并提交。

### Task10：真实会话恢复、发送与退出保存

**文件**：web/src/pages/Chat.tsx、store/workspace.ts、store/auth.tsx；hooks/useWorkspaceController.ts、useDraftPersistence.ts、components/workspace/ChatComposer.tsx（新）；hooks/useWorkspaceController.test.tsx、useDraftPersistence.test.tsx（新）。

**接口**：URL /chat/:sessionId为选择源；默认 /chat加载本人workspace.last_session_id；useDraftPersistence返回saveStatus/flush/recoverLocalDraft，保存请求携view_version。

- [ ] 写失败断言：刷新/重新登录恢复已保存消息与状态；新建可复用/新建画像；同session重复发送不重复写，pending/failed/interrupted可区分。
- [ ] 未完成提问从request_payload恢复成明确标记的临时气泡；retry调用专用接口，409 stale_context可复制原文为新提问，不把失败请求重复写入历史。
- [ ] 写保存断言：500ms草稿防抖、1秒阅读锚点节流、切换/正常退出flush；409保留本机草稿；A保存晚响应不覆盖B；换账号旧请求结果丢弃。
- [ ] 写退出断言：保存成功再清认证；失败提供重试或明确保留本机副本退出；强制关闭只恢复最近已确认版本与账号隔离副本，不声称保证最后按键。
- [ ] 运行 npm --prefix web test -- useWorkspaceController useDraftPersistence 确认红灯；实现请求状态查询和恢复，普通HTTP为首版发送，现有SSE后端继续通过Task8对照测试，不另做一套状态机。
- [ ] UI显示保存中/已保存/未保存与重试；不因有教学文字就显示保存成功。更新README并提交。

### Task11：真实知识库、主题画像页与摘要连接

**文件**：pages/Knowledge.tsx、Profile.tsx；components/profile/{ProfileDetail,ProfileSummaryCard}.tsx、components/knowledge/{KnowledgeLibrary,ResourceDialog}.tsx（新）；对应DOM测试（新）。

**接口**：两种画像视图同用 TopicProfileSummary；resource详情只展示真实文本/来源，不展示假的PDF页数或上传成功；画像页默认当前会话profile。

- [ ] 写断言：搜索、详情、新建、编辑、删除后重载真实资源；跨账号不存在；网络失败不清空旧内容并显示重试。
- [ ] 写画像断言：主题切换不改会话绑定；来源点击进入对应会话；null显示待评估；摘要与详情revision一致；仅有真实edges才画关联。
- [ ] npm --prefix web test -- Knowledge Profile 先红后绿；实现终稿页面，移除预览样式选择和固定示例数据。
- [ ] npm --prefix web run build通过；更新README第一阶段支持文本与未支持上传的边界，提交明确文件。

### Task12：可拖动A环形浮卡、响应式与无障碍

**文件**：components/profile/FloatingProfile.tsx、hooks/useFloatingProfile.ts及其测试（新）；index.css；web/playwright.config.ts、web/e2e/workspace-layout.spec.ts（新）；package.json/package-lock新增@playwright/test开发依赖并锁定兼容版本。

**接口**：useFloatingProfile接受主区/导航/输入区测量值、progress_y_ratio与savePreference，输出open/drag/position状态及pointer/key处理；业务summary通过props注入，不在拖动时重取消息。

- [ ] 写纯逻辑断言：4px阈值、350ms防误点、capture释放/取消/重绘清理、方向键12px、0–1比例归一、展开/resize不越边；鼠标与键盘关闭均可再次打开。
- [ ] 写浏览器断言：1440/1024/760/600/481/480/390宽及450px短高；481以上默认双栏，主区无水平裁切；账号与输入区可达；折叠后主区变宽；modal盖在浮卡上。
- [ ] 写实际pointer/hover断言：入口→卡片不闪退；离开收起；touch可开关；拖后不误点；切会话高度保留，重新登录从workspace恢复并夹取；卡片仅问答可见。
- [ ] 使用本地HTTP启动正式React服务做浏览器测试，不能尝试绕过此前对用户file标签的访问拒绝；命令 npm --prefix web exec -- playwright test --config=playwright.config.ts，工具不可用明确记录未验收。
- [ ] 检查中文长标题/长链接/放大字号/键盘focus/减少动效；npm测试和build通过，更新README、留截图与尺寸证据，提交。

### Task13：跨层真实验收、文档与分支审查

**文件**：tests/integration/test_workspace_resume.py（新）、web/e2e/workspace-real.spec.ts（新）、docs/delivery/2026-10-23-workspace-acceptance.md（新）、README.md、docs/asset-inventory.md（保留既有改动后追加本任务条目）。

**接口**：验收使用独立PG数据库、真实模型、两个测试账号；不打印凭据，不触碰现有生产数据，不执行发布。

- [ ] 按原始需求逐项建立追踪表；独立账号A创建两主题三会话，学习→切换→关闭→登录→继续旧问题，截取上下文调用证据证明真实连续性。
- [ ] 验证同主题共用画像、不同主题独立，当前知识点稳定，详情/缩略同revision；真实persisted=true且消息/状态/证据数据库可读。
- [ ] 重启应用和测试PG后再次读取；账号B替换session/profile/node/library/request ID全部被拒；验证冲突、保存失败、租约中断和幂等重试。
- [ ] 运行 uv run pytest tests/ -q、固定版本Ruff检查、npm --prefix web test、npm --prefix web run build、Playwright正式HTTP验收，以及已列integration测试；报告实际命令与通过数，不借用其他分支结果。
- [ ] 更新README当前能力、API、运行方式、迁移/恢复边界，标第二阶段未实施；独立审查整分支并处理影响验收的问题。只有满足门槛才标第一阶段完成，不自动push/PR/部署。

## 依赖、提交与停止条件

Task0→1；Task2→3/4/5；3+5→6；1+2+3+5+6→7→8；6+9→10；4+5+9→11；10+11→12；1–12→13。涉及同一tables/schema/README的任务按序实施，不能让多个实现者同时改共享文件。

每个任务按“失败测试→最小实现→本任务验证→README→明确文件提交”执行，生成提交前查看diff。任务红灯若是基线问题先记录归因，不能通过放松归属/事务断言绕过。

暂停交付门槛：真实模型或PG缺失、迁移不能保持旧数据、跨账号隔离失败、未解决的事务/幂等漏洞、正式HTTP浏览器验收不可用。允许完成不依赖的任务，但不能宣称整个MVP已完成。

## 本轮计划自审

- [x] 已将用户终稿、会话恢复、共享画像、知识库、浮卡收展/拖动分别映射到任务。
- [x] 区分用户已批准UI与待确认技术默认值；网络/文档规划保留独立第二阶段。
- [x] 原始设计、Store/DTO/调用签名、SQL事务与前端版本一致；原接口兼容有具体规则。
- [x] 五项Review Focus均有任务测试归属；不把SQLAlchemy create_all、HTTP200或假模型替身当真实交付验收。
- [x] 尚未执行任何产品任务；确认本计划后再开始。
