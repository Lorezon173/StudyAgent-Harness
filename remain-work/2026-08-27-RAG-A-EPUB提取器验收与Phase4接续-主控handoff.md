# RAG-A EPUB 提取器验收与 Phase 4 接续主控交接

## 1. 一句话接手说明

- RAG-A 的 Phase 1A（A-01~A-07）已完成并验收：正式 `EpubExtractor` 已纳入产品 extractor 工厂，当前只交付并验证“.epub → 纯文本”能力；接手者无需重做 A 线编码，应在 Phase 4 启动时先验证主清单的 F-01 前置环境，再用真实 EPUB 驱动 F-02 的产品摄入链。

## 2. 当前状态

- 已完成：
  - Phase 1A（A-01~A-07）与 BLK-009 已完成/解除；权威状态见 `docs/rag-work/status/RAG-A.md` 的“交主窗口记录 / 比对的当前快照”。
  - `EpubExtractor` 已实现并注册进 `get_extractor()`；专项测试当前实测为 24 passed。
  - 当前工作树全量非 integration 测试实测为 `597 passed, 1 skipped, 8 deselected`；这是共享工作树的总结果，不能仅归因于 RAG-A。
- 进行中：
  - 无 RAG-A 编码任务；RAG-A 处于待命状态。
- 未开始但已确认要做：
  - Phase 4 的 F-01~F-06，RAG-A 在 F-02 以真实 EPUB 输入提供 extractor 协作。
- 当前卡点 / 待确认项：
  - F-01 的真实 PostgreSQL/pgvector/embedding 环境验证尚未完成；主清单当前将 PostgreSQL 迁移前置列为 Phase 4 工作，不能用 SQLite/Fake 测试替代。
  - 真实 EPUB 兼容性尚未经过生产样本验证；当前验证以动态最小 EPUB fixture 为主。

## 3. 接手后第一动作

1. 先打开主清单的 Phase 4（F-01~F-06），确认 F-01 的干净 PostgreSQL migration 已完成且有可复跑证据；没有 F-01 证据时，不要启动真实 EPUB 写入或对外宣称摄入链完成。
2. 再阅读 RAG-A 权威状态片段的“待命状态与遗留风险”，确认真实 EPUB 测试样本、提取范围和安全边界；然后读取 RAG-B/C 的权威状态，核验 F-02 所需的 Chunking、Ingestion、provider 和在线基础是否仍可用。
3. 仅在 Phase 4 被正式调度后，沿 `真实 EPUB → EpubExtractor → ChunkingService → KnowledgeIngestionService → EmbeddingService → PgVectorProvider` 运行 F-02，并将发生的问题限定为 extractor、chunk/ingestion、embedding/provider 或基础设施中的可证实归属，再分别派回对应模块。

## 4. 关键决策与边界

- 已确认决策：
  - Extractor 公共边界冻结为 `extract(file_path: str) -> str`；EPUB 输出是纯文本，非空块以双换行分隔，块内 `<br>` 归一为换行。
  - `.epub` 与 `.EPUB` 均由既有 `get_extractor()` 工厂匹配；实现采用 Python 标准库，不新增第三方 EPUB 依赖。
  - Phase 1A 的完成口径仅为“EPUB 提取能力已实现并验证”，不等于摄入、chunk、索引、检索、在线 grounded answer 或黄金集 baseline 已完成。
- 明确不要做的事：
  - 不把 `EpubExtractor` 扩张为返回 section、paragraph、metadata 或 chunk；结构化切块和 provenance 归 RAG-B。
  - 不在 RAG-A 内直写向量库、绕过 `KnowledgeIngestionService` / `RAGCoordinator`，或从 benchmark 导入生产代码。
  - 不因 RAG-A 验收而跳过 F-01、F-03~F-06，也不以 SQLite/Fake 测试宣称真实 pgvector 产品链已验证。
- 仍未定论、不能当作事实的点：
  - 当前真实 EPUB 的兼容性范围尚未验证；`li`、`blockquote`、`pre` 等未由最小块解析范围保证提取。
  - ZIP bomb 的成员数和未压缩大小防护未实现；接入不可信上传入口前必须另立安全治理任务。

## 5. 必看材料索引

- 用途：获取 RAG-A 的权威完成状态、复跑命令、实现范围、审查修复与 Phase 4 风险。  
  索引：`docs/rag-work/status/RAG-A.md`，重点“交主窗口记录 / 比对的当前快照”“Phase 1A 完成证据”“待命状态与遗留风险”。

- 用途：确认 Phase 4 的串行任务、前置条件和验收口径。  
  索引：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`，重点 `Phase 4：首本书正式摄入与证明`（F-01~F-06）。

- 用途：确认 EPUB extractor 的冻结行为与明确非目标。  
  索引：`docs/rag-work/specs/2026-07-24-epub-extractor-spec.md`。

- 用途：确认 RAG-B 的 chunk/ingestion/identity/provenance 是否满足 F-02。  
  索引：`docs/rag-work/status/RAG-B.md`。

- 用途：确认 RAG-C 的 provider、visibility、在线 composition 与真实环境边界。  
  索引：`docs/rag-work/status/RAG-C.md`。

- 用途：确认 RAG-D 的 admission、baseline 与 Phase 5 依赖。  
  索引：`docs/rag-work/status/RAG-D.md`。

## 6. 代码 / 产物落点

| 产物 | 用途 / 当前关系 | 本次核验 |
|---|---|---|
| `app/infrastructure/rag/extractors/epub_extractor.py` | `EpubExtractor` 的标准库 EPUB → 纯文本实现 | 已用 CodeGraph 核验：OPF spine 顺序、严格 UTF-8、`<br>` 归一化、任意异常整体空串 |
| `app/infrastructure/rag/extractors/base.py` | 既有扩展名工厂，将 `.epub/.EPUB` 路由至 `EpubExtractor` | 已用 CodeGraph 核验 |
| `tests/unit/infrastructure/test_extractors.py` | 动态 EPUB fixture 与回归用例 | 本窗口实测 24 passed |
| `docs/asset-inventory.md` | EPUB extractor 的项目事实登记 | 已核验“EPUB Extractor 正式接入（已实施）”节 |
| `README.md` | 用户可见功能说明 | 当前共享工作树已含 EPUB 标准库 extractor 描述；由其他共享改动维护，勿单独回退 |
| `docs/rag-work/status/RAG-A.md` | RAG-A 唯一写者的权威状态片段 | 主控只读，不应代替 RAG-A 窗口改写 |

## 7. 待办清单

### 必须先做

1. Phase 4 开始前：验证 F-01 的干净 PostgreSQL Alembic migration、pgvector 与 embedding 环境，不以单测/SQLite 代替。
2. Phase 4 中：执行 F-02 的真实 EPUB 产品链，并保存可以复跑的输入、环境和结果证据。
3. 随后完成 F-03~F-06：attestation、identity/source locator round-trip、跨用户/范围隔离、append-only 边界记录。

### 可后做

4. 若真实样本暴露 EPUB 解析问题，仅在 `epub_extractor.py` 与其专项测试范围修复，并重新评估是否需扩展最小 HTML 块语义。
5. 若未来接入不可信上传入口，单列 ZIP bomb 防护、成员数/解压大小上限及安全测试，不将其夹带进当前 F-02。

## 8. 风险与坑点

- **完成口径膨胀**：RAG-A 已完成不等于 RAG 产品链完成；F-02 尚未完成前不得称为“正式 EPUB 摄入已完成”。
- **共享工作树风险**：当前工作树含其他模块的未提交改动。运行验证、创建交接或修复时，不要 reset、批量暂存或提交非己归属文件。
- **状态片段单写者约束**：`RAG-A.md` 属 RAG-A 窗口，主控只能读取和比对；本 handoff 才是主控侧记录。
- **测试范围误读**：24 passed 证明 extractor 专项行为；597 passed 是当前共享工作树全量非 integration 测试，不能推导真实 PostgreSQL/embedding/pgvector 的环境正确性。
- **HTML 范围边界**：当前最小解析仅关注 `p` 与标题块；不要把未覆盖内容的保留情况当成已验证兼容性。

## 9. 交接完成判据

- 新窗口阅读本文件第 1、3、5、7 节后，能明确 RAG-A 已无需重做编码、Phase 4 的第一动作是先验证 F-01、随后才执行真实 EPUB F-02。
- 新窗口能从权威状态、主清单和 RAG-B/C/D 状态片段回到一手材料，不把本文件的摘要替代为事实源。
- 新窗口能维持 extractor-only 边界，并在真实样本或安全问题出现时正确分流到 RAG-A、RAG-B/C 或基础设施/安全任务。
