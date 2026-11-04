# Task10 第二轮代码审查修复实施计划

> **执行方式：** 使用 `superpowers:subagent-driven-development`；本计划和 raw 须先经独立 subagent 审查通过，再实施。每个缺陷先观察业务 RED，再实现 GREEN；修复后重新独立审查完整 Task10，再做真实功能验收。

**目标：** 恢复失败重试后能打开最近会话；安全清除已匹配请求的本页 linked 副本；切换回会话时保留历史分页且不静默吞掉消息冲突或间隙。

**架构：** 路由重试携带位置与账号身份；完成关联后按 prepareId/requestId/owner/writer/完整内容精确清理；snapshot 与连续历史通过可证明的分页链衔接。三个子模块均继承此前活动、请求身份、分页及账号代次保护。

**技术栈：** React、TypeScript、Vitest、既有 fetch、Storage 和 workspace store。

**设计来源：** `superpowers/frontend-ui/task10-review-fix-round2-raw.md`；继承 `superpowers/frontend-ui/task10-review-fix-round1-raw.md`、`docs/superpowers/plans/2026-10-28-task10-review-fix-round1.md` 和原 Task10 v1.3。阻断证据：`docs/delivery/study-workspace-goal/evidence/Task10/review-fix-final-product-code-review.md`。

## 全局约束和文件边界

- 不改后端、外部 DTO、依赖或另一窗口的路由意图工作；不提交、覆盖或整文件暂存用户已有 README/asset 修改。
- 产品白名单：`web/src/hooks/useWorkspaceController.ts`、`web/src/components/workspace/WorkspaceLayout.tsx`、`web/src/store/workspace.ts`、`web/src/store/workspaceController.ts`、`web/src/pages/Chat.tsx`（历史同步提示与旧 writer 已匹配确认出口）。测试白名单：`web/src/pages/Chat.test.tsx`、`web/src/store/workspace.test.ts`、`web/src/components/workspace/WorkspaceLayout.test.tsx`、必要时 `web/src/hooks/useWorkspaceController.test.tsx`。计划之外增改产品文件须先说明、补充方案并独立复审。
- 本计划只授权列出的功能；先核原有证据及 frozen SHA，差异未解释不实施。`docs/delivery/study-workspace-goal/evidence/Task10/` 保存所有有退出码的测试日志、报告和哈希。
- 任一写入/读回失败按原批准契约警告且在其他安全条件满足时允许已授权发送；不能以清理副本、降级门禁或清空历史来让测试通过。不得把 404、网络错误或 HTTP 200 单独当作 completed 或持久化证据。
- 冻结后所有变更需重新运行受影响验证及前后 SHA 校验；独立代码审查完整覆盖全部 Task10，非三个补丁的局部复审。真实验收在审查通过之后进行。

## 全局审查重点与覆盖归属

1. 默认页重试进行中用户主动离开后又返回同一路径：任务 1 的 location.key/账号/选择序号交错。
2. 保存重试与读取重试混淆、读取成功返回 null、重复点击：任务 1 的类型化结果和 UI 测试。
3. 相同 requestId 的多 writer 或不同 payload/baseline、删除失败、matched 再查：任务 2 的逐候选测试。
4. 最新页与旧链无交集、消息 ID 相同但内容不同、cursor 回环或桥接失败：任务 3 的连续性和冲突测试。
5. 上翻与 reload 的任意返回顺序、账号换代、旧页失败迟到：任务 3 的分页票据测试；既有活动/教学/画像和草稿不得回退。
6. 已匹配但写入/读回未知与退出备份：任务 2 区分服务端已保存的内存工作项和未知持久候选，不以写失败推断未写入。
7. 重启后旧 writer、仍活跃的其他页面与同 ID 冲突：任务 2 逐候选确认仅影响当前代次，不删除其他 writer，不承诺跨页面原子互斥。
8. 未关联继续及完成关联都写消息列表：任务 3 同一连续链与冲突契约覆盖所有四个写入口，并维持继续/关联各自语义。

## 任务 0：冻结输入与先决检查

**文件：** 只读 `review-fix-source-after-v3.json`、`review-fix-final-product-code-review.md`、raw 及本计划；写本轮证据目录。

- [ ] 核 `git status`、HEAD、原 46 项当前哈希及用户已有 README/asset 改动，记录逐项差异和计划、raw SHA。若与审查输入不一致，先由主会话判断后再编码。
- [ ] 阅读 `loadWorkspace/flushWorkspace/retryWorkspace`、`useWorkspaceController` 和布局的路由处理；`send/recheckCandidate/confirmCompleted`、localRecovery 精确删除；`beginSessionLoad/applySnapshot/loadOlder` 及服务端分页方向。记录实际调用/数据结构，不能把推测的竞态写成已证实事实。

## 任务 1：最近会话读取重试与路由身份

**文件：** `web/src/hooks/useWorkspaceController.ts`、`web/src/components/workspace/WorkspaceLayout.tsx`、`web/src/store/workspace.ts`、`web/src/store/workspaceController.ts`；测试 `web/src/pages/Chat.test.tsx`，必要时布局测试。

**接口：** `retryWorkspace()` 产生可区分 `read-success(lastSessionId)`、`write-result`、`failed/stale` 的结果；store 保存 load/save 错误来源和重试所需序列；现有 `lastSession(ticket)` 的初次恢复继续可用。具体结果可用判别联合类型，但调用方不能把失败当作成功 null。

- [ ] 写真实 MemoryRouter、AuthProvider、App 和底层 fetch 测试：默认 `/chat` 首次 workspace GET 失败；显示“加载失败”和读取重试；点击后 GET 返回用户 1 的最近会话 A，地址变为 `/chat/A` 且 A 快照和历史实际可见。冻结原实现运行，确认业务失败为未导航/错误类别而非选择器或网络桩错误，保存 `review2-workspace-retry-red.log` 和退出码。
- [ ] 写延迟重试测试：用户在 GET 等待时依次分别选择 B、打开知识库、访问画像、离开再回 `/chat`（同 pathname 新 location.key）、浏览器历史、同账号换代；释放旧结果 A，断言没有劫持新路径/新账号、不覆盖 B 的选择。另使 B 的 workspace 写入完成后才返回旧 GET，断言 version、lastSessionId 和错误不回退，且被读取去重复用的保存可以重试并最终成功。重复点击同时只允许有效最后一次结果生效；localOnly 默认页不恢复；读取成功 null 不导航；读取失败仍可重试。写入失败重试成功不得意外导航，用户显式选择仍按原规则保存。
- [ ] 将失败来源、读取结果和用户动作 identity 接入 store/controller/UI；对重试开始及返回双方核账号 generation、route key/path、localOnly 和工作区选择 sequence。不得因监听 lastSessionId 改动无限重新读取或使旧响应抢导航。
- [ ] 运行上述测试记录 GREEN、退出码；同时运行现有最近会话保存、冲突、账号切换及默认路由测试，记录结果。

## 任务 2：关联完成后的本人 linked 精确清理

**文件：** `web/src/store/workspaceController.ts`、`web/src/store/workspace.ts`、`web/src/pages/Chat.tsx`；测试 `web/src/pages/Chat.test.tsx` 与必要的 `localRecovery` 既有测试（若要修改该测试，先将 `web/src/store/localRecovery.test.ts` 加入白名单并在计划复审时确认）。

**接口：** 控制器内部处理过程输入 `AuthTicket, sessionId, requestId, payload, RequestTurnBaseline, attempt`；分别反馈 matched-absent、matched-removed、matched-storage-uncertain、conflict/stale，不能以 requestId 作为 prepareId。store 按 exact candidate identity 和账号代次记录待检查警告、逐候选的 matched 知情继续；`Chat` 提供“确认此请求已完成并继续”，只对本人权威完成且历史已匹配、候选完整一致时启用。它不公开新服务端 API，不删除非当前 writer 的副本。

- [ ] 显式增加来源判别联合：真实 `linked` 来源携带 prepared 副本完整身份及 prepareId；真实 `request` 来源携带 request 副本完整身份；仅内存来源携带当前 generation 证据且不得伪报落盘。由 `recheckLinkedPreparation` 按真实 linked 原 requestId 查询，并将来源贯穿 GET、消息分页和 matched 最终提交；每个异步边界核账号、session、操作序号和实际 prepared exact writeId/内容，不能用派生对象冒充已持久化 request。`resendLinkedPreparation` 同样重用来源核验和原 ID/payload，不得自动重发。
- [ ] 用真实 Storage 准备**唯一存活的 linked**（prepared 中只有 linked；request 命名空间完整读取为空，不写入任何 request 项），随后重建第二 writer 的独立 Provider/App：点击“查询原请求”，验证 GET 恰好使用 linked 的原 requestId；返回完整 owner/session/profile/node/payload/base/attempt/persisted completed，分页消息按 baseline 唯一匹配；用户看到知情提示，明确确认后可输入并另行点击发送。原 requestId 未自动重发，其他 writer 的 linked 未删除；验证业务 RED 应定位到缺少知情确认/不能继续等真实表现，不能预设 GET 必然失败。保存 `review2-linked-only-red.log` 的实际断言和退出码，再做最小实现并记录 GREEN；若原实现某一步已通过，保留记录并仅对真正未实现行为取 RED。
- [ ] 以 `setItem` 模拟 request 副本写失败后只剩可读 linked，再重建 writer 并重复完整链路；另让 request 列表读取抛错而 prepared 列表仍完整可读，断言用户仍可按 linked 发只读 GET 并看到经过验证的原请求状态，同时显示“其他本机请求暂时无法读取”，不声称 request 为空；有已知其他候选或列表不完整时不解锁已有外部候选的确认、原 ID 重试或新提问，恢复读取后再逐项检查。普通无已知外部候选的备份失败发送仍按前版允许并警告。
- [ ] 精确源验证交错：分别在 GET 在途、完成消息翻页中、明确确认前后改写 linked 的 prepareId/writeId、owner/session、requestId、payload 或 baseline，或改账号 generation/服务端 attempt；旧结果不能 matched、清除或给予豁免。覆盖同 ID 其他 writer 等值/冲突、请求 namespace 后来出现其他未决项、404/running/failed/不一致消息及无可信 baseline；只允许显示相应状态与原 ID 安全处理，不以这些条件自动解锁或新 ID 重发。确认后至最终读取间发生变化要撤销豁免，最终读取后写入不能宣称原子排除，须保留提示。
- [ ] 写真实 UI + 延迟 fetch：本页发送创建独立 prepareId/requestId，服务端实际完成但 POST 响应丢失；用户使用 request 副本查询原 ID，服务端 GET 返回原 payload、baseline 对应 completed/persisted 及真实消息页；精确关联后本人 linked 与对应 request 副本被安全清理，可继续输入，且从未以新 ID 自动重发。冻结原实现确认失败由本页 linked 残留/门禁造成，保存 `review2-linked-red.log` 和退出码。
- [ ] 用同一场景设置另一个 writer 的相同 requestId 候选，分别测 payload、profile、node、baseline、attempt 冲突及内容相同；仅当前 writer 的完整匹配候选可删除，其他 writer 保留并仍按原规则展示/阻塞。重复原 ID 查询已 matched、候选覆盖换 writeId、remove/读回失败、多个 prepareId、其他待处理 request、旧 attempt、账号换代和用户编辑草稿均不得误删或解锁其他项；清理失败后仍可显式再次检查且不假称删除成功。
- [ ] 在 matched 原子确认后接入统一清理，且已有 matched 重新查询同样必须先完整验证身份；不改变 unassociated/failed/unknown 的保留规则，不用 ID 相同推断跨 writer 排他。每项依赖本 writer 的操作在调用 remove 前后核身份，尊重 Storage 非跨标签事务的事实边界。
- [ ] 按 `prepared`、`linked`、`request` 三阶段分别模拟 `setItem` 在写前失败、写后 `getItem` 抛错、读回不一致；随后服务端确实返回 persisted completed，消息精确匹配。断言完成项可从内存未决备份集合退出，不把失败误称“未落盘/已删除”；读不完整保留可见的已知候选和“本机副本状态无法确认”提示、可重查。没有已知其他未决项时可在可见警告下继续或退出；仍缓存本 writer 已 matched 候选而无法读回时先明确点击“知悉本机状态不确定，继续本页”，且提示另一页可能新增或改变副本；恢复读取后若已变化则撤销、重登不继承。另有未保存草稿、其他请求或外部候选时仍执行各自的保存/确认门禁，不能用已匹配项绕过；已知外部候选读不完整时不能新建或沿用需要精确重读的豁免。`flushAll` 与 `prepareAccountTransition` 不再次将该已完成内存项写成未决，401 仍立即换代。
- [ ] 覆盖 storage 完整读取且精确本人项不存在、存在且成功删除、同键新 writeId、读取不完整及删除失败：校验分别报告 matched-absent、matched-removed、uncertain 或冲突，仅成功删除持久项后才说已清理；对应内存移除不等于删除其他候选。原实现先运行并记录业务 RED `review2-matched-storage-red.log`，每一不同故障分类记录预期错误而非仅 mock 调用。
- [ ] 使用真实 Storage 和两个隔离 Provider 模拟保存 linked 后新 writer 重登：用户用原 ID 查询并匹配持久消息，看到“其他页面可能仍使用/不删除/本页有效/重登需再确认”的提示，显式点击候选级确认后可继续输入并单独点击发送；复制或确认不自动 POST、不删旧 writer。并存第二个相同 ID 不同 payload/profile/node/baseline 或其他 unknown 候选时仍阻止发送，逐候选确认不扩大范围。测试候选在确认前、确认后发送前变化、attempt 或账号换代、部分读取失败时撤销/拒绝相应豁免并保留其他记录；用屏障覆盖确认后另一页仍能写入，UI 明示无法跨页面原子保证。原实现先记录缺少出口的业务 RED `review2-old-writer-red.log`。
- [ ] 重跑定向和既有双 Provider、readback、401、其他请求门禁测试，保存 GREEN 与退出码。

## 任务 3：普通 snapshot 的连续历史与冲突处理

**文件：** `web/src/store/workspace.ts`、`web/src/store/workspaceController.ts`，按实际错误展示需要 `web/src/pages/Chat.tsx`；测试 `web/src/pages/Chat.test.tsx` 和必要 store 测试。

**接口：** 保留 `loadSession(id): Promise<void>`、`loadOlder(id): Promise<boolean>`、`continueUnassociated(id, requestId): Promise<void>` 外部接口；引入本地连续页来源/前沿描述及共享桥接流程，不能把只由完成确认合入的孤立消息视为连续页。输入为会话票据、当前分页前沿、最新 snapshot 及 cursor、load 或 continue 的操作身份；结果是完整可证明合并或保留现有数据的失败/过期，不改后端 cursor。

- [ ] 真实路由测试：A 初始 snapshot 给第 3 页、上翻至第 2 页并保留 next cursor；切 B 再回 A，新 snapshot 与 A 最新页重叠，断言已显示的旧消息、锚点、最旧 cursor 和 visited 均保留且去重；再上翻第 1 页成功。原实现必须因历史/游标丢失而 RED，记录 `review2-history-return-red.log`。
- [ ] 普通 reload 的 snapshot 与现有任一页相同 ID 不同完整字段时，当前消息、cursor、visited、锚点、草稿和原关联保持，错误可见且重试后可恢复；snapshot 自身或桥接页内重复 ID 冲突也安全失败。冻结原实现业务 RED 记录 `review2-snapshot-conflict-red.log`。
- [ ] 已上翻至少两页后，通过真实 UI 点击“保留未关联记录并继续”：无并发时保留全部旧消息、最旧 cursor、visited、阅读锚点并可上翻下一页，原请求仅标用户显式继续而不伪造 matched 或删除副本。旧实现应因消息/游标被替换产生业务 RED `review2-continue-pages-red.log`；之后验证新旧页不重叠须桥接、桥接失败/ID 冲突仍保留历史和 unassociated、其他活动请求出现则不继续，新 attempt/账号换代不得误写。
- [ ] 测多于一页新增内容：新 snapshot 与旧连续链无交集，按后端不透明 cursor 顺序桥接至实际交集后，所有页不漏不重、旧向前游标仍可使用；同回合 user 的 id 高于 assistant 时显示顺序仍遵循服务端角色顺序。无交集且服务器已到末尾、桥接网络失败、cursor 回环、同 ID 冲突时不声称同步完成，保留已有历史与错误重试出口。加入页中普通消息与关联过程偶然并入消息的区别，防止将孤立记录当交集。
- [ ] 测上翻在途时 reload 返回及反序、页在途时切会话、相同账号换代、旧 page 失败迟到；只在实际 cursor 与页身份仍适用时接纳，其他情况保留现有前沿且可继续/重试。该并发是应验证的风险，不将其预先当作审查已证实的缺陷。
- [ ] 盘点并测试 `applySnapshot`、`loadOlder`、`confirmCompleted`、`continueUnassociated` 四个消息/游标写入入口：所有使用 `(turn_index, role_order, id)` 排序及完整 ID 冲突校验；确认完成仅合入验证过的孤立显示消息，不更改/伪造连续页元数据、cursor 或 visited，不能靠孤立消息证明桥接成功。按 raw 记录必要连续页来源/前沿，在 controller 按 cursor 桥接并最终原子核验；独立合并教学状态、画像、活动观察和草稿，不以消息页版本推断服务器其他字段。运行全部定向测试、原上翻/锚点/完成关联/活动观察测试，保存 GREEN 及退出码。

## 任务 4：全量回归、完整独立审查与真实验收

- [ ] 将所有变更逐项对应到 raw 和本计划；列出不能证明的行为、真实进程中断与跨标签事务边界。对最终所有源码和测试建立至少原 46 文件加新增文件清单，测试前后 SHA 不一致则重跑。
- [ ] 运行 `npm.cmd --prefix web test`、`npm.cmd --prefix web run build`，保留完整输出及退出码；针对新失败按系统排障并先测后改，不增加超时掩盖问题。记录实际通过数、warnings 与未覆盖项，不沿用旧快照的 237/237 证据。
- [ ] 主会话检查 README，按用户规则更新与本次实际变化有关的内容并保留用户既有行；检查变更白名单及不相关文件未被覆盖，不使用 `git add -A`、不 amend。
- [ ] 交新的独立 agent 审查当前冻结清单和整个 Task10 原计划、所有代码/测试、后端 DTO/事务边界及此前未判断项；如 Needs changes，先按流程规划和独立 plan review，再修复，不能跳过代码审查。
- [ ] 完整代码审查 PASS 后才运行真实浏览器 + 已授权后端 + 本机模型代理的功能验收，记录实际请求、持久化确认、读取以及截图；未经真实验证不得宣称服务或问答通过。真实 PostgreSQL 重启后可读与跨账号拒绝依项目要求在 Task13 验证。
