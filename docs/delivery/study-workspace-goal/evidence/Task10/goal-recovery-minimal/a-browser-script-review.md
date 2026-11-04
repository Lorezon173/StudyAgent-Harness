# A 浏览器受控验收脚本独立 OCR 审查

日期：2026-11-03。结论：**Needs changes**。本次只审查 `a-browser-controlled.cjs`，未运行功能按钮场景，未修改脚本或产品代码；以下是验收设施的问题，不是已确认产品回归。

## 范围、规则与覆盖

脚本全文 1–247 行，审查前后 SHA256 均为 `FAA458A5390DDFE8180E73ABBF6AD0724C37509C5F01C906C271D9C1C724E87F`。已全文读取设施 raw、实施计划、`browser-facility-plan-review.md`、A 产品 `a-ocr-code-review.md`，并追踪 `Chat.tsx` 实际按钮、`ChatComposer.tsx`、`workspace.ts` 恢复门禁及 `workspaceController.ts:765–879` 的重查/响应处理，参照 `Chat.test.tsx:3831–3891` 对照案例。

使用 open-code-review-delegate：preview 原会话 94107 最终 exit=0；先完整写入 `a-browser-script-review-preview.json`，终端回显虽截断，未把回显用作完整清单。workspace 模式，无分支引用；tracked 比较 HEAD，目标是 added 未跟踪文件，全文即新增内容，亦核对了 HEAD diff。Git 使用 no-pager/no-ext-diff/no-textconv/no-color。

全部 1687 条可审路径分 17 批获取规则，原会话 22513 exit=0，`a-browser-script-review-rules.json` 保存全部输出；逐条比对规则映射遗漏为 0。目标对应 offset=500 批次的 group_id=4（JS/TS 系统规则）。硬编码 fixture、有限场景门闩属于已批准设施合同，不机械据通用风格规则扩大成通用框架。

| 统计范围 | total_files | reviewed_files | skipped_files | coverage_rate |
| --- | ---: | ---: | ---: | ---: |
| OCR 可审 `(path,status)` | 1687 | 1 | 1686 | 0.0593% |
| 本次指定设施脚本 | 1 | 1 | 0 | 100% |

preview 总计 4287 条，另外 2600 条由工具排除，完整原因仍在 preview。`a-browser-script-review-checklist.json` 为每条可审路径保留 path/status/review/reason；1686 条逐项标为任务外 skipped，没有宣称工作区或整个 Task10 已覆盖。源码上下文不计作另一次产品完整审查。

## Medium

### M1：同一已存在警告不能证明 B/A 响应完成处理

- 文件：`docs/delivery/study-workspace-goal/evidence/Task10/goal-recovery-minimal/a-browser-controlled.cjs`，准确新版行 **196–203**（相关释放函数行 126–131）。类别：test。
- 触发：运行支持的 `conflict` 场景。行184已经等待同一“已保存的消息与请求不一致，请检查”出现；行194又确认 A 挂起时该状态仍在。因此 B 释放后的行197、A 释放后的行201都可能立即满足，没有观察到该次前端处理完成这一新的事件。
- 证据：`release()` 只 await `route.fulfill()`，没有等待页面的请求生命周期/响应消费和后续渲染；`capture()` 的截图与 storage 读取也不是对指定响应处理完成的断言。产品 `confirmCompleted` 在 await 消息页之后才核对并发布冲突或接受成功（controller 约835–875行），这一阶段与测试进程是异步的。脚本随即在行203发起主动恢复，不能把“尚未消费响应时仍显示初始警告”当作“消费了 A 旧成功之后仍保留新冲突”。
- 影响：这是本设施要证明的核心先后关系。B可能未发布冲突时就释放A，或者A尚未处理时就截取“A-returned”并启动 recover，产生错误时序证据或掩盖原始竞态。这里不声称已实测出现假绿；这是由当前等待条件可立即成立、缺少完成事件得到的静态审查结论。
- 最小修复：为 B 和 A 的精确请求分别建立浏览器侧完成/消费及渲染观察屏障，事件记录明确区分“已释放”和“完成观察”，完成后再核 DOM、副本、禁发，最后才允许主动 recover。保留真实网络客户端和按钮，不读写私有 store/controller，不使用固定 sleep，也不新增产品接口或通用任务框架。应验证此屏障确实在后续 UI 工作之后，单独 requestfinished 也不要冒称业务处理完成。

## 其他分级

Critical：无。High：无。Low：无有明确修复价值的问题。没有把仅凭低层可构造的场景追加为产品任务。

## 已核对边界与未验证范围

- 实际输入、发送及两次重查均使用真实页面按钮；初始 inconsistent 来自实际 POST 后的矛盾消息，A/B 按显式 phase 与 cursor 捕获，不按 StrictMode 全局请求次数分配。网络/游标场景的“复核失败”相较初始警告是新可见状态；最终正确答案也提供新的正向观察。
- 本人副本来自真实应用写出的 request 候选，另一 writer 使用独立身份；`exactCopies` 核精确 key/value，成功后只要求另一 writer 完整；意外重复 POST 即使不计入已接受 postCount，也会进入 failures 并使断言失败。
- 静态服务限定自有 loopback、GET/HEAD、dist 实路径和 SPA 回退，不代理后端；API白名单外 abort 并计失败；`/api` 本身会由静态服务拒绝。外网 origin abort 且记失败。未发现可达真实8000/8001的回落路径。
- 依赖解析限定专用 tool 内且固定 playwright-core 1.64.1；每场景独立非持久 context，禁 service worker。源码/hash只记录不写入。正常 finally 和场景超时均关闭自有 context，主 finally 关闭自有 browser/server并核端口释放；本次没有故障注入验证所有清理异常或强制终止路径。
- source-change经 prepared 候选实际“查询原请求”入口，只改本 context 合成候选，核变化警告及其他副本；脚本明确返回 blocked，主汇总不视为 pass。它尚未证明已有 inconsistent 的双重 source 组合可达，也未验证该组合，不能据相邻案例声称完成。该限制与 A 产品报告一致。
- 只读取了此前 probe 的 report：有一次 `ERR_NETWORK_ACCESS_DENIED`，另一次 probe=pass 且 portReleased=true，未见 scenarios；这些不是此次冻结脚本按钮场景的运行证据。本次未执行真实浏览器功能场景，未验证截图或实际 A/B 处理顺序，也未重跑产品测试/构建。
- report 明确 real browser / synthetic controlled network；persisted=true仅fixture。真实登录、模型、正常退出、真实慢生成/保存故障、PostgreSQL重启及跨账号拒绝仍未验证。

先修 M1，再独立复核相应局部变更，通过后才执行既定按钮场景。无需据此改产品或扩架构。根 README 由主会话集中同步本审查状态与未完成项，避免并发改写。
