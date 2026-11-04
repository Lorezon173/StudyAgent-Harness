# Task10 round1 独立计划审查

结论：**NEEDS REVISION**，存在 4 项需要在编码前明确的阻断；其余范围、后端DTO、正常发送/重试与用户要求的计划→审查→编码→代码审查→功能验收顺序基本相符。

对象：`docs/superpowers/plans/2026-10-27-task10-round1.md`，SHA256 `80d5735a47c53461ea2847222cdd32f8e2b5671272e78b0ac42972b53b4482aa`。独立核对原始设计、Task10 计划、实际 AuthProvider/client/store 和会话 API；以下是可由当前代码与计划证实的缺口，不是声称产品已有这些新缺陷。

## P1-1 认证失效/身份切换前如何同步备份未定义

计划第 73、101 行要求 401 后同步保底再立即失效；实际 `web/src/store/auth.tsx` 的 logout 先 `workspaceStore.clearAccount()`，login 先 `startAccount()`，两个动作同步用 emptyState 替换全部 session 桶；`web/src/api/client.ts` 的当前 401 同步调用 invalidation listener，随后在非/login URL 可硬跳转。计划未定义如何在 clear/start 前获得旧身份、桶、未确认请求、未发队列与最新输入的同步快照，订阅回调若只在 publish 后读取 store 已看不到原桶，React effect/异步备份在硬导航后也不可靠。需要规定受同一账户generation约束的认证前置同步 hook / 快照所有权、注册/卸载/StrictMode顺序、storage异常不能阻塞401清认证但必须显式保留失败事实、同用户同token显式login及另一用户login前如何处理。至少写真实Provider+client回归：A未flush输入→保护请求401→同tick清认证/可能硬跳转→重新登录A可恢复、B不可见；A→同账号再登录或B时旧桶也不会先丢；旧401不触发新身份备份或登出。

## P1-2 同一请求的旧状态可能覆盖已完成结果

计划第 59–63、81–94 行要求恢复/轮询且按request sequence和account ticket归位，但未给跨 POST、GET poll、snapshot 多个异步源的同 request_id、attempt 的单调合并/失效规则。交错：请求A已有一个GET观察running在途；POST返回completed/persisted=true并重读snapshot确认消息；较早GET晚到、仍携相同request/attempt和有效sequence，若覆盖会把完成回退running、恢复临时气泡或再次锁发送。另失败/中断后显式retry会提升attempt，旧attempt的running/failed不能覆盖新attempt；旧snapshot不能复活已确认完成的非completed请求。需明确 request状态的单调合并权威、每次轮询和snapshot/POST交错的序号或代际、同attempt终态优先及retry仅以更高attempt前进、完成消息确认与删除unknown备份的条件，并补可控延迟真实DTO测试（running GET延迟→POST completed→回读真实消息→旧GET返回；旧snapshot延迟→新completed；attempt N→retry N+1后N返回）。不得把单个load sequence或message.id去重当成请求状态去重。

## P1-3 同账号多标签的本机草稿可互相覆盖或删除

计划第 71、99 行指定副本key只有namespace+user_id+session_id，值的本机修改序号由单个页面内递增。浏览器同源localStorage跨标签共享：两个标签各从revision 1编辑同一会话，后写覆盖先写；A收到自己的PATCH成功后按revision 1清理，还可能删除B同revision但尚未保存的备份。服务端CAS能阻止远端覆盖，却不能修复本地副本丢失。需设计可区分写入者及每次写入唯一身份且不丢另一标签副本的存储布局、确认后仅清除与请求内容/身份匹配的版本、重新登录发现多个候选与选择、迁移/兼容原key及配额/不可写失败语义。补两个独立controller/页面共享真实Storage的交错测试：A/B同会话同本地序号不同草稿→A完成保存→B断线/409→B草稿仍可被本人恢复，其他账号不能查看。

## P1-4 工作区最近会话保存失败的本机恢复契约缺失

计划第45行承诺workspace PATCH冲突或网络失败“保留本机恢复提示”，73行要求退出聚合所有session和workspace队列，并在本机备份成功后允许“退出并保留本机草稿”；但本机数据结构第63、71、99行仅定义session draft/anchor及unknown request，没有workspace last_session_id待保存值、归属、版本、版本冲突和重登处理。若最后选B的workspace PATCH离线失败、view草稿均成功，退出后服务端仍是A，当前方案没有B的本机记录可供提示恢复，且不能把session草稿备份成功等同workspace保存成功。需规定该项在安全退出方案中如何处理：例如按账号记录last_session候选、在身份恢复并确认目标归属后显式恢复/冲突选择，或明确该项失败不得承诺已保留并让用户留页重试；同步规定在途保存、先前server版本和B→C晚响应场景，补离线退出、强关重登、跨账号隔离及storage不可写测试。

## 其他需纳入实现审查的对照

- GET request404表示未查到，不代表确定未领取；保持原ID/payload并只按用户明确操作重发，409 payload_conflict/session_busy/stale_context逐一按服务端实际语义展示，不能无条件更换ID。当前计划有此大方向，建议将404→首次请求迟到/领取→同ID重发和后台占用、快速双击重发列为明确测试。
- 送发前/任意await后继续发PATCH、GET、POST、retry时先重新验证完整账号ticket；`client.ts` 在调用时从localStorage读当前token，仅抑制旧响应不能防止旧A的延续在B登录后用B凭证发请求。补A的409刷新/轮询等待→B登录→旧续体不得发网络请求，也不得改B状态；同账号同token重登同理。
- 除显式点击侧栏，浏览器前进后退、知识库路由、创建成功后的程序导航均需相同离开A同步本地备份/flush，不能只包装selectSession。强制刷新只能同步本地备份，不能宣称unload期间网络保存成功。
- 原Task9无snapshot断言可按批准Task10新行为修改，但既有账号、路由与布局测试不可为绿灯移除。功能验收必须在代码子代理review通过之后执行；真实后端/浏览器与Task13 PostgreSQL重启证据不可相互替代。

请计划作者在新版本中补齐以上P1并冻结新SHA，由独立审查范围复审；此报告没有授权编码，不修改产品源码。
