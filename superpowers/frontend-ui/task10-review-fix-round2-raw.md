# Task10 第二轮审查修复：三层设计原始文档

## 1. 模块总览

目标是按 `docs/delivery/study-workspace-goal/evidence/Task10/review-fix-final-product-code-review.md` 修复三个阻断，保留已批准的 Task10 v1.3 与第一轮审查修复契约。范围仅涉及客户端的最近会话恢复、已完成请求的本人准备副本清理、普通会话快照与历史分页的衔接；不改服务端、数据协议、主题设计、其他窗口的意图路由，也不将客户端缓存变化称为服务端数据丢失。

事实核对：`useWorkspaceController` 的 `/chat` 恢复 effect 只在其依赖变化时启动 `lastSession`；`WorkspaceLayout` 的 `retryWorkspace` 当前不返回读取结果，重试成功仅更新 workspace store。`send` 的 `prepared` 使用独立 prepareId，linked 候选含 requestId；`recheckCandidate` 当前用 requestId 查 prepared，且已 matched 时提前返回。`applySnapshot` 在教学版本不旧时替换整个消息列表及游标，`loadOlder` 用 load sequence 和 cursor 判定回复是否过期。后端 `SessionService.load_messages` 的游标对应 `(turn_index, role_order, id)` 的严格向更早边界；新旧页面重叠或顺序连续不能仅因同一教学版本就假定。审查证实切回造成客户端旧页消失与该入口缺少同 ID 检查；普通 reload 与上翻并发的具体错误仍需测试证明，不预称已经发生。

技术选型：沿用 React、现有认证票据和 store、TypeScript、Vitest、原本 `loadSnapshot/loadMessages` 与 storage 接口；不引入依赖。状态只证明当前客户端观察，不声称跨标签事务或服务器实时静止。冻结输入以 `review-fix-source-after-v3.json` 和代码审查报告为基线；开始前必须重算 46 项并记录差异，发现外部源码变化先停止并通知主会话。

## 2. 子模块概述与契约

### 2.1 最近会话读取重试与导航

职责：区分 workspace 读取与写入错误，读取重试成功后在仍属同一次默认 `/chat` 访问且用户未改变选择时恢复服务端最近会话；保存重试只处理保存，不额外导航。数据流为 `WorkspaceLayout` 发起 → controller 结果 → 仍当前的路由及账号检查 → 按可用 ID 导航 → 既有路由加载会话。空 ID 留在默认页，网络错误保留可重试提示，401 按现有认证失效处理，错误文案区分加载与保存。

身份及防抢导航：读取重试捕获账号 userId/token/generation、发起时 location.key、精确 pathname、localOnly 状态与 workspace 选择 sequence；返回后再次核对所有条件，确认仍是同一次 `/chat` 或 `/chat/` 访问、非 localOnly、没有新选择/冲突，且结果属于同次成功读取。离开后回到相同 pathname 的新 location.key 也不允许旧重试导航。重复点击去重或分配单调序列，较早完成不能覆盖较晚用户动作。显式选 A/B、打开知识库/画像、浏览器历史、新建会话、退出或同账号重登均是不可被旧响应抢占的用户动作；请求继续按账号票据处理但不得改变新路径。初始恢复 effect 与重试不得重复导航；重试读到 null 不循环重试。新增错误来源标记须区分 load/save 并在账号换代、成功及冲突处理时正确更新，避免以 `dirty` 的瞬时值猜测先前错误来源。

### 2.2 匹配完成请求后本人 linked 副本的精确清理

职责：将“服务端身份经核验的 completed + 本人可信 baseline + 历史消息已精确关联 matched”与可删除的本页 linked 准备关联；原 ID 查询从 request 副本或 linked 副本进入，以及正常 POST 完成路径，都应使用同一幂等清理门禁。`unassociated`、inconsistent、failed、running、404、网络错误和仅有 POST HTTP 200 均不能触发清理。

数据结构：`prepared[prepareId]`、`preparedCandidates` 的 schema 2 linked 候选、`localRequests[requestId]` 和 request 记录不混用键。精确身份至少包括账号 generation/userId、session、当前 writerId、prepareId、writeId、requestId、完整 payload、baseline、request attempt 和 matched 记录；最终处理时重新读取并验证 exact candidate。持久候选只有删除并读回成功才能宣称删除；失败或内容变化保留已知候选、提示可重新检查，不改变其他 writer、其他 prepareId、其他 request、草稿与已确认结果。已确认匹配的**内存工作项**与持久候选独立处理，见 3.2 的三态规则；不能因为持久读取不可用就把已由服务器保存且已核对消息的内存请求当成永久未决。清理发生前后的 writeId 变化、会话/账号换代或 attempt 变更使旧续体失效。

已 matched 的原 ID 被再次查询时，不因提前 return 跳过有资格的清理；也不能仅凭任一 candidate 的 ID 匹配就使用先前 matched 状态：必须再次验证 payload、baseline、owner、session、attempt 与当前 matched 记录。`getLocalRecovery().remove` 是本 writer 的读-比对-删-读，不是跨标签原子事务；设计不宣称它能排除浏览器进程间同时改写。重登后 writer 变化，旧 writer 副本不因本页匹配而删除；本轮新增有清晰提示、逐候选的显式确认继续出口，详见 3.2。

### 2.3 普通 snapshot 与历史页的衔接

职责：进入或重新加载同会话时，既显示权威最新内容，也保留已成功加载的历史、最早可继续翻页的 cursor、已访问 cursor、阅读锚点及在途分页的可证明结果；消息冲突不能静默选择一个版本。账号、load sequence、message epoch 和会话身份仍分别生效，教学版本、画像 revision、活动观察各按原规则独立合并。

首次加载没有已确认历史时，采用原有 snapshot 页和 cursor；已有分页链时，snapshot 不得直接重置旧页。维护可追溯的连续已加载区间：最新 snapshot 页、每个按前一 cursor 成功读取的页及其前沿身份；不能把 `confirmCompleted` 偶然合入的孤立消息当作连续页证据。按完整消息字段比较相同 ID；相等才去重、按现有消息序排序，不同则保留当前消息、cursor、visited、锚点、在途操作和关联状态，显示安全错误，允许用户重试，不伪造 matched。有效最新页与现存连续链重叠后才可并入，保留最早页的向旧 cursor；新消息多到第一页与旧链不重叠时，从 snapshot 的 next_cursor 顺序向旧读取直到与可信连续链相接，逐页验证 owner/session 所属请求上下文、cursor 不重复/回环、所有 ID 完整一致，保留旧链和新页而不形成静默缺口。若请求失败、账号/会话换代、cursor 非法或抵达终点仍无可信交集，保留既有历史及其分页前沿，显示同步失败与显式重试，不把缺失当删除；中间结果不得作为已同步的完整连续历史。

在途上翻与 reload：本方案要求新旧观察分别携带会话和分页身份，旧页只有原 cursor 仍是当前待用前沿、请求身份和账号仍一致时才可一次性合入；否则丢弃其分页变更并可重试，不写入其他桶。reload 前后顺序、cursor 在途变化和上翻失败各测，避免以旧 load sequence 无条件失效造成不可恢复的前沿或以旧 cursor 覆盖新前沿。`continueUnassociated` 的 snapshot 必须经过同一连续性与冲突门禁，不得在无并发时重置旧分页；只有桥接成功、当前 account/request/attempt/sequence 和本人活动空闲观察均仍有效，才能原子保留分页并记下显式继续，失败保持未关联和副本、显示重试，不解除其他请求门禁。`confirmCompleted` 仍可把精确验证的消息并入显示列表，但这些孤立消息不改变连续页前沿、cursor 和 visited，也不能作为桥接命中；所有入口使用同一角色排序及完整 ID 冲突规则。若无法依据现有协议证明连续性，保留并报错而非虚构或静默漏页；分页只保证读取接口提供的历史，不保证另端随时不再添加新消息。

## 3. 子模块详细实施设计

### 3.1 最近会话恢复：函数、字段、行为

- `retryWorkspace` 输出可辨识的完成结果：读取成功时返回本次 workspace 读取所获的 lastSessionId 与账号/序列信息；写入、失败、过期为不同结果。不得把读取失败与有效 null 合并成“成功无会话”；初次 `lastSession` 的既有调用与退出保存语义保留。
- `workspace` 状态增加明确的错误来源与需要的读取序号，读取成功、写入成功、冲突及账号换代分别清理或更新；读取发起时捕获选择 sequence、已知 version 及读取身份；其间用户选择变化或新写入已完成时，旧读取不能覆盖较新 `lastSessionId/version/desiredSessionId` 或清除较新错误，也不能触发导航。既有 dirty 和冲突数据不得被重试覆盖。若被 `flushWorkspace` 共用的读取因并发选择变化而失效，调用者必须可重新读取或沿用较新已确认版本，不能使写入永久卡住；同 generation 的去重不能把先前过期结果误当当前读取成功。
- `WorkspaceLayout` 的重试处理函数捕获 route key/path、账号票据、localOnly、选择序号及本次重试身份，等待结果并原子核验再导航；文案分别为最近会话加载失败/保存失败及对应重试按钮。当前已有的初始 effect 不因订阅变化进入重复请求循环。

### 3.2 linked 清理：函数、字段、行为

- **linked 是唯一持久身份的查询路径：** 区分来源为 `linked`、`request` 和当前代次 `memory` 的查询上下文；linked 来源保留实际 prepared 副本的 schema、owner、session、writerId、prepareId、writeId、requestId、text、完整 payload 和 baseline，不创建或展示一个声称存在于 request 存储的伪候选。`recheckLinkedPreparation` 使用原 requestId 发本人权威 GET，GET 前、GET 返回后、完成消息分页及最终 patch 前均重新读取并逐字段核验原 linked 候选及账号 generation/会话/操作 sequence；任何内容、writeId、baseline 或归属变化均放弃该次查询或关联结果，保留候选并提示重新检查。来源为实际 request 候选时继续核验该 request 项；内存来源仅限已知当前 generation，不能把它当作可靠落盘。
- **现状证据边界：** 当前 `recheckLinkedPreparation` 会构造 request 形状的临时对象，但 `recoveryCandidateUnchanged` 对仍带 `phase: linked` 的对象实际读取 prepared 列表并按变换后的完整对象比较；不能断言现有代码一律要求 request 存储项。已有 linked 原 ID 查询/404 重试定向测试不证明“唯一 linked → 完成消息匹配 → 旧 writer 知情继续”的全链路，仍需在冻结代码上执行该链路并保存实际业务 RED；若该链路意外通过，记录事实并测试审查其余确实缺失的用户出口，禁止捏造失败。
- **request 候选缺失与不可读：** linked 本身完整、可重读且身份有效时，request 列表完整读取为空、写入失败后缺失、或 request 列表读取失败均不妨碍用户按 linked 中原 ID 发起只读权威查询；不为了查询强行写 request 副本，也不把 request 读取失败当作不存在。request 读取失败时显示“其他本机请求暂时无法读取，不能确认是否还有未决请求”，保留既有已知 request/其他 writer 门禁；可展示经身份与消息校验的原请求状态，但不能以列表为空或查询结果替代对其他候选的完整检查。已知外部候选的逐项继续确认、原 ID 显式重试及新提问发送，在其他候选读取不完整时需恢复读取并检查现存其他项后才能解锁；这不改变没有已知外部候选时普通已授权发送遇本机备份失败的原警告并允许发送契约。
- linked 来源的 GET 若为 completed，必须校验 server owner/session/request/profile/node、payload、base、attempt、persisted response 及可信 baseline（包括 turn）；再按现有消息关联流程核查唯一 user/assistant 消息、完整同 ID 冲突并保留证据来源。可信 baseline 缺失或不满足绑定校验时可查原 ID，但不得伪造 turn 或 matched，沿现有 unassociated/不一致路径，不显示匹配后知情继续按钮。running、failed、404、payload/baseline 冲突、消息缺失均不得仅凭查询解除 linked 自身门禁；404 不能证明原 ID 从未或将来不会被其他页面使用，原 ID 原 payload 的显式重试仅在其他门禁许可时提供，不能自动重发或换 ID。
- **候选和其他 writer 的时序：** 当前 linked 候选在 GET/消息分页/用户确认期间变化、写入同键的新 writeId、账号代次/attempt 变化，均撤销该来源的验证和豁免；不同 writer 的同 ID 同内容项要各自明确确认，不同 payload、profile、node 或 baseline 项仍按冲突阻止，不因本项 matched 消除。用户确认后、下一次发送前重新读取 prepared 和 request 列表，核对 exact 已确认候选及其他已知/新出现的未决项；读取不完整不得为已知外部候选沿用豁免。最终读取后另页仍可写入，显示已批准的风险提示；不得把一次读取描绘成跨页面锁。
- 控制器内部增加一个职责单一的处理过程，输入账号票据、sessionId、requestId、可信 payload/baseline、已匹配 attempt；输出 `matched-absent`、`matched-removed`、`matched-storage-uncertain`、`conflict/stale` 等明确结果。先重新验证 persisted completed、对应唯一 user/assistant 消息 matched、当前 account/session/request/attempt/payload/baseline，再按 `linked.requestId` 查本人精确 prepareId；只有当前 writer 才尝试 `remove`，不对其他 writer 调删除。多个候选逐项处理，未确认的其他候选仍可见且各自参与门禁。
- **当前完整读取、本人精确项不存在：** 仅当 `listResult.ok` 且没有同键新 writeId/冲突候选，才认定该次读取时精确项不存在；不倒推它从未写入、也不承诺以后不会出现。该匹配请求对应的内存 `prepared`/`localRequests` 可标记已完成并从待备份集合移出；删除仅指内存工作项，不宣传删除过持久副本。完全读取后若同键内容变更，视为冲突而非不存在。
- **能读到精确本人持久项：** 以完整 exact identity 调用本 writer `remove`，成功并读回不存在才报告该持久项已删除；失败或发现变化保留原候选与清理待重试提示。已 matched 的内存内容不再作为未保存请求重复写回，但持久候选的保留和未决项必须分别展示；不得清除其他 writer 或用这次完成来解除其他请求门禁。
- **读取失败、不完整或写入返回失败但落盘未知：** 不从失败结果推断没落盘、不宣称持久副本不存在或已删除；保留已知候选和处理信息，记录独立 `cleanupUncertain`，显示“本轮回复已保存，但本机副本状态无法确认，重新登录后可能再次出现；可重新检查”。对已经本人权威 matched 的同一 request，仅将精确绑定的当前代次内存工作项移出未保存待备份集合，不能重复写入、不能让 `flushAll`/`prepareAccountTransition` 因该已完成项永久卡住。若只存在本次已 matched 的内存项且没有任何已知其他候选/请求，存储不可读时按既有备份故障契约警告并允许用户主动继续或退出；退出前给出可见提示，不能伪称持久清理成功。
- 若此时还缓存着本 writer 的已 matched 候选，因不能重读而无法证明它此刻未变化，不能静默宣称处理完或删除：显示“当前页面已核对的请求已保存，但本机副本此刻无法确认，其他页面可能改变或新增副本”，用户可以明确选择“知悉本机状态不确定，继续本页”；此选择只针对该代次的已 matched 记录及已知原候选，不宣称存储精确状态，且该选择不会删除或改写存储。恢复读取时先重核候选和全部已知其他项，发现变化即撤销选择；重新登录不继承。若有其他已知外部候选、未决请求、未保存草稿或冲突，仍分别执行原门禁，不因这次选择豁免；无法读取时不允许为已知外部候选新建或沿用需要精确重读的豁免。完全不可读时无法发现另页新建的未知项，明确告知并不声称跨页排他；401 即时清认证的原规则不变。
- **旧 writer 的知情继续：** 对每个 schema 2 linked 候选，新增“确认此请求已完成并继续”入口。先按原 requestId 权威查询并校验 user/session/profile/node、完整 payload、baseline/attempt、persisted completed，再完成历史消息唯一配对和冲突检查；无可信 baseline、404、running、failed、unassociated、冲突或消息未匹配时不显示可确认成功。用户看见“此请求和历史已核对；本机副本可能仍由另一页面使用，本操作只让当前页面继续，不会删除副本；重新登录需再次确认”，显式针对具体 owner/session/writer/prepareId/writeId/requestId/payload/baseline/attempt 确认。只记录当前账号代次的该候选豁免，不删除持久内容、不自动发送、不覆盖草稿、不解除其他候选/请求/活动门禁。
- 在用户下一次主动发送前重新完整读取该候选并比较完整身份和所有已知其他项；候选变化、出现新冲突、attempt 或账号代次变化撤销豁免，读不完整保留记录并要求恢复读取后重新检查。没有已知外部候选、只有前述已完成内存项且 Storage 完全不可用时仍适用“警告后可发”的原契约；本例不把已知外部候选的读取失败误当作空。只读回不能锁住其他页面：对确认后、最终读后发生的其他页面写入无法形成跨标签原子保证，提示必须说明该边界，不能声称绝对不会再出现或永久消除重复风险。

### 3.3 历史合并：函数、字段、行为

- `beginSessionLoad/applySnapshot` 保留 account/load ticket，并新增或扩展用于连续页来源和分页版本的最小字段；`loadOlder` 给成功页记录其输入 cursor、输出 cursor 与页的消息身份。具体字段以能够证明首尾连续及判断在途页是否仍适用为准，不能把 opaque cursor 解码成客户端权威顺序。合并后的显示顺序须遵循后端 `(turn_index, role_order, id)`，role_order 为 user 0、assistant 1、其他 2，不能假设同回合 id 顺序总与角色一致。
- controller 增加共享的按 snapshot cursor 向更早获取桥接页过程，输入认证票据、sessionId、操作身份（load sequence 或 continue 的 requestId/attempt/sequence）、snapshot 页、当前连续链标识；输出可合并连续页或失败/过期，不直接修改其他桶。`loadSession` 与 `continueUnassociated` 均消费它；后者最终 patch 额外校验本人空闲观察及请求状态，成功才设置 `continuedUnassociated`，桥接失败或冲突不继续。每个网络边界和最终单次 patch 都重新检查身份、游标、冲突和 epoch；若上翻并发改变前沿，则基于当前状态重新验证交集，无法安全合并就保留当前值并提示重试。
- 同 ID 冲突比较当前桶、snapshot 及所有桥接页中的完整消息对象；分页内部重复冲突、游标循环、非数组或身份异常均安全失败。独立更新教学、画像、活动字段时遵守原计划；发生消息冲突不得写入冲突消息或以页合并证明关联完成，错误展示不得抹除已有恢复告警。

## 4. 验证与交接

逐项先编写真实 Provider/路由/控制器与底层延迟 fetch 测试，运行冻结实现并保存带退出码且业务断言失败的 RED，再最小实现并保存 GREEN。对现有合法行为做反向回归；失败属于原有缺陷或测试设置必须在日志中分别说明，不得修改断言掩盖。先前 237 项和 46 项哈希仅证明旧快照，不证明本次修复。产品代码完成后运行全前端测试和构建，按原清单及新文件产出前后哈希；主会话保护 README/asset 用户改动、检查并按项目规定更新 README。随后交不参与编码的 agent 完整审查全部 Task10 范围（非只看三个修复），审查 PASS 后再执行原计划真实浏览器、后端和模型验收；PostgreSQL 重启及跨账号真实持久化验收按 Task13 约束执行。实测代理连通和 GET/POST 结果才可作为真实模型证据。
