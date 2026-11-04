# Task10 第五轮审查修复：三层详细设计（raw）

依据：`docs/delivery/study-workspace-goal/evidence/Task10/review4-final-product-code-review.md`，继承 Task10 原计划及前四轮设计、审查和门禁。本轮先复现，未经独立计划审查通过不编码。旧 continue 桥接失败叠加活动重查、跨画像异常快照均是源码推导，审查未执行业务交错，不能表述为已发生的线上故障。

## 一、模块总览

目标：在旧继续操作的历史桥接失败与较新活动观察交错时，按各领域的有效身份和先后顺序处理画像、活动、历史与请求错误，阻止旧活动相关错误覆盖较新请求，同时保留仍有效的历史失败提示与重试；在已知会话绑定与输入快照画像不兼容时，防止跨画像教学、画像、消息或请求状态被混合，并保留清晰的恢复出口。

后端事实核对：`SessionService.create` 在创建时绑定 profile，`load_snapshot` 根据已拥有会话行的 profile_id 读取同一用户画像及摘要；当前 `app/api/sessions.py` 路由包括新建、读取、view-state、active-node、请求和重试，未见会话画像改绑路由。`conversation_service.py` 对既有会话指定的不同画像进行检查；但 `alembic/versions/20261023_session_workspace_state.py` 存在历史数据 null 画像补绑定迁移，数据库外部变更、历史版本和异常响应也不能凭上述代码排除。因此 p1→p2 的快照作为异常或外部变更防御，不冒充正常用户操作；null→p1 需单独讨论迁移/刷新边界，不能断言所有 profile_id 永远不变。先以实际路由、真实 controller/store 和可控响应复现，不更改后端或响应契约。

继承账号代次、load sequence、请求 ID/sequence/attempt、活动 epoch/观察序号、教学版本、画像 revision、连续消息和旧游标、writer 候选身份等原门禁。不同领域有不同发布资格：活动过期不能覆盖较新活动或请求错误；但不能因此一概丢掉同一 load 中仍有效且身份可信的画像及历史失败。完成后全量验证、完整 Task10 独立审查、真实持久化验收依次进行。

## 二、子模块概述

### 2.1 继续操作的历史错误与活动错误分离

continue 捕获账号、会话、原 request ID/sequence/attempt/association、load sequence、活动 epoch/观察序号。旧桥接请求在途时，新活动查询开始或完成但 load 和原请求未变；旧桥接失败。静态路径表明 `applySnapshot` 在活动过期时仍可写历史错误且返回 true，随后继续写请求错误。先验证真实页面是否呈现此情况；特别区分历史桥接失败本身与依赖活动观察的请求错误。

历史错误仅在账号、会话、原请求身份、历史加载序号及对应历史任务仍有效时可写；若新活动观察不影响该历史任务、且没有较新历史成功或错误，它仍是当前有效事实，必须展示并保留重新同步入口，不能机械地因为活动序号变化而吞掉。旧请求错误还须其活动 epoch 与观察序号有效，否则保留现有请求错误/较新状态，不写过期的“尚无法继续”之类信息；正常活动上下文未变且桥接确实失败时保留原请求错误。迟到的活动错误不能覆盖新活动锁；较新的 load、账号换代、替换请求/attempt、较新的历史错误或成功则依各自票据拒绝旧发布。画像遵循自己可比的 revision 和身份规则，不受单纯活动过期牵连。

### 2.2 画像绑定兼容性与恢复

会话已有可信 session 时，以其 owner/session/profile ID 作为绑定上下文；客户端仅验证 DTO 实际提供的身份字段：session 的 user_id/session_id/profile_id、profile 的 id/user_id、summary 内 node/edge 的 profile_id，以及 pending request 的 user_id/session_id/profile_id。summary 和 evidence 本身没有 user_id/profile_id，客户端不能独立证明其归属，须信任已认证的后端 snapshot/summary 查询及其数据库约束；不以缺失字段臆造验证结果。recent_evidence 的 session_id 可不同于当前会话：同一用户和画像下的不同会话共享画像证据是合法行为，不能按当前 session 过滤或拒绝。不同非空画像 p1→p2 时在此客户端视为不兼容，拒绝将新画像或其 revision 与旧画像做同一序列比较，也不将其 session、教学、消息、活动或请求混入现有会话。保留旧组、草稿、已加载消息与游标、旧请求与副本；设置保守门禁和可见、可重新查询的身份冲突提示；不自动重发、不标记 matched/continued、不清 writer 副本。

已知绑定为 null 的旧会话接收到非空画像，可能对应历史迁移而非恶意异常。该仓库迁移在升级时离线补绑，尚无证据表明运行中的会话自动重绑是受支持用户流程；先核对迁移执行条件并测试客户端。默认不得静默混合旧 null 会话数据与新画像数据；保留可恢复的旧内容、阻断发送并提示刷新/重新查询，不能自动删除旧历史或备份。已拥有 session 的非空→null 同样防御；首次加载没有可信旧 session 时，只要服务器内部及归属验证通过即可接纳 null 或非空绑定。若未来要接受已运行页面中可靠迁移后的新绑定，必须另行确认权威语义及用户安全路径，不在本轮发明无证据的自动重新绑定。

检查所有快照入口：`loadSession` 正常/桥接失败、`continueUnassociated`、`confirmCompleted`、`recheckSessionActivity`、`send` 的发送前快照、恢复候选/重发/请求重试以及草稿/阅读位置等读取；不把不同 profile 的错误 revision、active_request_id 或已验证消息写入旧组。对于不写画像或教学的 view 同步，单独核查是否可能污染绑定并仅在业务测试证明需要时扩大；不机械地让无关领域回退或删除用户数据。新账号或新会话的初始加载不应受旧账号 ID 缓存影响。

### 2.3 错误与独立领域的恢复边界

遇到活动观察过期但历史失败仍有效时，显示历史重试，不重写请求错误；画像如来源仍可信且 revision 更新，可独立进步，低 revision 不回退，同版本内容冲突保留并警告。遇到身份不兼容时不接纳该快照的任何绑定依赖数据，保留最新有效旧组和草稿、活动门禁，不能把旧画像版本与新画像版本混比。重新查询得到与原可信绑定一致的有效快照后，恢复教学/画像/活动并清理本次身份错误，但仍需独立满足历史连续与当前活动查询；继续未关联请求保留原确认机制与手动恢复出口。若长期出现不兼容响应，页面须说明用户可重试，不能伪造已安全恢复，也不自动重发或清理。

## 三、详细实施设计

### 3.1 操作票据与错误分派

审查 `continueUnassociated`、`connectSnapshotHistory`、`applySnapshot` 及请求状态写入的现有票据：输入账号 generation、用户、会话、load sequence、request ID/sequence/attempt/association、活动 epoch/观察序号及当前历史同步进度；输出分别是历史失败可否发布、画像是否可独立更新、请求错误可否发布和活动是否可发布。只把与对应领域相关的过期条件用于该领域。必要时给当前历史错误明确任务身份以防旧任务覆盖新错误；不能仅测试最终 gate 而漏掉 request.error。失败后页面仍显示原历史、草稿、最新锁，并能点击实际重试；有效失败提示和旧活动错误分别验证。

### 3.2 可信会话绑定校验

设计一个可复用的纯校验边界或等效局部规则，输入捕获账号、目标会话、当前可信 session 和 incoming snapshot，输出可信首次加载、同绑定、内部/所有权无效或已知绑定不兼容。它不比较不同画像 revision，也不凭一条异常快照覆盖可信绑定。对 null 必须区分“无 session 缓存”和“有 session、profile 为 null”，不能以 falsy 把二者混淆。请求阶段保留请求和本地副本的 owner/profile/payload/baseline 精确身份；不兼容不能启动不同画像的 POST/重试或匹配清理。

校验时机要早于 `applySnapshot` 的画像 revision、活动请求、教学和历史任何写入，以及 `confirmCompleted` 的匹配消息/清理等副作用；已启动的桥接页结果仍须校验最新账号、load 和绑定。错误发布也须对应当前账号和观察序号，不得让迟到不兼容响应覆盖较新正确加载。对首次无 session 和合法 null 画像保持可加载，不绕过服务端归属检查。

### 3.3 可恢复交互与分页

明确区分绑定异常提示与教学同版本冲突：用户需要看见具体风险及重试入口；再次读取到原绑定后仅清除对应身份错误，不能误清其他历史、画像冲突、备份写失败或活动警告。恢复后已加载旧消息和 cursor/visited 保持，成功桥接才提交连续新消息；活动清除仍需当前权威 idle，running 或未知继续阻断。所有请求身份、草稿、副本与其他 writer 精确清理规则维持原样。所有字段合并按各自版本单调；用户后续编辑的草稿及导航不能被旧任务抢占。

## 四、验证与交付

真实业务 RED 先于产品更改，必要时证明无法到达并明确证据；记录网络开始/结束顺序、旧/新身份及行为。每一安全防御至少覆盖较高/相同/较低新画像 revision、null 绑定、账号/新 load 换代、旧/新活动请求、错误和恢复成功；同一 load 新活动查询同时在途/完成时分别检查仍有效的历史错误、过期请求错误和独立画像。回归先前路由、持久副本、跨 writer、历史桥接/冲突、教学版本/活动门禁，最终对完整 46 项冻结前后 SHA 并全量测试构建。全范围独立复审通过后再做真实浏览器、模型、persisted=true 消息读取、PostgreSQL 重启和跨账号验收。

## 五、画像摘要 DTO 归属边界（独立审查修订）

### 模块总览

画像是用户与主题关联的共享数据；同用户、同画像的多个会话可以共同贡献学习证据。`ProfileSummary` 未携带自身 `user_id`/`profile_id`，`ProfileEvidence` 也未携带这两个字段。客户端应信任已认证后端的 `SessionService.load_snapshot` 与 `ProfileService.get_summary` 在当前用户、画像范围内的查询，以及部署数据库实际启用的相关约束；客户端只验证 DTO 显式给出的身份，不把这一信任误称为客户端独立证明。若需要证明 DTO 未暴露的证据归属，须先确认并获授权修改协议或后端，本轮不扩范围。

### 子模块概述

`ProfileItem` 的 `id` 与 `user_id` 可对照 session 的 `profile_id` 与当前用户；`ProfileNode`、`ProfileEdge` 各自含 `profile_id`，可以验证等于已绑定画像；`RequestSnapshot` 含 `user_id`、`session_id`、`profile_id`，分别核验所属用户、当前会话和绑定画像。对于 summary 为 null 的合法快照，不要求生成缺失字段；画像为 null 且 summary 为 null 的合法首次加载正常支持。异常节点/边或请求如能通过现有字段发现，拒绝污染缓存并保守提示，不能以合法跨会话 evidence 的 session_id 为理由拒绝摘要。

`ProfileEvidence` 虽含 session_id/request_id/message_id/node_id，但无 owner/profile 字段；`get_summary` 查询按用户与画像过滤并连接相应 session、request 和 message，recent_evidence 可以来源于同画像的其他会话。并且摘要节点只列未归档节点，证据未按该活动节点集合过滤，因此不得将 evidence.node_id 必须出现在当前 summary.nodes 当作归属证明或验收条件。客户端不能推断未暴露字段，仍需对明显错误的可见 DTO 身份采取防御。

### 详细实施设计

设计验证函数或等价规则时：以捕获账号和 `session.profile_id` 为核验上下文，先检查 session 的用户与目标会话，再检查非空 profile 的用户和 id；针对非空 summary 的每个 node/edge 比较它各自可见的 profile_id，不检验 summary/evidence 不存在的 owner 字段，也不要求 evidence.session_id 等于当前 session。每个 pending request 检查它自身的 user_id、session_id 与 profile_id。任何这类可见身份不一致均不得发布对应异常数据到旧缓存或清除备份，并显示可重查的保守状态；不能为“解决”异常而丢掉已有可信学习历史。

新增真实页面和控制器正向回归：用户 1 的画像 p1 同时包含来自会话 A、B 的 evidence，打开 A 时两条证据均保留并允许正常加载，不能将 B 的证据视为跨账号或跨画像；同一摘要包含有效 p1 节点和边。另测节点或边的 profile_id 不等于 p1、pending request 的 user_id 或 profile_id 异常、summary 为空、合法 null 画像，检验缓存不受污染、账号隔离、旧 cursor、重试与发送门禁。对于无法从 DTO 确定的 evidence owner/profile，不模拟出不存在的字段或宣称被客户端验证。
