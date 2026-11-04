# Task10 A 真实浏览器受控设施独立计划审查

日期：2026-11-03。结论：**PASS**。本报告仅审查设施计划，不表示已安装工具、启动浏览器、审阅设施实现或完成任何行为验收。

## 范围与依据

完整阅读以下两份计划，并核对已批准 A 计划任务1、任务5及相关源码：

- `superpowers/frontend-ui/2026-11-03-task10-a-browser-controlled-raw.md`
- `docs/superpowers/plans/2026-11-03-task10-a-browser-controlled.md`
- `docs/superpowers/plans/2026-11-02-task10-goal-recovery-minimal.md`
- `web/src/pages/Chat.test.tsx` 的来源变化案例及已有 inconsistent 双重查案例（3853—3893行附近）；`web/src/pages/Chat.tsx` 的恢复/查询入口；`web/src/api/client.ts`；`web/src/main.tsx`；`web/vite.config.ts`。

这是两份规划文档的独立审查，不是项目产品代码 OCR 完整审查；未执行 OCR，不宣称覆盖 Task10 全部产品实现。

## 审查判断

1. **设施及授权：通过。** 已批准 A 任务1明确要求真实浏览器受控交错，并允许设施欠缺时提出最小设施安排。专用临时目录内固定版本 playwright-core、复用系统浏览器及单文件静态入口直接服务此验收；没有新产品依赖、产品 API、后端控制接口或架构机制。原 A 的“不新增依赖或 API”结合本补充的明确隔离边界，不能自动解释为禁止常规临时验收工具。无需为相同已授权测试重复征求用户许可；若工具审批或网络访问被实际拒绝，仍应依项目纪律处理具体失败，不能擅改权限。
2. **最小性：通过。** 有限两个 route 门闩和显式阶段足以安排 A/B，无需改 Python harness、产品代码或新建控制 API。静态服务去除了 Vite 默认 8000 代理，未知 API 不落到真实后端。系统浏览器兼容性由 launch/route/close 探针判定，不把已安装视为已能运行。
3. **真实页面与受控证据：通过。** 正常构建入口、真实输入/按钮、真实前端网络客户端，配合合成认证和合成响应，只能证明 browser/controlled-network 行为。计划明确区分登录、模型、persisted=true fixture、数据库写入、PG 重启和跨账号真实验收；没有把模拟成功提升为生产成功。
4. **交错及副本证据：通过。** 初始 inconsistent 来自实际发送后的矛盾消息，A/B按阶段和请求到达分配，防止初始化 GET 消耗计数；证据包括 A 挂起后仍冲突、B先返、A后返、警告/禁发/答案/原文、本人及另一 writer 精确键值及 POST=1。主动新一致重查作为独立恢复行为保留。
5. **凭据与运行边界：通过。** 新非持久 context、同一合成 origin、专用工具/cache、禁止用户 profile/token/真实服务及外网回落，日志不保存认证键或 HAR/通用 trace。认证 fixture 不证明真实权限。
6. **故障及收尾：通过。** 单步/整场景上限、未知网络和页面异常使失败显式化，保留日志/截图；finally只关闭本轮 browser/context/server，清理失败列自有 PID，不杀同名进程、不递归删除证据。检查产品源码及 dist 一致性，避免以旧构建冒充现状。
7. **source 不可达边界：通过。** 实际源码案例通过 prepared 候选的“查询原请求”建立 source，和实际发送后的普通重查不完全相同。计划已要求实际选择候选及现有页面入口，禁止 controller/store 注入；inconsistent 同起点组合不可达则单列 blocked，保留 UI/网络证据，由主会话裁决。相邻来源案例通过不能替代该组合通过；任一 blocked 不能汇总为全通过。

## 必要修订与后续闸门

**无阻断性修订。** 未决的是实施和运行证据，不是另一次用户授权：

- 落地时必须执行计划中已经规定的版本/Node兼容核验、实际 route 探针、API未知路径阻断及端口释放验证。
- source-change组合的可达性仍未证实，必须按计划保留独立状态，不能为了达成全绿扩产品入口或更改原合同。
- 实现之后独立代码审查再运行按钮场景；真实模型与 PostgreSQL 等 A任务5仍须另行验收。
- 根 README 由主会话按已约定方式集中同步，不由本审查覆盖既有内容。
