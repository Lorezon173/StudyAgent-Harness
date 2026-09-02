# RAG-A 状态：EPUB 正式摄入能力

> 唯一写者：窗口 A  
> 主清单：[`../designs/2026-07-24-rag-foundation-parallel-todolist.md`](../designs/2026-07-24-rag-foundation-parallel-todolist.md)（**只允许主控修改**）  
> 状态片段目的：向主控提供 RAG-A 的范围、证据、已冻结规格、剩余共享裁决和放行条件；本文件本身不冻结共享契约。  
> 当前状态：✅ **Phase 1A（A-01~A-07）主控验收通过（2026-07-29），BLK-009 已解除；本轮无编码任务，待命 Phase 4（首本书正式摄入）**

---

## 0. 主控最终裁决摘要（先读此节）

### RAG-A 要解决的目的

为项目正式 `app/` extractor 主链补齐 `.epub -> str` 能力，使未来的正式摄入入口能够通过既有工厂选择 `EpubExtractor`。本任务只交付“文件 → 纯文本”组件能力，**不另造 RAG，也不接管 RAG-B 的 chunking、RAG-C 的在线接线或 RAG-D 的黄金集/评测**。

### 主控裁决结果（M-01，已放行）

主控已批准 RAG-A 进入 extractor-only 编码，冻结并放行如下：

1. **Extractor 边界**：`Extractor.extract(file_path: str) -> str`；不返回 section / paragraph / metadata / chunk，也不负责 ingestion（DEC-002）。
2. **EPUB 行为规格采纳为放行依据**：OPF spine 顺序、严格 UTF-8、`<br>` 归一化、任一 spine 资源失败整体空串（spec 独立复审通过）。
3. **asset inventory 唯一事实源已裁定**：保留「EPUB Extractor 正式接入（待实施）」节；ChunkingService 节条目已改为引用行，主控已执行去重（已核实 `docs/asset-inventory.md:103-112` 为唯一事实源，`:136` 为引用行）。
4. **README 同步属于本轮交付范围**：只声明 extractor 支持 EPUB，不宣称上传、chunk、索引或检索完成。

### 主控验收结果（第二轮回执，✅ 通过）

主控已于 2026-07-29 完成 A 线独立验收：

1. **24 测试全通过**（`tests/unit/infrastructure/test_extractors.py`，含 17 个 EPUB 专项 + 7 个原有 text extractor）。
2. 实现审查合格：标准库实现（zipfile/ElementTree/HTMLParser/posixpath/unquote）、OPF spine 顺序、严格 UTF-8、`<br>` 哨兵归一化、任一 spine 资源失败整体空串、损坏 ZIP/缺 container/OPF/spine/无效 UTF-8/malformed XML 均返回空串、无未 spike 依赖。
3. 资产清单去重已执行（唯一事实源为「EPUB Extractor 正式接入」节）。

**Phase 1A（A-01~A-07）正式完成。BLK-009 解除。**

### 配套裁决（DEC-012 §13.4，影响 RAG-A）

- **EPUB 纳入 Gate 0 happy-path**：`EpubExtractor` 已成为正式 Gate 0 摄入链的 EPUB 输入源；RAG-B 的 `ChunkingService` 会预留 `source_format="epub"` 适配。
- 对 RAG-A 的含义：extractor 输出边界维持 `str`（纯文本 + `"\n\n"` 块分隔，无结构化元素），与 DEC-002 冻结一致；如 RAG-B 在 Phase 2 需要元素适配说明，本窗口可配合提供输出格式说明，但不扩张 extractor 契约。

### 交主窗口记录 / 比对的当前快照

- **完成状态**：Phase 1A（A-01~A-07）已完成；主控验收通过；BLK-009（EPUB extractor 尚未实现）已解除。
- **代码事实**：已新建 `app/infrastructure/rag/extractors/epub_extractor.py`；已在 `app/infrastructure/rag/extractors/base.py` 注册 `.epub/.EPUB`；未改 RAG 主链写入/检索组件。
- **验证事实**：`uv run pytest tests/unit/infrastructure/test_extractors.py -v` 为 **24 passed**；`uv run pytest tests/ -q` 为 **511 passed, 1 skipped, 8 deselected**。测试和独立代码审查发现的 `<br>`-only 块、块首尾 `<br>`、rootfile 缺失、spine idref 缺失与畸形 XML 边界均已修复或补测。
- **文档事实**：README 已同步 EPUB 是内置标准库 extractor；资产清单唯一事实源已更新为「EPUB Extractor 正式接入（已实施）」节；ChunkingService 节仅保留引用行。
- **完成口径**：仅“EPUB 提取能力已实现并验证”；不得记录为正式摄入、chunk、索引、检索、在线 grounded answer 或黄金集 baseline 已完成。
- **当前职责 / 下一触发**：RAG-A 本轮无待办编码任务，待命至 Phase 4（F-02）。届时配合真实 EPUB 经 RAG-B 的 `ChunkingService` / `KnowledgeIngestionService` 进入正式主链；若真实样本暴露 extractor 问题，只在 extractor 范围内修复。
- **非阻断备档**：真实 EPUB 兼容性尚未验证；`li/blockquote/pre` 内非 `p` 文本尚不提取；ZIP bomb 防护不在本轮范围，接入不可信上传入口前需单列安全治理。

### 放行后允许的资产范围

| 允许修改 | 原因 |
|---|---|
| `app/infrastructure/rag/extractors/epub_extractor.py`（新建） | 正式 EPUB → 纯文本实现 |
| `app/infrastructure/rag/extractors/base.py` | 在既有工厂注册 `.epub` |
| `tests/unit/infrastructure/test_extractors.py` | 直接验证 extractor 契约、工厂和降级语义 |
| `README.md` | 代码落地后同步已实现格式及边界 |
| `docs/asset-inventory.md` | 按主控裁定合并/去重既有 EpubExtractor 记录 |
| `docs/rag-work/status/RAG-A.md` | 每完成一个 RAG-A todo 回写状态 |

### 放行后明确禁止的扩张

- 不修改主清单 `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`
- 不修改 `RAG-B.md` / `RAG-C.md` / `RAG-D.md`
- 不新增 chunking、ingestion service、上传 API、向量库写入、检索事件、黄金集或 benchmark 私有 extractor
- 不绕过正式主链 `EmbeddingService / PgVectorProvider / RAGCoordinator / RetrieverAgent / RetrieverAgent.evaluate`
- 不从 `benchmarks/` import 生产代码，不引入未 spike 的第三方 EPUB 依赖

---

## 1. 当前结论与完成进展

1. ~~RAG-A 已完成现状核查、extractor-only spec、多轮独立隔离 review 和 review 修订。~~（已完成，见下方）
2. ~~最新独立 review 结论为通过。~~（已完成）
3. ~~现阶段尚未创建 `EpubExtractor`。~~（已完成：Phase 1A 编码 + 主控验收通过，BLK-009 解除）
4. 本窗口不直接修改 RAG 主链组件；EPUB extractor 将为未来经由正式主链的摄入提供 `str` 输入，而不是自建一条 extraction → embedding → database 私有链。**当前状态：Phase 1A 完成，待命 Phase 4。**

### RAG-A todo（Phase 1A，编号对齐主清单；每项完成后必回写本文件）

**前置阶段（已通过独立复审）**

- [x] A1：核查正式 extractor / benchmark EPUB / README / 依赖边界
- [x] A2：产出 EPUB extractor-only spec
- [x] A3：完成独立 review 并收敛初始阻断项
- [x] A4：按 review 修订 spec（含严格 UTF-8 契约）
- [x] A4.1~A4.4：完成 `<br>` 归一化、spine 顺序对抗、整体失败语义冻结与多轮独立复审（通过）

**Phase 1A 编码（主控已放行）**

- [x] A-01 实现 `app/infrastructure/rag/extractors/epub_extractor.py`（已完成；17 测试通过）
- [x] A-02 在 `get_extractor()` 注册 `.epub` / `.EPUB`（已完成）
- [x] A-03 动态 EPUB fixture 单测：spine 顺序、strict UTF-8、`<br>`、HTML entity、块分隔（已完成）
- [x] A-04 降级单测：损坏 ZIP、缺 container/OPF/spine、无效 UTF-8 均返回空串（已完成）
- [x] A-05 确认 asset inventory 去重已由主控执行（核实：`docs/asset-inventory.md:103-112` 唯一事实源，`:136` 引用行）；RAG-A 不再新增条目
- [x] A-06 同步 README：只声明 extractor 支持 EPUB，不宣称上传/chunk/索引/检索（已完成）
- [x] A-07 运行全部测试并回写证据（20 passed；独立代码审查通过，已修复 `<br>`-only 块过滤缺陷并补回归测试）

### Phase 1A 完成证据（A-01~A-07）

**实现文件**
- `app/infrastructure/rag/extractors/epub_extractor.py`：`EpubExtractor(Extractor)`，`extensions=[".epub"]`，`extract(file_path: str) -> str`；标准库 zipfile / xml.etree / html.parser；OPF spine 顺序；严格 `decode("utf-8")`（无 errors 容错，UnicodeDecodeError → 整体空串）；`<br>` 哨兵归一化（精确命中冻结表五例）；任一 spine 资源失败 → 整体 `""`；块间 `"\n\n"` 拼接。
- `app/infrastructure/rag/extractors/base.py:20-28`：`get_extractor()` 函数内导入并注册 `EpubExtractor`，固定类列表 `[TextExtractor, PDFExtractor, DocxExtractor, EpubExtractor]`；签名、`.lower()` 匹配、未知扩展返回 `None` 均未变。
- `tests/unit/infrastructure/test_extractors.py`：新增 17 个 EPUB 用例（24 passed 含原有 7 个非回归）。

**测试命令与结果（可复跑）**
```bash
uv run pytest tests/unit/infrastructure/test_extractors.py -v
# 24 passed in 0.03s
uv run pytest tests/ -q
# 511 passed, 1 skipped, 8 deselected
```
覆盖：工厂路由（`.epub`/`.EPUB` 大小写）、spine 顺序对抗（ZIP/manifest/spine 三序不同）、`<br>` 归一化精确表、块首/块尾 `<br>` 收敛、HTML entity、块分隔、href URL 解码/去 fragment/POSIX 规范化、`<br>`-only 块过滤、降级路径（损坏 ZIP、缺 container/OPF/rootfile、缺 spine 资源、spine idref 缺失、XML 畸形、无效 UTF-8、文件不存在）、非回归（txt/md/unknown/抽象类）。

**独立代码审查结论（skill 化 code-review + 隔离审查，两轮，均已处理）**
- ✅ 契约、严格 UTF-8、`<br>` 冻结表、spine 顺序、href 归一化、异常路径均通过（审查 agent 实际运行验证，含 mutation 实证）；全量非 integration 测试 511 无回归。
- 🔧 已修复 1（真实缺陷）：`<br>`-only 块未被过滤（`if text:` → `if text.strip():`），补 3 回归测试。
- 🔧 已修复 2（真实缺陷）：块首/块尾 `<br>` 泄漏换行（`_finish_block` 追加前 `strip()`），补 `test_epub_br_at_block_edges`。
- 🔧 已补强：三条 spec §5.1 点名的失败路径测试（rootfile 缺失、spine idref 不在 manifest、畸形 XML → 均 `""`）。
- 🔧 已处理：asset-inventory 的「EPUB Extractor 正式接入」节更新为「已实施」，四行状态与引用行同步（`docs/asset-inventory.md`）。
- 📌 非阻断建议（未强制处理）：测试样板可抽 helper（可维护性）；`test_extractors.py:180-181` 显式顺序断言与整串断言冗余（保留作文档价值）；EPUB 解析机制知识可后续按 learning-docs 沉淀到 `Learned/`；`<br>`-only 语义 spec 留白建议主控裁决；`li/blockquote/pre` 内非 p 文本按 spec 最小范围丢弃（已知边界）；zip 炸弹治理保留为后续安全任务。

**禁止项遵守确认**
- 未宣称摄入/索引/检索完成；未直写向量库或调用 `RAGCoordinator.index_documents`；未 import `benchmarks/` 代码；未引入第三方 EPUB 依赖；未修改主清单与 RAG-B/C/D 状态片段。

---

## 2. 已核实事实（主控可逐条复核）

| 事实 | 位置 | 验证方式 | 对裁决的含义 |
|---|---|---|---|
| `Extractor` 唯一抽象契约是 `extract(file_path: str) -> str`；`extensions` 为类属性 | `app/infrastructure/rag/extractors/base.py:7-15` | 已读源码 | EPUB 不应扩张输出为结构化 section/chunk |
| `get_extractor()` 只导入 Text/PDF/Docx，按 `.lower()` 后缀和固定类列表匹配，未知格式返回 `None` | `app/infrastructure/rag/extractors/base.py:18-28` | 已读源码 | `.epub` 只需按既有工厂模式注册，不需要新注册框架 |
| Text 提取失败返回空串 | `app/infrastructure/rag/extractors/text_extractor.py:9-14` | 已读源码 | EPUB 采用空串失败语义有现有模式依据 |
| PDF 提取失败返回空串 | `app/infrastructure/rag/extractors/pdf_extractor.py:9-27` | 已读源码 | 同上；不修改 PDF 的异常策略 |
| DOCX 提取失败返回空串 | `app/infrastructure/rag/extractors/docx_extractor.py:9-18` | 已读源码 | 同上；不修改 DOCX 的异常策略 |
| 现有单测仅覆盖 Text、txt/md/unknown 和抽象类，不含 EPUB | `tests/unit/infrastructure/test_extractors.py:8-56` | 已读源码 | EPUB 测试是新增而非重构现有测试架构 |
| benchmark 有标准库 container → OPF → spine → HTML 文本机制 | `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:40-137` | 已读源码 | 可借鉴机制，但不能导入生产模块 |
| benchmark 具有绝对路径、`BODY_SECTIONS`、JSONL、CLI 和单书记录契约 | `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:16-36,110-159` | 已读源码 | 证明生产不得直接 import benchmark |
| benchmark 的 `<br>` 实现会被后续空白折叠压成空格 | `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:53-54,72` | 已读源码 | 正式 `<br>` 语义必须独立实现，不能照抄 benchmark |
| benchmark 对 spine 内容实际使用严格 `.decode("utf-8")` | `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:120-122` | 已读源码 | 支持 strict UTF-8 作为可行机制参考，但不等于导入 benchmark |
| `pyproject.toml` / `uv.lock` 未声明 EPUB 解析库 | `pyproject.toml`、`uv.lock`（grep 为空） | 依赖 grep | 本轮只能使用标准库，不引入未 spike 依赖 |
| README 当前只声明 `PDF/DOCX/TXT` extractor | `README.md:146-148` | 已读源码 | EPUB 代码落地后 README 同步是必须交付 |
| asset inventory 当前已有两处待建 EpubExtractor 记录 | `docs/asset-inventory.md:75-84,101-109` | 已读源码 | 必须主控裁定唯一事实源，不能再新增 |
| knowledge API 只是 CRUD，不是文件上传入口 | `app/api/knowledge.py:10-28` | 已读源码 | upload/ingestion 不是 RAG-A 当前编码前置依赖 |
| PgVectorProvider 负责索引与搜索，不负责文件提取 | `app/infrastructure/rag/pgvector_provider.py:22-37,60-180` | 已读源码 | RAG-A 不应直写向量库 |
| RetrieverAgent 经 RAGCoordinator 检索和评估，不触及 extractor | `app/agents/retriever.py:31-32,67-101,105-265` | 已读源码 | RAG-A 不应修改 Retriever / evaluate |

---

## 3. 方案与选择理由

| 方案 | 做法 | 收益 | 已核验代价 / 缺口 | 结论 |
|---|---|---|---|---|
| A. 标准库正式实现 | 在正式 `app/.../extractors/epub_extractor.py` 使用 `ZipFile`、`ElementTree`、`HTMLParser` | 无新增依赖；保持当前同步轻量 extractor 形态；项目内有机制参考 | 需自行实现通用文本归一化；不承诺完整 EPUB 标准覆盖 | **拟实施** |
| B. 新增第三方库 | 引入 EbookLib/BeautifulSoup/lxml 等 | 可能减少解析代码 | 当前无声明、无 lock、无 API spike；扩大依赖和验证范围 | **排除** |
| C. 直接导入 benchmark | import `benchmarks/.../extract_epub.py` | 表面复用快 | 单书白名单、绝对路径、JSONL/CLI、错误 `<br>` 语义污染生产 | **拒绝** |

选择 A 的事实依据：项目内已存在标准库机制参考，而第三方库没有已验证项目依赖；直接导入 benchmark 与 `app/` 唯一主体边界冲突。

---

## 4. 已冻结的 RAG-A 实施规格（待主控决定是否采纳为共享放行依据）

详细文本：`docs/rag-work/specs/2026-07-24-epub-extractor-spec.md`。

### 4.1 公共契约

| 项 | 冻结值 |
|---|---|
| 类 | `EpubExtractor(Extractor)` |
| 扩展名 | `[".epub"]` |
| 方法 | `extract(file_path: str) -> str` |
| 成功 | 单个纯文本 `str` |
| 失败 | `""` |
| 工厂 | `get_extractor("book.epub")` 与 `get_extractor("BOOK.EPUB")` 返回新实例 |
| 非目标 | metadata / section / paragraph / chunk / ingest docs / 索引 / 检索 / 上传 |

### 4.2 EPUB 语义

| 行为 | 冻结要求 | spec 依据 |
|---|---|---|
| 阅读顺序 | 按 OPF spine / `itemref` 顺序读取 | EPUB spec §4.1、§6.2、§6.3 |
| 解码 | 每个 spine 资源必须严格 `decode("utf-8")` | EPUB spec §4.1、§4.3.2 |
| 禁止容错 | 禁止 `errors="ignore"` / `errors="replace"` | EPUB spec §4.1、§4.3.2 |
| `<br>` | 哨兵切分 → 各片段折叠普通空白并 trim → 真实 `\n` 回连 | EPUB spec §4.3.1 |
| `<br>` 示例 | `A<br>B -> A\nB`；`A <br> B -> A\nB`；`A<br><br>B -> A\n\nB` | EPUB spec §4.3.1 |
| 任一 spine 资源失败 | 不可读 / `UnicodeDecodeError` / 解析失败 → 整体 `""` | EPUB spec §4.3.2 |
| 输出块分隔 | 非空标题/段落块以 `"\n\n"` 拼接 | EPUB spec §4.1、§6.3 |

### 4.3 独立 review 结论

最终独立 review：**通过**。

该 review 已分别核验并确认：
- strict UTF-8 + `UnicodeDecodeError -> ""`
- 无效 UTF-8 fixture 的稳定性
- 确定性 `<br>` 归一化
- 多 spine 顺序对抗
- 整体空串失败语义
- README 同步边界
- asset inventory 去重表述

证据：会话工作流 `wjwzup2og` 的最终结果；主控仍应自行打开 spec、源码与资产清单复核，而不是只采信该 review 结论。

---

## 5. 拟修改资产与精确影响

| 文件/资产 | 当前职责 | 放行后改动 | 三色 | 影响与边界 |
|---|---|---|---|---|
| `app/infrastructure/rag/extractors/epub_extractor.py` | 不存在 | 新建正式 EPUB → `str` extractor | 🔴 | 只实现 Extractor，不索引/分块 |
| `app/infrastructure/rag/extractors/base.py` | 后缀 → extractor 工厂 | 函数内导入并将 `EpubExtractor` 加入固定类列表 | 🟡 | 不改函数签名或注册模型 |
| `tests/unit/infrastructure/test_extractors.py` | extractor 基础测试 | 动态 EPUB fixture、工厂、顺序、`<br>`、严格 UTF-8、降级、非回归 | 🟡 | 不新增真实版权 EPUB fixture |
| `README.md` | 项目功能说明 | 加 EPUB extractor-only + 标准库边界 | 🟡 | 不宣称上传/索引/检索完成 |
| `docs/asset-inventory.md` | 项目事实索引 | 按主控裁定去重更新既有条目 | 🟡 | 不新增第三条同名事实 |
| `docs/rag-work/status/RAG-A.md` | RAG-A 进展片段 | 每个 todo 完成即同步状态、验证、风险 | 🟡 | 仅 RAG-A 窗口写 |

### 不受影响的内容

- 数据库、`vector_chunks`、向量 embedding：本轮不写入、不改 schema
- `EmbeddingService`、`PgVectorProvider`、`RAGCoordinator`、`RetrieverAgent`、`RetrieverAgent.evaluate`：本轮不修改
- 在线事件、上传 API、chunking、golden set、benchmark corpus：本轮不修改

---

## 6. 测试矩阵（已全部实现并通过，24 passed）

### happy-path

- [x] 动态生成最小合法 EPUB，至少两个 XHTML spine 项（`test_epub_extract_follows_spine_order_and_br_normalization`，实际三页）
- [x] ZIP 写入顺序和 manifest 顺序均故意不同于 spine 顺序（三序互异 + 显式顺序断言）
- [x] 输出严格按 OPF spine，而非 ZIP/manifest 顺序
- [x] `.epub` / `.EPUB` 工厂均返回 `EpubExtractor`（lowercase/uppercase 两例）
- [x] HTML entity 被解码（`Entity &amp; &lt; &gt;` → `Entity & < >`）
- [x] `<br>` 精确覆盖：`A<br>B`、`A <br> B`、`A\t<br>\n B`、`A<br><br>B`（`test_epub_br_normalization_exact` 五例冻结表）
- [x] 非空块以 `"\n\n"` 分隔
- [x] 块首/块尾 `<br>` 收敛（`test_epub_br_at_block_edges`）
- [x] href URL 解码 / 去 fragment / POSIX 规范化（`test_epub_href_url_decoding_and_fragment`）

### 降级路径

- [x] 文件不存在 → `""`
- [x] 损坏 ZIP / 非 ZIP → `""`
- [x] 缺 `META-INF/container.xml` → `""`
- [x] 缺 OPF / rootfile 无效 → `""`（含 `test_epub_container_without_rootfile_returns_empty`、`test_epub_malformed_xml_returns_empty`）
- [x] spine 引用资源缺失 → `""`（含 `test_epub_spine_idref_missing_from_manifest_returns_empty`）
- [x] spine 内容不是有效 UTF-8（严格 decode 稳定触发）→ `""`
- [x] `<br>`-only 块过滤（`test_epub_br_only_block_filtered` / `test_epub_br_only_book_returns_empty`）

### 非回归

- [x] `.txt` / `.md` 保持 `TextExtractor`
- [x] 未知扩展保持 `None`
- [x] `Extractor()` 保持不可实例化

---

## 7. 影响传播与协作边界

- **RAG-B（chunking）**：只可消费未来 extractor 返回的 `str`，不能反向要求 RAG-A 输出 section/chunk/metadata。
- **RAG-C（在线 RAG）**：后续可将正式摄入接至 `RAGCoordinator.index_documents()` 与 provider 主链；本任务不直接接线，也不绕过主链。
- **RAG-D（黄金集/评测）**：可在正式摄入链建立后评估 EPUB 语料；本任务不生成 benchmark 私有 corpus/JSONL，不改 `RetrieverAgent.evaluate()`。
- **主控**：负责冻结共享边界、裁决资产事实源、更新主清单并确定 RAG-A 是否可进入编码。

---

## 8. 当前阻断项 / 非阻断风险

### 8.1 主控裁决前的放行阻断项

| 阻断项 | 详情 | 需要主控的最终决定 |
|---|---|---|
| Extractor 共享边界尚未由主控确认 | RAG-A spec 冻结 `file_path -> str`，但 RAG-B/C 后续可能需要结构化输入；若主控不确认边界，编码可能被后续窗口反向扩张 | 是否正式冻结 Extractor 仅返回 `str` |
| EPUB 语义是否作为共享放行依据 | spec 已通过独立 review，但状态片段不能自行冻结共享契约 | 是否采纳 strict UTF-8 / `<br>` / spine / 整体空串语义 |
| asset inventory 唯一记录未裁定 | 当前已有两处待建记录 | 哪一处保留，另一处删除或改为引用 |
| README 是否是本轮交付范围 | 当前 README 还未写 EPUB | 放行时确认 README 同步为 RAG-A 必须交付 |

### 8.2 已知但不阻断 extractor-only 编码的风险

| 风险 | 当前处理 | 后续归属 |
|---|---|---|
| ZIP bomb / 成员数 / 未压缩大小限制 | 直接 `ZipFile` 读取；本窗口不解压到磁盘，不执行脚本；未承诺大小限制 | 不可信上传入口 / 安全治理任务 |
| EPUB 规范边缘特性（`xml:base`、导航、`linear="no"`、非 UTF-8） | 不承诺全面兼容；严格 UTF-8 是本轮明确选择 | 后续格式兼容性扩展 |
| 真实生产 EPUB 兼容性 | 当前只有动态最小 fixture 规格，未做真实样本兼容实验 | 后续摄入/质量验证 |

---

## 9. 验证状态表

| 声称/API/签名 | 状态 | 依据 |
|---|---|---|
| `Extractor.extract(file_path: str) -> str` 是正式共享契约 | ✅ 已验证 | `app/infrastructure/rag/extractors/base.py:7-15` |
| 工厂使用函数内导入 + 固定类列表 + `.lower()` 后缀匹配 | ✅ 已验证 | `app/infrastructure/rag/extractors/base.py:18-28` |
| 当前 app 尚无 EPUB extractor / 工厂注册 | ✅ 已验证 | `app/infrastructure/rag/extractors/base.py:18-28` |
| 现有 extractor 均是同步 `str` 输出，失败走空串路径 | ✅ 已验证 | Text/PDF/DOCX 文件：见 §2 |
| benchmark 标准库路径可作机制参考 | ✅ 已验证 | `benchmarks/.../extract_epub.py:40-137` |
| benchmark `<br>` 行为可作正式语义参考 | ❌ 已证伪 | `extract_epub.py:53-54,72` |
| benchmark 可被生产 app 直接 import | ❌ 已证伪 | `extract_epub.py:16-36,110-159` |
| 项目已声明可直接采用的第三方 EPUB 库 | ❌ 未验证（grep 为空） | `pyproject.toml`、`uv.lock` |
| EPUB spec 的 strict UTF-8 / `<br>` / spine / 失败 / 去重要求 | ✅ 规格已冻结、独立 review 已通过 | `docs/rag-work/specs/2026-07-24-epub-extractor-spec.md`；工作流 `wjwzup2og` |
| 资产清单尚无 EpubExtractor、可直接新增 | ❌ 已证伪 | `docs/asset-inventory.md:75-84,101-109` |
| README 已反映 EPUB 支持 | ❌ 实施前状态 | `README.md:146-148` |
| EPUB 实现与测试已经验证通过 | ❌ 尚未实施 | 当前源码与测试中无 EPUB 实现/用例 |

---

## 10. 裁决记录（原"请求主控最终裁决"，已全部闭环）

| 原请求项 | 主控裁决结果 | 依据 |
|---|---|---|
| 1. 总裁决（是否允许进入编码） | ✅ 允许（M-01，2026-07-29 放行） | 主清单 §9 RAG-A 回应包 |
| 2. 共享边界：`Extractor: file_path -> str` | ✅ 冻结（DEC-002），禁止 RAG-B/C 反向要求结构化输出 | 主控回应包 M-01 |
| 3. 行为采纳：strict UTF-8 / `<br>` / spine / 整体空串 | ✅ 采纳为放行依据（spec 独立复审通过） | 主控回应包 M-01 |
| 4. 资产唯一事实源 | ✅ 保留「EPUB Extractor 正式接入」节，ChunkingService 节改引用行（主控已执行） | `docs/asset-inventory.md` |
| 5. README 同步为交付必需 | ✅ 确认（已随代码同步落地） | `README.md:151,153` |
| — 验收（第二轮回执） | ✅ 通过；Phase 1A 正式完成，BLK-009 解除；EPUB 纳入 Gate 0 happy-path（DEC-012 §13.4） | `docs/rag-work/dispatch/2026-07-29-dispatch-rag-a-round2.md` |

---

## 11. 待命状态与遗留风险

### 当前状态：待命 Phase 4（首本书正式摄入）

- 本轮（第二轮）无编码任务。Phase 4 届时会调用 `EpubExtractor` 完成 真实 EPUB → 纯文本 → 摄入主链（F-02）。
- 前置依赖：Phase 2 的 B-08~B-11（`ChunkingService` / `KnowledgeIngestionService` / 正式 ID / provenance round-trip）与 C-09~C-11 完成后，Phase 4 才启动（见主清单执行顺序）。

### 可选预备工作（不阻塞，按需响应）

- 如 RAG-B 在 Phase 2 实现 `ChunkingService` 时需要 EPUB 元素适配说明，本窗口可提供 extractor 输出格式说明：**纯文本 `str`，非空块（段落/标题）以 `"\n\n"` 分隔，块内 `<br>` 为单个 `"\n"`，无结构化元素 / metadata / 章节标记**。
- 如发现 EPUB spec 有可改进点，回写本节。

### 遗留风险与改进建议（均非阻断，供主控备档）

1. **spec 留白**：`<br>`-only 块与块首/块尾 `<br>` 的语义未在 spec 冻结表中显式声明；当前实现已按"收敛为纯空白即过滤 / 块级边界换行 strip"处理并有测试锁定（`test_epub_br_only_*`、`test_epub_br_at_block_edges`），建议主控在 spec 修订时补记，消除 §4.1 与 §4.3.1 的内部张力。
2. **内容丢失边界**：`BLOCK_TAGS` 仅含 `p`/`h1`~`h6`，`li`/`blockquote`/`pre`/`div` 内非 p 文本被静默丢弃。这是 spec §4.3 的最小范围选择；真实书籍的列表/引用/代码块内容会丢，Phase 4 摄入真实 EPUB 前建议主控评估是否扩 `BLOCK_TAGS`。
3. **ZIP 安全**：无成员数/未压缩大小限制（zip bomb 防御）。当前无不可信上传入口，风险可接受；接入上传 API 前必须单列安全治理。
4. **真实样本兼容性**：仅动态最小 fixture 验证过，未对真实生产 EPUB 做端到端抽取对比；Phase 4 首本书摄入即是首次真实检验。
5. **工程性小改进**（非阻断，未处理）：测试样板可抽 helper；`test_extractors.py:180-181` 顺序断言与整串断言冗余（保留作文档价值）；EPUB 解析机制知识可按 learning-docs 沉淀到 `Learned/`。
