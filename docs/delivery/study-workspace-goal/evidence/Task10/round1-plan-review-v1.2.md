# Task10 round1 v1.2 独立范围复审

结论：**NEEDS REVISION**。v1.1 的 N1/N2 和两项早前补充的原始设计方向已处理，但最新发送准备保护引入一项生命周期缺口，以及一项与现有返回 DTO 相关的清草稿条件不够明确；须补后再冻结新SHA独立复审。

对象：`docs/superpowers/plans/2026-10-27-task10-round1.md`，最终磁盘 SHA256 `c89a8fba9053a7fb76074a5da11167b90b31bb4d4473e0c31bf27b57bb8f922d`；最初派审SHA 5fcb32…及中间 d55f580…、197620…均因作者继续修订而不作为本报告对象。结束前再次核当前SHA。与已归档 v1.1 SHA `5abee737871741dcdd81e52cad9df7b282254910b889d0b530f9d9318f746b57` 比较，核对后台 CAS/消息事务和具体 API。

## 原阻断与修订

- v1.1 **N1 ADDRESSED**：正常POST失败/中断 attempt N+1 为待核实信号；先经同 request 的GET、完整票据核验后采纳真实终态，GET失败保持unknown；旧POST不能覆盖新retry。包含失败、超时、旧结果和换代测试，符合 `ChatRequestStore.interrupt` 与 `ConversationService._response`。
- v1.1 **N2 ADDRESSED（设计）**：在同一本人snapshot捕获 state_version 和 next_turn_index，POST expected_version约束服务端claim；commit检查原base，事务内使用next_turn_index并 state_version加1。已核 `commit_turn` 与 `SessionService` 的snapshot锁、SQLite事务；真实GET核请求身份、精确目标回合并跨页取user/assistant。无基线的旧/跨设备请求不猜测，明确保留候选与用户选择继续。两项无法仅凭计划证明运行正确，仍需编码后代码审查、真实验收。
- 版本测试冲突 **ADDRESSED**：base=7时response.version=8而最新snapshot.version可≥8；response=9拒绝匹配。
- 目标turn跨页 **ADDRESSED**：直到两角色都获得、越过目标或无cursor；网络失败不算缺失。
- 发送准备 A→B **部分 ADDRESSED，见 P2.1**：同步捕获原文/编辑序号，切走不POST、返回保留原文；后续新编辑不被旧操作清除，并列deferred测试。但新引入的独立候选尚未接入整体持久化与身份生命周期。
- v1.1四项原阻断与三项建议未见新修订将其撤销；新增Login/localRecovery允许文件符合旧桶清理前备份的既有用户需求。

## P2.1 [必须修订] 发送准备独立候选的退出和换账号恢复契约缺失

v1.2末节规定：发送准备时用户编辑新内容，原点击文本保存成与草稿/请求副本分开的“待重试候选”。但第140行 `prepareAccountTransition` 仅枚举dirty草稿/锚点、未确认request、workspace候选；`flushAll` 与 `localRecovery` key/回读验证也只对这些类型有定义。此候选既未向服务器POST，也不能假装成已有request；若仅放内存，A在准备期改写草稿→切B→401/同账号重新登录/正常退出/强关，emptyState或页面销毁会丢失原点击文本，而另一个新草稿备份成功仍可能让退出误称“已保留”。目前测试只覆盖切回A，不覆盖身份/退出边界。

请明确独立候选的账户/session/writer隔离数据结构、唯一write_id、原文及准备序号；同步写本机并记录成功/失败，纳入 `prepareAccountTransition`、`flushAll`、beforeunload/pagehide 与“退出并保留本机”的逐项可读回校验；只在本人session所有权确认后显示/恢复，不能覆盖更高序号新草稿，明确清理条件。存储失败沿用401立即失效但告警、正常退出不能谎称保留。补真实Provider/共享Storage测试：原点击X、后续新编辑Y→切B→401、显式换账号、正常退出及强关→重登A，X候选和Y草稿可区分恢复，B不可见；storage失败的报错和退出门禁。此要求只保护计划新加入的数据，不要求后端扩展。

## P2.2 [必须修订] 清输入需要服务器payload证据，POST响应本身不含该字段

v1.2第235行写“通过服务端权威响应/GET证明已领取……且有服务器request_payload可恢复原文”时才清，但真实 `app/models/schemas.py::ChatResponse` 不包含 `request_payload`；此字段在 `RequestSnapshot`（GET request或snapshot.pending_requests）中。将原始本地POST body或单独HTTP200/`persisted=true`当“服务器 payload 可恢复”不满足该条件；尤其失败/unknown可能没有持久记录。原测试只说“GET/响应 confirmed … payload匹配”，没有真实DTO明确让 POST先于 GET 的行为可区分。

请规定：除非之前同一request、同账号、同attempt已从可信GET或同一有效snapshot的 `RequestSnapshot` 核到本人/session/request/payload，否则POST 200（running、failed/interrupted、completed包括persisted=true）都不能单独满足payload恢复前提；由GET权威确认（包含前述N1更高attempt情况），取不到/404/网络失败保持原草稿并提示，已完成状态的真实消息关联另遵循N2，不能错误发新ID。已核到request_payload后仍需当前草稿revision与全文匹配才清。真实DTO测试应禁止给ChatResponse虚构payload：POST 200后GET pending/404/失败→旧草稿不清；GET确认同ID/attempt/原文→可清；POST completed后GET失败→不清、不重发、可查；换账号/新编辑/旧POST到达均不清新草稿。

审查属于计划层；未修改源码、未执行产品测试、未声称Task10完成。
