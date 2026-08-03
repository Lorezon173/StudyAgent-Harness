# RAG-A 状态：EPUB 正式摄入能力

> 唯一写者：窗口 A  
> 主清单：[`../designs/2026-07-24-rag-foundation-parallel-todolist.md`](../designs/2026-07-24-rag-foundation-parallel-todolist.md)（**只允许主控修改**）  
> 状态片段目的：向主控提供 RAG-A 的范围、证据、已冻结规格、剩余共享裁决和放行条件；本文件本身不冻结共享契约。  
> 当前状态：🟡 **Extractor-only spec 已通过独立复审；等待主控完成共享边界与资产唯一事实源裁决后，才能进入编码。**

---

## 0. 主控最终裁决摘要（先读此节）

### RAG-A 要解决的目的

为项目正式 `app/` extractor 主链补齐 `.epub -> str` 能力，使未来的正式摄入入口能够通过既有工厂选择 `EpubExtractor`。本任务只交付“文件 → 纯文本”组件能力，**不另造 RAG，也不接管 RAG-B 的 chunking、RAG-C 的在线接线或 RAG-D 的黄金集/评测**。

### 建议主控裁决

**建议裁决：有条件允许 RAG-A 进入编码。**

条件不是新的代码技术缺件，而是主控须先在主清单中明确以下共享决策：

1. **接受 Extractor 边界**：`Extractor.extract(file_path: str) -> str`；不返回 section / paragraph / metadata / chunk，也不负责 ingestion。
2. **接受 EPUB extractor 行为**：严格 UTF-8、`<br>` 归一化、OPF spine 顺序、任一 spine 资源失败即整体空串；这些行为已在 spec 冻结并通过独立 review。
3. **裁定 asset inventory 的唯一事实源**：当前存在两条待建 `EpubExtractor` 记录，需由主控决定保留/重写哪一条；实施窗口不得自行制造第三条。
4. **确认本轮交付包含 README 同步**：代码落地后 README 需记录 EPUB 是 extractor-only、标准库实现，不得宣称上传、分块、索引或检索已接通。

### 放行后允许的资产范围

| 允许修改 | 原因 |
|---|---|
| `app/infrastructure/rag/extractors/epub_extractor.py`（新建） | 正式 EPUB → 纯文本实现 |
| `app/infrastructure/rag/extractors/base.py` | 在既有工厂注册 `.epub` |
| `tests/unit/infrastructure/test_extractors.py` | 直接验证 extractor 契约、工厂和降级语义 |
| `README.md` | 代码落地后同步已实现格式及边界 |
| `docs/asset-inventory.md` | 按主控裁定合并/去重既有 EpubExtractor 记录 |
| `docs/rag-foundation-status/RAG-A.md` | 每完成一个 RAG-A todo 回写状态 |

### 放行后明确禁止的扩张

- 不修改主清单 `docs/designs/2026-07-24-rag-foundation-parallel-todolist.md`
- 不修改 `RAG-B.md` / `RAG-C.md` / `RAG-D.md`
- 不新增 chunking、ingestion service、上传 API、向量库写入、检索事件、黄金集或 benchmark 私有 extractor
- 不绕过正式主链 `EmbeddingService / PgVectorProvider / RAGCoordinator / RetrieverAgent / RetrieverAgent.evaluate`
- 不从 `benchmarks/` import 生产代码，不引入未 spike 的第三方 EPUB 依赖

---

## 1. 当前结论与完成进展

1. RAG-A 已完成现状核查、extractor-only spec、多轮独立隔离 review 和 review 修订。
2. 最新独立 review 结论为 **通过**：严格 UTF-8、无效 UTF-8 fixture、`<br>` 归一化、spine 顺序对抗、整体失败语义、README 范围与 asset inventory 去重要求均已有可验证规格；未发现 extractor-only 范围内仍成立的规格缺口。
3. 现阶段尚未创建 `EpubExtractor`、未注册 `.epub`、未新增测试，也未更新 README 或 asset inventory；因此“通过”只表示**可实施规格通过**，不表示功能已落地。
4. 本窗口不直接修改 RAG 主链组件；EPUB extractor 将为未来经由正式主链的摄入提供 `str` 输入，而不是自建一条 extraction → embedding → database 私有链。

### RAG-A todo（每项完成后必回写本文件）

- [x] A1：核查正式 extractor / benchmark EPUB / README / 依赖边界
- [x] A2：产出 EPUB extractor-only spec
- [x] A3：完成独立 review 并收敛初始阻断项
- [x] A4：按 review 修订 spec
- [x] A4.1：补齐 `<br>` 与相邻普通空白的确定性归一化算法与边界测试
- [x] A4.2：完成第三轮独立复审并定位严格 UTF-8 契约缺口
- [x] A4.3：在 spec 中冻结 spine 内容资源必须严格 `decode("utf-8")`
- [x] A4.4：完成严格 UTF-8 修订后的独立复审（通过）
- [ ] A5：收到主控关于 asset inventory 唯一事实源的裁定后，合并/去重既有记录
- [ ] A6：收到主控对共享 Extractor 边界和 RAG-A 编码顺序的最终裁决
- [ ] A7：裁决放行后实施 `EpubExtractor + get_extractor() + 单测 + README`
- [ ] A8：运行验证、独立代码 review，并回写实现结果、证据与剩余风险

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

详细文本：`docs/designs/2026-07-24-epub-extractor-spec.md`。

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
| `docs/rag-foundation-status/RAG-A.md` | RAG-A 进展片段 | 每个 todo 完成即同步状态、验证、风险 | 🟡 | 仅 RAG-A 窗口写 |

### 不受影响的内容

- 数据库、`vector_chunks`、向量 embedding：本轮不写入、不改 schema
- `EmbeddingService`、`PgVectorProvider`、`RAGCoordinator`、`RetrieverAgent`、`RetrieverAgent.evaluate`：本轮不修改
- 在线事件、上传 API、chunking、golden set、benchmark corpus：本轮不修改

---

## 6. 测试矩阵（规格已写清，尚未实现）

### happy-path

- [ ] 动态生成最小合法 EPUB，至少两个 XHTML spine 项
- [ ] ZIP 写入顺序和 manifest 顺序均故意不同于 spine 顺序
- [ ] 输出严格按 OPF spine，而非 ZIP/manifest 顺序
- [ ] `.epub` / `.EPUB` 工厂均返回 `EpubExtractor`
- [ ] HTML entity 被解码
- [ ] `<br>` 精确覆盖：`A<br>B`、`A <br> B`、`A\t<br>\n B`、`A<br><br>B`
- [ ] 非空块以 `"\n\n"` 分隔

### 降级路径

- [ ] 文件不存在 → `""`
- [ ] 损坏 ZIP / 非 ZIP → `""`
- [ ] 缺 `META-INF/container.xml` → `""`
- [ ] 缺 OPF / rootfile 无效 → `""`
- [ ] spine 引用资源缺失 → `""`
- [ ] spine 内容不是有效 UTF-8（严格 decode 稳定触发）→ `""`

### 非回归

- [ ] `.txt` / `.md` 保持 `TextExtractor`
- [ ] 未知扩展保持 `None`
- [ ] `Extractor()` 保持不可实例化

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
| EPUB spec 的 strict UTF-8 / `<br>` / spine / 失败 / 去重要求 | ✅ 规格已冻结、独立 review 已通过 | `docs/designs/2026-07-24-epub-extractor-spec.md`；工作流 `wjwzup2og` |
| 资产清单尚无 EpubExtractor、可直接新增 | ❌ 已证伪 | `docs/asset-inventory.md:75-84,101-109` |
| README 已反映 EPUB 支持 | ❌ 实施前状态 | `README.md:146-148` |
| EPUB 实现与测试已经验证通过 | ❌ 尚未实施 | 当前源码与测试中无 EPUB 实现/用例 |

---

## 10. 请求主控最终裁决

请主控阅读本状态片段、EPUB spec 与实际源码后，按以下格式作出裁决：

1. **总裁决**：允许进入编码 / 暂缓编码 / 退回修订
2. **共享边界**：是否冻结 `Extractor: file_path -> str`，并禁止 RAG-B/C 反向要求结构化 extractor 输出
3. **行为采纳**：是否采纳 spec 中 strict UTF-8、`<br>`、spine 顺序、整体空串的实现要求
4. **资产唯一事实源**：`docs/asset-inventory.md` 中 EpubExtractor 的唯一保留位置及另一处的处理方式
5. **交付范围**：是否确认 README 同步是本轮编码完成的必需条件
6. **若不放行**：请只列出已验证、带 `file:line` 的阻断项

---

## 11. 未做事项

1. 未收到主控对第 10 节的最终裁决。
2. 未清理/合并 `docs/asset-inventory.md` 中重复的 `EpubExtractor` 记录；等待主控指定唯一事实源。
3. 未开始编码，未创建 `EpubExtractor`。
4. 未运行任何 EPUB 单测、集成测试或真实样本验证。
5. 未更新 README；其更新必须与代码落地在同一交付中完成。
