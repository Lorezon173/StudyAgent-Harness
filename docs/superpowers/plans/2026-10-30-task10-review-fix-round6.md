# Task10 第六轮审查修复实施计划

> 本计划与 raw 须先经独立 subagent 复审通过；再用真实页面交错验证原实现，只有取得有效业务 RED 才实施修复。来源 `superpowers/frontend-ui/task10-review-fix-round6-raw.md`；证据 `docs/delivery/study-workspace-goal/evidence/Task10/review5-final-product-code-review.md`。审查竞态目前仅是静态推导，不得称为已实测线上故障。

## 范围、限制与保持条件

- 产品白名单：`web/src/store/workspaceController.ts`、必要时 `web/src/store/workspace.ts` 或 `web/src/pages/Chat.tsx`（明确关联状态、重试和警告）；测试白名单：`web/src/pages/Chat.test.tsx`、`web/src/store/workspace.test.ts`。其他文件、后端、协议、依赖或恢复存储格式需先补充规划并独立审查。
- 继承 Task10 全部已批准账号与会话身份、活动观察、教学/画像版本、消息连续/冲突、草稿、多个 writer、本地备份读写失败和最近会话路由等门禁；不得用删除副本、跳过真实消息校验、取消用户重查或降低阻塞通过测试。必须区分 request record 与当前 UI request 字段，既不污染其他 request，也不把所有历史/画像错误与关联错误绑定。
- 每项测试保留退出码及原始日志，包括失败、夹具错误、不可达与已满足；对无法形成的交错核实并解释，禁止伪造 RED。全量前先完成所有修改并固定 46 文件或实际完整源集，审查期间绝不追加源码/测试。

## 任务 0：确认冻结与原调用链

- [ ] 对照 `review5-source-after.json` 核查 46 项、HEAD、用户 README/asset 改动与是否有在途测试，记录差异与 raw/plan SHA；不明差异先停下核实。
- [ ] 阅读 `Chat.tsx` 的 pending_messages “重新查询”、`reconcile`、`readRequest`、`mergeRequestValue`、`confirmCompleted` 的基线/页匹配、同 ID 内容冲突分支与 catch、`cleanupMatchedRequest`；明确所有调用方，包括恢复候选/linked、自动发送、活动检查和 polling。确认是否能并发而不是预设实现。

## 任务 1：真实 UI RED 或不可达证据

- [ ] 使用真实 MemoryRouter/AuthProvider/App、store/controller 与受控 fetch，在页面触发一次完成后历史关联：服务器 completed 有 `persisted=true`、合法 owner/profile/ID、payload/baseline 和正确 turn；第一次消息页延迟，页面显示“回复已保存，正在同步”。用户点击“重新查询”，同一请求 GET 返回 completed，第二次关联拿到真实匹配的 user/assistant 消息并标记 matched/completed，确认页面内容和清理的当前 writer 副本，再释放第一次页 503。断言记录仍 matched、UI 不退回 pending_messages/错误、不持续禁用发送，历史/草稿/门禁正确，无额外 POST；记录两次 GET、两个页和关联完成顺序，确认失败源为旧 catch 而非网络桩。
- [ ] 分别让旧页返回循环游标、同一消息 ID 不同内容和不匹配的回答，检查不能把较新 matched 变为 inconsistent，也不能清理其他 writer；上述旧结果应当来自第二次成功前已启动的操作。验证服务端确实返回原始消息内容及持久化，不能仅伪造 store matched。
- [ ] 检查旧成功晚于新失败、两次都失败、首次失败后用户再次点击并最终匹配，以及首次成功后重复点击/新请求不同来源；明确哪些交错由用户入口可达，确保现有当前失败仍显示错误和重试出口。若单飞方案使指定并发不再存在，测试应明确确认实际只有一个安全关联且首个失败后可重试，不能把人为直接调用单个内部函数冒充 UI。
- [ ] 如原实现无相应业务失败，保留含 EXIT_CODE 的结果，按源码及请求计数核查路径，不做猜测性修改；若所需行为或方案超出已审白名单，先修订 raw/plan 复审。

## 任务 2：仅在有效 RED 后选择最小安全设计

- [ ] 明确采用按账号 generation/owner、session ID、request ID、attempt、request sequence、payload/response、可信 baseline 及候选来源区分的关联票据或安全单飞。若合并同一请求，必须论证相同/不同 writer、来源变更、版本和尝试的共享资格，且失败后可再次查询；不采用会话级全局序号互相取消不同请求。
- [ ] 在启动、异步返回、成功提交、ID 冲突分支、异常 catch 及清理前核对适用身份；旧错误/冲突不能把已匹配的可信结果或已完成的当前 UI 请求回退。当前唯一有效操作的网络失败、缺页与真实内容冲突仍要显示真实错误与相应重试/阻塞；不能掩盖在较新主动验证中出现的可证明冲突。
- [ ] 有效成功维持 persisted=true、完整 owner/profile/payload/baseline、消息 turn/role/content/ID 一致及已有身份验证；候选来源改变、其他 writer 同 ID 变化、读写失败时沿用精确清理和警告，绝不删除其他 writer。任何并发防护结束应清理自身任务而不是误删较新任务；失败或换代不永久缓存 Promise/锁。
- [ ] 任务 1 真实业务测试 GREEN 并保留日志，逆序与单飞恢复均有证据。检查最新活动和画像/教学数据、旧 cursor、阅读位置、用户草稿和其他独立错误不回退，不以过期错误覆盖其他 request。

## 任务 3：身份、字段与并发矩阵

- [ ] 以用户入口/真实控制器分别验证：旧 attempt 延迟后新 attempt，账号代次变化，当前 request A 切换为 B，同 ID 新 sequence，旧 response/baseline/payload 冲突。旧任务不得改变新请求的 association、status、error 或消息；不同请求可各自独立完成，不能被会话级锁互相取消。
- [ ] 验证当前一次关联返回 503 时的 pending_messages/错误和“重新查询”，重新查询成功可真实显示持久化用户消息和答案；真实 ID 冲突及无法核实 baseline 时保留正确错误/阻塞与所有未确认副本。已匹配的旧任务错误不能清掉更新活动锁、historySyncError、recoveryError 或新画像。
- [ ] 补同一 request ID 的不同 writer 及相同/冲突 payload/baseline；来源在页请求中改变、清理/读写/删除失败、已匹配但副本不确定/需知情继续。至少一组用两个真实 Provider 共享 Storage，验证本 writer 精确清理而其他 writer 保留，所有异常警告可见，不声称跨标签原子事务。
- [ ] 逐项列出触发入口和相应日志：自动发送、用户重新查询、恢复候选/linked、活动查询和 polling；若已有测试仅提供间接证据，不将它记作新的交错已验证。不可达或未完成的组合如实保留在报告供独立审查。

## 任务 4：冻结、复审与验收

- [ ] 按前三层设计列覆盖矩阵、实际结果、失败原因、未测限制；检查根 README 是否需按用户可见变更最小更新，不能覆盖用户已有修改。
- [ ] 代码与测试冻结后生成完整 46 项 SHA；依次执行相关定向、完整前端测试及构建，保留输出与明确退出码，结束后重算 SHA；有变化须重新冻结并重跑。保留之前各轮失败与成功证据，不覆盖。
- [ ] 停止所有源码及测试修改，将报告与冻结交独立 subagent 进行 **整个 Task10** 的需求、代码与证据复审；审查通过后另做真实浏览器、模型问答、persisted=true 与消息读取、PostgreSQL 重启和跨账号拒绝验收。未完成不得宣称目标完成。
