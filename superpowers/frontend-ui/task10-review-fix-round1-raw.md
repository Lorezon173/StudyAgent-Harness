# Task10 完成确认并发修复原始设计

## 第一层：模块总览

目标：修复 `confirmCompleted` 在异步翻页期间，同一会话已经接纳更新快照后，被旧快照回写而导致教学状态或画像摘要回退。范围包含本问题及文末已证实的发送准备竞态；不扩展到其他路径或后端。依据已批准的 `docs/superpowers/plans/2026-10-27-task10-round1.md` v1.3、`docs/delivery/study-workspace-goal/evidence/Task10/implementation-report-final.md`，冻结清单 SHA256 为 `03e86a90e145c63d9868d027c1fe8e38d3800af7b9c463613c376ea1a0dd979f`。修复保持 React/TypeScript/Vitest 与现有 store 结构，无新依赖。消息关联与快照字段接纳分开：过期状态不能回退，但已核实的历史消息仍可合并并标记匹配。

事实：`applySnapshot` 分别比较 `teachingStateVersion` 与 `profileRevision`，画像版本来源为 summary 的 `profile_revision`，缺失时取 profile 的 `revision`。`confirmCompleted` 取得快照后可能等待多个消息页，其最终 patch 无上述比较。相同教学版本不证明 session 活动请求相同；活动请求按下述独立观察 epoch 保护。同 revision 画像若出现冲突，不凭到达顺序猜测，应保留当前数据并安全提示重新查询。空画像版本沿用现有 store 策略：已有非空版本时不接纳空值；当前为空时可接纳。身份及快照校验沿用现有规则，不扩大所有权授权。

## 第二层：子模块概述

1. **完成确认与关联**：保持 persisted、基线、目标 turn、用户和助手各一条、内容、分页游标循环、重复 ID 冲突等既有检查；在最终原子 patch 内重新核账号票据与当前 request 的 completed/attempt。请求已替换、身份换代或 attempt 不符时不关联、不清恢复副本，不能影响新请求。
2. **教学字段合并**：以 patch 时桶内 `teachingStateVersion` 比较快照 `session.state_version`，不小于现值或当前为空时接纳教学字段、`teachingState`、`teachingStateSource` 和对应版本；session 的活动请求按下述独立规则决定；较旧时全部保留现值。判断与修改在同一 patch 内，避免检查后再竞态。
3. **画像字段合并**：独立比较快照 summary/profile 的 revision 与 patch 时 `profileRevision`，沿用 `applySnapshot` 的空值和比较规则，接纳时成组更新 `profile`、`profileSummary`、`profileRevision`，过期时全部保留。教学与画像任一新旧组合均独立处理，不交叉比较。
4. **消息与恢复**：通过现有 message ID 去重、顺序和目标回合严格校验完成关联；旧快照不覆盖当前游标、草稿、其他请求或 UI 保存状态。保留已有成功清理条件与失败提示；验证旧确认无法清除新 attempt/账号的副本。冲突消息维持原异常行为，不扩大覆盖。

## 第三层：详细实施计划

- 函数 `confirmCompleted(id, requestId, ticket) → Promise<void>`：保留对外接口和网络流程；输入是会话、请求与账号票据，输出通过 store 更新。最终 patch 的输入为当前桶与此前已验证的快照及消息；先核当前记录 attempt/status 和请求身份，再按教学版本与画像 revision 独立组装字段，消息按 ID 合并后排序、设置该请求 matched。失败或过期不进行清理。
- 如需提取纯合并函数，仅在现有 store 文件内定义，输入当前桶和 `SessionSnapshot`，输出教学及画像字段 patch；变量分别代表 incoming/current 教学版本和 incoming/current 画像 revision，不能共用比较器状态。若复用 `applySnapshot` 逻辑，不能触发它对消息、草稿或 pending 列表的替换。无需新增持久状态或 API。
- 测试使用 `web/src/pages/Chat.test.tsx` 现有真实控制器与底层 fetch 模拟：延迟历史页，等待新同会话 snapshot 实际落桶，再释放旧页；分别验证教学旧/画像新及教学新/画像旧、两者旧、相等或空 revision，断言字段和版本成组、source 一致。验证真实消息 ID 去重、排序及匹配仍成功，且页游标不被快照覆盖。身份变更（含同账号 generation）和更高 attempt 期间释放旧页，断言不污染、不清副本或覆盖当前请求。旧 attempt 的关联失败与网络失败继续符合原提示。测试必须能在当前冻结产品代码上因回退而 RED，而不是因设置错误失败。
- 精确产品白名单：`web/src/store/workspaceController.ts`；必要且经审查才可修改 `web/src/store/workspace.ts`；测试白名单 `web/src/pages/Chat.test.tsx` 和必要时 `web/src/store/workspace.test.ts`；最终由主会话检查更新根 README。证据记录写入 `docs/delivery/study-workspace-goal/evidence/Task10/`，不得修改其他产品文件；超范围先暂停。保存 RED、GREEN、完整测试及构建日志和退出码，冻结前后源码清单。独立计划审查 PASS 后才编码；完成独立代码审查 PASS 后按原计划进行功能验收。此设计仅覆盖当前已证实的两项问题，其他审查发现另行增补。

## 审查新增：发送准备的 A→B→A 竞态（本节扩展以上范围）

**模块总览：** `send` 准备期间仅检查当前 activeSessionId，无法识别曾切走又切回；真实切换一旦发生，应取消尚未发送的准备，但已发出的请求仍在原会话后台完成。新增会话选择 epoch，在真实 activeSessionId 变化时递增；同 ID 重复选择不递增，账号 generation 变化另由票据失效保证。该 epoch 是本地生命周期状态，不存储或作为服务端版本。

**子模块和契约：** `setActiveSession(id)` 是实际状态切换的统一边界，必须核查所有路由入口确实调用它；若存在绕过路径，纳入明确白名单并使其通过同一边界。`send` 在准备开始捕获 epoch、票据和 request sequence；异步快照后及 POST 前再次核对账号、active ID、epoch 与当前 request 身份。无 await 的最后检查和 POST 发起应在同一同步执行片段。失效时仅在仍属原 request/sequence 时解除 preparing 并显示未发送可恢复提示，保留原 draft 和 prepared 副本；不能把未发送状态记为 unknown 或自动发起。若新请求已经替换，不清理或更改新请求。切换发生在 POST 已发起后不取消该请求，仍按原账号票据和会话归位。安全清理仅在用户恢复或现有成功确认条件成立时按原副本身份清除，不因作废批量删除。

**详细实施：** 在 `workspace.ts` 工作区状态添加数值 `activeSessionEpoch`，初始为 0；`setActiveSession(id: string | null) → void` 在真实变化时同时更新 ID 和递增 epoch；账号重置可重新初始化，因为票据 generation 同时改变。`send(id: string) → Promise<void>` 读取捕获值，并在最后校验时验证票据、epoch、会话及 request id/sequence；作废分支只更新与捕获身份一致的准备状态，保留数据。测试通过实际 MemoryRouter 导航 A→B→A、延迟 A 的 snapshot、释放后断言零 POST、原文与副本可恢复、状态不被锁死；同账号换代、双击、切换后新准备与旧响应相交、重复选中 A、以及 POST 已发出后切换均分别验证；不得用直接改 active ID 代替真实路由覆盖。计划必须先独立审查 PASS；当前完整代码审查未完成，仍可能增补。


## 审查补充：未关联请求的继续操作

源码核实 `continueUnassociated(id, requestId)` 在异步 snapshot 返回后直接写 session、teachingState、profileSummary、消息与游标，并未更新 teachingStateVersion、profileRevision 或 teachingStateSource。加载期间同会话若接纳了更新状态，该路径也会回退，甚至内容与来源不一致。以上模块范围包含此路径；审查来源为 `docs/delivery/study-workspace-goal/evidence/Task10/round1-product-code-review.md`。

**职责及契约：** 继续操作仍须验证账号、会话、画像归属、请求当前为相同 attempt 的 completed/unassociated、返回 snapshot 无活动请求且版本至少为 response；在最终 patch 内重新检查这些请求条件和账号票据。教学字段（含 source 与版本）和画像字段（含 revision）分别采用本设计的独立单调组规则。返回 snapshot 的消息与游标必须按下述独立分页 epoch 规则处理，不能只依据教学版本；若当前桶有更新的活动请求，不得将旧继续操作标为 completed 或解锁新请求，而应保留请求和数据并提示重新查询。可安全接纳快照时保留现有继续操作语义，包括消息页、游标和显式继续出口；不伪造关联，不删除未关联的恢复副本。网络失败及身份/attempt 改变时沿用安全失败语义，错误回写也只作用于匹配的原请求，不能污染新请求。

**测试设计：** 通过真实控制器底层 fetch 延迟 `continueUnassociated` 的 snapshot，期间以正常路径接纳同会话更新，然后释放旧 snapshot，验证教学版本/session/state/source 不回退且一致、画像 revision/profile/summary 独立不回退、消息与游标不丢；分别覆盖教学旧画像新、教学新画像旧，以及当前出现新活动请求、账号换代和 attempt 变化。验证无竞争时原有继续出口仍可用。测试先在冻结产品代码运行并因可观察回退 RED，修复后 GREEN。修复后的最终冻结清单须重新进行完整独立代码审查，原报告没有对未覆盖路径作通过判断。


## 独立计划审查阻断修订（优先于前文有冲突的规则）

事实依据：`ChatRequestStore._occupy` 仅设置 `active_request_id`，不增 `state_version`；`commit_turn` 提交时才递增教学版本；`loadOlder` 会改变消息、游标和已访问游标而不改变教学版本。因此同教学版本不证明活动请求或分页状态相同，不能把整个 session 当作一个受教学版本保护的不可分组。

**活动状态观察与安全出口：** 每个会话桶维护本地单调 `activityEpoch`，任何接纳的 session 活动锁观察或同会话权威 request 观察（含 running、终态、重试）均递增；身份换代重置桶但由账号票据阻止旧写入。完成确认/继续操作在发起 snapshot 前捕获 epoch，最终原子 patch 对照当前值。若 epoch 变动或有其他正在运行/待确认的本地请求，旧 snapshot 不得改变活动锁、清除 busy 或把旧继续操作当作可发送证明。保留当前活动锁和请求信息，显示待重新查询并保持发送门禁；关联可独立成功但不能解锁新请求。epoch 不变时也不得以旧完成请求的终态推断其他活动锁为空；仅接纳该次本人 session snapshot 的活动锁观察，要求该观察身份有效且该路径尚无较新观察；若其为非空，保持门禁并针对该 ID 走已有权威查询。若数据冲突或查询失败，保持保守门禁并提供显式重新查询；刷新发起前后也捕获、比较 epoch 和账号票据，避免晚查询再次清除更新锁。门禁解除须来自未过期的本人空闲 snapshot，且没有本地已知运行/未知/待确认请求；新建状态如需专门标记需描述为本地 uncertainty，不改服务器契约。教学 state/source/version 按教学版本独立单调接纳；session 内活动字段不能随教学字段盲目替换。与新活动观察相关的完整 session 其他字段若无法安全拆分，则保留当前 session，待刷新，不合成不可证明的状态。

**分页并发：** 每个桶维护 `messageEpoch`，任何成功替换或合并消息、游标或 visitedMessageCursors 的操作均递增；请求发出时记录 epoch，以及当前游标和 load sequence。`continueUnassociated` 最终只有在 epoch 未变且无在途上翻时才可用最新页整体替换并同步 cursor/visited；否则保留当前完整消息、cursor、visited 和在途请求，继续出口只在活动规则允许时完成，且不得用旧结果修改分页门禁。进行中的上翻应能按其已有序号和游标完成，后续上翻仍可用。不能只因版本相等覆盖，不能把旧 cursor 合并为新 cursor；快照页若同 ID 与现有消息不一致，保留现有数据，提示不一致并停止关联或继续，不清副本。epoch 检查与写入同一个原子 patch；任何新路径更新消息或分页均须纳入增量，相关账号切换由票据保护。

**关联冲突：** `confirmCompleted` 最终 patch 比较 found 内及 found 与当时桶内相同 ID 的完整消息；如任一内容不同，保留桶内全部消息、游标、教学与画像状态，不能标 matched 或清恢复副本；仅在当前 request ID、attempt、状态仍匹配时标 inconsistent 并显示重新查询提示，旧结果不能污染新请求。相同 ID 内容一致才去重并排序；关联成功与活动锁状态独立，不因消息匹配解除其他活动请求门禁。成功清理必须以最终 patch 的明确 matched 结果为前提，再次检查身份、原请求 attempt 和副本身份。

**验证增量：** 以真实 fetch 延迟及真实控制器路径构造：同教学版本旧空闲 snapshot 延迟，新 running snapshot/权威查询先接纳，随后释放旧确认和旧继续，断言锁、busy 不丢；完成/查询交错及刷新失败/成功明确恢复门禁。延迟继续 snapshot 时真实上翻同版本并加载下一页，再释放旧 snapshot，验证消息、cursor、visited、后续分页及在途页均保持；构造当前桶和 found 同 ID 不同完整消息，断言保留当前、inconsistent、不清副本，且不靠文本匹配。分别先证实冻结代码业务 RED，修复后 GREEN；保留账号换代、attempt、真实路由离开聊天至画像/知识库、浏览器历史、默认路由、多次准备及异常分支覆盖。

## 独立计划审查 v2：门禁、恢复和观察边界（覆盖此前冲突表述）

**允许改动与界面。** 在此前白名单中明确加入 `web/src/pages/Chat.tsx`（测试 `web/src/pages/Chat.test.tsx` 已包含）。每个 session 桶增加 `activityGate`：`clear | checking | uncertain`，附可见错误及活动观察 epoch；该状态只表明客户端对上次观察的处理，不是服务端实时锁。`Chat` 在 checking/uncertain 显示“会话状态待确认”及按钮“重新查询会话状态”，checking 禁止重复点击，失败展示“查询失败，请重试”，uncertain/checking 令 composer busy；`send` 的 guard 使用同一门禁和下表，不能仅靠 UI。按钮调用 `recheckSessionActivity(id): Promise<void>`，复用经认证 snapshot 与必要的 request GET；成功仍显示具体其他未决请求或未关联继续入口，不静默清除记录。页面上的提示不含原文之外的敏感身份信息。

**状态与门禁真值表（对每个 request ID 和权威 attempt 分别计算；同 ID 多副本不得当作不同活动请求）。**

| 本地事实 | 对发送/继续的影响 | 如何更新 |
|---|---|---|
| preparing、running、unknown，或没有权威终态的 prepared/localRequest/candidate | 阻止发送和其他请求的继续；保留副本 | 明确未发送的准备作废并按原身份转 unsent；其他情况按原 ID 查询，失败/404 不视为终态 |
| completed 且 pending_messages | 阻止发送，允许重查/确认消息；保留副本 | 权威相同 attempt 完成后关联；关联失败维持同步/不一致提示 |
| completed 且 unassociated，未显式继续 | 阻止发送，允许该请求自身的“保留未关联记录并继续” | 核身份、attempt、完成响应和最新可接受活动观察；不以该记录或其副本自身阻止其继续 |
| completed 且 unassociated，已对该 ID/attempt 显式继续 | 本记录及其对应保留副本不再独立阻止发送；仍受所有其他请求及 activityGate 限制 | 在桶内保存 `continuedUnassociated` 的 request ID→attempt；attempt 或身份变化即失效；保留未关联记录和副本供恢复，不视为已匹配 |
| completed 且 matched | 不因该记录或其原副本单独阻止；其他门禁仍有效 | 仅在一致关联后按既有副本身份规则清理；清理失败保留副本并可见 |
| 权威 failed/interrupted | 不再是 running 门禁；保留失败内容和显式重试，仍受其他请求与活动观察限制 | 同 ID 的权威终态以现有 attempt 单调规则替代旧 running；旧 running 不得复活；未知或不同 attempt 不得猜成终态 |
| inconsistent 或同 ID 身份/内容冲突 | 阻止该请求继续和发送，提示重新查询；保留原记录及副本 | 只有对相同 ID、身份、payload/base 的权威查询证实可接纳终态，且冲突消解后解除；失败保留 |

所有请求求并集：只排除明确已继续的那个 completed/unassociated ID/attempt 及其对应副本；其他 ID 的未知、运行、待消息或冲突仍阻止。多个 writer 同 ID 仅在身份、payload、baseline 与权威事实一致时归属该记录，否则当冲突处理，不能按 ID 单独排除。`flushAll` 的退出未解决项与发送门禁是不同契约：继续后保留副本不自动代表退出备份已成功，不放宽原 flush 验证。

**观察事件、顺序和清理。** `activityEpoch` 只排列已接纳的本地观察；每次发起 snapshot 或 request GET 前捕获账号票据、目标会话、当前 epoch，并分配该桶单调 `activityObservationSequence`；含普通 `loadSession/applySnapshot`、完成确认、继续与独立重查的所有活动观察入口均使用同一机制。返回时在原子更新内验证票据、发起 epoch 未变化且该观察序号仍是最新已发出序号；符合才接纳活动字段并递增 epoch，否则丢弃其活动字段，保留较新事实并在必要时维持 uncertain。一个过期/失败响应不能解除较新检查；检查结果只由当前序号完成，失败恢复 uncertain 并保留所有记录。若其他权威观察或本地发送改变相关事实，立即递增 epoch 并使较旧在途观察失效；查询得到对应 ID/attempt 权威终态时按现有单调合并清除该 ID 的过时 running 门禁，不能删除其他请求。未过期空闲 snapshot 加上上述请求真值表允许 `activityGate=clear`；仍有其他未决请求时保留相应请求门禁而非声称空闲。重复查询应可重试，按用户选择继续后不能被其自身遗留副本再次锁死。账号切换清桶与本地 epoch；旧结果不得写新账号。request attempt 改变时清除该 ID 的旧 continued 标记；成功 matched 可移除该标记，保留现有精确副本清理规则。

**远端边界与提交。** epoch 和一次空闲 snapshot 仅证明本机最后一次可接受观察，不证明另一客户端之后没有领取。保留 `send` 真正 POST 前的本人 snapshot 校验及 A→B→A epoch/账号/request sequence 检查；即使该 snapshot 为空，远端仍可能在它之后 claim。后端 `_occupy` 原子条件及 `session_busy` 是最终兜底：收到冲突保留草稿和 prepared 副本、不得宣称发送成功，提示会话忙并刷新；刷新失败则 uncertain，不能自动重发、不能清新请求或原文。不能把后台实时空闲或跨客户端绝对互斥当作客户端观察的保证。

**真实行为验证。** 使用真实 Provider、路由、Chat 和底层延迟 fetch：冲突后输入禁用、重查按钮可见；失败持续禁用并显示失败，再权威空闲后仅在真值表许可时可发。覆盖无竞争 unassociated 显式继续、相同 ID 保留多副本、其他 ID running/unknown 阻止、权威终态清理旧 running、重复刷新及失败恢复、attempt 与账号变化清标记。并发 snapshot 与独立查询逆序返回，以及普通 `loadSession/applySnapshot` 与查询交错，确认较旧观察不可覆盖新活动。模拟另客户端在发送前空闲 snapshot 返回后领取、POST 返回 session_busy，确认原文/副本保留、无自动重发、可见反馈。所有案例先对冻结代码 RED，再实现 GREEN；分页/跨源同 ID 冲突、source/revision、真实路由和完整回归及独立审查要求全部保留。

## 独立计划审查 v3：可证明未发送与未知结果（覆盖此前真值表的相关行）

**证据和身份。** 在当前账号代次的 session 桶内为每个准备记录维护 `submissionEvidence`，以 userId、generation、sessionId、requestId、request sequence、原文/草稿 revision 和当前 writer 的精确副本身份绑定；值为 `before_post | rejected_busy | unknown`。证据仅能由控制器在对应同步事件设置，不能从副本存在、404、文本相同或客户端时间推断；任何 ID/payload/baseline、writer 身份不一致归冲突，不排除门禁、不删除。代次变化清内存证据，迟到响应只能在账号、会话、请求 ID、sequence、原 payload 及仍匹配的当前记录全部成立时改变该记录；不能更改新请求、草稿或其他 writer。未使用持久化状态推断历史 POST：重新登录或重启后的旧副本默认未知，按已有安全查询/用户恢复流程处理，不宣称仅凭本次内存证据可跨代生效。

**事件及状态转换。**

1. 在 POST 调用之前创建 `before_post`；实际发起 POST 的同一同步片段必须先把证据转为 `unknown`，再立即调用传输。若 A→B→A 或快照不合格在调用前作废，且票据、request sequence 和证据仍对应该准备，则状态为 `unsent`、证据保留 `before_post`，保留草稿与 prepared 副本；该 ID 精确绑定且一致的本人副本不再独立阻止发送。已有草稿可直接由用户再次点击发送，采用新的 request ID 和正常准备流程，旧副本保留且不得自行覆盖新编辑；其他未知记录继续阻塞。若没有草稿，用户可按现有明确恢复操作恢复原文，不能覆盖非空编辑。
2. POST 的 `unknown` 状态仅在收到该调用真实结构化 `session_busy` 拒绝、账号/session/request/sequence 和发送 payload 与当前记录一致、且没有同 ID 已接纳权威运行或终态/身份冲突时变 `rejected_busy`、request 变 `unsent`。后端 claim 首先查已有 ID，随后才在新 ID 判断锁、创建行并原子占用；因此本证据只描述该调用明确拒绝，若同 ID 曾被其他 writer 使用或存在矛盾权威观察，必须保守为冲突/未知，绝不据此假设该 ID 在全系统不存在。该证据精确匹配的本 writer prepared/request 副本从发送门禁排除但不删除；其余 writer 或不一致副本仍阻塞。远端活动请求仍由 activityGate 与权威查询限制；权威刷新恢复后原文保留且用户可明确重新发送，以新 ID 走正常提交。`payload_conflict` 不属于此类，继续 inconsistent。
3. 超时、断线、响应丢失、不可识别错误或身份/序号不匹配均为 `unknown`；POST 已调用即使 GET 404 也不能反推未发送。保持原 ID、payload、request 副本和查询/原 ID 重试出口，阻止新发送；查询失败或 404 保持未知，只有现有契约认可的权威观察或用户明确且安全的恢复流程改变状态。

**清理和跨会话恢复。** 仅排除与上述证据精确相符的当前 writer 副本；不批量删除，也不删除用户草稿。若用户明确放弃或恢复某项，沿用现有身份和写入 ID 精确匹配删除规则，失败则保留提示；退出 flush 仍逐项报告，不因发送门禁排除就将未备份视为成功。退出/重登时证据清空，副本重新归属当前账号后先按原有候选恢复和服务端核验规则处理；无法证明旧调用未发送时标未知，404 不自动放行。用户明确恢复 prepared 原文只能填入空草稿，已有草稿不得覆盖；对可能已 POST 的 request candidate 不得仅凭用户恢复动作宣称未提交或自动新发。此限制可能要求用户按已有重查/安全恢复出口处理，不得伪造可用性。

**验证：** 真实 Chat/Provider 和 fetch 延迟：A→B→A 在 POST 前作废后原草稿仍在、本人副本保留且用户可再次发送；`session_busy` 明确拒绝后远端结束、本人快照可接受，原文仍在且用户点击才可新 ID 发送；同 ID 其他 writer/权威 running 或 payload 冲突不得排除；网络中断和 404 始终未知、无新 POST；迟到响应和同账号换代不能写新请求或错误地设 rejected；退出重登副本仍可见、旧内存证据失效，空草稿时用户明确恢复，不覆盖新编辑，未知请求仍需权威核验。分别记录冻结代码真实业务 RED 和修复 GREEN，保留此前全部门禁、分页、活动观察、教学/画像、消息冲突、真实路由和独立完整审查要求。


## 独立计划审查 v4：同 ID 跨客户端边界（覆盖 v3 冲突表述）

**事实：** 后端 claim 先查询同 ID，存在时按原 payload 重放；新 ID 才检查活动锁。snapshot 的 pending_requests 排除 completed；因此一次 busy 仅证明该调用被拒绝，空闲 snapshot 或一次同 ID GET 404 均无法证明另一个客户端从未使用或之后不会使用该 ID。不能将 `rejected_busy` 作为发送门禁排除依据，也不能根据该响应换新 ID。保留 ID、payload、草稿和全部副本，状态显示“原请求结果待确认”，提供“查询原请求”和明确的“按原请求重试”入口，后者严格复用原 ID 和原 payload/上下文、现有权威校验与重发规则；不自动重试或以新 ID 重新提问。

**before_post 严格范围：** 只有能证明当前调用尚未发起 POST，且该 request ID 自生成以来未写入共享存储、未发送到任何网络或其他可被其他客户端观察的通道、未交给其他执行者，并且账号/session/request/sequence 仍匹配，才能视为可证明私有的 before_post 并排除它自身的发送门禁。任何无法证明未暴露的情况（包括已经写入共享恢复副本）按 unknown；原文与副本保留。现有流程在准备时写入 prepared 副本，不能仅凭“本次未发 POST”推断该 ID 私有。若实施方案不能在不破坏原有可靠备份的前提下证明私有性，就保守使用 unknown，不强行承诺 A→B→A 后立即新 ID 发送；需在测试中明确区分未暴露和已暴露。绝不把缺少观察当作未暴露证据。

**同 ID 重查及限制：** 执行本人 GET `/sessions/{session_id}/requests/{request_id}`，在发起和接收时核账号票据、session/request、sequence、观察顺序与副本身份；返回记录必须完整匹配 owner、profile、node、payload、base、attempt 及可信基线，按现有单调合并进入 running、failed/interrupted 或 completed；completed 必须走 persisted、精确 turn 消息关联或明确 unassociated 流程。若身份或 payload 冲突则 inconsistent，保留并提示；GET 失败或 404 维持 unknown。GET 404 后仍可能有别的客户端后续 claim，现有 DTO 无法提供全局排他证明：不能由此解锁并换新 ID。按原 ID 原 payload 显式重试依靠后端幂等 claim 降低重复提交风险；仍须承认 payload 冲突、stale_context、busy 和未知结果并保留原数据。已有本机其他 writer/副本若冲突亦需分别展示和核对，不能凭空闲 snapshot 忽略。

**可见出口与安全退出：** 对 unknown 展示“原请求可能已提交，查询原请求或按原请求重试”，查询失败或未查到保持原提示；绝不承诺后台实时空闲或必然可新发。原始退出 flush 的逐项备份结果和账号代次隔离保持不变；安全退出或换账号不清未确认副本。现有协议无法安全确定某个已暴露 ID 永远不会被其他客户端使用时，不能承诺无条件解除该门禁；由用户通过原 ID 重查/重试或现有明确的已完成未关联继续流程处理。

**真实交错验证：** 模拟当前 POST busy 后另客户端以同 ID claim 并完成、本人空闲 snapshot 无 completed，断言不出现新 ID POST；随后 GET 同 ID 完成并正确核对/关联。另测 GET 404 返回后远端同 ID claim、迟到旧 GET 在新权威记录之后返回、payload/基线冲突、账号换代及退出重登，均不能错误解锁或删除副本。私有 before_post 与已经共享副本两条路径分别测试；记录冻结代码业务 RED 和修复 GREEN。保留 v1–v3 中与本节不冲突的所有分页、活动观察、版本、路由、身份和完整审查要求。

## 准备 ID 与请求 ID 分离：恢复原始 A→B→A 目标（优先于 v4 冲突条款）

**事实与边界：** 当前 `writePrepared` 使用与 request 相同的 itemId，写入共享 Storage；`recoverPrepared` 只在空草稿恢复，`recheckCandidate` 用同 ID 关联准备副本。现有 schema 1 的 `prepared` 只含 text/sequence，没有类型标记，不能证明旧 itemId 是纯准备 ID。单纯推迟生成不够：准备副本与 request 副本的转移可能在任一步崩溃，必须保留可验证的对应关系。以下是设计提案，须通过独立复审与真实测试后实施，不声称当前代码已支持。

**数据及白名单：** 增加 `web/src/store/localRecovery.ts` 与 `web/src/store/localRecovery.test.ts` 到白名单。新增明确版本化的准备副本类型，字段包括独立随机 `prepareId`、owner/session/writer/writeId、text、draftRevision、阶段 `prepared | linked`，linked 还含精确 `requestId`、原 payload、可信 baseline；不得与 legacy schema 1 混为同一种含义。校验字段与原有大小限制、归属、只移除本人精确 writeId 的规则保留。新准备 ID 只标识可恢复的原文，从未作为服务端 request ID；其他客户端看到它不意味着任何请求已提交。旧 schema 1 prepared 一律视为可能关联相同 ID 的旧请求：按原 ID 和现有 request 候选/权威 GET 保守处理，不凭文本、缺少本地 request 副本或 404 升级为新准备类型，不自动改写/删除旧数据。旧副本仍可显示原文；安全退出及跨账号隔离不放宽。

**事件与顺序：** `send` 开始生成独立 prepareId、立即保存带版本标记的 `prepared` 副本并保持草稿，持有账号票据、session、准备 sequence 与路由 epoch；不生成 requestId。snapshot await 返回后验证全部票据、当前准备身份、有效本人 session/profile/版本、无其他未决门禁及路由 epoch。A→B→A 时不进入提交阶段：此 prepareId 从未是 request ID，标记已取消准备并保留原文和 prepared 副本，允许用户在其他门禁许可时使用当前草稿再次发送；草稿为空时用户明确恢复到空草稿，不能覆盖其他编辑。账号切换后旧准备不能继续写或发；有可信版本化纯准备副本时同账号重登可恢复原文，但不自动发送，其他账号不可见。

验证全部通过后，在同一同步片段生成全新 requestId 并构造与 snapshot 对应的 payload/baseline；先把本人准备副本安全写成 `linked` 并读回，确保 prepareId→requestId/payload/baseline 持久绑定，再写 request 副本并读回，最后再核票据、路由 epoch、准备 sequence 和门禁，之后同步进入 POST；无 await 夹在最后核对和实际发起之间。若任一存储写入/读回失败，则不 POST、保留原文及所有可能写入的副本，显示备份失败；不能用不完整写入当作已提交或假称可安全发新 ID。linked 一旦可见，即使尚未 POST 或页面崩溃，恢复也以原 requestId/payload 为未知结果保守重查或用户显式原 ID 重试；不能再自动把同一准备当作全新可发原文。这样在任何崩溃点要么只有可信纯准备副本，要么存在可识别的 linked 意图；如果 Storage 无原子单项覆盖和读回保证或存在不一致，则保留两个候选并标冲突/未知，不猜测。按原本 request ID 幂等及所有权契约处理 busy、404、重试；POST 开始后切会话不取消已发请求。

**恢复和清理：** 新纯 prepared 不构成服务端未决请求，只是文本副本；linked 及其 request 副本按 requestId 合并去重并施加未知门禁，双方身份、payload、baseline 不符或多 writer 竞争则保守冲突。成功权威接受及完成关联后，仅清理对应本 writer、exact writeId 与 payload/baseline 均一致的关联副本；失败保留并显示。准备取消后可保留其纯副本供用户选择删除或恢复，但它不能阻止用户继续；恢复写入空草稿并有可靠备份后才依既有规则清除本人精确副本。`flushAll` 逐项报告尚未持久/尚未解决项，不以发送门禁排除代替备份成功。request 副本持久化与 linked 的中断、存储失败、恢复检测和用户提示须逐点测试，不能以删除副本实现通过。

**必须验证：** 真实路由 A→B→A 且 snapshot 延迟：零 POST、不曾生成 requestId、纯准备副本和原文仍可恢复；用户返回后可明确点击并成功发送一次。覆盖纯准备跨账号/同账号重登、非空草稿保护、linked 写前/写后、request 写前/写后、POST 前后模拟中断、存储异常/读回失败、同 tick 双击、新旧准备及账号换代；确保 linked 重启后仅按原 ID 处理，旧 schema 1 不猜测；真实 busy 后同 ID 其他客户端完成、404、迟到结果仍遵守 v4。每个行为先对冻结产品 RED，修复 GREEN，保留完整回归和独立代码审查。实际 Storage 并发能力若无法保证上述单项覆盖和读回一致性，实施者须暂停并报告设计冲突，不做无法证明的自动迁移或放行。

## 存储不可用时保留发送能力（优先于前文禁止 POST 的冲突文字）

已批准 v1.3 第 63、141–142、253 行要求发送前尽力写入，失败须提示本机恢复不可用，但不因此禁止发送；主动换账号及“退出并保留本机”在未确认内容无法备份时必须阻止，401 则立即清认证并以固定提示报告失败。上节“任一写入失败则不 POST”与此冲突，撤销该限制。

**事件与状态：** 准备和 linked/request 写入与读回仍按上节顺序尽力进行，但任一失败或读回不一致时标记该次 `recoveryAvailability=memory_only`（也记录哪些副本确已读回、哪些未知），在 Chat 明确显示“本机恢复副本不可用，关闭页面或账号失效后未确认内容可能丢失”；在完整身份、请求、路由、活动门禁检查通过后仍允许用户已发起的发送继续，不要求额外点击。不得声称所有副本已保存，也不能根据读取失败断言某次写入必然不存在。内存保留 prepareId、requestId、payload、baseline、原文、sequence 与当前账号票据，POST 一旦发起即 unknown；掉线、404、busy 和跨客户端竞态沿 v4 原 ID 权威重查/显式重试，不换新 ID。备份失败不得清空草稿、删除其他候选或妨碍同会话内显示未确认记录；成功的 server 完成仍按真实消息关联和既有清理条件处理。

**身份与生命周期：** 内存仅在当前 generation 有效。主动换账号或同账号显式重登、显式退出保留本机时先重试逐项备份并读回，失败保持当前账号、内存和页面且列出失败项；不得经另一条路径绕过。强制 401 必须立即同步尝试备份并清认证换代，失败时显示不含敏感信息的固定丢失警告，旧结果不得写入新账号。强关/pagehide 只能尽力写，不承诺成功；重启或重登后只能按实际可读副本和服务端本人权威记录恢复，若 requestId 和 linked 都未持久化且服务器没有记录，无法定位或保证恢复原内容。不能把未观察到当作从未发送，不能将任何旧内存证据用于新代次。

**事实冲突与保守恢复：** 若纯 prepared 曾成功持久化、随后 linked 写入或读回失败但仍允许 POST，崩溃后仅看到纯 prepared 并不能证明该内容从未进入 POST；Storage 没有可靠的跨键事务或失败标志持久性时，无法同时保证该纯副本重登后可无条件当作未发送且避免重复。因此此前“任意重启看到纯 prepared 即可安全新发”的承诺撤销：当前代次内尚未生成 requestId 的取消可按准备证据恢复并继续；重启后仅纯 prepared、无法证明转移未发生时，显示原文及不确定警告，不自动发新 ID，不以缺少 linked、request 或 GET 404 推断未发送。可读 linked/request 按原 ID 查询或显式原 ID 重试；服务器可见的本人请求按权威内容核对。若用户明确选择复制原文，只能放入空草稿并明确提示可能重复，不能将其动作当作原请求不存在的证明。该边界是对备份不可用时的事实说明，不阻止当前代次发起发送；无法提供无持久标志且跨重启完全确定的保证。

**验证：** 真实 Storage setItem/getItem 抛异常和写入成功但读回失败，确认可见警告、符合原规则的 POST 仍发生、内存 unknown 可重查且不假称持久备份；主动换账号/退出失败保持旧账号与内容，401 立即清除并固定警告，旧响应不污染新账号。模拟纯 prepared 成功、linked 或 request 写失败、POST 发起后崩溃重登，验证不凭纯副本自动新 ID 发送；可读 linked 时原 ID 恢复。保留真实 A→B→A 未发阶段当前代次可继续、所有先 RED 后 GREEN、独立审查和完整回归要求。

## 第五轮审查：跨标签准备副本的未知状态（优先于前文冲突文字）

**已批准范围及事实：** 保留当前执行上下文、同账号 generation、session、prepareId 和 sequence 均匹配，且在生成 requestId 前由路由 epoch 失效明确取消的 A→B→A 恢复并继续目标；保持 v1.3 存储失败仍可发送且显示本机恢复不可用、主动身份切换/退出备份门禁、401 即时清认证。Storage 按 writer 分键但同源共享；单项读回或 writer/writeId 验证不能形成跨标签事务。其他标签或重登无法观察原执行上下文是否后来 linked/POST，纯 prepared 不是未发送证据，包括 linked 写失败后仍可见的纯副本。

**状态与门禁：** 仅当前上下文持有内存取消证据，且账号 generation/session/prepareId/sequence 匹配、从未创建 requestId、取消后旧续体永久失效，才能将该纯准备项视为确定取消，不单独阻止当前用户继续；草稿保持已有编辑。所有其他执行上下文（包括同 writer 身份无法证明仍是原执行上下文、其他标签、重登或证据丢失）看到纯 prepared 均为 `unknown_preparation`，提示“这段内容可能已在其他页面发送，无法确认”，对该候选阻止静默以新 ID 发送；不阻止查看原文、权威重查已知关联 request ID 或显式处理其他可辨识请求。保留候选，未知项按独立 prepareId/writer/writeId 计入门禁；关联 request 的 running/unknown 等仍单独按既有规则判断，不能因处理文本而解除。其他请求、账号和 activityGate 仍各自生效。

**显式知情复制：** 提供“复制原文并自行决定是否重新提问”，用户先看到明确警示“另一页面可能已经发送，重新提问可能产生重复回复；系统无法确认是否已发送”，需针对该具体候选主动确认此风险，不能将普通恢复或重查等同确认。仅当当前草稿为空、账号/session/候选身份仍匹配时复制；非空草稿保持不变并提示先处理当前草稿。复制不发送、不删除候选、不声称不存在原请求。为避免无出口，对该具体候选记录本执行上下文的风险已知选择；用户随后显式按发送按钮才可把这段草稿作为新提问，该选择仅解除该候选的文本不确定门禁，不解除任何已知 linked/request、其他未知候选、活动状态或身份门禁。内容编辑后视为用户新编辑，但不得自动发送；重新登录或候选 writeId 改变时风险选择失效、再次确认。候选不因复制或发送而被自动删除，退出 flush 继续逐项报告。

**再次核验与不可避免边界：** 执行恢复、风险确认及最终发起新提问前，按 owner/session/writer/itemId/writeId 重新读共享 Storage，与已展示候选完整内容比较；发现升级 linked、写入 ID 或内容变更、缺失、读取失败均撤销该候选的风险选择，刷新候选并走已知 request ID 重查或保守提示。此核验只能发现之前已发生的变化，不能防止原标签在核验之后升级并提交；即使核验一致也不声称绝对未发送。用户知情选择是在明确告知可能重复后主动重新提问，不是系统提供跨标签排他保证。linked 写失败且 POST 继续时风险警告与 memory_only 规则不变，其他标签仍按未知处理。

**真实双标签验证：** 两个独立 controller/Provider 与真实共享 Storage，通过底层 fetch/存储屏障控制 A、B：A 写纯 prepared，B 读取并缓存，A 升级 linked、POST 完成，B 执行恢复/发送；断言 B 不自动以新 ID 发，重读发现 writeId/阶段变化并撤销选择，已知 request 经身份核对后展示。另一场景 A linked 写入失败、纯副本持续可读而 POST 成功，B 依旧显示未知与明确重复风险，不静默新发；再安排 B 最后核验后 A 才升级，验证系统仍明确警示并只在 B 针对候选确认后由用户另行点击发送，不能声称事务保证。测试 B 非空草稿不覆盖、其他未决请求仍阻塞、候选变更和重登撤销选择；分别在冻结代码 RED、修复 GREEN。当前标签 A→B→A 在 requestId 生成前确定取消可恢复并继续，保留账号切换/退出、401、错误及全部此前测试。
