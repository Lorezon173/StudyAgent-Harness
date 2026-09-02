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
- `decision-canvas/` HTML 由 render-html 从 Markdown 源渲染

## 当前阶段

- P0 裁决：DEC-001~012 全部冻结 ✅
- Phase 1A（RAG-A extractor）：验收通过 ✅
- Phase 1B（RAG-B 补证）：B-04 复核通过，DEC-012 冻结 ✅
- Phase 1C（RAG-C spec）：C-08 provisional 通过 ✅
- Phase 1D（RAG-D 工具）：待实现 🟡
- Phase 2（B 线 + C 线编码）：已放行 🟢
