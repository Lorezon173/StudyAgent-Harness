# RAG Foundation 工作文档区

> 本目录集中存放「RAG 基础能力建设」（2026-07-24 起）的全部工作文档：计划、规范、决策画布、派工提示词、各窗口状态片段。  
> 唯一主清单与全局 blocker 账本：[`plans/2026-07-24-rag-foundation-parallel-todolist.md`](plans/2026-07-24-rag-foundation-parallel-todolist.md)。  
> 已确认决策记录：[`plans/2026-07-27-rag-p0-confirmed-decisions.md`](plans/2026-07-27-rag-p0-confirmed-decisions.md)（DEC-001~012）。

## 目录结构

| 子目录 | 用途 | 关键文件 |
|---|---|---|
| [`plans/`](plans/) | 计划、blocker 账本、执行顺序、已确认决策记录 | 主清单、execution-order、confirmed-decisions |
| [`specs/`](specs/) | 设计规范 | epub-extractor-spec、online-rag-p0-repair-spec、project-chunking-service-spec |
| [`decision-canvas/`](decision-canvas/) | 决策画布（Markdown 源 + HTML 视图） | P0 面板、BLK-004/006/007 dashboard、program-cockpit |
| [`dispatch/`](dispatch/) | 多窗口派工提示词 | RAG-A/B/C/D 第一轮 + 第二轮 |
| [`status/`](status/) | 各任务窗口状态片段（唯一写者为对应窗口） | RAG-A/B/C/D.md、README（同步协议） |

## 主控单写者约束

- `plans/` 与本 README 由**主控窗口**维护
- `status/RAG-X.md` 由对应 **RAG-X 窗口**唯一写，主控只读
- `specs/` 由对应任务窗口修订，主控复核
- 既有 `decision-canvas/` HTML 由 render-html 从 Markdown 源渲染；2026-10-17 缺口决策页为独立 HTML，原始证据快照保存在同名日期的 JSON 中。

## RAG 全貌与阶段说明

[2026-10-18 模块全貌 HTML](decision-canvas/2026-10-18-rag-module-overview.html)展示当前模块、四条链路、S0～S6 阶段及 T00～T14 工作包关系，每阶段列出实现基线、已完成、剩余、输入输出和验收要求。事实来自同目录架构及阶段审计 JSON；[可编辑源文件](decision-canvas/2026-10-18-rag-module-overview.src.html)经 Visual Explainer kit 渲染为无需联网的页面。此页为说明材料，不变更实现、执行计划或关卡状态。

## 缺口决策网页

[2026-10-17 RAG 就绪与缺口决策页](decision-canvas/2026-10-17-rag-readiness-decision.html)：逐项展示当前证据、规则来源、影响、延后后果、处理方案与验收要求；覆盖 8 类盘点缺口、9 项计划审阅问题及 50 处原文依据。支持筛选、原文弹窗和 Markdown 草案导出，草案选择不改变任务验收或关卡状态。 [Visual Explainer 图解版](decision-canvas/2026-10-17-rag-readiness-visual.html)采用 Instrument 风格，首屏呈现并行准备与关卡约束，详细证据仍可展开查看；[源文件](decision-canvas/2026-10-17-rag-readiness-visual.src.html)经官方 kit 渲染并将样式和脚本内联，输出使用本机字体，无需联网。

图解版现附有页内中文阅读说明：解释图例、任务与关卡编号、8 类缺口的决策含义，以及草案选择和导出步骤。

## 当前阶段

2026-10-16 增量：[T00共享契约当前v1.0.1](specs/2026-10-16-rag-mvp-contracts-v1.md)已归档并记录后续勘误，[记录](../../superpowers/rag-foundation/2026-10-16-t00-contract-freeze-record.md)。该新增主控共享spec由主控维护，不改变旧窗口spec/状态的唯一写者。[独立T02/T03/T04计划](plans/2026-10-16-execution-plan-index.md)已由三个子代理编写；[主窗口逐份复查及关闭记录](plans/2026-10-16-first-wave-plan-rereview.md)中的离线隔离、SDK索引对应及judge汇总一致性验收已修订并通过文档复核。用户随后授权三个 gpt-6-luna / xhigh 子代理实施；T02/T03/T04已通过实现复审与最终组合离线回归（547 passed、1 deselected）。实际进展与命令结果见[主窗口验收](evidence/2026-10-16-first-wave-execution.md)；真实环境验收尚未开始。

第二批按DAG分别编写T08、T09、T05独立三层计划，由三个gpt-6-luna / xhigh子代理起草并在当前主窗口审阅；[计划审阅记录](plans/2026-10-16-second-wave-plan-review.md)区分私有装配建议、已有契约及真实运行前置。本轮只规划，不启动这三包编码。 最新[2026-10-17正式审阅](plans/2026-10-17-second-wave-plan-review.md)确认9项需修订问题，当前三包均暂不派发实现。

用户已将[T01环境与资产只读盘点计划](plans/2026-10-17-t01-execution-plan.md)加入本批，覆盖资产/哈希、运行时/CI、受控PG身份与embedding绑定来源；用户随后授权先执行T1，[盘点覆盖已完成](evidence/t01/2026-10-17-inventory.md)，资源就绪blocked、PG/embedding未探测；T05/T08/T09的9项审阅问题及G1～G6状态保持不变。

以下条目为旧阶段快照，D工具已在后续实施回报完成、B/C基础已落地；当前本轮状态以主清单增量、实际实施回报及T00记录为准，不能把旧“待实现”当当前事实。

- P0 裁决：DEC-001~012 全部冻结 ✅
- Phase 1A（RAG-A extractor）：验收通过 ✅
- Phase 1B（RAG-B 补证）：B-04 复核通过，DEC-012 冻结 ✅
- Phase 1C（RAG-C spec）：C-08 provisional 通过 ✅
- Phase 1D（RAG-D 工具）：待实现 🟡
- Phase 2（B 线 + C 线编码）：已放行 🟢
