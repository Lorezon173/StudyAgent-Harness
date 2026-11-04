# Task11：真实知识库与主题画像三层详细设计原稿

日期：2026-11-04。基线 HEAD：`4fff6e1fb250112c9faaa05a914f84164f7f96e9`。本文件仅细化已批准 SC-004 / 核心计划 Task11，不实现产品代码。原范围授权沿用主会话记录；独立计划审查 PASS 后按既定子代理流程执行，不重新索取相同授权。若发现实质新增范围，先呈报主会话。

## 来源与已核事实

- 直接来源：`docs/superpowers/plans/2026-10-23-study-workspace-core.md` Task11；`superpowers/frontend-ui/2026-10-23-final-implementation-raw.md` 的 D/E/F 节；同目录 multi-session-profile、paper-preview、knowledge-planning-future 原稿。后续实施计划必须追溯本文。
- 视觉来源：`docs/designs/frontend-paper-study.html`，沿用纸色、墨绿、宋体标题、文本资料卡、画像双区及来源列表。原型 JS 中示例分数、资料、固定 SVG 关系、样式选择和伪上传交互不进入产品。
- Task4 round1/2 已定义数据库私有文本 CRUD、搜索和独立连接验证；Task5 round1/2 已定义真实 summary、null、归档、来源与各请求一致快照；Task9 round1/2 已有认证代际隔离、终稿壳与 API DTO。不能将这些历史通过结论替代本次前端验收。
- 实际 Knowledge 页面仍直接调用 client，仅名称/说明创建、列表与删除；无搜索、详情、正文编辑。Profile 页面仍读取旧 `/api/profile/` stats 并带过时占位文案。
- `api/knowledge.ts` 已有 list/get/create/patch/delete；list 使用 q/profile_id/limit/before_id，返回数组，按 id 降序。`api/profiles.ts` 已有 listProfiles/getProfile/getProfileSummary，列表为 items/next_cursor。
- `types.ts` 的 ProfileSummary 就是后端 ProfileSummary DTO（本文所说 TopicProfileSummary），不得新造另一套指标。get_detail 包含归档节点；get_summary 只含有效节点、相应真实边，最近十条证据仍可能引用已归档节点。
- WorkspaceLayout 离开 `/chat/:sessionId` 会将 activeSessionId 清空。因此画像导航必须在离开前携带本人当前 session/profile 定位，不依赖画像页挂载后残留 activeSessionId。
- 两个画像 HTTP 读各自有一致快照，但不承诺跨请求冻结 revision；前端必须匹配后再发布。mastery 范围是 0–100，assessment_coverage 是 0–1。

## 第一层：模块总览

### 目标、入口与完成条件

在既有 `/knowledge`、`/profile` 受保护入口实现纸感终稿真实内容。用户可搜索本人文本资料、阅读详情、新建/编辑/删除并重载确认；失败可见且保留可重试内容。画像默认定位从当前会话进入的主题，允许浏览其他本人主题但不修改会话绑定；详情与缩略组件来自同一份同 revision summary，显示真实节点、关系与证据来源。

完成必须包含：真实 HTTP 下 A 创建→搜索→详情→编辑→重载→删除；B 替换资源/画像 ID 被拒；画像来源点击进入实际 session；80/null 显示 80、1/2，与当前节点 null 的待评估分开；空关系不画线；合法并发更新不显示混合版本；读取/保存失败均能保留并重试；真实浏览器查看终稿及模态框键盘焦点。DOM mock 不能替代真实服务或浏览器记录。

沿用 React18/TypeScript/Vite/React Router/Vitest/Testing Library 与现有 API/client/AuthProvider/workspaceStore。无需新依赖、全局框架、后端 API、表或迁移。页面数据局部保存，异步续体复用 workspaceStore.captureTicket/isCurrent，再加页面 mount/操作 sequence，不建设第二账号状态系统。

### 范围与信任边界

- 第一阶段仅手动文本资料管理/阅读；不上传 PDF、不展示伪页数/文件下载、不声称资料已索引或进入教学检索。网络规划、上传解析、权重编辑仍第二阶段。
- 本轮不增加画像/知识点管理新功能、不变教学请求、草稿、本机恢复、退出、活动门禁、B checkpoint 或安全合同。新建主题沿用 Task9 NewSessionDialog。
- Task12 实现聊天页 A 环形浮卡挂载、拖动、hover/touch 和全尺寸验收；本轮交付纯 ProfileSummaryCard 可复用组件及同源输入合同，不提前修改 Chat.tsx。本轮画像页面中实际使用该卡，并验证卡与正文一致。
- JWT 是用户归属唯一权威。query 参数、主题选择、文本均不可信；仅作查询提示，后端仍校验 owner。正文用 React 文本渲染，保留换行并折行，不注入 HTML。凭据不进入 URL/证据。
- 不修改其他窗口负责的后端路由；README/status 由主会话最终串行收口。本规划代理不修改共享文档，不提交 Git。

## 第二层：子模块概述

### A. KnowledgeLibrary 与 ResourceDialog

Knowledge.tsx 作为 API/状态容器；KnowledgeLibrary 展示标题、文本资料说明、搜索、资源卡、加载更多与错误；ResourceDialog 承担详情/新建/编辑和删除确认。名称、说明、正文、可选本人主题是完整表单，不再只有旧两个输入框。

搜索显式提交，q trim 后长度最多256，清除搜索重新加载；不让每个按键发请求。limit=50，首次/查询变化清分页游标，加载更多用成功页最小 id 作 before_id，按 id 去重；返回少于50才判断结束，恰好50允许下一次空页收束。列表不展示伪造总数/文件数量。切查询时旧列表可保留但标明“仍显示上次结果”，只将本次成功结果标为当前搜索。

列表、详情、写入各有独立 pending/error/sequence。加载失败保留此前成功列表；切换详情目标后不把旧正文冒充新资源。刷新同一详情失败保留旧正文并标旧内容。创建/编辑失败保留所有字段；保存成功后关闭编辑，保留成功实体并重新读取详情/当前查询列表，读取失败单独提示“已保存，刷新失败”，重试只 GET，不再次 POST/PATCH。删除成功即移除该 ID 并关闭其详情，列表刷新失败提示已删除；删除失败保留条目和确认上下文。

原合同没有创建幂等键/资源版本，不能偷偷加后端协议。POST 连接失败结果可能不确定时保留表单并提示先刷新核对，提供明确“再次提交可能重复创建”的用户主动重试；不自动重发。PATCH 失败重试是用户明确操作，告知当前文本尚未确认保存，不伪称服务器回滚。重复点击同步 busyRef 防重入；pending 时禁用提交/删除，允许关闭但 late 结果不得关掉新弹窗或清新表单。

### B. Profile 页面、同源摘要与来源

WorkspaceLayout 仅将学习画像 NavLink 目标改为含 `profile_id` 和 `session_id` 的 `/profile` 查询链接：从当前已核 owner/session/profile 的 bucket 取；无当前 chat 时优先保留当前 profile 查询，否则走 `/profile`。不改离开路由时的保存、选中或恢复逻辑。

Profile 页面加载本人 listProfiles，支持 cursor 加载更多/失败重试。显式 profile_id 优先通过 getProfile 校验，允许目标在列表后页；有 session_id 时使用现有 loadSnapshot 只读验证其绑定关系，绝不 applySnapshot 或写工作区，不覆盖 Task10 桶。snapshot/profile_id 不匹配时报链接不一致，不悄悄换绑；snapshot 失败可重试。无显式参数时以服务端 workspace-state.last_session_id 的 snapshot 解析默认画像；无最近会话才选择本人列表第一项，空列表展示新建会话引导。明确链接404显示不可访问，不自动退回别的画像冒充成功。

选择主题只更新 `/profile?profile_id=...` 的查看参数，清除此前 session_id 定位；不调用 session patch/create/active-node，不写 last_session。来源链接是 `/chat/{encodeURIComponent(evidence.session_id)}`，交现有 Task10 路由恢复，message_id/request_id 作为可读来源元信息，不新增自动滚动锚点协议。已归档来源节点可显示“已归档知识点”与 node_id，不伪造活动节点标题。

读取 getProfile 与 getProfileSummary，同一操作 ticket 下并发取得；必须 profile.id/user_id 正确，detail.profile.revision=detail.profile_revision=summary.profile_revision 才一次发布配对。若不同版本，最多再完整读取一对；仍不同则提示“画像已更新，请重试”，保留上次同主题成功配对并标上次版本；无成功对则显示错误，不无限重取。不同主题正在加载时不把旧主题正文放在新标题下。连续刷新可呈现新合法 revision，但旧晚响应不得回退当前视图。

ProfileDetail 与 ProfileSummaryCard 都消费同一个 summary 引用及选定 ProfileItem；正文节点/边不混用 detail 的另一套值。detail 用来核身份/名称/说明/revision；summary 负责分数/节点/真实边/来源。同一对对象一起传给两个组件，revision 可见便于核验。

### C. 视觉与可访问性

沿用现有 CSS 变量和 WorkspaceLayout，不复制原型全局 CSS。新增知识库/画像局部类；大屏卡片两列、窄内容区单列，长中文/链接/100000字正文不横溢。画像双区展示有效知识点、评估均值/覆盖率、真实关系和来源；可用稳定节点列表与真实边关系列表表达图谱，若绘 SVG 则只从 summary.edges 构线，不使用原型固定坐标连线冒充关系。空 edges 明确“暂无已记录关系”。

“已评估知识点平均掌握度”显示 mastery_score，不能称课程完成率；null 显示“待评估”，0 显示0%；覆盖率独立显示 assessed_count/total_count，total_count=0 时文字“暂无知识点”。当前知识点仅在已验证 session.active_node_id 匹配 summary.nodes 时展示，未匹配显示“未选择或已归档”，不推断别的节点为当前点。无会话上下文则不声称正在学习某节点。

ResourceDialog 使用原生 dialog，带标题/label、Escape关闭、初始焦点、关闭回到触发按钮；删除确认指明真实名称。错误 role=alert、加载 role=status、按钮 accessible name 明确。保留减少动效设置，不引入样式切换器。

## 第三层：函数与状态详细实施设计（无实现代码）

1. Knowledge 页面 loadResources：输入 q、beforeId 或 null、replace/append，输出 Promise<void>；消费 listKnowledge，捕获账号ticket/mount/listSequence/query，成功替换或按 ID 合并 items 并更新 hasMore/cursor，失败仅更新本操作错误。旧结果与finally不得改变新查询 pending。
2. openResource：输入真实 itemId、触发按钮引用，输出 Promise<void>；生成新的 dialogEpoch，以 getKnowledge 拉详情，保留独立 detailTargetId/detail/error。关闭递增 epoch；再开其他资源不能吃旧响应。
3. saveResource：输入 create/edit 模式、可选 itemId、LibraryCreate 完整表单，输出 Promise<void>；先校验 name trim非空且≤128、description≤2000、content_text≤100000、profile_id属于本人候选或null，同步 busyRef 防双发。createKnowledge/patchKnowledge 仅发送允许字段，不发送 user_id/source_type/id。成功进入 confirmed 状态、保存返回 item，按上述只读重载；失败保留form/target并显示ApiError.message。
4. removeResource：输入 itemId、对应dialogEpoch，输出 Promise<void>；确认后单次 deleteKnowledge，成功从 items 去除，失败保留；用 mutationSequence/账号票据防迟到副作用。404 表示资源已不存在或不可访问，不解释成其他账号资源；可刷新/关闭，不能造删除成功。
5. ResourceDialog：输入 open、mode、item、form、pending、error、onChange/onSave/onDelete/onClose、returnFocus，输出可访问模态界面。Form字段 name/description/content_text/profile_id；错误与dirty仅局部内存，不写Task10本机恢复。用户主动关闭可丢未保存表单，不承诺跨导航保存；pending关闭不取消服务端写入。
6. resolveProfileTarget：输入 URLSearchParams 与账号ticket，输出 Promise<{profileId, sessionId:null或字符串, activeNodeId:null或字符串}>；显式profile优先，session绑定只读核验；否则 getWorkspaceState→loadSnapshot→本人列表fallback。每次等待后核ticket及页面sequence，错误向页面明确传播，不吞成空列表。
7. loadProfilePair：输入 profileId 与账号ticket，输出 Promise<{profile:ProfileItem, summary:ProfileSummary}>；两次以内完整读取配对、核owner/id/revision，返回匹配对象或明确版本错误。是否接受结果还由页面selectedProfileId/loadSequence/mount共同判断。不写 workspaceStore 或创建长驻全局缓存。
8. Profile 页面 selectProfile：输入 profileId，输出 void；更新查询和局部选择序号，触发读取，不发送任何变更请求。loadProfileOptions 输入 cursor|null 输出 Promise<void>，消费 listProfiles，按ID去重、维护nextCursor，保留旧选项和错误。
9. ProfileDetail：输入 profile、summary、activeNodeId|null、sourceSessionId|null，输出真实详情；节点标题/描述/mastery/rationale/practice_count、edges、recent_evidence均从DTO读取，不推导虚假“薄弱原因”。证据为空显示无已记录来源。
10. ProfileSummaryCard：输入同一 profile/summary/activeNodeId|null，输出纯展示 JSX；无fetch/存储/拖动副作用。保留summary.profile_revision；mastery_score null和0严格区分，覆盖率单列。Task12可直接注入该合同，不要求本轮实现其浮卡。
11. 页面通用局部状态：items/options、已成功pair/detail、query/selectedId、loading/errors、cursor/hasMore、dialog(mode/epoch/target/form/confirmed)、操作sequence/busyRef/mountRef。账号变代、卸载或dialog关闭使旧票据失效；普通同generation工作区通知不得清表单。generation改变重置私有状态，旧成功/失败/finally/导航都不能回填。

## 验证与交付约束

实施计划逐条安排真实 RED→最小 GREEN：Knowledge CRUD/失败保留/迟到响应、Profile默认目标/版本配对/null/真实边/来源、导航只读与Task10回归；不通过删断言降级已有合同。完整前端测试/build只在最终产品冻结后运行一次；新修改或失败再按需要补验。

真实HTTP与浏览器使用独立测试账号/临时数据库或既有隔离验收实例；不打印凭据、不写用户生产库。无真实证据只能标未验收。数据库重启完整验收仍Task13，不在本轮宣称通过。执行完成后完整OCR preview/rule、覆盖全部文件的独立 Sol medium 审查；主会话裁决发现，修复有实际依据且与本次目标相关的问题。随后主会话更新README/清单/状态并明确文件本地提交，不推送/部署，不amend共享HEAD。
