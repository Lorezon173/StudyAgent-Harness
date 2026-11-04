# Task10 第四轮审查修复实施计划

> 本计划及 raw 须先经独立 subagent 审查通过，之后逐项先业务复现再决定是否修复。设计来源：`superpowers/frontend-ui/task10-review-fix-round4-raw.md`；审查依据：`docs/delivery/study-workspace-goal/evidence/Task10/review3-final-product-code-review.md`。两处审查问题目前是静态推导，尚未业务复现；不得提前宣称故障已发生。第三轮及先前所有已批准门禁仍有效。

## 范围与验收准则

- 产品文件白名单：`web/src/store/workspace.ts`、`web/src/store/workspaceController.ts`，必要时 `web/src/pages/Chat.tsx` 用于保守状态与重试提示。测试文件白名单：`web/src/pages/Chat.test.tsx`、`web/src/store/workspace.test.ts`。超出白名单或需更改后端/协议/依赖/存储格式时先补设计并复审。
- 保留审查期间已经追加的测试，不恢复或覆盖用户、其他窗口现有 README/asset 修改。根 README 按实际结果检查是否需要最小更新；避免把未审查的代码描述成已交付。
- 任何自动重查均仅对原请求 GET，禁止重复 POST；404、HTTP 200、completed 均不单独证明消息持久化。保护账号代次、请求 ID/sequence/attempt、payload/baseline、已存在的活动门禁和不同 writer 副本，保留历史、旧分页前沿与草稿。
- 每个测试先在待修产品快照运行，记录完整日志及退出码，检查失败是否业务语义而非时序或 fixture 错误。若原实现已满足或交错不可达，记录充分证据，不做猜测性修复。任何方案无法满足当前边界时先修订计划并复审。

## 任务 0：固定输入和恢复基线

- [ ] 读取第三轮 `review3-source-after.json`、独立审查及 `review3-extra-bridge2.log`，核对原 46 文件：预计仅 `web/src/pages/Chat.test.tsx` 因中间页桥接及 continue 账号/attempt 测试发生改变；若还有其他变化，先停下核查来源。保存当前差异、HEAD、用户原有 README/asset 状态、raw/plan SHA；排查测试进程，不并发重复运行。
- [ ] 保留新增测试，运行其定向基线；核对 `continueUnassociated` 内外 catch、load ticket、`applySnapshot` 成功/历史失败分支、`recoverSupersededSend`、`readRequest` 和 `confirmCompleted`。区分既有 evidence 的旧冻结 296 项与当前待重新冻结快照。

## 任务 1：旧 continue 桥接失败晚于新 load 的验证

- [ ] 真实路由、AuthProvider、store/controller 和模拟 fetch：已有连续旧历史及未关联 completed 请求；开始 continue 并挂起桥接页，原 request ID/sequence/attempt 保持不变；启动并完成较新 `loadSession`，使其历史成功连接、更新画像/活动或保留已有锁，记录新 load 序号、游标与成功界面；最后让旧桥接页返回 503。断言没有旧 `historySyncError` 或旧请求错误、无旧页残留，较新结果、草稿、请求与锁均保持，且没有 POST。记录网络请求次序并观察原实现；预期如静态路径所述产生过期错误则为有效 RED。
- [ ] 覆盖新 load 成功后桥接返回游标回环/内容冲突，以及新 load 仍在途时旧桥接失败、新 load 自己也失败两种次序：旧错误不能覆盖新结果，真实最新失败仍可见且可重试。区分历史错误与请求错误，防止用笼统断言漏掉其中之一。
- [ ] 与账号换代、同 ID 新 attempt、不同请求替换、较新活动 recheck、并发上翻分别交错；保持已追加的 attempt/账号测试，额外检查与 load 序号同时变化的组合。有效 continue 自己失败仍要显示错误，不标记继续或 matched，不清任何副本、游标或门禁。

## 任务 2：条件修复迟到错误

- [ ] 若任务 1 有有效 RED，在 continue 的异步操作中使用统一票据校验，至少核对账号、session、load sequence、request ID/sequence/attempt/association 与适用的活动 epoch/观察序号；确保旧结果不得写历史/请求错误，也不能使有效当前失败消失。核实 `applySnapshot` 返回 false 后的控制流，不能在外层 catch 重新发布已拒绝结果。
- [ ] 按任务 1 的业务矩阵逐项 GREEN，记录日志、退出码；再运行此前正常 continue、重试、历史冲突、活动锁和存储恢复定向测试。保持新旧 load 的错误归属独立，不能通过只显示 loading 或清除错误来过关。

## 任务 3：教学组与 session 版本交错验证

- [ ] 建立真实页面与有效 DTO：初始化 session 版本 v1、旧教学状态与活动；启动当前 load 并使更高版本 v2 快照在途；期间执行较新活动 recheck，分别返回 running 及 idle；然后释放 v2 快照，让它的 `activityCurrent` 失效但 load sequence 仍最新。分别测试历史桥接成功和桥接失败（其中失败应保留原消息、historyIds、cursor、visited、进行中上翻）。断言最终 `session.state_version` 与 `teachingStateVersion` 相等，教学状态/来源、`active_node_id`、`next_turn_index` 来自同一 v2，且较新活动锁、pending 请求与对应门禁没有回退；历史失败有可见重试入口、无半截消息。
- [ ] 检查交错确实让活动观察失效且版本 v2 大于 v1，分别留原实现日志；如未出现预期脱节，核实可达性并记录，不改产品代码。验证相同版本不同内容、旧教学版本、空 session 首次失败、跨账号/画像不匹配、不同活动节点或基线不一致：不伪造一致性，不自动清除请求/锁，不能以不一致教学组继续发送；较新画像仍遵守自身 revision。
- [ ] 核实 `continueUnassociated` 和 `confirmCompleted` 是否存在相同写入风险；对实际可达路径建立用户可观察测试，不能仅测内部赋值。检查运行中活动恰与较新教学版本不同步时，保留独立请求真实身份并保守提示。

## 任务 4：条件修复教学组一致性

- [ ] 仅在任务 3 有业务 RED 时，按 raw 分领域合并：先校验同账号、同会话、兼容画像及合法版本；教学 session 的 state_version、active_node_id、next_turn_index 与教学状态、来源、版本从同一快照成组更新；有效较新活动的 active_request_id、请求集合、gate、epoch、观察序号不回退。列清其他 session 字段的来源，避免无意覆盖新活动元数据。
- [ ] 缺少可证明的当前 session、身份/版本不兼容、同版本不可解释冲突时保留旧一致组并维持保守门禁，提供重查而不构造未经验证的 session。新教学与运行请求存在上下文差异时，不能修改请求的真实 payload/baseline 或把它当作已关联。发送仍需服务端快照与当前版本检查。
- [ ] 两条快照路径及相关写入口的任务 3 真实业务测试 GREEN；验证画像冲突、历史同步失败、分页、草稿、账号换代和活动查询既有测试，不弱化原门禁。

## 任务 5：补齐第三轮自动重查交错矩阵

- [ ] 用真实路由触发唯一 POST、延迟第一次 GET、以切会话触发新观察并使旧 GET 失效；控制第二次原请求 GET 在途。其间替换当前 request ID/sequence，返回旧结果后断言新请求、消息和门禁未被旧结果或错误覆盖，旧流程无第二次 POST；记录复现顺序及结果。
- [ ] 在第二 GET 在途时先接受同 ID 更高 attempt 的 running、completed/matched 状态，再分别返回低 attempt 的成功和错误；断言 attempt/终态、消息、锁不回退，旧请求不得清除副本。对已 matched 的合法情形检查无多余清理和无新 POST；若某一状态组合从业务入口不可达，提供具体调用链证据而非直接跳过。
- [ ] 通过另一个独立 writer（如已有双 Provider 测试模式）在第二 GET/消息读取在途新增或改变同 ID 的 linked/request 副本，分别测相同内容及冲突 payload/baseline；成功匹配只按已有规则精确清理本 writer 原候选，不删除外部副本，不掩盖冲突或读取/删除失败警告。核对草稿修改及退出时的备份；不宣称跨标签原子互斥。
- [ ] 以上各项先运行当前实现并记录结果；如失败且属真实业务问题，提出最小修复、补足身份/尝试次数/候选完整性检查后运行 GREEN。若修复需要超出本设计，停止并补充规划复审。

## 任务 6：完整回归、冻结与审查

- [ ] 对照前三轮和本轮要求逐项记录已覆盖、仅单项覆盖、未覆盖及不可达证据，包含活动/教学/画像、消息桥接与 cursor、认证换代、写失败警告、多个 writer、路由恢复和真实消息关联。不得把单项测试外推为组合通过。
- [ ] 完成所有变更后检查 README，并冻结 46 项或包含新增文件的完整输入 SHA；依次运行所有受影响定向测试、前端全量测试和构建，保留原始日志及退出码；结束后重算 SHA，若变化则重新冻结与完整回归。
- [ ] 提交覆盖报告、原始失败/通过证据及冻结信息，交独立 subagent 全范围审查 Task10。审查通过后才开展真实浏览器、模型、`persisted=true` 与消息读取、PostgreSQL 重启后仍可读及跨账号拒绝验收，未执行的项逐一标明。

## 任务 7：登录测试异步导航断言增补（须先独立复审）

**依据：** 本轮冻结全量 `review4-final-suite.log` 和 `review4-final-suite2.log` 两次为 318/319，均失败在 `Login.test.tsx` 的认证成功后路由立即断言；该用例隔离 `review4-login-diagnostic.log` 通过。`Login.submit` 顺序调用认证状态发布和导航；推测测试在前者渲染完成后、后者渲染前读取路由，但这不是已证明的唯一原因。

- [ ] 扩大测试白名单，仅增加 `web/src/pages/Login.test.tsx`；本增补不授权修改 Login 产品代码或其他文件。独立审查通过后，检查当前精确用例与原始失败，记录增补后 raw/plan 哈希。
- [ ] 将该用例等待条件从仅等待认证值，调整为等待真实路由变为 `/chat`；保留并独立检查认证 `2:RETRY`、实际路由 `/chat`、四次请求、旧提交不覆盖当前错误和其余所有原有断言，不修改 mock 或全局超时，不用直接赋值或手工导航代替 UI 行为。
- [ ] 运行定向用例与 Login 测试文件，保存每次日志和退出码；失败则追查真实原因，不仅凭此增补声称修复。完成后重新生成全部 46 项输入哈希，依次执行完整前端测试和构建，核对最终 SHA 未变并记录所有失败及结果，旧冻结失效。
- [ ] 更新覆盖报告，明确两次失败、隔离通过及调整后的实测范围；冻结后停止修改，交全范围独立代码审查，再进行真实功能与数据库验收。
