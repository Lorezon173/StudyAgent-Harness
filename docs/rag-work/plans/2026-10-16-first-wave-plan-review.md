# 首批 T02/T03/T04 独立执行 plan 主窗口审阅记录

> 本文件保留首轮审阅历史；当前状态以[逐份复查及修订关闭记录](2026-10-16-first-wave-plan-rereview.md)为准：三个问题已定向补入对应plan，文档复核通过，未实施。

日期：2026-10-16。用户授权：分别派发子代理编写三个独立plan，由当前主窗口review。本轮只写计划、核查代码事实和文档，不派发业务实现、不运行pytest或真实服务。

## 1. 产物与审阅方式

| 包 | 编写代理 | 独立plan | 主窗口结论 |
|---|---|---|---|
| T02 | plan_t02 | [写入确认与产品预计划](2026-10-16-t02-execution-plan.md) | 完成针对性修订后通过，计划可派发，尚未实施 |
| T03 | plan_t03 | [评测状态、多k与20题](2026-10-16-t03-execution-plan.md) | 完成针对性修订后通过，计划可派发，尚未实施 |
| T04 | plan_t04 | [证明契约与embedding身份](2026-10-16-t04-execution-plan.md) | 完成针对性修订后通过，计划可派发，尚未实施 |

代理只写自己指定的plan，主窗口独立读取三份全文/关键修订、冻结spec、实际模块与测试/CI入口；review不交还给原代理自行批准。原代理按主窗口意见修订，主窗口再核对。这里的“通过”仅指执行材料满足派发前置，不是测试或实现通过。

## 2. 编写过程中形成的契约勘误

原v1归档：[原冻结字节](../specs/2026-10-16-rag-mvp-contracts-v1-original.md)，SHA-256 `64e1f13d58adc2c30685284f2e221584951b974416609637d6ee46192e133cc0`。

当前唯一执行基线：[共享契约v1.0.1](../specs/2026-10-16-rag-mvp-contracts-v1.md)，SHA-256 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。文件名保留v1入口以免失效；契约集标识/证明contract_version使用rag-mvp-contracts-v1.0.1，各数据schema_version不变。

主窗口按原冻结变更规则记录勘误及影响包，没有让子代理私自改共享接口：

| 暴露的空隙 | 固定后的契约 | 影响 |
|---|---|---|
| build_attestation无本次核验时间输入 | 新增关键字verified_at:UTC ISO8601字符串；调用方提供，纯函数不读时钟 | T04/T08 |
| 非法top_k输出值与未知耗时未定义 | 非法top_k=null；仅query非法仍保留合法top_k；未查询/无法取得可信search耗时为null，不用0冒充 | T03/T09 |
| evaluate异常/坏结构如何保留失败attempt | 完整合成失败metrics；TimeoutError→failed/timeout，未知异常→failed/backend_unavailable，坏schema→invalid-request/invalid_request；失败计数并停止 | T03/T09 |
| 没有执行judge/无gold指标边界 | 未judge为三项unavailable及judge_degraded=true；检索故障仍inconclusive；健康无gold的redundancy可计算 | T03/T09 |
| 准备异常摘要和非法provider计数 | 固定三个摘要；非法/超计划确认值转0并明确未确认，不表示零写入 | T02/T08 |
| policy“正整数”过于笼统 | size/hard_limit正整数、overlap非负且小于size；拒bool | T02/T04 |

这些是将已批准意图落成可执行接口所需的最小补正，不扩展上传、幂等、数据库表、额外回答器或真实运行范围。旧v1冻结记录不被删除，也不再作为首批plan的当前SHA。

## 3. 主窗口review发现与关闭

| 包 | 审阅发现 | 修订与核对 |
|---|---|---|
| T02 | 只有测试侧动态oracle，生产/测试可能同算法错误而自洽 | 加完整合成单行、content SHA与固定manifest SHA；与T04同向量，无运行时依赖；主窗口重算核对 |
| T02 | uv run ruff与当前CI工具配置不符 | 改uvx ruff限定文件；缺工具/审批/下载按环境阻断，不伪称lint通过 |
| T02 | “离线”只有意图，旧RAGCoordinator()可能读取真实环境后端 | 增模块内fake/受控provider与SDK/连接陷阱、仅允许内存SQLite；不改共享conftest，所有pytest禁cacheprovider |
| T03 | evaluate新null字段缺消费方兼容验证 | 增只读ComponentBench回归，并在允许测试文件中计划真实evaluator的受控贯通；不越权改consumer |
| T03 | 缺限定lint步骤 | 增CI一致四文件uvx ruff检查，区分历史告警和本包新增 |
| T04 | “共享算法供T02”可能暗增首批硬依赖 | T04 helper供后续T08/T09；T02本批内部实现同规范+固定向量一致，不能导入尚未交付T04模块 |
| T04 | 证据目录建议与允许六文件清单不一致 | 固定一个验证记录并明确六实现/测试文件加一证据记录的允许清单 |
| T04 | 安全warning模板可能拒绝已有产品合法warning；端点比较可能任意宽松化 | 接受既有oversized安全模板与明确合成变体；实际SDK端点严格匹配，不strip路径/query/尾斜杠 |

主窗口另独立重算T04三组规范JSON/hash向量，均与文档字面摘要一致；T02固定单行摘要与其中一组一致。这里只证明计划中的固定测试向量算对，不是产品测试已经通过。

## 4. 派发约束

- 首批三个plan统一锁定v1.0.1与SHA；发现后续spec漂移暂停并报主控，不自行适配。
- T02独占既有摄入/embedding/provider写入文件；T03独占evaluate/rag_d核心和相应测试；T04只新增三个共享模块和对应测试，不抢既有文件。
- 证据路径固定，各包执行后填实际红绿命令/结果。当前所有实施checkbox保持未勾选，不预造测试通过数。
- T03仅交付评测执行核心与计数；T09才连接T04 gate/正式报告。当前不存在T04也应能独立验证T03。
- T02/T04在执行时共享的现有IngestResult保持路径和字段兼容；T04测试不依赖T02新准备接口。
- 根README、主清单和跨包集成由主窗口负责，子代理提交变更摘要不并写主控文档。
- 可派发不等于本轮已经派发。后续若开始编码，按这三份plan并发实施，经过必要测试和主控review才能记T02/T03/T04完成；G1还依赖T09/T10等证据，不能提前放行。

## 5. 本轮验证边界

仅检查：现有源代码/CI事实、契约当前与原始SHA、计划三层结构/步骤/边界、固定合成摘要、Markdown链接及空白、Git变更范围。未运行计划中的pytest/lint命令，未安装依赖，未连接PG/embedding/LLM，未修改app/tests/benchmark实现，未commit/push。
