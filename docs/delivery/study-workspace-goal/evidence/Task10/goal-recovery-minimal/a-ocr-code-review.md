# Task10 方案 A 独立 OCR 代码审查

日期：2026-11-03。结论：**代码审查 PASS；未发现有实际依据的问题。Task10 与方案 A 的真实验收仍未完成。** 本结论只适用于下述冻结前端范围，不是整个脏工作区审查通过，也不证明浏览器、真实模型或数据库持久化已验收。审查未修改产品代码或测试，未实施 B。

## 范围、规则与冻结

已读取项目 AGENTS 的目标驱动与范围控制规则、CLAUDE、原 Task10 计划的文件白名单/精确查找合同/功能验收、A raw 与实施计划、独立 A 计划审查、第七轮实施及审查、A 实施报告和 RED/GREEN/全量/构建日志。依据 `open-code-review-delegate` 技能执行 OCR，而非依靠历史 OCR 清单。

当前 HEAD：`6d5829303f639e50ca15b11a9c8f79ee093caff1`。OCR 模式为 workspace，tracked diff 比较 HEAD；未跟踪文件直接读全文。Git 均使用 no-pager，diff 禁用 ext-diff/textconv/color。首次 preview 成功但终端输出截断，随后将同一 preview 完整保存到稳定文件；第二次捕获 exit=0，没有将截断输出当完整清单。

| 统计范围 | total_files | reviewed_files | skipped_files | coverage_rate |
| --- | ---: | ---: | ---: | ---: |
| OCR reviewable `(path,status)` | 1677 | 13 | 1664 | 0.7752% |
| Task10 原批准路径与第七轮/A 冻结范围并集的实际文件 | 46 | 46 | 0 | 100% |

preview 共列 4273 项：可审 1677、工具排除 2596。2596 项原排除原因完整保留，未计作人工已审；1664 项逐项标记任务外历史测试临时产物、其他任务改动或历史验收工具/证据，本次没有审查其实现。**不能用 Task10 的 100% 宣称工作区全覆盖。**

46 项中，13 项属于 preview 可审文件，9 项测试被 OCR 排除后主动补充审查，24 项是 HEAD 无 diff 的历史依赖/配置。原计划首段明确列出的 27 个实际路径全部映射；`useWorkspaceController.test.tsx` 为原计划允许新增或更新的可选测试文件，当前不存在，hook 入口由 Chat 业务测试覆盖。Sidebar 的最小兼容导出、Task9 对话框/导航与其他 API/页面依赖也纳入 46 项上下文，不把原计划“复用”误说成本轮新增改动。

原始与逐项证据：

- [本轮 preview](a-ocr-preview.json)：完整模式、所有路径/状态及工具排除原因。
- [全部规则](a-ocr-rules.json)：17 批覆盖全部 1677 条可审路径，规则遗漏为 0。
- [46 项补充规则](a-ocr-task10-rules.json)：包括被排除的测试与未变依赖；默认规则组 1、JSON 组 2、package 组 3、TS/TSX 组 4。
- [OCR 逐项清单](a-ocr-checklist.json)：所有可审 `(path,status)` 的 reviewed/skipped 及具体理由。
- [Task10 范围映射](a-ocr-task10-scope.json)：逐文件原计划提及、第七轮冻结、preview 状态/排除原因、diff 行数、规则组、审查方式、当前 SHA256 与冻结一致性。

本审查重新计算 46 项当前 SHA256，全部与 `a-final-source-after.json` 一致；核对 before/after 的 46 项差异为 0。审查完成后再次核算差异仍为 0，见 [审查后冻结核对](a-ocr-source-after.json)。与第七轮清单相比，仅 `workspaceController.ts` 和 `Chat.test.tsx` 变化。全量日志记录 11 文件/365 测试通过、exit=0，构建日志 TypeScript/Vite 成功、exit=0；这是对已冻结实施证据的独立核对，本审查没有重跑测试或构建。

46 项中产品/测试文件均读完整源码，并检查对应 tracked diff；新增文件全文即 diff。`Chat.test.tsx` 1–3891 行由主会话另外委派的独立辅助审阅者全文分段检查，结果与本报告合并裁决。锁文件使用完整 JSON 解析和全部键结构检查、无 diff/冻结哈希核对，未逐依赖值进行供应链安全审计；范围映射明确标注此限制。服务端 `session_service.py` 的所有权、消息分页排序/游标作为相关合同上下文读取，不将其计算为本次后端完整审查。

## 重点裁决与证据

1. **已有冲突的旧成功/新冲突。** `workspaceController.ts:812–817` 的 key 包含账号代次/用户、session/request/attempt、服务端身份/profile/node/base、完整 request_payload/response_json/baseline。`:849–854` 在同步提交内检查域实例和 `run.conflict > runSequence`，只有真正发布同 ID 矛盾时才推进冲突；`:869–875` 的 catch 只有当前账号、有效 source、最新运行及完整关联身份仍有效，且异常属于 `AssociationMismatch`，才推进冲突。较旧匹配被拒绝时 `matched` 保持 false，`:867` 不清副本。两次均从 inconsistent 启动已不再依赖初始布尔状态区分新冲突。这是源码推导，与业务 RED/GREEN 相互支持，不称真实浏览器实测。
2. **新 503/游标失败后旧有效成功。** 普通异常不增加 conflict；成功提交没有要求自身为 latest，故能接受仍有效的较旧成功。保留原有“旧失败不回退新 matched”的关联检查。新主动重查开始序号晚于已发布冲突，仍可匹配；活动归属、画像/教学版本与 UI sequence 仍分别核验，不因本次字段合并为一个资格。
3. **域与实例释放。** `:877–878` 只回收自身仍占据该 key 的实例，所有 active 完成后删除。账号 generation 变化会清 map，且旧调用受 current(ticket) 限制；旧 finally 不删除其他实例。key 不保存到本机，内存与当前在途关联域相关，不随历史累计。不同 payload/baseline 的 key 不共用冲突次序；实际 completed 请求事实又由 store 的不可变合并合同保护。不能把低层测试直接替换受控 store 字段描述成线上身份变更事故。
4. **精确副本与来源。** `recoveryCandidateUnchanged:88–95` 核完整候选而非仅 request ID；`cleanupMatchedRequest:114–170` 限当前账号/已匹配请求及完整 payload/baseline，并仅删除本 writer 的完整候选；`localRecovery.ts:94–102` 再核当前完整序列化内容及删除读回。新冲突被保留时不会进入该次 cleanup。此次没有放松其他 writer、writeId 或后续编辑保护，也未声称跨标签存储原子性。
5. **业务复现真实性。** `Chat.test.tsx:3863–3891` 经 App/AuthProvider/MemoryRouter、输入发送及受控响应进入 inconsistent，再点击两次实际“重新查询”按钮。新冲突保留警告、禁发、本人和另一 writer 精确 writeId；随后主动一致重查可恢复；POST 数一直为 1。B=503/游标回环对照存在。没有直接 patchBucket/mergeRequest 造目标起点。该测试仍是 jsdom/RTL 加 stub fetch。
6. **原 Task10 链路。** 全文检查 URL 恢复及异步导航资格、账号清理/401、每桶草稿/锚点保存及退出汇总、发送准备与原文保护、原 ID 查询/显式重发与 retry、活动门禁、消息合并/历史前沿，以及布局和对话框调用方。原 Task9 的“不可用/不请求 snapshot”断言被替换为 Task10 正常历史读取合同，布局/账户/导航覆盖仍保留；没有把正常发送改为固定拒绝来通过测试。模型文本仍经 React/ReactMarkdown 呈现，没有新增 HTML 执行、SQL、密钥或任意代码入口。
7. **分页合同。** 服务端 `session_service.py:147–170` 先验所有权，按 turn/role/id 向旧记录分页并反转页内顺序；controller `:831–848` 按 opaque cursor，取到两角色、越过 turn 或 cursor 耗尽结束。网络/游标错误不证明缺失；可信基线下合法查找结束缺角色/矛盾为 inconsistent；无基线走 unassociated 与显式继续。原计划后续“历史记录缺失”措辞歧义尚无实际响应触发，不据此阻断或新增全历史扫描框架。

## 计划内补证与未验证范围

**来源组合不应机械扩成矩阵。** 实施报告如实承认未补“已有 inconsistent + source 失效”所有组合。静态追踪表明：已有 inconsistent 的主按钮 `Chat.tsx:52 → reconcile(...,true) → controller:777` 调 `confirmCompleted` 不带 source；候选按钮 `recheckLinkedPreparation → recheckCandidate` 在 `:616` 遇已有 inconsistent 直接抛错，不会走 `:618` 的带 source 核验。因此“已有 inconsistent 起点、两次独立候选 source 核验”不是当前支持按钮可直接制造的交错。应保留这个不可达证据及 `Chat.test.tsx:3831–3862` 的相邻可达来源失效测试，不为补矩阵绕过页面入口或改产品协议。该相邻测试从 pending_messages 开始，不能冒称已有冲突起点的实测。

**身份组合的证据级别。** `Chat.test.tsx:3720–3735` 等身份变化有直接 store 注入/换代场景，不能称真实 UI 账号操作。完整 key、associationCurrent/current、实例限定 finally 提供静态隔离依据；现有页面与 store 测试提供相邻行为依据。尚无新增完整身份交错全组合实测，但没有证据证明需要任意组合穷举或新增通用机制。按 A 计划保留此限制；真实验收重点落实实际账号/会话切换，不把内部注入当成外部可达攻击。

以下均仍未完成，任何一项不能由此次 PASS/365 测试/HTTP 200 代替：

- A 任务 1 的真实浏览器受控双重查交错、按钮与网络时序/截图。需要补原计划内证据，最小设施是独立前端及专用可控制响应服务；不需要改产品代码或引入 B。
- 实际浏览器注册/登录、本人画像新建会话、草稿与恢复、真实模型提问及后续教学、persisted=true 后权威消息 ID/内容读取、刷新/重登恢复。
- 正常退出保存门禁成功、真实后端慢生成 A→B 后 A 按桶归位，以及失败/冲突/断网及恢复 UI。各类受控故障与真实模型正常路径须分开记录。
- 专用真实 PostgreSQL 重启后相同消息可读，以及第二账号 session/request/messages 的后端拒绝与实际 UI 无泄露。
- Task8 HTTP/SSE 对照与全部后端事务/持久化未在本审查重跑；依赖供应链、全部任务外工作区改动、跨浏览器原子性均未审计。

## 分级发现与后续边界

Critical：无。High：无。Medium：无。Low：无有明确修复价值的问题。**未发现有实际依据的问题。** 上述补证是 A 既有完成条件与证据限制，不是新代码缺陷或新架构授权。可据本次代码审查结论推进原计划真实验收，不能宣布 A/Task10 完成。若真实验收失败，应先记录真实入口/触发/用户影响及最小方案，由主会话独立裁决；不自动开启下一轮框架修复。

B 的 IndexedDB、FIFO、检查点/预算/并发配额及全历史扫描仍为 TODO 候选，未实施。README 当前尾段已准确保持真实验收未完成；由主会话追加本报告与最终进度，避免并发改写用户原有 README。
