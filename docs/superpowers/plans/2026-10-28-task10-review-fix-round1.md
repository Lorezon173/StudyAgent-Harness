# Task10 审查修复实施计划

> **执行方式：** 用户已授权逐步规划、独立计划审查、实施、独立代码审查与功能验收。实施者按任务跟踪；本版待完整审查与独立计划审查 PASS，禁止提前编码。

**目标：** 防止完成确认旧快照回退状态，以及发送准备期间 A→B→A 导致错误发送。

**架构：** 完成确认在最终 store patch 内按教学版本和画像 revision 分组独立接纳，同时保留经验证的消息关联。真实活动会话变更递增本地 epoch，准备中的发送在发起 POST 前验证其生命周期；已发出的请求继续原有后台处理。

**技术栈：** React 18、TypeScript、Vitest、现有 workspace store 与 fetch 测试设施。

**设计来源：** `superpowers/frontend-ui/task10-review-fix-round1-raw.md`；继承 `docs/superpowers/plans/2026-10-27-task10-round1.md` v1.3。原实施冻结清单 SHA256 `03e86a90e145c63d9868d027c1fe8e38d3800af7b9c463613c376ea1a0dd979f`。

## 全局约束

不改后端、API 或增加依赖；账号票据及 attempt 的原有规则不削弱。按 raw 中空 revision 和独立活动状态、分页票据规则处理；同版本不能证明活动状态相同，发现数据矛盾时安全保留并提示。白名单：`web/src/store/workspaceController.ts`、`web/src/store/workspace.ts`、`web/src/pages/Chat.tsx`、`web/src/pages/Chat.test.tsx`、`web/src/store/workspace.test.ts`；必要时经独立计划审查批准具体路由文件，其他产品文件禁止修改。主会话最终检查并更新 README。证据置于 `docs/delivery/study-workspace-goal/evidence/Task10/`。不 stage/commit 用户改动。

## 审查重点

- 异步翻页期间新教学与旧画像、旧教学与新画像交错：任务 1 各测。
- 空和相等 revision 以及版本字段与内容同步：任务 1 测。
- 旧 attempt 或账号 generation 的晚页及副本清理：任务 1 测。
- 实际 A→B→A 导航、同账号换代及双击：任务 2 测。
- 已发出的 POST 后切换、旧准备晚结果与新准备：任务 2 测。

### 任务 1：完成确认单调合并

**文件：** 修改 `web/src/store/workspaceController.ts`；必要时 `web/src/store/workspace.ts`；测试 `web/src/pages/Chat.test.tsx`，必要时 `web/src/store/workspace.test.ts`。

**接口：** 保留 `confirmCompleted(id: string, requestId: string, ticket?: AuthTicket): Promise<void>`；若提取纯合并逻辑，输入当前桶与 SessionSnapshot，输出受版本约束的字段 patch，不替换草稿、游标或 pending 列表。

- [ ] 写真实 fetch 延迟分页测试：确认初始 snapshot 后阻塞旧页，通过正常加载接纳同 session 更新后释放；断言教学/session/source/version 与画像/profile/summary/revision 各自单调；覆盖两种交错、两者旧、相等及空 revision。断言消息 ID 去重排序和精确回合关联仍成功，当前游标与草稿不丢。
- [ ] 增加身份换代及更新 attempt 后释放旧页的测试，断言不关联、不影响新请求或清理其副本；保留冲突 ID、失败提示和原关联测试。
- [ ] 运行 `npm.cmd --prefix web test -- Chat`，保存原始 RED、退出码；确认失败来自旧快照覆盖而非测试设置。
- [ ] 在最终 patch 内重新核当前记录与票据，按 raw 的独立字段组规则比较 patch 时当前版本；无效记录不清理副本。保留成功关联和现有异常语义。
- [ ] 运行相同命令，保存 GREEN 与退出码；复核既有测试未删改以掩盖失败。

### 任务 2：准备发送的会话生命周期

**文件：** 修改 `web/src/store/workspace.ts`、`web/src/store/workspaceController.ts`；测试 `web/src/pages/Chat.test.tsx`、必要时 `web/src/store/workspace.test.ts`。

**接口：** `setActiveSession(id: string | null): void` 在真实变化时递增 `activeSessionEpoch`；`send(id: string): Promise<void>` 捕获并验证该值、账号票据与 request ID/sequence。核查实际所有路由选择入口；发现绕过则先明确涉及文件并复审白名单。

- [ ] 写真实 MemoryRouter 导航测试：A 准备并阻塞 snapshot，A→B→A 后释放，断言无 POST、原草稿和 prepared 副本可恢复且状态解除 preparing；测试同账号换代、双击、同 ID 重复选择、旧准备与新准备交错，以及 POST 已发起后切换仍可在 A 完成。
- [ ] 运行 `npm.cmd --prefix web test -- Chat` 保存 RED 和退出码，确认 A→B→A 因错误 POST 失败。
- [ ] 实现 epoch 和最后同步检查；仅当仍属原请求时标记未发送，保留副本；不影响已发请求或新请求。
- [ ] 运行相同命令保存 GREEN 和退出码；核查安全清理仅作用于原副本。

### 任务 3：回归、审查与验收

- [ ] 记录变更前后精确文件与 SHA，确认白名单及用户已有改动；运行 `npm.cmd --prefix web test` 与 `npm.cmd --prefix web run build`，保存完整日志和退出码。若失败先诊断，不报告通过。
- [ ] 提交独立代码审查，包含所有竞态、范围及源码冻结；PASS 后依原 v1.3 进行真实浏览器与后端功能验收，并保留证据；不可将测试通过等同真实持久化验收。
- [ ] 主会话检查并更新根 README；如完整独立审查发现其他问题，先增补 raw 与本计划并重新审查，不在本计划外直接编码。

### 任务 1 补充：未关联请求继续操作

**接口：** `continueUnassociated(id: string, requestId: string): Promise<void>` 保留现有显式继续入口；共享或复用任务 1 的教学、画像独立单调合并规则，不将旧消息页覆盖较新桶。

- [ ] 测试真实控制器的延迟 snapshot：操作开始后阻塞返回，正常加载同会话更新后释放；断言 session、teachingState、teachingStateSource、teachingStateVersion 成组一致且单调，profile、profileSummary、profileRevision 独立单调，覆盖教学旧画像新、教学新画像旧；分页状态有并发变化或存在在途页时消息和游标保持当前值。
- [ ] 测试当前出现新活动请求、同账号换代及 attempt 改变时旧继续操作不解锁或污染新请求、不清副本；无竞争时显式继续仍可完成。保存当前冻结代码上的业务 RED 和退出码。
- [ ] 在最终 patch 中复核票据及原 request 身份、attempt、状态和当前活动请求；按 raw 规则接纳字段及消息页，仅对仍匹配的原请求写错误。运行 `npm.cmd --prefix web test -- Chat`，保存 GREEN 和退出码。
- [ ] 任务 3 的独立代码审查必须针对修复后的最终冻结清单重新完成完整审查，包括 `round1-product-code-review.md` 列出的未判断项；不能将首轮未发现问题视为通过。


### 独立计划审查阻断修订（优先于本计划先前冲突文字）

**接口与状态：** 每会话桶增加本地 `activityEpoch` 与 `messageEpoch`；前者在所有已接纳活动锁及权威请求观察时递增，后者在消息、cursor 或 visited 成功变化时递增。所有相关入口须盘点并覆盖；账号 generation 独立保护，禁止将二者作为服务器版本。

- [ ] 写真实 fetch/控制器交错测试：同教学版本旧空闲 snapshot 分别在确认与未关联继续时延迟，新 running snapshot 或权威查询先落桶再释放旧结果；断言新活动 ID、busy 和发送门禁不被清除。覆盖完成与查询交错、重新查询失败仍保守及成功空闲后恢复，旧查询不能覆盖新观察。
- [ ] 写继续操作延迟 snapshot 与同版本真实上翻交错测试，包含上翻在途、完成后下一页继续加载，断言消息、cursor、visited 无丢失及可继续；再测同 ID 不同内容的页冲突，保留当前数据和安全错误。
- [ ] 写确认关联 found 与并发当前桶同 ID 内容冲突测试，断言现有数据保留、当前请求 inconsistent、无 matched 或副本清除；旧 attempt 或换代不得写错误。分别对三个阻断运行 `npm.cmd --prefix web test -- Chat`，记录冻结代码下各自可观察业务 RED 和退出码。
- [ ] 实施 raw 中活动观察 epoch、保守门禁及显式重查询出口；分别保证教学字段和活动字段不错误捆绑，刷新自身也受 epoch/身份保护。消息分页 epoch 在所有消息、cursor、visited 写入处维护；并发变化或在途页时继续操作保留当前分页。原子检查 found 与当前桶同 ID 冲突，明确返回成功才可清副本。
- [ ] 重跑针对性测试记录 GREEN；补真实路由离开聊天到画像/知识库、浏览器历史、默认路由、同账号换代、多次准备和异常分支，验证新请求不受旧准备影响。完整前端回归和构建、源码冻结、完整独立代码审查及真实验收顺序不变。


### 独立计划审查 v2 修订：可见门禁与可恢复状态

**文件与接口：** 白名单额外包含 `web/src/pages/Chat.tsx`；`Chat.test.tsx`、`workspace.ts`、`workspaceController.ts` 原已允许。每桶 `activityGate: clear | checking | uncertain`、`activityObservationSequence` 和 `continuedUnassociated` 的 request ID→attempt；`recheckSessionActivity(id: string): Promise<void>` 使用本人 snapshot 与必要的权威请求查询，界面按钮调用它，输入与 `send` 共同执行 raw 真值表。相关状态只服务本地观察，不代表远端实时空闲。

- [ ] 根据 raw 真值表写真实界面测试：冲突后“会话状态待确认”和“重新查询会话状态”可见、输入与发送均禁止；查询失败可见且保持，权威空闲且所有其他请求许可时恢复。无竞争完成未关联请求显式继续后，保留自身副本但不死锁；不同 ID 的 running/unknown 仍禁止；同 ID 多 writer 的身份/payload/base 冲突不得排除。覆盖重复刷新、失败恢复及 attempt/账号变化清理标记。
- [ ] 写权威终态取代旧 running、旧 running 不复活，以及独立重查与普通 `loadSession/applySnapshot` 逆序交错测试：各活动观察发起时捕获账号、epoch、单调序号，只有仍为最新发起且 epoch 未变才接纳并递增；过期失败不解除较新检查。断言活动门禁与 request ID/attempt 各自正确，其他请求不被清理。
- [ ] 写另一客户端在提交前空闲 snapshot 后领取、POST 得到 `session_busy` 的真实 fetch 交错测试：原文与 prepared 副本保留，无自动重发，显示忙及刷新；刷新失败显示 uncertain，最终权威重查恢复。保留发送前 snapshot、路由 epoch、账号与请求序号验证，不宣称 epoch 可证明远端实时空闲。
- [ ] 在原冻结代码执行各测试并记录业务 RED；按 raw 真值表实现 store、controller 和 Chat 的状态与交互，重跑 GREEN。已有活动/分页 epoch、同 ID 冲突、教学 source/画像 revision、路由和完整回归测试不得删除；修复后的最终冻结清单须完整独立代码审查 PASS 后再开展真实验收。

### 独立计划审查 v3 修订：可信未发送证据

**数据与事件：** 本账号代次的桶按 user/session/request ID、request sequence、原 payload/草稿 revision 和精确 writer 副本身份记录 `submissionEvidence: before_post | rejected_busy | unknown`。POST 发起前同步转 unknown；仅经匹配的当前调用明确 `session_busy` 拒绝且无同 ID 权威/身份冲突时转 rejected_busy。账号换代清证据；重登副本不得凭内存或 404 推断历史未发送。遵守 raw v3 对身份冲突、多 writer、退出 flush 和安全清理的完整规则。

- [ ] 真实 UI 测试 A→B→A 后释放准备 snapshot：零 POST、原草稿及本人副本保留、该可信 before_post 不单独阻塞，用户点击可用新 ID 再次发送；不得覆盖新编辑或其他 writer。
- [ ] 测试提交前空闲快照后另一客户端领取、该 POST 明确 session_busy、远端结束与本人权威刷新：保留原文/副本，只有用户明确点击才能以新 ID 发送；同 ID 已有 running/终态或 payload/副本冲突保持保守，payload_conflict 不归类拒绝未领取。
- [ ] 测试网络中断、丢响应、GET 404 不解锁；测试迟到拒绝、请求 sequence 更新、账号换代及退出重登不使未知结果误归为未发送。重登后旧副本可见且用户可明确恢复到空草稿，不覆盖新草稿；未知 request 不能因恢复动作自动新发。
- [ ] 各交错在冻结代码运行并记录业务 RED 与退出码，实施后 GREEN；保持先前所有回归、源码冻结与完整独立代码审查要求，禁止以删除副本使测试通过。

### 独立计划审查 v4 修订：收窄同 ID 恢复

**契约：** 本节优先于 v3 允许 rejected_busy 排除门禁或换新 ID 的文字。busy 后保留原 ID/payload/副本并维持 unknown，界面提供“查询原请求”和用户明确“按原请求重试”；空闲 snapshot 和 GET 404 均不证明其他客户端未使用或将来不会使用原 ID。权威 GET 按账号、session、request、payload、base、attempt 与可信基线核验，completed 走真实消息关联或明确未关联流程，冲突安全提示。复用原 ID 原 payload 的显式重试及后端现有幂等契约，不保证全局排他。

- [ ] 真实 fetch 并发测试：本调用 busy 后另一客户端同 ID 先 claim/completed，而本人 snapshot 空闲且不含 completed；断言不以新 ID POST，GET 原 ID 的完成记录经身份与消息验证后处理。GET 404 后同 ID 随后 claim、旧 GET 迟到、payload/base 冲突、账号换代与退出重登均不误解锁、清副本或污染新请求。
- [ ] 测试 POST 前取消仅当 ID 从生成起未暴露共享存储、网络及其他执行者时可解除本人门禁；已写共享 prepared 副本或不能证明未暴露时保持 unknown，保留内容并提供原 ID 重查/重试。现有备份优先；无法证明时不承诺 A→B→A 后新 ID 立即发送。
- [ ] 真实 UI 验证提示与按钮、原 ID 重试复用原 payload、404/失败保守、无自动新发与退出备份/账号隔离；分别在冻结代码记录业务 RED 和修复后 GREEN。此前路由 epoch、分页及同 ID 消息冲突、版本保护、完整回归和最终独立代码审查要求继续有效。

### 独立准备 ID：恢复 A→B→A 继续发送（优先于 v4 相冲突条款）

**范围与接口：** 白名单追加 `web/src/store/localRecovery.ts`、`web/src/store/localRecovery.test.ts`；扩展版本化 prepared 候选为纯 `prepared` 或带 request ID/payload/baseline 的 `linked`，按 raw 的验证、精确 writer/writeId 和跨账号规则处理。legacy schema 1 不推断为纯准备。`send` 准备阶段生成 prepareId、备份原文，不生成 requestId；全部异步准备及路由/账号检查通过后才进入同步 request 生成与可靠持久绑定流程。

- [ ] 用真实路由/Provider/延迟 fetch 测 A→B→A：无 POST、无 requestId、原文及纯 prepared 保留，回到 A 后用户明确发送成功一次；空草稿用户可恢复，非空草稿不覆盖，其他未决请求门禁仍有效。旧 schema 1 和写入共享的真实 request ID 不能猜成纯准备。
- [ ] 分别在 linked 写入前后、request 副本写入前后和 POST 前后模拟中断/重登、setItem/getItem 失败或不一致；纯 prepared 可恢复而 linked 必须按原 request ID 重查或显式原 ID 重试，不自动新发；验证备份失败不 POST、同账号/跨账号隔离及精确清理。多 writer 与 payload/baseline 冲突保守处理。
- [ ] 在冻结代码逐项记录业务 RED；实现先备份纯 prepared、异步核验后生成 requestId、linked 持久并读回、request 持久并读回、最终同步校验与 POST 的顺序，修复后 GREEN。扩展恢复与 flush 适配，不改变已发请求后台行为；保留 v4 同 ID busy/404 并发、其他版本/分页/路由测试、完整回归及独立审查。发现 Storage 语义无法支撑时暂停并报告而非猜测。

### 存储失败下的发送与恢复（优先于此前“不 POST”条款）

**原计划约束：** 依据 v1.3 第 63、141–142、253 行，准备和 linked/request 写入均尽力而为；失败显示本机恢复不可用警告，完整身份/路由/门禁检查通过后仍可发送。按 raw 新增内存状态、主动身份切换/退出备份门禁、强制 401 即时清除及固定失败提示，不能声称持久副本存在。

- [ ] 真实 Storage 写失败、读回失败或不一致测试：界面显示可能丢失提示，用户发送仍 POST；当前账号内保留原 ID/payload 并按 unknown 查询，不能伪报已保存或删除其他候选。
- [ ] 测主动换账号和同账号重登、退出保留：未确认内容备份失败则保持旧账号及内存，明确显示失败；有效 401 立即清认证并显示无敏感信息警告，旧响应不能影响新账号。
- [ ] 模拟纯 prepared 写成功、linked/request 写失败而 POST 发起，再崩溃重登；单独纯 prepared 不能证明未发送，不能自动新 ID 发；可读 linked 时仅原 ID 恢复，原文复制仅在空草稿且明确提示可能重复。当前代次 A→B→A 在生成 request ID 前取消仍可由用户继续发送。验证无可靠持久标志时跨重启无法同时证明无重复与无损恢复的事实边界。
- [ ] 对上述行为保存冻结产品 RED 与修复 GREEN；其余原计划、回归和独立审查要求不变。存储故障不是暂停正常发送的理由。

### 第五轮审查：共享准备副本及用户知情操作

**契约：** 当前执行上下文以 generation/session/prepareId/sequence 和永久取消的旧续体证明 POST 前取消时，A→B→A 后可由用户继续；其他标签、重登或无此证据的纯 prepared 一律为 unknown_preparation，不能静默新 ID 发送。版本标记或 Storage 重读不能证明跨标签排他。存储失败仍按 v1.3 告警且允许已授权发送。

- [ ] 使用两个真实 Provider/controller 和共享 Storage，底层屏障实现 B 缓存 A 的纯 prepared 后 A linked/POST/completed，B 恢复时不能自动新发；再次读取完整 owner/session/writer/itemId/writeId 和内容，变化时撤销风险选择并按 linked 的原 request ID 核验。
- [ ] 模拟 A 的 linked 写失败而 POST 成功、共享纯副本持续可见；B 显示“可能已在其他页面发送，重新提问可能重复”的明确风险，不能按纯副本判未发送。B 核验后 A 才写入/提交的交错也必须维持警示，不假称重读提供事务。
- [ ] 测试仅对具体候选显式确认风险后允许复制到空草稿，复制不发送、不删除；非空草稿不覆盖，必须另行用户点击发送；该选择仅解除对应未知文本门禁，不解除其他未决/活动门禁，候选变化或换代后失效。分别验证原标签真实 A→B→A 在生成 requestId 前取消后可继续、账号隔离、退出与 401。
- [ ] 保留真实业务 RED→GREEN、原先分页、版本、消息冲突、活动门禁、busy/同 ID 并发与完整独立代码审查。重读只能检测已发生变化；对读后变化和风险知情新提问的边界必须在实现提示中呈现。
