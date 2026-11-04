# Task10 第七轮审查修复实施计划

> 本计划与 `superpowers/frontend-ui/task10-review-fix-round7-raw.md` 先交独立 subagent 审查，通过后才能测试驱动实施。审查依据 `docs/delivery/study-workspace-goal/evidence/Task10/review6-final-product-code-review.md`。新冲突后旧成功和多 writer 失效两项目前均仅为源码推导，未执行真实业务交错；不得声称线上已发生。

## 全局约束

- 白名单：产品 `web/src/store/workspaceController.ts`、必要时 `web/src/store/workspace.ts`、`web/src/pages/Chat.tsx`；测试 `web/src/pages/Chat.test.tsx`、`web/src/store/workspace.test.ts`。超出范围、后端/API/存储格式/依赖改动需先补 raw/plan 并独立复审。
- 继承前六轮账号代次、会话/画像绑定、request/attempt/payload/baseline、消息分页和 ID 冲突、活动观察、草稿、路由及恢复副本精确 writer 清理；不能为过关删除备份、静默取消冲突提示或用 HTTP 200/404 代替持久消息证明。修复后的本机并发控制不构成跨标签页或跨浏览器原子锁。
- 先记录真实页面业务 RED 或已满足/不可达证据，然后才做必要代码；每次测试记录原始日志和进程退出码。两个真实 Provider 的共享存储仅为模拟，不冒充真实持久化。最终源和测试冻结后审查期间禁止修改。

## 任务 0：核实输入与调用链

- [ ] 对比 `review6-source-after.json` 的 46 文件、HEAD 和工作区，记录已有用户 README/asset 修改与现存测试进程；差异不明则先核实。读取第六轮审查、计划、`associationRuns` 初始化/结束/账号换代清理、`confirmCompleted` 成功/ID 冲突/catch、`sourceCurrent`、`recheckCandidate`、`reconcile` 和 Chat 的用户出口。
- [ ] 核查相同 request 的多个 writer 候选何时在 UI 可见，`readRequest` 在途去重和 `recoveryCandidateUnchanged` 失效时会显示什么；把是否真的可形成并发、现有警告和重试出口列作待实测，不只按函数推测结论。

## 任务 1：真实 UI 复现新可信冲突先于旧成功

- [ ] 在真实 MemoryRouter、AuthProvider、App、store/controller 中发送一个合法问题；服务器返回 `persisted=true`、匹配 owner/profile/request/payload/baseline 和正确 turn；第一次历史页挂起。用户点击实际“重新查询”，让第二次返回可信的相同 message ID 不同内容或与服务端完成回复不一致，确认 `inconsistent`、相应页面警告和阻塞。随后释放第一次合法 user/assistant 消息，记录两个关联的网络起止顺序、当前 writer 副本和不同 writer 副本，断言仍为 inconsistent、警告可见、不得匹配或清理副本、无第二次 POST。原实现运行并确认失败属于旧成功覆盖新冲突，而非 fixture 错误；若未复现须记录实际行为和路径，不做猜测性修复。
- [ ] 分别覆盖新关联同 ID 不同内容、回答/问题不一致、游标异常；仅对真正可归类为可信内容冲突的结果施加冲突优先，暂时网络失败/404 不得伪装成内容冲突。核对旧页与新页的 owner/session/profile、request ID、attempt、baseline、期望 turn 和消息内容；合法真实冲突不得因修改被吞掉。
- [ ] 反向对照 `review6-reverse.log`：较新关联网络 503 后旧可信消息成功仍可完成并显示，不重复发送；同样测试新来源仅失效/取消、两个网络失败、较新成功后旧失败、真实新主动冲突及当前唯一失败。保留失败提示与重试入口，防止以一律拒绝旧成功来获得 GREEN。

## 任务 2：仅在业务 RED 后调整结果发布

- [ ] 以账号 generation/user、session、request ID、attempt、原 payload/response/baseline 及来源标识建立关联上下文；对每次运行区分在途、可信成功、可信冲突、网络失败、来源失效，记录能够判定先后的操作序号。仅同一身份共享保护，不使用会话级全局锁取消不同请求。
- [ ] 新有效可信冲突一经发布，较早操作的成功、冲突和错误不能回退该冲突、修改对应 UI 或触发副本清理；较新仅网络失败并不否决旧可信成功。若选用 per-request 数据结构，明确终结与清理时机、账号换代和新的 attempt 如何隔离，禁止旧 finally 删除较新运行记录或无限保留状态。
- [ ] 成功继续核验 persisted=true、完整身份、response、baseline、turn、消息 user/assistant 内容、相同 ID 一致性、候选仍有效；只有成功提交后才能执行原精确清理。真实现存冲突不因旧成功消失。真实 UI RED GREEN 后重跑前六轮旧失败/新成功、当前失败重试、匹配后主动新校验、不同 request 独立与教学/画像/活动回归。

## 任务 3：多来源失效可达性、失败与退出

- [ ] 从页面生成或恢复同 request 的两个 writer 候选（包含同 payload/baseline 与冲突内容分别测试），使用真实路由控制器、页面的“查询上次请求”或 linked “查询原请求”触发两次关联；避免人工直接注入关联结果。控制顺序：旧来源页在途，新来源查询在途后其精确候选被另一 writer 覆盖/删除或读取失败，待新来源退出后旧页 503。记录两个请求/页及来源 writeId、何时失效、界面实际警告、能否点击原请求重查、旧/新副本是否保留，判断审查推导是否可达及是否有真正缺失的错误出口。
- [ ] 若 UI 因候选过滤、恢复锁或请求去重使并发不可达，写精确可重现的用户操作、fetch 调用计数与阻断调用链证据；不能通过直接调用内部函数或两个共用 store 的伪 Provider 冒充 UI 复现；但应记录其它调用方是否可以实际触发，留待审查。
- [ ] 若发现有效业务 RED，保留新来源变化/读取失败警告和重查出口；令旧来源仍有效时的网络失败能合理提示，不覆盖更高 attempt、新 request、较新可信成功或冲突；按 writer/kind/phase/writeId/完整 payload/baseline 确认来源，未知存储失败不能当作副本不存在。测试失败后重查可真正再次发起、完成时只清理当前 writer 精确候选，另一 writer 和冲突副本均保留。
- [ ] 分别覆盖候选来源变化（覆盖/删除）、读取失败、同 ID 不同 payload/baseline、两个真实 Provider 共享模拟 Storage、重复点击、不同 request 同时进行；检查无隐式重复 POST、丢失用户草稿或过早清空风险警告。主动退出/登录换代会销毁运行记录且旧结果无副作用；精确比较本机候选前后但不承诺跨页面原子性。

## 任务 4：冲突状态真实 UI 与安全恢复

- [ ] 在任务 1 可信冲突后，实际检查 request record、当前请求 status/error、输入框与发送按钮、原请求重查出口、已加载历史、当前/其他 writer 副本；包括本机恢复写失败或没有 requestCandidates 的场景，不能仅依赖候选碰巧存在来阻止发送。若不存在安全出口或发送仍可用，先保留业务 RED。
- [ ] 必要时添加已完成 inconsistent 请求的明确重查入口；重查必须读取原 request 及可信消息，不重复 POST，不因 `reconcile` 的 inconsistent 提前返回而永远无法核验。可信新校验仍冲突或网络失败应保持阻塞与证据；只有新操作验证一致并通过原身份、turn 与候选门禁才能转 matched，并精确清理允许清理的副本。保留 `recoveryError`、其他画像/历史错误与最新活动锁。
- [ ] 以 UI 测试“新冲突→仍冲突/503→继续阻塞且可重试→可信一致结果→恢复”；检查不同 request、同 ID 新 sequence、attempt、账号切换期间旧结果不覆盖新请求。若产品需求不允许从 inconsistent 自动恢复或无法安全区分，先修订设计并复审，不猜测改变语义。

## 任务 5：验收及交付

- [ ] 汇总覆盖矩阵、真实交错与模拟边界、各源码入口、不可达依据、未测组合、原始失败/误判及出口；检查根 README 是否需最小补充，保留用户现有修改。所有源/测试修改结束后固定完整文件 SHA（至少前 46 项及本轮新增），定向、全量前端测试、构建，日志均有退出码，前后哈希一致；变化则重冻重测。
- [ ] 停止源码/测试修改，交独立 subagent 对整个 Task10 的需求与实现复审；通过后才做真实浏览器、模型问答、persisted=true 联合消息读取、真实 PostgreSQL 重启后可读及跨账号拒绝验收。不同证据分别记录；未完成不得宣称 Task10 已完成。
