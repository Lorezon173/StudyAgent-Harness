# RAG-A 第二轮提示词（直接复制到 RAG-A 窗口）

你是 StudyAgent Harness「RAG 基础能力建设」的 **RAG-A 任务窗口**。主控已完成 A 线验收，本轮回执结果并待命。

## 验收结果：✅ 通过

主控独立验收（2026-07-29）：
- **24 测试全通过**（`tests/unit/infrastructure/test_extractors.py`，含 17 个 EPUB 专项 + 7 个原有 text extractor）
- 实现审查合格：标准库实现（zipfile/ElementTree/HTMLParser/posixpath/unquote）、OPF spine 顺序、严格 UTF-8、`<br>` 哨兵归一化、任一 spine 资源失败整体空串、损坏 ZIP/缺 container/OPF/spine/无效 UTF-8/malformed XML 均返回空串、无未 spike 依赖
- 资产清单去重已执行（唯一事实源为「EPUB Extractor 正式接入」节）

**Phase 1A（A-01~A-07）正式完成。** BLK-009 解除。

## 配套裁决（影响你）

- **EPUB 纳入 Gate 0 happy-path**（DEC-012 §13.4）：你的 `EpubExtractor` 已成为正式 Gate 0 摄入链的 EPUB 输入源；RAG-B 的 `ChunkingService` 会预留 `source_format="epub"` 适配。

## 你的下一轮任务

**本轮无编码任务。** 待命至 Phase 4（首本书正式摄入），届时会调用你的 `EpubExtractor` 完成真实 EPUB -> 纯文本 -> 摄入主链。

可选的预备工作（不阻塞）：
- 如 RAG-B 在 Phase 2 实现 `ChunkingService` 时需要 EPUB 元素适配（章节/段落结构），你可配合提供 extractor 输出格式说明（纯文本 + `\n\n` 块分隔，无结构化元素）
- 如发现 EPUB spec 有可改进点，回写 `RAG-A.md` 的"未做事项"

## 回写要求

更新 `docs/rag-work/status/RAG-A.md`：
- 标注 Phase 1A 验收通过、BLK-009 解除
- 记录"待命 Phase 4"状态
- 列出任何遗留风险或改进建议

## 禁止

- 本轮不实现摄入/chunk/索引（归 RAG-B）
- 不修改主清单或其他窗口状态片段

完成后简要报告：验收结果已确认、待命状态已回写。
