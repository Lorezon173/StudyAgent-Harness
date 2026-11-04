# Task10 A 浏览器活动门禁恢复补充：独立计划审查

日期：2026-11-03。结论：**PASS**。新增步骤符合既有产品合同；未发现有实际依据、需要修改方案才能实施的问题。本结论仅批准既定设施的验收步骤补充，不代表脚本已修改或复验通过，不改变首轮失败结果，也不批准产品修改。

## 指定版本与范围

已全文读取 browser raw/plan，实算 SHA256 与交接指定版本一致：

- raw：`C1B811EFFA587BE42B55565C832E68E55505051D521470EAA88CDAC76E1F9FB0`，`superpowers/frontend-ui/2026-11-03-task10-a-browser-controlled-raw.md`。
- plan：`A95632852FCE5AAA71A4A43D59E170ECAE418EEAF503F06BABD052FADA452DE2`，`docs/superpowers/plans/2026-11-03-task10-a-browser-controlled.md`。

结合原 `a-browser-controlled.cjs` 全文、首轮 `browser-controlled/20261103-a-browser-final-01/report.json`、network/cursor-loop 的 recovered.json 与事件末段、controller 的关联/活动重查实现、Chat 实际按钮及 A 原批准计划核对。这是两份规划的定向独立复审：total_files=2、reviewed_files=2、skipped_files=0、coverage_rate=100%。未运行 OCR、浏览器、测试或脚本；此统计不表示产品源码或整个工作区审查覆盖。本次只写本报告，未修改脚本、产品或旧运行证据。

## 通过依据

1. **根因有源码和实际结果支持。** `workspaceController.ts:817–818` 每次核验推进活动观察序号；`:859` 分别判定活动观察资格，`:865` 允许消息匹配，同时在旧活动观察失效时把 activityGate 设为 uncertain。较新 B 已启动后，旧 A 可恢复匹配消息，而不能用其过期活动观察证明会话无占用。A 原计划明确保留活动门禁的独立资格，不要求“消息 matched 立即等于可发送”。这不是靠首轮结果反推的新产品语义。
2. **失败被准确定位且保留。** 原脚本 `:246–248` 在显示正确回答后直接要求发送 enabled。首轮两个 recovered.json 同时显示正确回答、会话状态待确认、可见“重新查询会话状态”、sendDisabled=true；事件记录 B/A 的 network-finished 与 render-observed、POST=1、errors/failures 为空。报告明确两个场景 failed。新增方案只补遗漏的实际恢复操作，不删失败证据，不将这次 fail 改称 pass。
3. **恢复入口真实存在。** `Chat.tsx:32` 的按钮调用 `recheckSessionActivity`；controller `:881–913` 捕获新 epoch/sequence、读取 snapshot、验证身份，且只有无活动请求、对应观察仍有效时在 `:907–910` 清除门禁。计划要求使用此真实按钮，取得身份/版本一致且 active_request_id=null 的合成 snapshot；不直接注入 store/controller、不合成业务成功、不自动重发教学 POST。
4. **最终行为要求保持。** 新步骤先保存旧 A 成功后的中间态：正确回答可见、会话待确认、发送 disabled、另一 writer 精确副本和 POST=1。然后读取一致活动 snapshot，仍必须检查正确回答、发送 enabled、待确认消失、另一 writer 精确键和值及 POST=1。出口缺失、不可点击、响应不一致或最终仍禁发都失败；没有把原 enabled 断言改成期待禁发。本人已匹配副本按既有清理合同处理，避免将正常精确清理误判为丢失。
5. **观察与范围没有放松。** 新 snapshot 沿用精确 Request 身份、状态、完整正文、requestfinished 和页面任务/双帧观察；不会只靠现存答案或警告进入下一阶段。首轮运行目录保留，新结果用新 run。source-change 的 blocked、有限黑盒观察边界及真实模型/持久化未验收均保持原样。无需修改产品或引入活动调度/状态框架。

## 实施时的既定约束

- 在点击活动重查前建立对应请求观察，或在现有路由捕获精确 snapshot Request 后再释放；不能先完成响应再注册监听而遗漏事件。fixture 须切到计划规定的一致恢复 snapshot，不能沿用 B 阶段的分页挂起响应。这是已有“精确请求与正文观察”的落实，不新增接口或框架。
- 保存“消息已恢复但活动待确认”与“活动重查后最终恢复”两份证据。不能将本人副本已按成功合同清理和另一 writer 副本完整保留混为同一断言。
- 脚本修改后仍需独立代码复审再运行；脚本最终失败或 blocked 不得用进程退出 0 掩盖。根 README 的集中同步由主会话负责。

Critical：无。High：无。Medium：无。Low：无需要修改方案的问题。下一步可按该补充做验收脚本的最小修改；首轮失败尚未解决，最终 enabled 及其恢复证据仍待真实浏览器受控网络复验。真实模型、正常退出、真实慢生成切换、数据库持久化及跨账号拒绝不属于本次通过结论。
