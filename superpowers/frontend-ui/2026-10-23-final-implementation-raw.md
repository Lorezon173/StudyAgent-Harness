# 页面终稿与前后端补足：三层实施设计原稿

状态：用户已确认页面终稿；本文为待确认的技术实施设计，未开始产品编码。
分支：codex/frontend-ui-optimization；核查 HEAD：d0584d9。日期：2026-10-23。

## 设计来源与优先级

1. 用户本会话需求和逐次确认优先；页面基准为 docs/designs/frontend-paper-study.html 本次终稿，2026-10-23本轮核查SHA256为9EDC828D7A2D7BDB40C0B5FD6D254250C932E754F1DD2723425D8D73BEABB91B，执行前重新校验，不再使用三套候选页。
2. 原始需求：2026-10-23-multi-session-profile-raw.md。
3. 视觉与交互演进：2026-10-23-paper-preview-raw.md，后节取代前节冲突内容。
4. 后续知识规划：2026-10-23-knowledge-planning-future-raw.md。原本标为后续，仍作为独立第二阶段，不阻塞第一阶段交付。

## 第一层：模块总览

### 目标与阶段

第一阶段形成真实可用闭环：终稿 React UI、按账号持久化多会话、会话上下文恢复、按主题共享画像、私有知识库、服务端状态与界面恢复、右侧可悬浮收展和纵向拖动的 A 环形画像。图片和固定示例不得混入真实数据页。

第二阶段补足默认网络来源的 LLM 知识规划、文档来源、内容编辑和权重版本。其依赖第一阶段画像标识和知识库归属，但有独立测试与交付门槛。

沿用 React 18、TypeScript、Vite、FastAPI、SQLAlchemy、Alembic、PostgreSQL，以及现有事件驱动 Agent；正式逻辑只在 app/ 新栈实现。测试使用开启外键的 SQLite 与真实 PostgreSQL。第一阶段不引入 Redis/Celery、图数据库或新 UI 框架。

### 经代码核查的缺口

- Chat.tsx 仅内存活动会话；Sidebar 未接入，缺少选择事件；刷新不恢复。
- sessions API 可查询但缺少创建、状态保存、分页和主题画像关联。
- assembly 每请求新建 WorkspaceState、TeachingPolicy；Tutor/Critic 主要收到主题文本，历史未恢复；persist_turn 写 state={}。
- MasteryNode/Edge 按 user_id 作用域保存；同用户不同主题没有独立画像容器；无来源回合证据。
- knowledge API 是无鉴权的模块级内存 Store；KnowledgeTable 字段并非当前 name/description 契约，不能仅换 Store 就宣称持久化。
- 当前在线教学无条件要求 pgvector；另一个“默认关闭 RAG”计划尚未出现在本 HEAD，不假设已合并。
- 原型只通过脚本与模拟检查，尚无本轮浏览器视觉验收。

### 本次技术选择（待整体计划确认）

- 一个用户拥有多份主题画像；一个主题画像拥有多会话。创建时显式选已有画像或新建。系统不自动合并画像；主题偏移只建议另开。
- 桌面中央单活动窗口，左栏切换；不同会话可各自有未完成请求。第一阶段不做并排窗口。
- 同主题共享知识点、评估与画像，不混合完整会话历史；当前知识点使用稳定 node_id，用户可选择/更换，LLM 不得用每条原始问题当作新知识点 ID。
- 第一阶段允许手动新建知识点和等权默认值，为真实画像提供稳定范围；LLM 自动规划与非等权编辑在第二阶段完成。
- 稳定消息/教学状态自动提交；草稿、阅读锚点、最近会话和 UI 偏好另行保存。正常退出先确认保存；强制关闭/断网只承诺最近服务端确认版本，未保存草稿保留账号隔离的本机恢复副本。
- 关闭页面后不承诺生成任务持续运行；请求状态必须可查询，服务重启后未完成任务标记中断、显式重试。不会把半截流或未保存回复标为完成。
- 本轮只写计划，不推送、发布、部署或改全局配置。

## 第二层：子模块概述

### A. 数据、迁移与归属

新增主题画像及其知识节点/关系/评估证据表，保持原 mastery_nodes/mastery_edges 作为历史兼容数据；新 Store 以 profile_id 绑定作用域，读取复用MasteryGraph契约。图谱供本轮内存推理使用，在线提交从result提取节点增量，由TopicProfileStore应用到最新版本；不调用整图graph.save覆盖旧快照。兼容save方法仅服务受控初始化/离线调用，也不得把旧节点覆盖新revision。

新表 topic_profiles：id、user_id、name、scope_description、kind(normal/legacy)、revision、created_at、updated_at；同一用户可有同名主题但创建前提示，名称不作身份键。

profile_nodes：id、profile_id、title、description、mastery(nullable)、last_practiced_at、practice_count、rationale、revision、archived；未评估为 null，不是 0。profile_edges：profile_id、from_node_id、to_node_id、type、weight、confidence、source；两端只能在同一画像。

profile_evidence：id、profile_id、node_id、session_id、request_id、message_id、score、rationale、created_at；同 request/node 评估唯一。重复请求不重复增加练习次数。图谱关系只有真实数据时展示，不画随机连接。

sessions 增 profile_id、active_node_id、state_version、next_turn_index；state_json 保存版本化教学快照。session_view_states 按 user_id/session_id 保存 draft、reading_anchor、version、updated_at。user_workspace_states 按 user_id 保存 last_session_id、sidebar_pinned、sidebar_collapsed、progress_y_ratio、version；位置存可用纵向区域的 0–1 比例，跨尺寸重新夹取。

chat_requests 按 user_id/session_id/request_id 幂等，记录 payload_hash、request_payload（原始message、选定profile/node、base_state_version）、attempt、status(running/completed/failed/interrupted)、lease_until、error_code、response_json；领取事务先保存完整原文，因此强制关闭后也可跨设备显示未完成提问。pending原文不是已提交消息，不重复进入模型历史。会话保留 active_request_id，原子领取避免同会话双发。每次 attempt 是提交栅栏，旧生成结果不能提交到新 attempt。

新增 library_items（真实 name/description/user_id/profile_id/content_text/source_type/created_at/updated_at），不复用语义不一致的 knowledge 表。旧 API 内存内容不具备可靠账号归属，不能自动归给当前用户。旧 knowledge 表和向量资产保留，不在本次擅自删除或复制。

迁移：原有效 user 的旧会话/图谱进入各用户唯一“历史待整理”画像，保留原分数及来源为 legacy；知识点使用确定性映射，避免名称截断/碰撞。来源不明的 NULL owner 会话保持隔离；旧图谱不得复制到每份新画像。不以 legacy 旧分数伪造来源消息。会话尚无教学快照时从历史消息重建上下文，教学模式使用标明的兼容默认值。

所有访问从 JWT 身份得 user_id，不信任请求 user_id。新增归属关系使用复合外键或等价数据库约束，阻止 session/profile/node/evidence 跨账号、跨画像关联；先验归属校验加数据库约束，不只依赖 UI。

### B. 会话服务与持久化

创建会话时即保存空会话与画像关联；切换只加载所选会话。列表分页并按主题聚合，组内 updated_at/id 稳定倒序；消息按 turn_index、role顺序和稳定 id 返回。

保存两类版本互不覆盖：教学快照 state_version 与界面 view version。界面 PATCH 携 expected_version，冲突返回 409，前端保留本机内容并提示恢复/重试；不能拿旧快照覆盖新回复。

发送请求先用短事务领取 request/会话占用；同 request_id+同payload 返回现有状态/完成结果，不再调模型；同 id 不同payload 返回409。生成期间不持 DB 连接或行锁；不同会话独立运行。

结束后短事务锁定/校验 request attempt 与会话状态，分配 next_turn_index；父会话先 flush，消息、教学快照、节点评估增量、证据与 request completed 同一事务一次 commit。失败全部 rollback，响应 persisted=false，保留可重试状态，画像不先行确认。请求领取/失败标记是独立管理事务，不计入“整轮业务结果一次 commit”。

同主题多个会话更新时，锁最新 profile revision，应用本轮节点增量，practice_count 只递增一次，旧快照不得覆盖其他会话更新；同节点结果以服务端提交序列为准，证据全部保留，不以模型调用开始时间猜测顺序。

请求租约 180 秒，每30秒用短事务续租；运行最长300秒，超时中断，释放占用并提升 attempt 栅栏，后台线程即使结束也不能晚提交。恢复时过期 running 可标记 interrupted；未过期返回运行中，前端可查询。无持久化后台队列承诺。

failed/interrupted 的同 request_id 普通重发只返回原状态，不自动调用模型。显式 POST /sessions/{id}/requests/{request_id}/retry，输入 expected_attempt、expected_state_version；仅无其他活动请求且会话仍为原base_state_version时原子提升attempt重新领取，原payload不变。同会话已有新提交则409 stale_context，用户可基于原文主动创建新request，不能在过期上下文偷偷重跑。重试接口复用HTTP教学响应；前端调用后仍可查询同request的状态。

### C. 连续教学与画像评估

输入是已提交历史、当前消息、选定画像/知识点与教学快照；快照包含 schema_version=1、active_node_id、teaching_mode、mode_history、stage、last_question、summary、summary_until_message_id、committed_turn_count。协作环单次内部 turn_count 与用户往返回合数分开，不用旧累计回合触发新轮熔断。

恢复 TeachingPolicy.current_mode/history、WorkspaceState 的教学所需字段；不恢复 EventBus 订阅实例、线程对象、旧事件队列和临时证据池。每请求新装配仍保留，恢复的是业务上下文。

建立共享 TeachingContext，Tutor/ Critic/ Conductor 的必要提示词都使用它；Critic 必须看到用户原文及对应上一问题，不能只凭主题评分。已有 prompt 文档与 prompt.md 成对修改。Curator 保持只做结构与评估结果应用、不调用 LLM。

对话历史上下文上限默认12000字符、最多最近12条已提交消息，当前输入另限4000字符。最近一问一答各最多保留4000字符（超长截取注明），剩余额度用于更老历史的可追溯摘要；保留消息引用，即使截断也可定位原记录。摘要不足/失败不虚构，安全截取并明确上下文缩减；摘要与对应提交边界一起保存。此为字符保护，不声称等于模型token上限；画像摘要另限制最多20节点、每节点说明200字，避免全图塞入提示词。

未有知识点时会话可以聊天，但评估暂不写成未知节点分数；创建画像默认生成一个与主题同名的手动知识点，用户可调整，后续规划再映射。评估只允许关联本人画像中有效 node_id；无法定位或评估无效时显示未评估。

### D. API 与错误

保留旧 GET sessions 和消息、POST chat/chat/stream 与 GET profile/ 基本字段；新增字段采用兼容可选项。旧 chat 未传 profile/session 创建信息时，只能路由到本人 legacy/default画像，不自动修改旧会话归属；传了不属于本人画像的 session 先拒绝，再谈模型调用。

新增 API 前缀 /api：

| 方法与路径 | 契约摘要 |
|---|---|
| GET/POST /topic-profiles | 本人分页主题列表／创建主题与初始节点 |
| GET/PATCH /topic-profiles/{id} | 详情／名称说明更新，expected_revision |
| POST/PATCH /topic-profiles/{id}/nodes[/{node_id}] | 手动节点创建/更新；第一阶段不硬删除证据节点 |
| GET /topic-profiles/{id}/summary | 全图和缩略图共享摘要，节点nullable掌握度/评估覆盖率/来源 |
| POST /sessions | profile_id、title、可选active_node_id，返回已保存会话 |
| GET /sessions?group_by=profile&limit=30&cursor=... | 新客户端分组分页；无group_by维持旧列表形状 |
| GET /sessions/{id}/snapshot | 最近消息、教学状态、画像引用、view状态与版本、未完成request |
| PATCH /sessions/{id}/view-state | expected_version、draft、reading_anchor |
| PATCH /sessions/{id}/active-node | expected_state_version、node_id；有活动请求时409 |
| GET /sessions/{id}/requests/{request_id} | running/failed/interrupted/completed及已提交结果 |
| POST /sessions/{id}/requests/{request_id}/retry | expected_attempt和expected_state_version，原子重跑保存原文，状态过期409 |
| GET/PATCH /workspace-state | 本人last_session、sidebar状态、progress_y_ratio、expected_version |
| GET/POST /knowledge；GET/PATCH/DELETE /knowledge/{id} | 本人持久化卡片、文本内容和主题关联；写入归属由服务端设置 |

消息读取新增 cursor/limit=50，旧无参数维持原契约，snapshot 提供向前翻页信息。chat 新增 request_id、expected_state_version，返回 request_id、state_version、profile_revision、active_node_id；旧客户端未提供 request_id 则服务端生成，但不承诺旧客户端重发幂等。

HTTP鉴权/归属与版本错误使用现有403/404/409/422约定；401统一退出并清账号私有缓存。运行中同会话另一请求409 session_busy。SSE只在提交成功后发 persisted=true 的 final，断流不得当已保存。旧final消费者仍可读取原字段。

### E. React 终稿与恢复

把终稿拆为 WorkspaceLayout、SessionSidebar、NewSessionDialog、ChatComposer、ProfileSummaryCard、ProfileDetail、KnowledgeLibrary 等组件，不嵌入独立 HTML、不把模拟回复移到生产。保留账号登录与 JWT。

默认固定展开，481px以上独立占位，481–760px紧凑170px侧栏，仅480px及以下抽屉；列表独立滚动、账号左下；主区完整自适应，右上知识库/画像。手动收起会取消固定，切会话不自动收起；点击固定展开。

会话 URL 用 /chat/:sessionId，缺省 /chat 恢复 last_session_id，否则引导新建。每 session 建状态映射，响应按 session/request_id 归位，切换不 abort 其他会话请求。API 异步结果有代际标识，账号切换后旧响应不得回填。返回会话时刷新共享画像版本。

草稿500ms防抖，阅读锚点1秒节流；切换/退出补存。正常退出失败提供重试或明确“退出并保留本机草稿”选择，不伪造保存成功。本机备份按 user_id/session_id命名，重新登录同账号可提示恢复；其他账号不可显示。服务器已确认版本是唯一可靠跨设备恢复来源。

右侧固定 A 环形；默认窄入口，hover/focus展开、远离收起，触屏可点，Escape可关；position:absolute于主区，低于modal层。仅纵向拖动，Pointer capture、4px阈值、350ms防误点；边界在topbar和composer之间，展开/resize夹取，短卡区内部滚动；键盘12px微调。保存的是相对高度，换设备纠偏；不让拖动触发消息重绘或丢草稿。

第一阶段主题总体显示“已评估知识点平均掌握度”，同时显示“已评估n/m”；只统计有效非空掌握度，不称课程完成率。当前node分数独立显示，未评估为null；图谱与来源页和缩略卡使用同一 summary。第二阶段才根据启用的规划版本使用权重计算。

### F. 知识规划（第二阶段独立）

默认 source_mode=web，支持 document 和 mixed；网络只在新建/重新规划时调用，不每轮教学默认搜索。用户手动调整范围、篇幅（首版单位字数）、内容占比与重要性权重。规划候选不可静默覆盖人工修改，确认激活才成为当前版本。

第一阶段知识库实现私有文本卡片；第二阶段增加本人文档上传、受限解析与来源定位。复用现有 extractors 能力但不把文本提取等同完成向量入库，规划不依赖 embedding。

第一阶段文本知识卡仅管理和阅读，不自动作为教学检索来源。若运维显式开启旧RAG，在线调用必须在服务端由JWT注入可信 VisibilityContext(user_id)，不接受请求或模型事件覆盖；禁止在线visibility=None。可见范围明确为公共向量资料＋本人所有主题私有向量资料，暂不声称按画像隔离。受限路径只用支持owner过滤的vector provider，不回退无过滤OCR/code来源。新library_items不会自动变成已索引向量；未来教学使用新资料另做显式索引流程。

可配置 SearchProvider 需返回真实URL与摘录证据；当前未发现产品可调用的网络搜索Provider，执行第二阶段前确定真实供应商和凭据，工具会话 web 不可嵌入生产服务。未配置时明确 provider_unavailable，不能用LLM常识冒充全网检索或回退假结果。

内容占比与重要性分别归一为总和100；原始权重非负且至少一项>0，拒绝NaN/无穷。人工锁定字段重新生成只出建议差异。weighted_mastery 对已评估节点按权重归一平均，同时独立返回 assessed_weight_coverage；全未评估为null。规划增删后新节点未评估，旧节点及证据归档保留；不重写历史指标。

## 第三层：函数、字段与验证责任

下面名称为正式计划接口基准，无实现代码。异步数据库服务必须在规定事务边界内执行。

- TopicProfileStore.create(user_id, name, scope) 返回 TopicProfile；get_owned(user_id, profile_id) 统一归属校验；apply_assessment_delta 接收最新画像修订、本轮节点结果与证据，返回新revision，禁止整图覆盖。
- SessionService.create/list_grouped/load_snapshot/save_view_state/set_active_node：分别消费上述API请求模型，返回对应版本化结构；保存界面状态不改教学状态。
- ChatRequestStore.claim(user_id, session_id, request_id, payload_hash) 返回 Claim(status,attempt,lease)；complete/interrupt 必须校验attempt，重复完成返回已提交结果。
- build_teaching_context(snapshot, committed_messages, current_message, profile_summary) 返回 TeachingContext；serialize_teaching_state(workspace, policy, context) 返回 schema1快照。
- run_online_agent_session 保留现有前置参数，新可选 context 置末尾；NewStackResult 增 teaching_state 和 assessment_deltas；当前画像store由API侧限定，不允许用户文本选择画像。
- ConversationService.submit_turn(user_id, request) 返回 ChatResponse；HTTP与SSE共用归属、领取、上下文与提交编排，SSE只负责事件传输。
- persist_turn 扩展为完整回合提交入口，输入 claim、snapshot_version、result 与画像增量，输出 CommitResult(turn_index,state_version,profile_revision,request_id)；旧调用通过兼容包装，父先flush且结果一次commit。
- LibraryStore 的 create/list/get/update/delete 接收 user_id，真实数据库实现，分页/搜索只覆盖本人资源。
- 前端 sessions/profiles/knowledge/workspace API模块返回类型化DTO；useWorkspaceController按session_id管理状态；useDraftPersistence处理防抖、冲突和本机恢复；useFloatingProfile处理收展、拖动与归一位置保存。
- 后续 KnowledgePlanService.propose/validate/activate、SearchProvider.search、DocumentService.upload/extract、normalize_plan_weights 与 summarize_weighted_mastery 在第二阶段计划细化。

测试责任：单元验证稳定状态/边界；API验证鉴权/幂等/冲突/事务；真实PG验证迁移、重启和并发；浏览器验证终稿视觉、滚动、focus、hover、pointer、窄屏、长中文/链接、真实AI上下文与保存。开启外键的SQLite不是可选项。验收保留版本/截图/请求证据，不拿HTTP200代替成功。

## 等待确认的实施范围与默认值

本文件把未定细节落为上述建议默认值供一次审阅：第一阶段先核心闭环、第二阶段再自动规划；主题一对一画像；当前节点显式选择；同会话串行不同会话独立；不承诺关闭页持续生成；状态冲突409而非覆盖；字数篇幅；权重与覆盖率分开。用户确认计划后才实施，不把页面终稿确认外推为这些技术规则已批准。
