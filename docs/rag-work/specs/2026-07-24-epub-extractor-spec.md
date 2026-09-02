# EPUB 正式接入 Spec（仅 Extractor 范围）

> 创建日期：2026-07-24  
> 状态：⏳ 待用户确认  
> 范围声明：**本 spec 只覆盖 EPUB 进入项目正式 `Extractor` 主链的接入，不覆盖 chunking、ingestion service、上传 API、黄金集接线**；这些由其他窗口负责。  
> 目标：让 `.epub` 与现有 `.txt/.md/.csv/.pdf/.docx` 一样，成为 `get_extractor()` 可识别的正式文件格式。

---

## 0. 资产清单

| 名字 | 归属子系统 | 功能（干嘛） | 触发 / 入口 | 位置（file:line） | 三色 |
|---|---|---|---|---|---|
| `Extractor` | RAG 基础设施 | 文件文本提取抽象协议，唯一抽象方法 `extract(file_path: str) -> str` | 被各格式 extractor 实现 | `app/infrastructure/rag/extractors/base.py:7-15` | 🟡 改动语境依赖 |
| `get_extractor()` | RAG 基础设施 | 按扩展名返回合适的 extractor；当前只注册 TXT/PDF/DOCX 三类 | 由调用方传入文件路径 | `app/infrastructure/rag/extractors/base.py:18-28` | 🟡 改动 |
| `TextExtractor` | RAG 基础设施 | 提取 `.txt/.md/.csv` 纯文本；读取失败返回空串 | 由 `get_extractor()` 选中 | `app/infrastructure/rag/extractors/text_extractor.py:6-14` | 🟢 保持 |
| `PDFExtractor` | RAG 基础设施 | 提取 `.pdf` 文本；优先 `pdfplumber`，回退 `PyPDF2`；失败返回空串 | 由 `get_extractor()` 选中 | `app/infrastructure/rag/extractors/pdf_extractor.py:6-27` | 🟢 保持 |
| `DocxExtractor` | RAG 基础设施 | 提取 `.docx` 文本；依赖 `python-docx`；失败返回空串 | 由 `get_extractor()` 选中 | `app/infrastructure/rag/extractors/docx_extractor.py:6-18` | 🟢 保持 |
| `EpubExtractor` | RAG 基础设施 | **计划新增**：提取 `.epub` 纯文本，遵循现有 `Extractor` 契约 | 由 `get_extractor()` 选中 | `app/infrastructure/rag/extractors/epub_extractor.py`（待建） | 🔴 新建 |
| `test_extractors.py` | 单元测试 | 当前只覆盖 `TextExtractor` 与 `get_extractor()` 对 txt/md/unknown 的行为 | `pytest tests/unit/infrastructure/test_extractors.py` | `tests/unit/infrastructure/test_extractors.py:8-56` | 🟡 改动 |
| benchmark `extract_epub.py` | benchmark | 用标准库解析某一本本地 EPUB，输出 paragraph 级 JSONL；**不是正式主链** | benchmark 脚本命令行 | `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:1-159` | 🟢 只读参考 |
| `README.md` 中 extractors 描述 | 项目文档 | 当前声明 `extractors/` 支持 `PDF/DOCX/TXT`，并说明重依赖惰性 import + 优雅降级 | 用户阅读项目说明 | `README.md:146-148` | 🟡 改动 |
| `docs/asset-inventory.md` | 项目资产索引 | 维护项目事实清单 | 方案/设计产出后同步 | `docs/asset-inventory.md` | 🟡 改动 |

---

## 1. 目标边界

### 1.1 做什么

本阶段只做一件事：**把 EPUB 纳入项目正式 extractor 主链**，使下面的调用具备 `.epub` 识别能力：

```python
extractor = get_extractor("book.epub")
text = extractor.extract("book.epub")
```

满足后，EPUB 与现有 TXT/PDF/DOCX 在“文件 → 纯文本”这一层拥有同等地位。

### 1.2 明确不做

- ❌ 不设计 chunking 规则
- ❌ 不设计 ingestion service / knowledge upload API
- ❌ 不设计黄金集如何走正式 RAG
- ❌ 不设计 EPUB 元数据入库结构
- ❌ 不引入 benchmark 私有 JSONL 输出格式到 `app/`

这些范围被排除，是为了把本窗口工作严格收缩在 **Extractor 层**，避免与其他窗口交叉。

---

## 2. 当前事实与问题定义

### 2.1 已核验事实

1. `Extractor` 的正式契约只有一个：`extract(file_path: str) -> str`，没有 metadata 返回、没有异常类型契约、没有 async 约束。见 `app/infrastructure/rag/extractors/base.py:7-15`。
2. `get_extractor()` 当前只导入 `TextExtractor`、`PDFExtractor`、`DocxExtractor`，并按 `[TextExtractor, PDFExtractor, DocxExtractor]` 顺序匹配 `extensions`。见 `app/infrastructure/rag/extractors/base.py:18-28`。
3. 现有 extractor 的共同降级模式是“出错返回空字符串”：
   - Text：`IOError/UnicodeDecodeError` → `""`，见 `text_extractor.py:9-14`
   - PDF：`ImportError` 或其他异常 → `""`，见 `pdf_extractor.py:9-27`
   - DOCX：`ImportError` 或其他异常 → `""`，见 `docx_extractor.py:9-18`
4. 当前单测只覆盖 `TextExtractor` 和 `get_extractor()` 的 txt/md/unknown 分支，未覆盖 PDF/DOCX，更未覆盖 EPUB。见 `tests/unit/infrastructure/test_extractors.py:8-56`。
5. 仓库内已有 EPUB 解析实现，但位于 benchmark：
   - 用 `ZipFile` 打开 EPUB
   - 用 `META-INF/container.xml` 找 OPF
   - 用 OPF spine 决定阅读顺序
   - 用 `HTMLParser` 提取段落与标题块文本
   见 `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:83-137`。
6. 当前依赖清单中**未查到** `ebooklib`、`beautifulsoup4`、`lxml`、`html5lib` 等 EPUB/HTML 解析库声明；本结论来自对 `pyproject.toml` 与 `uv.lock` 的 grep，结果为空。
7. README 当前把 `extractors/` 描述为 `PDF/DOCX/TXT`，尚未包含 EPUB。见 `README.md:146-148`。

### 2.2 问题的精确定义

当前项目缺的不是“EPUB 全流程摄入”，而是更窄的一环：

> **正式 extractor 主链无法识别 `.epub` 文件。**

因此本 spec 的问题重述为：

> 在不越界到 chunking / ingestion / API / golden set 的前提下，如何把 `.epub` 纳入现有 `Extractor` + `get_extractor()` 体系，并保持与现有 extractor 一致的契约与降级语义？

---

## 3. 选型对照

### 3.1 EPUB 实现路径对照

| | 方案 A：标准库实现（推荐） | 方案 B：新增第三方库 | 方案 C：直接复用 benchmark 脚本 |
|---|---|---|---|
| 做法 | 在 `app/infrastructure/rag/extractors/epub_extractor.py` 内用 `zipfile` + `xml.etree.ElementTree` + `html.parser.HTMLParser` 实现 `Extractor` | 新增如 `ebooklib`/`bs4`/`lxml` 等依赖，再封装为 `EpubExtractor` | 从 `benchmarks/.../extract_epub.py` import 或复制逻辑到生产路径 |
| 与现有契约匹配 | 高：直接返回 `str`，最接近现有 extractor | 中：可实现，但需先 spike 库 API 与依赖行为 | 低：benchmark 产物是 paragraph records/JSONL 导向，不是生产 extractor 契约 |
| 依赖代价 | 低：无新依赖 | 高：当前未声明，需先 spike、补依赖、补锁文件 | 表面低，实则把 benchmark 假设带入生产 |
| 事实确定性 | 高：仓库已有标准库 EPUB 解析参考可验证 | 低：当前未验证任何第三方 EPUB API | 中：实现可读，但包含 `BODY_SECTIONS` 等 benchmark 私有假设 |
| 风险 | 需自己处理 XHTML 文本清洗与顺序 | 库行为/版本/打包成本未验证 | 生产与 benchmark 边界污染 |

**选择理由**：选 **方案 A（标准库实现）**。原因不是“看起来简单”，而是：
1. 仓库里**已经有**标准库 EPUB 解析参考实现，且可验证其核心步骤；
2. 当前没有任何第三方 EPUB 库被声明，若 spec 直接写入某库属于未验证事实；
3. benchmark 脚本的章节白名单 `BODY_SECTIONS` 是该书私有逻辑，不能原样进入正式 extractor。见 `extract_epub.py:18-36`。

### 3.2 是否允许直接导入 benchmark 代码

| | 本方案（不导入 benchmark） | 备选（直接 import benchmark 模块） |
|---|---|---|
| 做法 | 在 `app/` 下重写一个正式 `EpubExtractor`，只借鉴已验证解析步骤 | 让生产代码 import `benchmarks/.../extract_epub.py` |
| 收益 | 保住 `app/` 与 benchmark 边界；去掉 `BODY_SECTIONS` 等样本私货 | 开发快，似乎复用现成逻辑 |
| 代价 | 需要重新整理通用 EPUB 文本抽取逻辑 | 把 benchmark 的书籍假设、JSONL 导向、CLI 入口带进生产 |

**选择理由**：不导入 benchmark。生产 extractor 需要“通用 EPUB → 纯文本”，而 benchmark 脚本做的是“特定图书 EPUB → paragraph records”，目标不同。

---

## 4. 实现规格（仅 Extractor 范围）

## 4.1 新建 `EpubExtractor`

**位置**：`app/infrastructure/rag/extractors/epub_extractor.py`

**职责**：从 `.epub` 文件中提取稳定的阅读顺序纯文本。

**必须满足的契约**：

- 继承 `Extractor`
- `extensions = [".epub"]`
- 提供 `extract(file_path: str) -> str`
- 成功时返回 `str`
- 失败时返回空字符串 `""`
- 不返回 paragraph records / JSON / metadata

**解析步骤**（允许写入 spec，因为已由 benchmark 参考实现验证存在）：

1. 用 `ZipFile(file_path)` 打开 EPUB 容器；
2. 读取 `META-INF/container.xml`，找到 OPF 根文件路径；
3. 解析 OPF，读取 manifest 与 spine，按 spine 顺序获取内容文件；
4. 对每个 spine 内容资源执行**严格 UTF-8 解码**：
   - 必须采用语义等价于 `archive.read(source_file).decode("utf-8")` 的严格解码；
   - **不得**使用 `errors="ignore"`、`errors="replace"` 或其他容错解码；
   - 任一资源抛出 `UnicodeDecodeError` 时，整个 `extract()` 立即返回 `""`；
5. 对成功解码后的 XHTML/HTML 内容文件，提取标题与段落块文本；
6. 过滤纯空白块；
7. 按文档顺序将块文本以 `"\n\n"` 拼接为最终纯文本。

上面 2-4 步的参考来源见：
- OPF 根路径：`benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:83-89`
- spine 解析：`.../extract_epub.py:91-107`
- HTML 块文本抽取：`.../extract_epub.py:40-77`
- 主提取流程：`.../extract_epub.py:110-137`

### 4.2 必须删除的 benchmark 私有假设

正式 `EpubExtractor` **不得**继承以下 benchmark 私有逻辑：

- `DEFAULT_EPUB` / `DEFAULT_OUTPUT` 路径常量，见 `extract_epub.py:16-17`
- `BODY_SECTIONS` 这类按 конкрет 书籍文件名筛章节的白名单，见 `extract_epub.py:18-36`
- `paragraph_id`、`chapter`、`section`、`source_file` 等 benchmark 记录字段，见 `extract_epub.py:124-135`
- `write_jsonl()` 与 CLI `main()`，见 `extract_epub.py:140-159`

正式 extractor 的输入只有文件路径，输出只有纯文本字符串。

### 4.3 HTML 文本抽取边界

正式 `EpubExtractor` 的**最小可交付版本**只承诺：

- 支持提取段落标签与标题标签中的文本；
- 保持 OPF spine 顺序；
- 忽略样式、图片、脚注链接、目录导航等富结构信息；
- 将 `<br>` 视为**受保护的行内换行**；
- 对任一 spine 内容资源的解码或解析失败，采取**整体失败返回空串**，而不是跳过坏页继续产出部分文本。

#### 4.3.1 空白归一化规则（冻结）

为避免实现者误把 benchmark 当前空白折叠逻辑当作正式契约，本 spec 明确冻结以下**确定性算法**；实现可换用等价代码，但输出必须一致：

1. 在 HTML 抽取阶段，将每个 `<br>` 替换为不可能来自普通文本的受保护哨兵 `BR`；
2. 以 `BR` 切分块文本，得到按原始顺序排列的普通文本片段；
3. 对**每一个普通文本片段单独**执行：
   - 将连续的普通空白（空格、制表符、普通换行等）折叠为单个 ASCII 空格；
   - 去除该片段首尾普通空白；
4. 用一个真实 `"\n"` 重新连接相邻片段；每个 `BR` 恰好产生一个 `"\n"`；
5. 不删除、合并或折叠由 `BR` 产生的换行。块级标题/段落之间仍由 §4.1 的 `"\n\n"` 拼接规则决定。

因此必须满足以下精确输出：

| XHTML 输入（同一块） | 归一化输出 |
|---|---|
| `A<br>B` | `A\nB` |
| `A <br> B` | `A\nB` |
| ` A\t<br>\n B ` | `A\nB` |
| `A<br><br>B` | `A\n\nB` |
| `A   B` | `A B` |

> 说明：benchmark 参考实现虽在 `<br>` 时追加 `"\n"`，但其 `_finish_block()` 使用 `re.sub(r"\s+", " ", ...)` 会将换行压成空格，因此 **benchmark 只可作为 container / OPF / spine / block 收集机制参考，不可作为 `<br>` 语义参考**。见 `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:53-54,72`。

#### 4.3.2 内容资源失败语义（冻结）

本 spec 在 extractor-only 范围内明确选择：

- **任一 spine 内容资源不可读取、不可解码或不可解析 → 整个 `extract()` 返回 `""`**。
- 其中“不可解码”进一步冻结为：**必须使用严格 `decode("utf-8")`，任一 `UnicodeDecodeError` 直接导致整体 `""`**。

选择理由：

| | 本方案（整体空串 + 严格 UTF-8） | 备选（跳过坏资源继续输出 / 使用容错解码） |
|---|---|---|
| 契约形状 | 与现有 Text/PDF/Docx 的“失败返回空串”语义更一致 | 会引入“部分成功”或“悄悄吞坏字节”的语义 |
| 测试可判定性 | 高：失败样本统一断言 `""`，无效 UTF-8 可稳定触发 | 低：需额外定义哪些资源可跳过，或无效字节是否被容错吞掉 |
| 代价 | 严格，坏一页会丢全书 | 更宽松，但更难稳定说明与测试 |

**本 spec 不要求**：
- TOC 层级恢复
- 注释/脚注/索引页过滤
- 图片 alt 文本提取
- EPUB 3 media overlay / script 内容支持
- 非 UTF-8 内容的全面兼容策略

这些都超出“先纳入正式 extractor 主链”的最小目标。

### 4.4 `get_extractor()` 改动

**位置**：`app/infrastructure/rag/extractors/base.py`

**改动要求**：

- 在函数内部新增 `from app.infrastructure.rag.extractors.epub_extractor import EpubExtractor`
- 将遍历列表从：
  - `[TextExtractor, PDFExtractor, DocxExtractor]`
- 改为：
  - `[TextExtractor, PDFExtractor, DocxExtractor, EpubExtractor]`

**保持不变的内容**：
- 函数签名不变：`get_extractor(file_path: str) -> Extractor | None`
- 扩展名匹配机制仍使用 `os.path.splitext(file_path)[1].lower()`，见 `base.py:24`
- 未知扩展仍返回 `None`

### 4.5 向后兼容约束

本改动不得破坏以下既有行为：

- `.txt` / `.md` / `.csv` 仍返回 `TextExtractor`
- `.pdf` 仍返回 `PDFExtractor`
- `.docx` 仍返回 `DocxExtractor`
- `.xyz` 等未知扩展仍返回 `None`
- 现有 extractor 的“失败返回空串”语义保持不变

---

## 5. 错误处理与安全边界

### 5.1 错误处理

`EpubExtractor.extract()` 应与现有 extractor 对齐，采用“**不抛到上层，失败返回空串**”的契约。

建议覆盖的失败情形：

- 文件不存在 / 无法读取
- 不是合法 ZIP/EPUB 容器
- `META-INF/container.xml` 缺失
- OPF 缺失或结构错误
- XHTML 内容解码失败
- XML/HTML 解析异常

### 5.2 安全边界

由于 EPUB 本质是 ZIP 容器，正式 extractor 至少要明确以下边界：

- **不解压到磁盘目录**，直接在 `ZipFile` 内读取成员，减少路径穿越面；
- 不执行 EPUB 内任何脚本、样式或外链资源；
- 只读取文本相关内容文件；
- 若后续实现需要限制 ZIP 成员数或总未压缩大小，应在代码注释中留出 hook，但本 spec 不强制第一版就实现硬限制。

> 这里特意不把“必须做 zip bomb 防御”写成已定事实，因为当前项目没有现成文件上传入口，这一层约束更适合在上传/API 窗口统一收口；本窗口只需保证 extractor 不做磁盘解包与脚本执行。

---

## 6. 测试规格

## 6.1 直接单测（必须）

修改 `tests/unit/infrastructure/test_extractors.py`，补齐以下用例：

1. `get_extractor("book.epub")` 返回 `EpubExtractor`
2. `get_extractor("BOOK.EPUB")` 也能匹配（验证 `.lower()` 路径）
3. `EpubExtractor.extract()` 对一个最小合法 EPUB 返回非空文本
4. 非法 EPUB / 损坏 ZIP 返回空字符串
5. 不存在文件返回空字符串
6. 现有 txt/md/unknown 用例继续通过

### 6.2 fixture 策略

当前仓库中**未发现已提交的 `.epub` 测试 fixture**。因此有两个实现路径：

| | 本方案（推荐） | 备选 |
|---|---|---|
| 做法 | 在测试里动态生成最小 EPUB ZIP（含 `container.xml`、OPF、**至少两个 XHTML 页面**） | 提交一个小型 `.epub` fixture 到 `tests/fixtures/` |
| 收益 | 仓库不引入二进制样本，测试更自解释；可精确构造顺序对抗样本 | 书写更直接 |
| 代价 | 需要在测试里组装 ZIP/XML 字符串 | 增加二进制资产管理成本 |

**选择理由**：推荐动态生成最小 EPUB。它更符合当前 extractor 单测风格（`tempfile.NamedTemporaryFile`），参见 `tests/unit/infrastructure/test_extractors.py:14-35`。

**额外冻结的 fixture 要求**：

1. 至少构造两个 spine 内容页面；
2. **ZIP 写入顺序**与**manifest 列出顺序**故意与 **spine 顺序** 不同；
3. happy-path 断言必须证明最终文本按 spine 顺序输出，而不是按 ZIP 成员顺序或 manifest 顺序。

### 6.3 happy-path 与降级路径

**happy-path**：
- 动态生成一个最小合法 EPUB；
- 至少包含两个 XHTML spine 项；
- `container.xml`、OPF、manifest、ZIP 成员写入顺序中，至少两者与最终 spine 顺序不同；
- 真实调用 `EpubExtractor.extract()`；
- 断言：
  - 返回文本包含已写入的标题/段落内容；
  - 两个页面的文本顺序与 OPF spine 顺序一致；
  - `A<br>B` 被提取为 `A\nB`；
  - HTML entities 被解码；
  - 块与块之间以 `"\n\n"` 分隔。

**降级路径**：
- 损坏 ZIP
- 缺 `container.xml`
- 缺 OPF
- spine 引用资源缺失
- spine 资源内容字节不是有效 UTF-8（由严格 `decode("utf-8")` 稳定触发）
- 不存在文件

> 说明：这里特意不用“不可解析 XHTML”作为强制测试名目，因为标准库 `HTMLParser` 对许多畸形 HTML 会容错而非抛异常。若实现阶段要增加更严格的 XHTML 失败测试，应以实际选定解析器可稳定触发的错误形式为准，而不是在 spec 中预设一个可能无法稳定复现的失败标签。

这些测试必须断言返回 `""`，而不是只断言“不抛异常”。

---

## 7. 文档同步要求

若该 spec 被实施，README 至少同步两点：

1. `extractors/` 支持格式从 `PDF/DOCX/TXT` 改为包含 `EPUB`；位置见 `README.md:146`
2. 惰性依赖说明是否变化：
   - 若采用标准库实现，`README.md:148` 无需新增第三方依赖名；
   - 若实施过程中改成第三方库方案，则必须同步该依赖是否属于“惰性、未声明、缺失即降级”还是“正式依赖、必须安装”。

同时，`docs/asset-inventory.md` 应**合并、去重并更新既有** `EpubExtractor` 相关条目为正式实现事实；不得新增第三条同名资产记录。当前该文档已在不同章节出现待建 `EpubExtractor` 记录，实施时应由其维护者裁定保留位置或消除重复，而不是再次“补入”。

---

## 8. 验证状态表

| 代码片段 / 断言 | 验证状态 | 依据 |
|---|---|---|
| `Extractor.extract(file_path: str) -> str` 是当前唯一正式契约 | ✅ 已验证 | `app/infrastructure/rag/extractors/base.py:7-15` |
| `get_extractor()` 当前只注册 Text/PDF/DOCX | ✅ 已验证 | `app/infrastructure/rag/extractors/base.py:18-28` |
| 现有 extractor 失败时返回空串 | ✅ 已验证 | `text_extractor.py:9-14`、`pdf_extractor.py:9-27`、`docx_extractor.py:9-18` |
| benchmark 存在标准库 EPUB 解析步骤可复用为 container / OPF / spine / block 收集参考 | ✅ 已验证 | `benchmarks/.../extract_epub.py:40-137` |
| benchmark 的 `<br>` 当前实现不能直接作为正式换行语义参考 | ✅ 已验证 | `benchmarks/.../extract_epub.py:53-54,72` |
| benchmark 对 spine 资源采用严格 UTF-8 解码，可作为“严格解码可行”的机制参考 | ✅ 已验证 | `benchmarks/.../extract_epub.py:120-122` |
| 正式 `EpubExtractor` 的严格 UTF-8 解码与 `UnicodeDecodeError -> ""` | ✅ 已冻结，待实现验证 | 本 spec §4.1 / §4.3.2 / §6.3 |
| 项目已声明某个第三方 EPUB 库可直接采用 | ❌ 未验证，实际 grep 为空 | `pyproject.toml`、`uv.lock` grep 结果为空 |
| 当前仓库已有 `.epub` 单测 fixture | ❌ 未验证，实际搜索为空 | `tests/` 与 `benchmarks/` 对 `.epub` 搜索为空 |
| `docs/asset-inventory.md` 尚未登记 `EpubExtractor` | ❌ 未验证，实际已有重复待建记录 | `docs/asset-inventory.md` 现有记录（实施时需去重更新） |

---

## 9. 影响传播检查

若实施本 spec，需同步检查：

- [ ] `tests/unit/infrastructure/test_extractors.py` 是否补上 EPUB 用例
- [ ] `README.md` 的格式支持描述是否更新
- [ ] `docs/asset-inventory.md` 是否完成 `EpubExtractor` 相关重复条目的合并/去重与状态更新
- [ ] 是否存在任何假设“未知格式一定返回 None”的上游逻辑需要新增 `.epub` 分支测试
- [ ] 若最终实施偏离标准库方案、转向第三方库，需回写本 spec 的验证状态表与 README 依赖说明
- [ ] `<br>` 归一化规则与“任一 spine 资源失败即整体空串”的测试是否已严格保护

---

## 10. 最小实施清单

只针对本窗口范围，最小变更应收敛为 4 项：

1. 新建 `app/infrastructure/rag/extractors/epub_extractor.py`
2. 修改 `app/infrastructure/rag/extractors/base.py` 注册 `EpubExtractor`
3. 修改 `tests/unit/infrastructure/test_extractors.py` 补 EPUB 单测（含多 spine 顺序对抗、`<br>` 换行与整体失败语义）
4. 修改 `README.md`，同步正式支持 EPUB 的事实与组件边界
5. 修改 `docs/asset-inventory.md`，对既有 `EpubExtractor` 相关记录做合并/去重并更新状态

除此之外的 chunking / ingestion / upload / golden set 改动，**都不属于本 spec 的实施范围**。

---

## 11. 提交前自检

### 事实臆测
- [x] 文件路径、函数签名、README 位置都已验证
- [x] 第三方 EPUB 依赖未被假定为已存在
- [x] benchmark 逻辑与生产逻辑的边界已明确拆开

### 自洽即停
- [x] 已比较“标准库 / 第三方依赖 / 直接复用 benchmark”三条路径
- [x] 已说明为什么只做 extractor，不扩张到 ingestion/chunking

### 局部视角
- [x] 已列出测试、README、asset inventory 的同步项
- [x] 已标出若实施方案切换到第三方库时需要回写 spec/README
- [x] 已将 `<br>` 归一化、spine 内容资源失败语义与顺序对抗测试同步写入实现契约、测试矩阵和影响传播检查
- [x] 已将 asset inventory 要求修正为合并/去重更新既有条目，避免重复登记

