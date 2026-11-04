# A 浏览器脚本：活动门禁恢复局部补充独立 OCR 复审

日期：2026-11-03。结论：**PASS；未发现有实际依据的问题。** 本轮落实已通过的活动恢复补充计划，没有降低最终可发送、精确副本及 POST 断言。结论仅为脚本代码审查通过；首轮失败仍保留，新浏览器场景尚未运行。

## 冻结与 OCR 范围

完整读取指定脚本 `a-browser-controlled.cjs` 1–303 行，审查开始及完成前 SHA256 均为 `68F83610A0D09989C0BB44A7057729AAA3124FA4C2DF848BD3003DA5FA94398C`。对照 [活动恢复计划复审](activity-recovery-plan-review.md)、[v2 脚本复审](a-browser-script-review-v2.md)、现有产品的活动门禁与真实按钮、首轮 report/recovered/事件证据。raw/plan 哈希分别仍为 `C1B811EFFA587BE42B55565C832E68E55505051D521470EAA88CDAC76E1F9FB0`、`A95632852FCE5AAA71A4A43D59E170ECAE418EEAF503F06BABD052FADA452DE2`，与本次已批准补充相同。

已加载并沿用 OCR delegation skill。最新 preview 原句柄 18471 exit=0，完整捕获而非读取截断终端输出；模式 workspace。目标为 added 未跟踪文件，全文即新增 diff，并执行 HEAD diff 核对；Git 使用 no-pager，diff 禁用 ext-diff/textconv/color。preview 共 4350 项，其中 1718 可审、2632 工具排除，原始排除原因完整保留。

全部 1718 路径分 18 批取得规则，原句柄 99305 exit=0，规则映射遗漏 0；目标对应 offset=500 批的 group_id=4，JS/TS 系统规则（拼写、异步/空值、资源、代码注入、敏感信息与原型安全等）。目标另行取得同内容规则，未用历史规则冒充本轮执行。

| 统计范围 | total_files | reviewed_files | skipped_files | coverage_rate |
| --- | ---: | ---: | ---: | ---: |
| 最新 OCR 可审清单 | 1718 | 1 | 1717 | 0.0582% |
| 指定设施脚本 | 1 | 1 | 0 | 100% |

证据为 [preview](a-browser-script-review-v3-preview.json)、[全部规则](a-browser-script-review-v3-rules.json)、[逐项清单](a-browser-script-review-v3-checklist.json)。所有 `(path,status)` 均已标记；1717 项任务外产品/临时产物/其他任务或历史证据明确跳过，不宣称工作区或整个 Task10 完整审查。A 冻结集的 46 项产品/测试文件重新计算哈希，mismatches=0。

## 局部补充裁决

1. **B/A 交错与中间态：通过。** `:238–242` 仍先完成 B 的精确网络/页面观察，再核冲突或复核失败、禁发、本人和其他 writer 完整副本、POST=1 与未知请求清单，才释放 A。conflict 的 `:243–246` 仍保留 A 后冲突/禁发/所有副本断言与实际主动 recover，不进入活动补充。network/cursor-loop 在 `:248–255` 先核正确答案、其他 writer 完整键值、POST=1、无页面/网络错误，再核会话待确认和 disabled，并保存 `activity-pending`。本人副本仅按既有匹配清理合同处理，没有改成要求成功后仍保留全部本人副本。
2. **精确 snapshot C：通过。** `:113` 只在 activity 阶段捕获指定 session 的 GET snapshot 为 held.C，记录用途；`:256–258` 先切阶段，经实际“重新查询会话状态”按钮触发，再等待 C 已捕获，调用现有 releaseAndObserve。该函数在 `:158–164` 从 held route 取得精确 Request，先建立 response/requestfinished/requestfailed 观察及拒绝处理，再释放，避免先响应后监听。`:166–175` 核同一 Request、状态、完整 fixture JSON、网络结束及页面任务/双帧观察后才继续；C 没有因按 URL 匹配而混入 A/B 的请求。
3. **一致恢复 fixture：通过。** `:129` 的 activity outcome 用现有 baseSnapshot 构造完整同 session/owner/profile、state_version=1、next_turn_index=1、active_request_id=null、pending_requests=[]、正确 user/answer 的 snapshot。它不会沿用 B 阶段空页/new cursor，也不修改应用 store、controller 或 fetch。释放与验证共用 expected fixture，身份/状态/正文异常通过现有观察失败路径阻止继续。
4. **最终恢复要求：通过。** `:259–264` 在 C 观察后要求“会话状态待确认”隐藏，保存 `activity-recovered` 并核另一 writer 的精确副本，再核正确回答、POST=1、无未知请求/页面错误，最后仍强制发送按钮 enabled。若按钮不存在/不可点击、C 不到达/失败、提示不消失或最终禁发，均无法标 pass。不是将原 enabled 改为 disabled，也未增加内部状态注入来强行解锁。
5. **原场景与失败边界：通过。** source-change 在 `:202–223` 的原分支返回，仍记录相邻来源变化且标 blocked，POST=0、其他来源副本保持，不把它当已有 inconsistent 双重查的通过证据。conflict 仍走原主动请求重查，新增 C 只作用于其余两个既定场景。`:286–289` 任一 failed/blocked 仍使汇总非零；每次新建唯一 run 目录，未覆盖首轮失败。原隔离静态服务、loopback/外网阻断、独立 context、90 秒场景上限、收尾及合成数据报告边界未扩大。

## 验证与未完成项

本审阅者独立执行 `node --check`，exit=0。没有运行新浏览器场景、模型调用、后端或数据库，也没有修改脚本或产品；未重复产品测试/构建。脚本哈希复核不变，产品 46 项与 A 冻结一致。

现有首轮 network/cursor-loop 的 failed 保留为真实旧运行结果；新增恢复步骤是否在系统浏览器实际解除门禁仍须新 run 的 DOM、截图、C 的精确网络时序与副本证据验证。finite task/frame 屏障仍不证明业务函数规范级退出，合成 persisted=true 不证明真实保存；source-change 的 blocked 与 A 任务 5 的真实模型/正常退出/慢生成切换/PG 重启/跨账号边界不变。

Critical：无。High：无。Medium：无。Low：无有明确修复价值的问题。**未发现有实际依据的问题。** 可继续已批准的真实浏览器受控网络复验，不据本次 PASS 另开产品修复轮，也不提前宣称场景或 Task10 完成。根 README 由主会话集中同步本次审查和后续实际结果。
