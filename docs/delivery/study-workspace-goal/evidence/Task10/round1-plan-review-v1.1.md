# Task10 round1 v1.1 独立范围复审

结论：**NEEDS REVISION**。四项原阻断均已提出有针对性的设计和测试，三项并发建议已吸收；复审发现两个与实际后端契约有关的新阻断，须再冻结并独立复审后才能编码。

审查对象：`docs/superpowers/plans/2026-10-27-task10-round1.md`，SHA256 `5abee737871741dcdd81e52cad9df7b282254910b889d0b530f9d9318f746b57`；与归档v1 SHA `80d5735a47c53461ea2847222cdd32f8e2b5671272e78b0ac42972b53b4482aa` 比较，核对真实代码、DTO和事务。

## 上轮四项复核

- P1-1 **ADDRESSED（设计层）**：统一账号transition，emptyState之前同步捕获旧generation桶；401成功或备份失败均清失效认证，警告不含个人内容；显式换账号失败不导航；无Provider、旧401、同账号重登、StrictMode均有测试。新增Login及localRecovery白名单有必要、处于原需求范围。仍须代码审查验证无旁路。
- P1-2 **原交错已 ADDRESSED，另见新项 N1/N2**：同attempt终态不回退、低attempt忽略、旧snapshot/GET和确认后仅清对应副本均有明确测试；完成消息关联与普通POST的更高attempt仍有实际契约缺口。
- P1-3 **ADDRESSED（设计层）**：本机按user/session/writer分键，唯一write_id及完整内容比较清理；多候选、原单键兼容、Storage异常和双标签回归均有定义。物理本地存储不伪称加密隔离。
- P1-4 **ADDRESSED（设计层）**：workspace候选另按user/writer持久化，失败时退出逐项验证可读回；重登先验归属、用户选择、版本冲突不静默覆盖，覆盖B→C、强关和跨账号。
- 原建议：404同ID重发竞态、await后发下一请求前校验完整ticket、侧栏/前后退/新建/其他页面各导航与强关已具体写入测试及规则，**ADDRESSED（设计层）**。每项仍须编码后由独立review与功能验收核实。

## N1 [P1] 普通POST自己的失败响应可能携带更高attempt

依据 `app/infrastructure/storage/chat_request_store.py::interrupt`，running attempt N被打断或失败时，服务端先令attempt递增至N+1；`app/orchestration/conversation_service.py::run_claim` 捕获普通模型异常后调用 `_interrupt(..., status='failed')`，通过 `_response` 返回 `HTTP 200, status=failed, persisted=false, attempt=N+1`；超时/断连路径也可能返回interrupted的新attempt。v1.1第2节只允许“更高attempt来自retry响应或后续GET/snapshot”，而第3节普通POST要求状态可用，未规定如何处理来自原POST的更高attempt终态。若仅忽略，前端可能一直unknown/处理中；若直接接受而未核校，晚结果又可能覆盖新状态。

**可行修订**：原POST携更高attempt的failed/interrupted先视为待核实信号；保留临时气泡和原请求，不自动重发/解锁为成功；以同账号/同session/request_id的最新GET（必要时snapshot）取得服务端权威attempt、status、payload和base，成功后按已定义单调规则合并。GET发出前以及返回后均校验完整身份和该request当前sequence；404/网络失败保持unknown可重查。若GET观察到已完成或更高retry attempt，按新的服务端事实合并，旧POST不覆盖。新增真实DTO测试：initial N→POST返回failed N+1→GET确认→failed可专用retry；包含interrupted、GET网络失败、POST失败晚于retry N+2、身份换代后不得发GET。不得把正常的failed响应一概判 malformed/成功。

## N2 [P1] completed后的目标消息关联无法从当前返回契约无歧义推断

`app/orchestration/turn_commit.py::commit_turn` 以提交时 `session.next_turn_index` 创建一对 `MessageTable`，内部 `CommitResult` 确实有turn_index，但公开 `ChatResponse`/持久化 `response_json` 不含turn_index或消息ID；消息表只有session_id、turn_index、role/content，没有request_id，RequestSnapshot也只含payload与上述response_json。`turn_count` 是教学快照的committed_turn_count，不能普遍等同消息turn_index，特别是历史迁移存在不连续或不完整回合。

v1.1要求完成后“分页直至得到该会话已提交的真实用户/助手消息”才清请求本机记录并解锁，但没有规定如何识别“该请求”的消息；在其他标签完成后连续产生超过50条新消息、相同问题/回答多次出现、浏览器重登或本地记录缺失时，最新页或仅用文本匹配不能证明找到了目标回合。不能伪造确认，也不应无限阻塞普通会话。

**可行修订：** 对由本控制器创建的请求，在发送前同时持久记录通过本人snapshot取得的 `session.next_turn_index`、base_state_version及请求身份，只有确认发送的状态/版本与该snapshot一致才使用该基线；恢复后核 GET request_id/payload/base/attempt/completed 与response version、获取真实message页，查该turn_index上user/assistant角色的唯一记录并核原始用户文本与已保存reply；必要时分页，缺失时保留同步状态与本地记录，不能靠同文本的其他turn清理。服务端 `uq_message_turn` 支持同一session/turn_index/role唯一，完成事务先分配并在同一事务递增next_turn_index。需处理另一标签在snapshot后先行提交导致的 `stale_context`，不可将旧基线归属到另一个请求。

对于**未由本浏览器发送、原本机记录没有可靠发送前next_turn_index**的跨设备/旧版记录，仅凭现有DTO无法无歧义定位某次completed request与消息的关系；不能把 turn_count、当前next_turn_index、匹配文本或时间猜测当权威。请在计划明确保守降级（请求状态以已认证GET completed为准，历史以真实分页显示，关联不明保留候选/提示，不自动宣称精确匹配；避免无期限阻塞新发送），或提出经用户范围批准、独立计划审查的最小后端契约扩展（在同一提交事务的已保存response或请求结果中加入实际turn_index或消息ID，并处理旧记录兼容）。如选择后端改动，现v1.1“不得修改后端”白名单须先明确修订并通过计划审查，不能自行偷加。

测试应覆盖：本人发出基线、重复完全相同文本与回复、>50条后分页；回包后断网重登、未知发送前next_turn_index、legacy不连续turn index、并发他标签推进以及不同account晚结果。完整执行验收仍在代码review后。

计划审查结果不等于运行时问题已证实，也不授权编码；请计划作者修正N1/N2并重算SHA，原reviewer范围复核。
