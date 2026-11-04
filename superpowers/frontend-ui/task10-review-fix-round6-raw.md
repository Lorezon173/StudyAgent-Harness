# Task10 第六轮审查修复：三层详细设计（raw）

来源：`docs/delivery/study-workspace-goal/evidence/Task10/review5-final-product-code-review.md`，继承前五轮 raw、计划、独立审查和全部原有约束。此审查指出的并发关联问题是静态推导，尚无真实 UI 交错实测；必须先在冻结版复现并记录，不能称为线上已发生故障。本设计及实施计划经独立审查通过之前不编码。

## 一、模块总览

目标：当同一个已完成请求触发多次历史关联时，已由可信消息证明的关联不得被另一个过期失败或冲突回退；真正的当前失败依然可见并可重试，关联、消息、活动门禁、画像与本地副本各自沿用原有独立身份和版本约束。不能把“完成请求”或 HTTP 200 当成消息持久化证明，也不能以删除备份或放开门禁解决卡住。

现有 `reconcile` 通过 `readRequest` 查询 completed 后可调用 `confirmCompleted`；`Chat.tsx` 的重新查询按钮提供用户入口。`confirmCompleted` 查快照和分页、验证 response.persisted、baseline、用户消息与答案后写 `matched` 并精确清理；catch 目前仅核同一 completed attempt，理论上不能区分旧关联和随后已 matched 的关联。成功分支内既有同 ID 内容冲突、以及入口中 baseline 缺失/不符等其他写入也须检查；本轮先用页面交错确认实际可达，再选择最小修复。沿用 React、TypeScript、当前 API、store、账号代次和 localStorage，不改后端或协议。

## 二、子模块概述

### 2.1 每个请求独立的关联操作身份

关联操作身份必须至少作用于账号 generation、用户、会话、request ID、attempt 和受信任 baseline/response 及候选来源；如果记录请求 sequence，要防止同 ID/attempt 但当前 UI 请求已替换后的写入。它不能仅采用会话全局 activity 序号，否则同一会话不同 request 的关联会互相取消，也不能只用 requestId 导致账号或 attempt 相互干扰。账号换代或页面销毁后旧异步结果不可改变新用户状态。

可选设计为每请求可复核的关联操作序号或安全单飞；具体由真实可达交错、现有候选来源和恢复语义决定。若单飞，说明相同请求但不同 source/writer、baseline 或已变化的候选是否可共享，以及失败后用户重试如何启动新的有效操作；不得让某个无效/变更的来源替另一个来源确认或清理。若允许并发，旧失败和旧冲突不能降低同一已验证 matched 结果；有效当前失败仍能报错重试。不得依赖简单全局 `activityEpoch` 取代独立关联身份。

### 2.2 已匹配、失败、冲突及请求字段

同一 account/session/request/attempt 的 `association=matched` 须基于已有 persisted、owner/profile、payload、baseline、确切 turn、两条消息内容以及一致消息 ID 验证。与之对应的较旧网络错误不得把当前 request 从 completed 改回 pending_messages；较旧 ID 内容冲突不得把该 matched 记录改为 inconsistent。修复需同时保护 catch 和成功写入前的 ID 冲突分支，不因忽略错误丢失实际可信冲突：**仍为当前的首次或最新关联**遇真实 ID/内容不一致应提示并阻止继续，保留数据和用户复核入口；若 matched 后用户主动发起全新校验而发现新可信矛盾，必须按原冲突警告和安全门禁处理，不能一概隐藏与现有证据矛盾的新问题。对于旧 attempt 或不同 payload/baseline/response，不能借用 matched 放行；维持原有 mergeRequestValue 的终态/attempt 冲突语义。

保护请求记录与当前 UI 请求字段分别比较：关联属于某个 requestId，不能把后台 A 的结果写到当前显示的 B；即便 ID 相同，当前 UI 的 sequence/attempt 已替换也不得改其状态或 error。消息、画像 revision、教学版本和活动 epoch 按原领域规则独立处理：不能为了丢弃过期请求错误而覆盖较新消息、画像、活动锁、读取位置或历史 cursor，也不能以某个其他请求已完成抑制当前请求的正常错误。错误提示与恢复副本/画像/历史错误互不覆盖。

### 2.3 复核入口及本地副本

自动发送确认、用户重新查询、已恢复 request/linked 来源、活动检查及 polling 均可触发关联，逐入口核查但不擅改协议。有效首个关联失败后，用户仍可以真实点击重新查询；新操作成功可完成并解锁，不能因残留单飞 Promise 或旧序号永久阻塞。一次成功只调用已有身份完整检查与精确清理：user/session/request/prepareId/writer/完整 payload/baseline 必须匹配，不能删除其他 writer 或变化的候选；本机写/读/删除失败警告仍可见。旧任务失败不能重新制造已清理的副本，也不能清掉未关联或未知副本。

## 三、子模块详细实施设计

### 3.1 业务复现与操作资格

先检查 46 文件与 `review5-source-after.json` 一致，核实当前真实按钮与 fetch 请求。通过真实路由/AuthProvider、页面点击和真实 controller/store 构建已持久化 completed 请求：首次 `confirmCompleted` 挂起旧消息分页；用户看到“回复已保存，正在同步”后点击重新查询；服务端返回同一 completed attempt 和可验证历史，使第二次关联成功并实际显示对应用户与助手消息，再释放旧分页。分别让旧分页返回 503、游标回环或同消息 ID 不同内容，观察 matched、request.status、错误和提交状态；记录两个请求的 URL/起止先后、请求次数、最终消息和本地候选。若当前实现未形成并发或不能复现，记录原因并核对真实代码，不编造 RED 或实施假设修复。

如业务 RED 成立，明确每次关联开始、复用、完成及失效资格：按账号/会话/request/attempt/sequence 和证据来源建标识，逐个 async 边界检查当前票据、操作来源仍有效以及原请求记录仍匹配；成功、冲突和错误都在同一安全身份约束下发布。只在必要范围设计共享调用；新账号或新 attempt 与其他 request 独立，结束后清理只属于本操作的运行记录，失败不永久缓存。

### 3.2 安全发布与终态

匹配发布前再次核验 request 身份、attempt、baseline/source 与记录；确认成功即调用已有精确清理；旧任务在新操作已验证 matched 后的失败/冲突只停止自己的发布，不改变当前 completed、关联、其他错误和门禁。若是当前唯一或最新操作的 503，则保持 pending_messages、明确错误和重新查询；当前有效的 ID 冲突保持 inconsistent 与阻塞、原消息和副本保留。测试反向时序：旧成功晚于新失败、两次失败、新查询启动前首次成功、重复点击和立即重试，验证不会把有效新问题都忽略或不必要重复发送。

状态判定同时核对请求记录与 UI request 独立字段：A 的后台结果不能把 B 的状态/error 改写；同一 ID 的新 sequence/attempt 或账号代次不能被旧任务更新；新活动、历史及画像数据按原本单调合并规则，不能由关联重试回退。并发同 ID 不同 payload/baseline 被视为冲突，不借用已有匹配结果；保留原文、门禁和其他 writer 副本。

### 3.3 验证、副本与恢复

构造真实 UI 完成+重新查询及失败重试用例，网络桩只控制响应顺序；备份断言检查当前 writer 原候选、另一 writer 的相同/冲突候选及写入/读取/删除失败警告；匹配前不得清理，匹配后仅符合条件的当前 writer 精确移除，其他 writer 始终保留。额外用两个真实 Provider 覆盖共享存储的必要跨窗口隔离，不能将单 controller 模拟冒充两个 Provider，也不承诺 localStorage 跨页面原子事务。

固定 46 项或实际完整源集哈希，定向测试、前端全量及构建留原始日志/退出码并比对前后 SHA。独立审查必须覆盖整个 Task10，再单独执行真实浏览器、模型、persisted=true、消息读取、PostgreSQL 重启及跨账号拒绝验收；未验证或超出本轮范围如实记录。
