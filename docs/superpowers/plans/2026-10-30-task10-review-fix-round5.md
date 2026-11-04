# Task10 第五轮审查修复实施计划

> 先独立审查本计划及 raw，通过后逐项业务复现，再按实际结果实施。raw：`superpowers/frontend-ui/task10-review-fix-round5-raw.md`；依据：`docs/delivery/study-workspace-goal/evidence/Task10/review4-final-product-code-review.md`。继续错误与跨画像问题均为静态推导，未实测，不得提前宣称线上发生。继承前四轮所有活动、分页、画像、请求、路由、备份与账号门禁。

## 边界与后端契约

- 当前后端 `app/orchestration/session_service.py` 的 create 绑定画像，snapshot 按已拥有 session 的 profile_id 读取该用户画像；`app/api/sessions.py` 未见更改会话画像的公开接口；`app/orchestration/conversation_service.py` 对已有会话不同画像提出冲突。`alembic/versions/20261023_session_workspace_state.py` 有历史 null 画像补绑定迁移，因此不能概括为所有情形永久不变。异常或迁移导致快照变化的概率和真实发生均未知；本轮作为客户端防御测试，不宣称正常流程会发生。
- 产品白名单：`web/src/store/workspace.ts`、`web/src/store/workspaceController.ts`、必要时 `web/src/pages/Chat.tsx` 的身份错误提示/重试；测试白名单：`web/src/pages/Chat.test.tsx`、`web/src/store/workspace.test.ts`。其他产品或测试、后端、API、存储格式和依赖若需更改，先修订规划并独立复审。
- 保留所有用户已有修改及前四轮测试；不把另一画像的 revision 与旧画像比较，不跨画像混合 session、画像、教学、消息、请求或关联清理；禁止以 GET/404/POST 200 直接判断持久化，不重复 POST、不丢备份、不削弱活动门禁。连续历史、原 cursor/visited、草稿和用户导航仍受保护。
- 保留每次业务 RED、误判、GREEN、全量和构建的原始日志及退出码；验证后前后冻结哈希一致。不能把模拟 fetch/Storage 作为真实服务或多标签原子验收。

## 任务 0：冻结输入及边界核查

- [ ] 对照 `review4-v2-source-after.json` 重算 46 项、检查 HEAD 和用户 README/asset 现有修改、正在运行的测试，记录差异；不明差异先停下核实。阅读第四轮独立审查、`continueUnassociated` 内外 catch、`applySnapshot`、`confirmCompleted`、`recheckSessionActivity` 与原请求发送/重试及视图保存路径。
- [ ] 核对 create、snapshot、active-node、conversation 及历史迁移代码，记录可确定的契约和不确定范围；区分无缓存 session 与已有 session.profile_id 为 null。不得将未发现公开改绑接口当成数据库不可能变化的证明。

## 任务 1：真实复现 continue 桥接失败与较新活动观察

- [ ] 用真实路由/AuthProvider/store/controller 与可控 fetch：已加载 session A 及旧消息/游标，原请求 r1 为 completed/unassociated；点击继续并挂起桥接页；保留同账号、同 request ID/sequence/attempt 和同 load sequence。启动 `recheckSessionActivity`，让新观察发起或完成，再让旧桥接页 503。网络时间顺序与观察序号可核验，检查旧 request.error 不覆盖较新请求错误或状态，较新 running、门禁和其他请求不回退；检查历史失败在仍属当前历史任务时可见且可重试，旧消息/cursor/草稿保留，无第二次 POST。原实现在该交错下的实际结果写入 RED 或“已满足”日志，不用纯内部状态构造替代真实操作。
- [ ] 分别测试活动查询在途、返回 running、返回 idle、失败，以及同一次 load 有更高画像 revision：独立画像按归属和 revision 更新，同版本冲突提示不被旧错误清掉；活动过期不影响仍有效的历史失败提示。记录开始/结束事件和两个不同错误域。
- [ ] 对照有效失败（没有新的活动观察）应继续显示历史及请求错误；较新 load 成功/失败、账号换代、替换请求或 attempt、其他已存在历史错误和上翻并发：按各自身份拒绝旧发布，不能隐藏当前最新失败，不能误将请求 marked matched/continued、删副本或放开门禁。

## 任务 2：条件修复领域化错误发布

- [ ] 仅若任务 1 有有效 RED：对历史错误使用账号、session、原请求及 load/历史任务身份校验；对请求错误另加活动 epoch/观察序号校验；对画像按独立可信身份/revision 判断。必要时提供显式结果类型区分“只接受历史/画像”和“可写请求错误”，避免把 `applySnapshot` 返回 true 当成所有领域有效。
- [ ] 新活动正在查询时不得由旧错误覆盖查询或 newer error；本历史操作确实失败且仍为最新时，仍显示其历史重试。新 load 已成功或新历史错误已替代时，旧错误不回写；继续操作自身失败时不能静默丢提示。任务 1 全矩阵 GREEN，记录原始日志和退出码；运行第三、四轮 continue、活动门禁和分页回归。

## 任务 3：跨画像绑定业务测试与边界判断

- [ ] 建立 p1、p2 均归属同一用户且快照内部 session.profile_id 与 profile.id 一致的真实页面测试。先加载 p1，创建旧消息、cursor、草稿、活动/恢复请求，接着同 session 收到 p2 快照；分别令 p2 revision 高于、等于、低于 p1，测试正常 load、桥接失败以及完成请求消息确认。预期保留 p1 的完整 session/画像/教学组、消息及旧游标和所有副本、保守发送门禁，显示身份异常与可重查出口，不误关联 p2 消息、不 POST、不清其他 writer。执行现有实现并定位 RED；若全部满足则记录结果而不猜测性修改。
- [ ] 测试 p1→null、已有 null→p1（模拟迁移或异常响应）均不得自动混合旧记录与新绑定；首次无 session 缓存分别收到 null/p1 的合法情况仍可载入；再模拟重新读取 p1 正确快照，错误可见且可恢复，且必须重新满足活动与历史检查。迁移只证明部署迁移可补绑定，不假定运行期间自动重绑定为支持功能。
- [ ] 测试账号换代、较新 load 后旧 p2 响应迟到、p2 返回 active_request_id、p2 恶意相同消息 ID/其他 request、历史桥接在途；旧响应不覆盖较新正确数据或写错误，正常 p1 画像可单调更新，已有最新 running 门禁、草稿和副本不丢。异常持久存在时能够提示并重试，不以清除缓存制造成功。
- [ ] 逐入口核查 `loadSession`、`continueUnassociated`、`confirmCompleted`、`recheckSessionActivity`、`send`、原请求重发与重试、视图保存相关 snapshot 读取。对可实际影响绑定、发送或清理的入口写真实用户路径测试；特别断言发送准备阶段 p1 缓存收到 p2 快照时零 POST，完成关联时不得匹配或清理 p1 副本。若仅静态推导某入口不可达，记录调用链及明确限制，不将未测入口标为通过。

## 任务 4：条件实施可信绑定与恢复

- [ ] 若任务 3 有有效 RED，按 raw 在任何领域发布、桥接页写入、消息匹配/副本清理及新 POST 前验证账号、会话、已知与 incoming 画像绑定；区分无缓存、已知 null、已知非空。相同 owner 但不同 profile 仍不兼容，不能仅因为 profile 自身归属正确而放行。
- [ ] 先拒绝整个不兼容快照的绑定依赖数据，再写受当前票据保护的身份错误和保守门禁；保留旧组、消息/游标、较新活动、草稿及所有副本。清除身份错误必须有同绑定可信结果并保留无关错误；在身份仍冲突时允许重查，不自动清空或重发。不得因不兼容错误屏蔽本来有效的历史失败或其他 writer 警告。
- [ ] p1 正确结果可在身份恢复后按已有画像/教学/活动版本规则更新；活动只由当前观察确认解除，历史必须连续；保留原备份读取失败、跨 writer 和恢复手动出口。任务 3 及受影响原测试 GREEN；如需后端或产品白名单外文件，先补充方案并独立审查。

## 任务 5：审查交付与真实验收

- [ ] 对照前四轮及本轮，写覆盖报告逐项区分真实业务交错、单项模拟、不可达依据、未覆盖组合与外部限制。覆盖两个错误域、画像版本、null/非 null、账号和观察竞态、页面恢复、全部快照入口及跨 writer 原有门禁。检查根 README，必要时不覆盖用户更改而最小更新。
- [ ] 所有代码和测试完成后冻结 46 项或包含新增文件的完整源集，先运行必要定向再完整前端测试及构建，记录原始日志/退出码并复核前后 SHA；若文件变动重冻重跑。期间不在审查进行时追加测试或修改产品。
- [ ] 停止源码和测试修改，交独立 subagent 对整个 Task10 代码、需求和证据进行全范围审查；通过后才进行真实浏览器、模型、`persisted=true` 联合消息读取、真实 PostgreSQL 重启及跨账号拒绝验收，分别记录。未完成不得标记目标完成。

## 任务 3 增补：摘要可验证字段与跨会话正例（独立审查修订）

- [ ] 以 `app/models/workspace_schemas.py` 为字段契约：session 可核验 user_id/session_id/profile_id；profile 可核验 user_id/id；summary 本身无 user_id/profile_id；summary 节点、边可核验 profile_id；pending request 可核验 user_id/session_id/profile_id；evidence 不含 user_id/profile_id。不得编造或要求这些缺失字段。
- [ ] 核实 `ProfileService.get_summary` 依据用户与画像过滤 evidence，并连接对应 session/request/message；其 recent_evidence 可以来自该画像下其他会话。客户端对 DTO 未提供的 owner/profile 信任认证后端查询及数据库约束，不得声称自己已独立验证；如需额外可证明性，另行计划协议变更并取得授权。
- [ ] 增加真实路由正向测试：A、B 属于同一用户和画像 p1，A 的 summary 含两会话的合法 evidence 及 p1 节点/边；A 能正常显示/保留两个来源，不将 B 的 evidence 当异常或过滤。不能要求 evidence.node_id 必须出现在 summary.nodes：后端只在 nodes中过滤 archived，而 evidence 查询不做该过滤。
- [ ] 对现有 DTO 实际可见字段分别构造跨画像 node、跨画像 edge、pending request 跨用户、跨画像、跨会话；验证异常不能污染已有用户/画像缓存，不误删已有消息、游标、草稿、请求或备份，并保守显示可重查出口。验证合法空 summary 和无画像/空 summary 首次加载可行，区分这些合法输入与身份不兼容。
- [ ] 在未实现前运行测试，按实际结果标注 RED、GREEN 或不可达与原因；修复限于已审白名单。最终在覆盖报告写明验证了哪些可见字段、哪部分依赖后端与数据库，不能将模拟数据或客户端校验描述为真实服务端归属验收。
