# 阶段 B-③：PDF 版面解析 Spec

> 创建日期：2026-07-03  
> 前置依赖：阶段 A（真向量检索）已完成  
> 来源追溯：`2026-06-16-rag-phase-a-plan.md` 第四层"下阶段 ③"  
> 状态：⏳ 待用户确认（技术选型待评估）  
> **优先级**：三个 B 子阶段中最低（"按知识源实际质量需求再评估"）

---

## 第一层：模块总览

### 1.1 目标边界

**做什么**：为教材 PDF 提供**版面级解析**能力（layout-aware parsing），提取结构化知识元素（标题层级、段落、表格、公式、图片说明），替代当前 `PDFExtractor` 的纯文本提取（pdfplumber/PyPDF2，无版面分析）。

**本阶段明确不做**：
- ❌ 知识内容图谱（B-① 独立阶段）
- ❌ 掌握度图谱时序化（B-② 独立阶段）
- ❌ 非 PDF 格式的版面解析（DOCX/PPTX 已有 `DocxExtractor`，Markdown/TXT 已有 `TextExtractor`，本阶段聚焦 PDF）
- ❌ 引入完整 RAG 平台（如 ragflow 整套平台，仅取其文档解析组件）

### 1.2 当前 PDF 解析能力的差距分析

| 能力 | 现有 `PDFExtractor` | 版面级解析（本阶段目标） |
|------|---------------------|------------------------|
| 文本提取 | ✅ 纯文本提取（pdfplumber 首选，PyPDF2 回退） | ✅ 文本提取 + 版面结构保留 |
| 标题层级识别 | ❌ 无（所有文本平铺） | ✅ 识别 H1/H2/H3 标题 |
| 段落分隔 | ⚠️ 按双换行粗略分隔 | ✅ 按版面区块精确分隔 |
| 表格提取 | ❌ 无（表格文本被打散混入正文） | ✅ 表格结构保留（行列 + 表头） |
| 公式提取 | ❌ 无（公式被当作乱码或丢失） | ✅ LaTeX 公式识别（或至少保留原始图像） |
| 图片说明 | ❌ 无 | ✅ 图片 + caption 配对提取 |
| 阅读顺序 | ⚠️ 按 PDF 内部对象顺序（可能与视觉顺序不一致） | ✅ 按视觉阅读顺序排列 |
| 依赖重量 | 轻（pdfplumber ~5MB） | 中-重（版面分析模型 ~200MB-2GB） |

**差距总结**：现有 `PDFExtractor` 对"教材 PDF"（版面复杂、含表格/公式/图片）的解析质量差，切块后语义被打散，直接影响 RAG 检索质量（垃圾进垃圾出）。版面级解析是提升教材知识源质量的关键。

### 1.3 技术选型评估框架（不预设结论，先评估再选）

本 spec **不预设选用哪个方案**，而是提供评估框架。实施前先按此框架做 spike（小范围实验），根据结果选定方案。

**评估维度**（按学习场景优先级排序）：

| 维度 | 权重 | 说明 |
|------|------|------|
| **解析准确率** | 高 | 教材 PDF 的标题/段落/表格/公式识别准确率 |
| **中文支持** | 高 | 中文教材的字体/排版兼容性 |
| **依赖重量** | 中 | 安装大小 + 运行时内存（影响部署成本） |
| **速度** | 中 | 单页解析耗时（影响批量索引效率） |
| **结构化输出** | 中 | 输出格式是否便于后续切块（JSON/Markdown/HTML） |
| **与现有架构契合** | 低 | 是否能作为 `Extractor` 协议的实现嵌入 |
| **活跃维护** | 低 | GitHub star + 最近更新频率 |

**候选方案**（5 个，按 star 降序）：

| 方案 | star | 定位 | 依赖重量 | 评估优先级 |
|------|------|------|----------|-----------|
| **ragflow DeepDoc** | 82.8k | 生产级 RAG 引擎的深度文档解析组件 | 重（整套平台，含前端+多服务） | 评估其解析组件是否可独立提取 |
| **LightRAG-MinerU** | 36.6k | LightRAG 并入的多模态解析（MinerU + Docling） | 中（MinerU ~500MB，含模型） | 高（与 B-① 技术栈一致） |
| **marker** | 22k+ | 专注 PDF→Markdown 转换（版面分析 + 公式识别） | 中（~300MB，含 surya OCR 模型） | 高（输出 Markdown，易切块） |
| **pymupdf4llm** | 8k+ | PyMuPDF 的 LLM 友好封装（版面分析 + 结构化输出） | 轻（~50MB，无额外模型） | 高（轻量，适合 MVP） |
| **unstructured** | 10k+ | 通用文档解析平台（PDF/DOCX/PPTX/HTML） | 中-重（~500MB+，含多种模型） | 中（通用性强但重量） |

**评估协议**（实施前必须完成）：

```
1. 准备 3 份典型教材 PDF 样本（中文，含表格/公式/图片）
2. 对每个候选方案做 spike：
   a. 安装依赖（记录安装耗时 + 磁盘占用）
   b. 解析 3 份样本（记录单页耗时 + 内存占用）
   c. 人工评估解析质量（标题/段落/表格/公式/图片 各维度打分 1-5）
3. 填写评估对照表（见第三层 §3.1）
4. 根据评估结果选定方案，更新本 spec 的"选定方案"章节
```

### 1.4 依赖关系与四层架构衔接

```
API 层
  ├─ /knowledge/upload (POST) — 用户上传 PDF 文件
  ↓
Orchestration 层
  ├─ 调用 KnowledgeIngestionService（知识摄入服务）
  ↓
Harness 层
  ├─ KnowledgeIngestionService（🔴 新建，PDF → 结构化元素 → 切块 → 索引）
  ↓
Infrastructure 层
  ├─ LayoutPDFExtractor（🔴 新建，实现 Extractor 协议）
  ├─ PdfExtractor（🟡 改动，降级为 LayoutPDFExtractor 的回退）
  ├─ get_extractor 工厂（🟡 改动，优先路由到 LayoutPDFExtractor）
  ├─ PgVectorProvider（🟢 保持，索引切块后的向量）
  └─ EmbeddingService（🟢 保持，embed 切块后的文本）
```

改动主要落在 **Infrastructure 层**（新建 `LayoutPDFExtractor` + 改动 `get_extractor` 工厂），新增 **Harness 层**的 `KnowledgeIngestionService`（知识摄入编排），符合四层单向依赖。

---

## 第二层：子模块概述

### 2.1 LayoutPDFExtractor（新建，实现 Extractor 协议）

- **职责**：版面级 PDF 解析，提取结构化元素（标题、段落、表格、公式、图片+caption）。
- **接口契约**：实现 `Extractor` 协议（`extensions: list[str]`, `extract(file_path: str) -> str`）。**额外**提供 `extract_structured(file_path: str) -> list[LayoutElement]`（返回结构化元素列表，供高级切块使用）。
- **数据流**：上游 = `get_extractor` 工厂（按扩展名路由）；下游 = 选定方案的解析库（spike 后确定）。
- **状态管理**：无状态，每次解析独立。
- **错误处理**：解析失败 → 降级到现有 `PdfExtractor`（pdfplumber/PyPDF2）；依赖缺失 → 降级 + 记录日志。
- **关键设计点**：
  - **`extract()` 实现**：调 `extract_structured()` → 按阅读顺序拼接为纯文本（标题前加 `#`/`##`/`###`，表格转为 Markdown 格式，公式保留 LaTeX，图片说明加 `[图片: caption]` 前缀）。
  - **`extract_structured()` 实现**：调选定方案的解析库 → 输出 `list[LayoutElement]`（每个元素含 `type`/`content`/`bbox`/`page_num`）。
  - **惰性 import**：选定方案的依赖（如 `marker`/`pymupdf4llm`）在 `__init__` 或 `extract` 内部 import，缺失时优雅降级（与现有 `PdfExtractor` 对 pdfplumber 的处理一致）。
  - **扩展名**：`extensions = [".pdf"]`（与 `PdfExtractor` 相同，通过 `get_extractor` 工厂的优先级控制路由）。

### 2.2 LayoutElement 数据结构（新建）

- **职责**：版面解析的结构化输出单元。
- **接口契约**：`LayoutElement` dataclass。
- **字段设计**：
  - `type: str`：元素类型（"title_h1"/"title_h2"/"title_h3"/"paragraph"/"table"/"formula"/"figure"/"caption"/"list"/"header"/"footer"/"page_number"）
  - `content: str`：元素内容（标题文本 / 段落文本 / 表格 Markdown / LaTeX 公式 / 图片路径 / caption 文本）
  - `bbox: tuple[float, float, float, float]`：边界框（x0, y0, x1, y1，PDF 坐标系）
  - `page_num: int`：页码（从 1 开始）
  - `confidence: float`：解析置信度（0-1，选定方案提供；若不提供则默认 1.0）
  - `metadata: dict`：额外元信息（如表格的行列数、公式的 LaTeX 源码、图片的分辨率）
- **关键设计点**：
  - **类型枚举**：覆盖教材 PDF 的常见元素（标题层级、段落、表格、公式、图片、列表、页眉/页脚/页码）。
  - **表格内容格式**：统一转为 Markdown 表格（`| 列1 | 列2 |\n|---|---|\n| 值1 | 值2 |`），便于后续切块和 LLM 理解。
  - **公式内容格式**：保留 LaTeX 源码（如 `$E = mc^2$`），若选定方案不支持 LaTeX 则保留图片路径 + `[公式]` 占位符。
  - **图片内容格式**：存储图片的临时文件路径（解析时提取图片到 `/tmp/studyagent_pdf_images/`），供后续多模态处理（可选，B-① 的 `doubao-embedding-vision` 可 embed 图片）。

### 2.3 get_extractor 工厂改动（改动）

- **职责**：按文件扩展名路由到合适的 Extractor。
- **改动点**：`.pdf` 文件优先路由到 `LayoutPDFExtractor`，若其依赖缺失则回退到 `PdfExtractor`。
- **接口契约**：`get_extractor(file_path: str) -> Extractor | None`（签名不变）。
- **状态管理**：无新增状态。
- **错误处理**：`LayoutPDFExtractor` import 失败 → 记录日志 + 回退到 `PdfExtractor`。
- **关键设计点**：
  - **优先级控制**：`get_extractor` 内部维护一个有序列表 `[LayoutPDFExtractor, PdfExtractor, ...]`，按顺序尝试 import，第一个成功的返回。
  - **惰性 import**：`LayoutPDFExtractor` 的 import 在 `get_extractor` 内部（而非文件顶部），避免依赖缺失时整个 `extractors` 模块不可用。
  - **向后兼容**：若用户未安装选定方案的依赖，`.pdf` 文件自动回退到 `PdfExtractor`（行为与改动前一致）。

### 2.4 KnowledgeIngestionService（新建）

- **职责**：知识摄入编排——PDF 解析 → 结构化元素 → 智能切块 → 向量索引 + 图索引（B-① 可选）。
- **接口契约**：`ingest_pdf(file_path: str, user_id: int, scope: str = "global") -> IngestResult`。
- **数据流**：上游 = API `/knowledge/upload`；下游 = `LayoutPDFExtractor`（解析）+ `ChunkingService`（切块）+ `PgVectorProvider`（向量索引）+ `GraphRetrievalProvider`（图索引，B-① 可选）。
- **状态管理**：无状态，每次摄入独立。
- **错误处理**：解析失败 → 返回 `IngestResult(success=False, error="解析失败")`；切块/索引失败 → 部分成功（返回已索引的 chunk 数）。
- **关键设计点**：
  - **切块策略**：按 `LayoutElement.type` 智能切块：
    - `title_h1/h2/h3` → 单独成块（作为"章节标题"chunk，metadata 含 `{"type": "section_header"}`）
    - `paragraph` → 按字数切块（默认 500 字/块，重叠 50 字）
    - `table` → 整个表格成块（metadata 含 `{"type": "table", "rows": N, "cols": M}`）
    - `formula` → 单独成块（metadata 含 `{"type": "formula", "latex": "..."}`）
    - `figure + caption` → 合并成块（metadata 含 `{"type": "figure", "image_path": "...", "caption": "..."}`）
  - **chunk 元信息**：每个 chunk 的 `metadata` 含 `{"file_path": "...", "page_num": N, "element_type": "...", "section_path": "第1章 > 1.2节 > ..."}`（`section_path` 由 `title_h1/h2/h3` 的层级关系拼接）。
  - **IngestResult dataclass**：`success: bool`, `chunk_count: int`, `element_count: int`, `error: str | None`, `warnings: list[str]`（如"第 5 页公式解析失败，已降级为纯文本"）。

### 2.5 ChunkingService（新建）

- **职责**：将 `list[LayoutElement]` 按策略切块为 `list[dict]`（供 `PgVectorProvider.index` 使用）。
- **接口契约**：`chunk_elements(elements: list[LayoutElement], chunk_size: int = 500, chunk_overlap: int = 50) -> list[dict]`。
- **数据流**：上游 = `KnowledgeIngestionService`；下游 = 无（纯函数，返回 `list[dict]`）。
- **状态管理**：无状态，纯函数。
- **错误处理**：`elements` 为空 → 返回空列表；单个 element 切块失败 → 跳过 + 记录 warning。
- **关键设计点**：
  - **切块策略详细逻辑**：
    1. 按 `page_num` 分组（同一页的元素一起处理，保持上下文连贯）。
    2. 对每个 element 按 `type` 分发：
       - `title_h1/h2/h3` → 直接输出为 chunk（`content = f"{'#' * level} {content}"`）
       - `paragraph` → 按 `chunk_size` 切块（重叠 `chunk_overlap`），每块附加所属标题路径（`section_path`）
       - `table` → 整体输出为 chunk（不切块，表格完整性优先）
       - `formula` → 整体输出为 chunk（不切块，公式完整性优先）
       - `figure + caption` → 合并输出为 chunk（`content = f"[图片: {caption}]\n{image_path}"`）
       - `list` → 按条目切块（每个条目一个 chunk，或合并为一个大 chunk，取决于条目数量）
       - `header/footer/page_number` → 丢弃（不索引）
    3. 每个 chunk 的 `metadata` 含 `{"file_path", "page_num", "element_type", "section_path"}`。
  - **section_path 计算**：遍历 elements 时维护当前标题栈（`[h1, h2, h3]`），遇到新标题时更新栈（如遇到 h2 时 pop 掉所有 h3），`section_path = " > ".join(stack)`。

### 2.6 API 端点（新增）

- **职责**：提供用户上传 PDF 文件并触发知识摄入的入口。
- **接口契约**：`POST /api/knowledge/upload`（multipart/form-data，字段：`file`（PDF 文件）, `scope`（"global"/"personal"，默认 "global"））。
- **数据流**：上游 = 用户请求；下游 = `KnowledgeIngestionService.ingest_pdf`。
- **状态管理**：无状态。
- **错误处理**：文件非 PDF → 400；文件过大（>50MB）→ 413；解析/索引失败 → 500 + `IngestResult` 详情。
- **关键设计点**：
  - **文件保存**：上传的 PDF 临时保存到 `/tmp/studyagent_uploads/{user_id}/{uuid}.pdf`，处理完成后删除。
  - **响应格式**：JSON，含 `IngestResult` 的所有字段。
  - **权限控制**：复用现有 JWT 认证（`jwt_secret_key`），仅登录用户可调用。
  - **文件大小限制**：50MB（可配置，`settings.max_upload_size_mb = 50`）。

### 2.7 测试兼容与新测试

- **保住旧契约**：既有 `PdfExtractor` 测试（如有）全绿；`get_extractor` 既有测试（如有）全绿。
- **新测试**：
  - `LayoutPDFExtractor` 单测（mock 选定方案的解析库，返回固定 `LayoutElement` 列表）
  - `ChunkingService` 单测（纯函数，测试各种 element type 的切块策略）
  - `KnowledgeIngestionService` 集成测试（mock `LayoutPDFExtractor` + `PgVectorProvider`，验证端到端流程）
  - API 端点集成测试（`/knowledge/upload`，FastAPI TestClient + mock 依赖）
  - **降级测试**：选定方案依赖缺失时，`.pdf` 文件自动回退到 `PdfExtractor`

---

## 第三层：子模块详细实施计划（文字描述，不含代码）

### 3.1 技术选型 spike（实施前必须完成）

- **spike 步骤**：
  1. 准备 3 份典型教材 PDF 样本：
     - 样本 A：中文教材，含大量表格（如《数据结构》教材）
     - 样本 B：中文教材，含大量公式（如《高等数学》教材）
     - 样本 C：中文教材，含大量图片+caption（如《计算机网络》教材）
  2. 对每个候选方案（ragflow DeepDoc / LightRAG-MinerU / marker / pymupdf4llm / unstructured）执行：
     - `pip install <package>`（记录安装耗时 + 磁盘占用）
     - 解析 3 份样本（记录单页耗时 + 内存占用 + GPU 占用（如有））
     - 人工评估解析质量（按下表打分 1-5）：

| 维度 | 样本 A（表格） | 样本 B（公式） | 样本 C（图片） | 加权总分 |
|------|---------------|---------------|---------------|---------|
| 标题识别准确率 | ?/5 | ?/5 | ?/5 | ? |
| 段落分隔准确率 | ?/5 | ?/5 | ?/5 | ? |
| 表格提取准确率 | ?/5 | N/A | N/A | ? |
| 公式识别准确率 | N/A | ?/5 | N/A | ? |
| 图片+caption 配对准确率 | N/A | N/A | ?/5 | ? |
| 阅读顺序正确性 | ?/5 | ?/5 | ?/5 | ? |
| 输出格式易用性 | ?/5 | ?/5 | ?/5 | ? |
| **加权总分** | ?/35 | ?/35 | ?/35 | **?/105** |

  3. 填写评估对照表：

| 方案 | 加权总分 | 安装耗时 | 磁盘占用 | 单页耗时 | 内存占用 | 选定？ |
|------|---------|---------|---------|---------|---------|-------|
| ragflow DeepDoc | ?/105 | ? | ? | ? | ? | ? |
| LightRAG-MinerU | ?/105 | ? | ? | ? | ? | ? |
| marker | ?/105 | ? | ? | ? | ? | ? |
| pymupdf4llm | ?/105 | ? | ? | ? | ? | ? |
| unstructured | ?/105 | ? | ? | ? | ? | ? |

  4. 根据加权总分 + 依赖重量 + 与现有架构契合度，选定方案。
  5. 更新本 spec 的"选定方案"章节（新增 §3.1.1）。

- **功能完成判据**：5 个候选方案全部 spike 完成，评估对照表填写完毕，选定方案明确。

### 3.1.1 选定方案（spike 后填写）

> ⏳ 待 spike 后填写。内容包括：
> - 选定方案名称 + 版本
> - 选定理由（加权总分 + 关键优势）
> - 未选方案的关键劣势
> - 选定方案的安装命令 + 依赖列表
> - 选定方案的 API 调用示例（Python 代码片段）

### 3.2 LayoutPDFExtractor

- **需要的函数**：
  - `__init__()`：惰性 import 选定方案的解析库（缺失时抛 `ImportError`，由 `get_extractor` 捕获并回退）。
  - `extensions: list[str]`：类属性，`[".pdf"]`。
  - `extract(file_path: str) -> str`：调 `extract_structured()` → 按阅读顺序拼接为纯文本（Markdown 风格）。
  - `extract_structured(file_path: str) -> list[LayoutElement]`：调选定方案的解析库 → 输出 `list[LayoutElement]`。
  - `_convert_to_text(elements: list[LayoutElement]) -> str`：将结构化元素拼接为纯文本。
- **`_convert_to_text` 详细逻辑**：
  - 遍历 elements，按 `type` 拼接：
    - `title_h1` → `f"# {content}\n\n"`
    - `title_h2` → `f"## {content}\n\n"`
    - `title_h3` → `f"### {content}\n\n"`
    - `paragraph` → `f"{content}\n\n"`
    - `table` → `f"{content}\n\n"`（content 已是 Markdown 表格）
    - `formula` → `f"$${content}$$\n\n"`（LaTeX 公式）
    - `figure` → `f"[图片: {metadata.get('caption', '')}]\n\n"`
    - `list` → `f"{content}\n\n"`（content 已是 Markdown 列表）
    - `header/footer/page_number` → 跳过
- **功能完成判据**：给定一份教材 PDF，`extract()` 返回的文本中，标题层级正确（`#`/`##`/`###`），表格保持 Markdown 格式，公式保留 LaTeX。

### 3.3 ChunkingService

- **需要的函数**：
  - `__init__(chunk_size: int = 500, chunk_overlap: int = 50)`：可配切块参数。
  - `chunk_elements(elements: list[LayoutElement], file_path: str) -> list[dict]`：主入口。
  - `_chunk_paragraph(element: LayoutElement, section_path: str) -> list[dict]`：段落切块（按 `chunk_size` + `chunk_overlap`）。
  - `_compute_section_path(elements: list[LayoutElement]) -> list[str]`：计算每个 element 的 `section_path`（标题栈维护）。
- **`_chunk_paragraph` 详细逻辑**：
  - 按 `chunk_size` 字符切块，每块重叠 `chunk_overlap` 字符（在句子边界切分，避免切词）。
  - 每块的 `content = f"[{section_path}]\n{chunk_text}"`（附加标题路径作为上下文）。
  - 每块的 `metadata = {"file_path": file_path, "page_num": element.page_num, "element_type": "paragraph", "section_path": section_path}`。
- **`_compute_section_path` 详细逻辑**：
  - 维护标题栈 `stack = []`（初始为空）。
  - 遍历 elements：
    - 遇到 `title_h1` → `stack = [h1_content]`（清空栈，只保留 h1）
    - 遇到 `title_h2` → `stack = [stack[0], h2_content]`（保留 h1，替换 h2 及以下）
    - 遇到 `title_h3` → `stack = [stack[0], stack[1], h3_content]`（保留 h1/h2，替换 h3）
    - 非标题元素 → `section_path = " > ".join(stack)`
  - 返回每个 element 对应的 `section_path` 列表。
- **功能完成判据**：给定 `elements = [h1("第1章"), h2("1.1节"), paragraph("..."), h2("1.2节"), paragraph("...")]`，第二个 paragraph 的 `section_path = "第1章 > 1.2节"`。

### 3.4 KnowledgeIngestionService

- **需要的函数**：
  - `__init__(extractor: LayoutPDFExtractor, chunker: ChunkingService, vector_provider: PgVectorProvider, graph_provider: GraphRetrievalProvider | None = None)`：注入依赖。`graph_provider` 可选（B-① 未实现时为 None）。
  - `ingest_pdf(file_path: str, user_id: int, scope: str = "global") -> IngestResult`：主入口。
  - `_extract_and_chunk(file_path: str) -> tuple[list[LayoutElement], list[dict]]`：解析 + 切块。
  - `_index_chunks(chunks: list[dict], user_id: int, scope: str) -> int`：索引到 `PgVectorProvider`，返回索引的 chunk 数。
  - `_index_graph(elements: list[LayoutElement], user_id: int, scope: str) -> int`：索引到 `GraphRetrievalProvider`（B-① 可选），返回索引的 element 数。
- **`ingest_pdf` 详细逻辑**：
  1. `elements, chunks = _extract_and_chunk(file_path)`
  2. `chunk_count = _index_chunks(chunks, user_id, scope)`
  3. `graph_count = _index_graph(elements, user_id, scope)`（若 `graph_provider` 不为 None）
  4. 返回 `IngestResult(success=True, chunk_count=chunk_count, element_count=len(elements), error=None, warnings=[])`
- **IngestResult dataclass**：
  - `success: bool`
  - `chunk_count: int`
  - `element_count: int`
  - `graph_element_count: int`（B-① 可选，默认为 0）
  - `error: str | None`
  - `warnings: list[str]`
- **功能完成判据**：给定一份教材 PDF，`ingest_pdf()` 返回 `IngestResult(success=True, chunk_count=50, element_count=100)`，且 `PgVectorProvider.search("教材中的某个概念")` 能召回相关 chunk。

### 3.5 get_extractor 工厂改动

- **改动点**：`get_extractor(file_path)` 内部维护有序列表 `[LayoutPDFExtractor, PdfExtractor, TextExtractor, DocxExtractor]`，按顺序尝试 import。
- **详细逻辑**：
  ```python
  def get_extractor(file_path: str) -> Extractor | None:
      ext = Path(file_path).suffix.lower()
      if ext == ".pdf":
          # 优先尝试 LayoutPDFExtractor
          try:
              from .layout_pdf_extractor import LayoutPDFExtractor
              return LayoutPDFExtractor()
          except ImportError:
              # 依赖缺失，回退到 PdfExtractor
              from .pdf_extractor import PdfExtractor
              return PdfExtractor()
      elif ext in (".txt", ".md", ".csv"):
          from .text_extractor import TextExtractor
          return TextExtractor()
      elif ext == ".docx":
          from .docx_extractor import DocxExtractor
          return DocxExtractor()
      return None
  ```
- **功能完成判据**：`get_extractor("test.pdf")` 在 `LayoutPDFExtractor` 依赖已安装时返回 `LayoutPDFExtractor` 实例；依赖缺失时返回 `PdfExtractor` 实例。

### 3.6 API 端点

- **新增端点**：
  - `POST /api/knowledge/upload`：multipart/form-data，字段 `file`（PDF 文件）+ `scope`（"global"/"personal"）。
- **详细逻辑**：
  1. 校验文件扩展名（必须 `.pdf`）+ 文件大小（≤ 50MB）。
  2. 保存文件到 `/tmp/studyagent_uploads/{user_id}/{uuid}.pdf`。
  3. 调 `KnowledgeIngestionService.ingest_pdf(file_path, user_id, scope)`。
  4. 删除临时文件。
  5. 返回 `IngestResult`（JSON）。
- **Pydantic schema**：
  ```python
  class UploadResponse(BaseModel):
      success: bool
      chunk_count: int
      element_count: int
      graph_element_count: int = 0
      error: str | None = None
      warnings: list[str] = []
  ```
- **功能完成判据**：`curl -X POST -F "file=@textbook.pdf" http://localhost/api/knowledge/upload` → 200 + `UploadResponse(success=True, chunk_count=50)`。

### 3.7 验证目标（Goal-Driven）

```
1. 技术选型 spike 完成，评估对照表填写完毕 → verify: spike 报告文档
2. LayoutPDFExtractor 能解析教材 PDF → verify: 单测 mock 选定方案 + 集成测试真实 PDF
3. ChunkingService 切块策略正确 → verify: 单测（各种 element type 的切块结果）
4. KnowledgeIngestionService 端到端流程通过 → verify: 集成测试（mock 依赖）
5. get_extractor 工厂路由正确 → verify: 单测（LayoutPDFExtractor 依赖存在/缺失两种情况）
6. API 端点 /knowledge/upload 可用 → verify: 集成测试（FastAPI TestClient + mock）
7. 降级测试通过 → verify: 单测（LayoutPDFExtractor 依赖缺失时回退到 PdfExtractor）
8. 既有 PdfExtractor 测试全绿 → verify: pytest < /dev/null
```

---

## 第四层：决策待定项（本阶段不拍板，记录备查）

### 4.1 技术选型的最终决定

- **待定**：ragflow DeepDoc / LightRAG-MinerU / marker / pymupdf4llm / unstructured 中选哪个。
- **决策方式**：spike 评估（见 §3.1），不预设结论。
- **倾向**：`pymupdf4llm`（轻量，适合 MVP）或 `marker`（输出 Markdown，易切块），但最终取决于 spike 结果。

### 4.2 图片的多模态处理

- **待定**：提取的图片是否需要多模态处理（如 `doubao-embedding-vision` embed 图片 → 支持图搜图）。
- **trade-off**：
  - 多模态处理：提升图片检索能力，但增加 API 调用成本 + 存储成本（图片向量）。
  - 仅保留 caption：简单，但图片本身不可检索（只能通过 caption 文本检索）。
- **建议**：MVP 仅保留 caption（图片存临时路径，不索引）。后续根据用户反馈决定是否引入多模态。

### 4.3 公式的 LaTeX 识别质量

- **待定**：选定方案是否能准确识别教材中的公式（转为 LaTeX）。
- **trade-off**：
  - 准确识别 LaTeX：公式可被 LLM 理解 + 可被 LaTeX 渲染，但识别模型可能重量大。
  - 保留公式图片：简单，但公式不可被 LLM 理解（只能作为图片检索）。
- **建议**：spike 时重点评估公式识别质量（样本 B）。若选定方案公式识别差，考虑额外引入 `pix2tex`（轻量 LaTeX OCR 模型）。

### 4.4 切块参数的默认值

- **待定**：`chunk_size=500` + `chunk_overlap=50` 是否合理。
- **trade-off**：
  - chunk 太大：检索精度低（一个 chunk 含多个不相关概念）。
  - chunk 太小：上下文丢失（一个概念被切成多个 chunk）。
- **建议**：MVP 用默认值，后续做 A/B 测试或用户调研调优。

### 4.5 与 B-① 知识内容图谱的联动

- **待定**：`KnowledgeIngestionService` 是否同时索引到 `GraphRetrievalProvider`（B-① 的图索引）。
- **trade-off**：
  - 同时索引：PDF 中的知识点自动进入图索引，支持"串脉络"检索，但依赖 B-① 已完成。
  - 仅向量索引：简单，但无法利用图结构。
- **建议**：MVP 仅向量索引（`graph_provider=None`）。B-① 完成后，`KnowledgeIngestionService` 自动检测 `graph_provider` 并启用图索引。

---

## 资产清单 + 三色（本阶段 B-③）

| 名字 | 归属 | 功能 | 位置 | 三色 |
|---|---|---|---|---|
| LayoutPDFExtractor | Infrastructure | 版面级 PDF 解析 | `app/infrastructure/rag/extractors/layout_pdf_extractor.py`（新） | 🔴 新建 |
| LayoutElement | Infrastructure | 结构化输出单元 | `app/infrastructure/rag/extractors/layout_types.py`（新） | 🔴 新建 |
| ChunkingService | Harness | 智能切块 | `app/harness/chunking_service.py`（新） | 🔴 新建 |
| KnowledgeIngestionService | Harness | 知识摄入编排 | `app/harness/knowledge_ingestion.py`（新） | 🔴 新建 |
| IngestResult | Harness | 摄入结果 | `app/harness/ingest_types.py`（新） | 🔴 新建 |
| /api/knowledge/upload | API | 用户上传 PDF | `app/api/knowledge.py`（新） | 🔴 新建 |
| get_extractor 工厂 | Infrastructure | 路由到 LayoutPDFExtractor | `app/infrastructure/rag/extractors/base.py` | 🟡 改动 |
| PdfExtractor | Infrastructure | 降级回退 | `app/infrastructure/rag/extractors/pdf_extractor.py` | 🟢 保持（降级路径） |
| PgVectorProvider | Infrastructure | 向量索引 | `app/infrastructure/rag/pgvector_provider.py` | 🟢 保持 |
| EmbeddingService | Infrastructure | 文本→向量 | `app/infrastructure/rag/embedding.py` | 🟢 保持 |
| GraphRetrievalProvider | Infrastructure | 图索引（B-① 可选） | `app/infrastructure/rag/graph_provider.py` | 🟢 保持（B-① 完成后） |

---

## 附录：与现有 extractors/ 的设计对照

| 现有 Extractor | 本阶段 LayoutPDFExtractor | 关系 |
|---|---|---|
| `PdfExtractor`（pdfplumber/PyPDF2） | `LayoutPDFExtractor`（版面分析） | `LayoutPDFExtractor` 优先，失败时回退到 `PdfExtractor` |
| `TextExtractor`（.txt/.md/.csv） | 不涉及 | 保持不变 |
| `DocxExtractor`（python-docx） | 不涉及 | 保持不变（DOCX 已有结构化解析能力，无需版面分析） |
| `Extractor` 协议（`extensions` + `extract`） | `LayoutPDFExtractor` 实现此协议 + 额外提供 `extract_structured` | 向后兼容（`extract()` 返回纯文本），高级功能通过 `extract_structured()` 暴露 |
| `get_extractor` 工厂（按扩展名路由） | `get_extractor` 优先路由到 `LayoutPDFExtractor`，失败时回退 | 向后兼容（用户未安装依赖时行为不变） |
