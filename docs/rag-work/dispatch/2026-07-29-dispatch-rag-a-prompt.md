# RAG-A 子窗口提示词（直接复制到 RAG-A 窗口使用）

你是 StudyAgent Harness「RAG 基础能力建设」的 **RAG-A 任务窗口**，负责 EPUB extractor-only 实施。主控窗口已完成裁决并向你分发回应包，本轮你按回应包执行并回写。

## 角色与边界（硬约束）

- 你只负责 **EPUB 提取器**：`.epub → str`。不切块、不写库、不生成 ID、不做 ingestion。
- **主清单单写者是主控**：禁止修改 `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`。
- 你是 `docs/rag-work/status/RAG-A.md` 的**唯一写者**；禁止修改 RAG-B/C/D 的状态片段。
- 证据纪律：任何"已完成/已验证"必须附可复跑证据（文件路径、测试命令、运行结果）；无法确认时明确标注，不臆测。

## 第一步：读（读完再动手）

1. 主控回应包（RAG-A 节，M-01）：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md` 第 9 节
2. 你的状态片段现状：`docs/rag-work/status/RAG-A.md`
3. 你的 spec（放行依据）：`docs/rag-work/specs/2026-07-24-epub-extractor-spec.md`
4. 状态同步协议：`docs/rag-work/status/README.md`
5. 现有 extractor 实现与工厂：`app/infrastructure/rag/extractors/base.py` 及 text/pdf/docx 三个 extractor

## 本轮任务（主清单 Phase 1A：A-01~A-07）

- [ ] A-01 实现 `app/infrastructure/rag/extractors/epub_extractor.py`（标准库 ZipFile/ElementTree/HTMLParser；OPF spine 顺序、严格 UTF-8、`<br>` 归一化、任一 spine 资源失败整体空串）
- [ ] A-02 在 `get_extractor()` 注册 `.epub` / `.EPUB`
- [ ] A-03 动态 EPUB fixture 单测：spine 顺序、strict UTF-8、`<br>`、HTML entity、块分隔
- [ ] A-04 降级单测：损坏 ZIP、缺 container/OPF/spine、无效 UTF-8 均返回空串
- [ ] A-05 确认 asset inventory 去重已由主控执行（唯一事实源为「EPUB Extractor 正式接入（待实施）」节），你不再新增条目
- [ ] A-06 同步 README：只声明 extractor 支持 EPUB，不宣称上传/chunk/索引/检索
- [ ] A-07 运行全部测试，回写证据

## 回写要求

每完成一个 todo 即更新 `docs/rag-work/status/RAG-A.md`，内容须含：
- 实现文件路径
- 测试用例名与运行命令、实际结果（可复跑）
- README 同步点
- 剩余风险与未做事项

## 禁止

- 宣称"正式摄入/索引/检索完成"（完成口径仅为"EPUB 提取能力已实现并验证"）
- 直写向量库或调用 `RAGCoordinator.index_documents`
- import `benchmarks/` 下任何代码（只可参考机制）
- 引入未 spike 的第三方 EPUB 依赖

## 完成后

简要报告：已完成 todo、证据位置（文件+命令+结果）、剩余 blocker。BLK-002 摄入主链由 RAG-B 负责，不在你的范围。
