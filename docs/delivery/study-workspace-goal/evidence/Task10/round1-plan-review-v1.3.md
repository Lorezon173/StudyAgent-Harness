# Task10 round1 v1.3 独立范围复审

结论：**PASS**，无计划层必改阻断。计划对象 `docs/superpowers/plans/2026-10-27-task10-round1.md`；实际SHA256 `0d7d3199e975ee44e5d4e979100ed23a7012a296d790eab6535db12505e82c51`，与派审值一致。比较归档v1.2 SHA `c89a8fba9053a7fb76074a5da11167b90b31bb4d4473e0c31bf27b57bb8f922d`，核对实际ChatResponse、RequestSnapshot、认证/本地恢复和前序计划设计。报告写入前后复核计划仍同SHA。

## 上轮必改

- **P2.1 ADDRESSED（设计层）**：准备候选独立定义 user/session/writer/prepare/write ID 与内容，不含凭据；点击时同步写并读回，所有路由离开、身份切换前、401、flushAll、正常退出、beforeunload/pagehide纳入；storage失败按被动401与主动退出不同规则处理；本人经服务端核会话所有权后选择恢复，原X与新Y不静默覆盖。包含账号切换、共享Storage、多writer、删除匹配、配额/损坏和正常退出/401回归；强关只承诺尽力本地。
- **P2.2 ADDRESSED（设计层）**：明确 ChatResponse无request_payload，普通POST 200即使completed/persisted=true也不能单独清输入；先取得已核当前identity/session/request/payload/status的可信GET或仍有效RequestSnapshot；404/网络失败/不一致保留草稿及本机记录，已有新编辑不被清；真实DTO场景覆盖POST先成功但GET失败、后续GET匹配、旧身份。v1.3明确覆盖旧文中“GET/响应”泛化表述，旧测试须以本节的真实DTO语义执行。

## 依赖和前序门槛

前序v1.2的POST高attempt GET复核、消息可信基线、response版本必须base+1、跨页找双角色、无可信基线安全继续、相同文本与legacy场景未被v1.3撤销；v1.1的身份失效前备份、跨来源状态不倒退、多标签writer隔离和workspace last-session候选仍适用。子代理计划PASS→实现及必要测试/冻结→独立子代理代码review→功能验收顺序保持，真实浏览器及独立库验收不能以mock代替；Task13真实PG/重启/跨账号验收不被提前认定。

## 执行阶段审查关注（非本版新阻断）

1. `flushAll` 和账户转移必须实际将prepared candidate纳入备份与失败门禁，不能只在保存API写类型；X与后续Y可独立恢复且无法跨账号展示。
2. GET由旧ticket触发前/返回后需检查generation，GET异常或尚未完成时，不得以本地请求body冒充服务端payload来清草稿。
3. 用户准备期间A→B取消前POST时必须清准备锁、保留A数据并明确提示；POST已发后切B不得把A数据写给B。
4. 目标回合user/assistant可能跨页；response.state_version必须恰好base+1，而最新snapshot版本可以更高。
5. 仍需用当前工作区重新确认README等用户改动及计划哈希；功能验收与客户端单元测试的证据分开保留。

PASS仅指计划设计达到本轮实施门槛，不代表功能已开发、测试通过或目标完成。
